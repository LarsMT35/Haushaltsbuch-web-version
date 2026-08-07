# Haushaltsbuch – Web-Version

Selbst gehostete Web-App als Ersatz für das Excel-Haushaltsbuch: echte Konten,
Mehrbenutzerfähigkeit, flexibler Bank-Import, durchgehende Historie ohne
Jahresschnitt. Grundlage ist das [Anforderungsdokument](docs/Anforderungen.md).

> Vor Arbeiten an Deployment/Betrieb: **[docs/kontext.json](docs/kontext.json)**
> lesen – Wissen, das sich nicht aus Repo/Code ableiten lässt (Proxmox-CT,
> Demo-Reset-Pflicht, offene Punkte, Hintergrund zu einzelnen Designentscheidungen).

## Stack

| Schicht | Technik |
|---|---|
| Backend | Python 3.12, FastAPI, SQLAlchemy 2, Alembic-Migrationen |
| Datenbank | PostgreSQL 16 (Entwicklung: SQLite) |
| Frontend | Vue 3 + Vite, Chart.js |
| Betrieb | Docker Compose (Proxmox LXC/VM), Backup-Skripte fürs NAS |

Die API ist versioniert (`/api/v1`), Fachlogik liegt ausschließlich im Backend,
Konfiguration (Kategorien, Regeln, Bankprofile) liegt als Daten in der DB –
siehe Leitprinzipien in Kapitel 3 des Anforderungsdokuments.

## Installation

**Proxmox-Einzeiler** (im Stil der Community-Skripte, erstellt einen LXC mit
Docker und richtet alles ein – inkl. Zufalls-Passwörtern):

```bash
bash -c "$(wget -qLO - https://raw.githubusercontent.com/LarsMT35/Haushaltsbuch-web-version/main/proxmox/haushaltsbuch-lxc.sh)"
```

**Oder manuell** auf einem Host mit Docker:

```bash
cp .env.example .env        # Passwörter & SECRET_KEY setzen!
docker compose up -d --build
```

→ Ausführliche Anleitung (Erste Schritte, Updates, Backup aufs NAS, HTTPS,
Fehlerbehebung): **[docs/INSTALL.md](docs/INSTALL.md)**

App: `http://<host>:8080` – Erstanmeldung mit `ADMIN_USERNAME`/`ADMIN_PASSWORD`
aus der `.env` (danach Passwort ändern). Weitere Nutzer legt der Admin unter
*Einstellungen* an – Selbstregistrierung gibt es bewusst nicht.

**Update**: `scripts/update.sh` (zieht vorher automatisch einen DB-Dump).
**Backup** (Kapitel 5): `scripts/backup.sh /mnt/nas/haushaltsbuch` per Cron,
Rücksicherung mit `scripts/restore.sh <dump.sql.gz>` mindestens einmal testen.

### Demo-Instanz zum Zeigen/Testen

Läuft parallel zu einer produktiven Installation, komplett eigene Datenbank,
kein Risiko für echte Daten. Wird beim ersten Start automatisch mit
Testkonten, ~150 Buchungen und Beispiel-Regeln/-Budgets befüllt – siehe
[`demo/README.md`](demo/README.md) für Details:

```bash
scripts/demo-up.sh      # startet auf Port 8181, Login test/test
scripts/demo-down.sh    # stoppen (Demodaten bleiben)
scripts/demo-down.sh --reset   # stoppen + Demodaten löschen (beim nächsten Start neu befüllt)
```

Für den Live-Import-Ablauf liegt eine passende Beispiel-CSV bereit:
[`demo/beispiel_import_sparkasse.csv`](demo/beispiel_import_sparkasse.csv).

## Entwicklung

```bash
# Backend (Port 8000) – nutzt SQLite-Datei, seedet Admin + Profile + Kategorien
cd backend
python -m venv .venv && .venv/bin/pip install -r requirements.txt pytest httpx
.venv/bin/uvicorn app.main:app --reload

# Frontend (Port 5173, proxied /api → 8000)
cd frontend
npm install
npm run dev

# Tests (Import-Parser-Regressionstests + API-Flow, Prinzip 9)
cd backend && .venv/bin/python -m pytest tests/
```

Schema-Änderungen laufen als Alembic-Migration (`alembic revision
--autogenerate`), nie händisch. Der Docker-Start führt `alembic upgrade head`
automatisch aus.

## Funktionsumfang (Stufenplan Kapitel 7)

### v1.0 – Kern

- ✅ Login & Rollen (Eigentümer/Bearbeiter/Leser je Konto, Admin-Benutzerverwaltung)
- ✅ Konten inkl. Anfangssaldo, Archivieren statt Löschen
- ✅ CSV-Import: Profile für **Sparkasse** und **ING** vorkonfiguriert,
  Mapping-Assistent für unbekannte Formate, Zielkonto-Erkennung per IBAN,
  Vorschau, Duplikatserkennung (inkl. „echte Doppelung“-Verdachtsfälle),
  Rohzeilen-Aufbewahrung, kompletter Rollback je Import-Vorgang
- ✅ Kategorien mit drei Geltungsbereichen (global/kontobezogen/persönlich),
  Ober-/Unterkategorien, Umbenennen & Zusammenführen ohne Datenverlust
- ✅ Regeln (Zweck, Gegenpartei, IBAN, Buchungstext, Betragsbereich, Konto) mit
  Priorität, „künftig immer so“-Regel aus manueller Zuordnung, rückwirkende
  Neuanwendung
- ✅ Umbuchungserkennung (auto bei IBAN-Beleg, sonst Vorschlag zur Bestätigung),
  manuelles Verknüpfen/Auflösen, jederzeit per Button „Umbuchungen erkennen“
  in der Buchungsliste erneut anstoßbar
- ✅ Manuelle Buchungen / Bargeld-Konto
- ✅ Dashboard: Kennzahlen, Monatsbilanz, Monatsausgaben, Kategorie-Donut,
  fix/variabel, Sparkonten-Bewegung, Top-Ausgaben, Warnkachel für nicht
  zugeordnete Buchungen, mobiltauglich; Filter für mehrere Konten UND
  mehrere Kategorien gleichzeitig kombinierbar, freier Zeitraum (defaultet
  auf den letzten abgeschlossenen Kalendermonat)
- ✅ Suche & CSV-Export, Änderungsprotokoll (AuditLog), Backup-Skripte

### v1.1 – Komfort

- ✅ **Splitbuchungen**: eine Buchung auf mehrere Kategorien aufteilen
  (Summenprüfung, anteilige Auswertung in Dashboard und Budgets)
- ✅ **Tags** als zweite Dimension (frei vergebbar, Filter in der Buchungsliste)
- ✅ **Budgets mit Ampel**: monatlich je Kategorie, ab Gültigkeitsdatum
  versioniert, Schwellwerte konfigurierbar, Ampelfarben schema-unabhängig
- ✅ **Kachel-Dashboard**: Kacheln per Drag & Drop anordnen, aus-/einblenden und
  am Griff unten rechts **frei in der Größe ziehen** (Breite rastet auf die
  Rasterspalten, Höhe stufenlos; Doppelklick setzt zurück). Diagramme folgen
  der Kachelgröße; wird sie kleiner als der Inhalt, wächst die Kachel mit,
  statt Legende oder Text abzuschneiden. Layout wird pro Nutzer und Bereich
  gespeichert.
- ✅ **Erweiterte Dashboards**: Vermögensverlauf pro Konto, Sparquote im
  Zeitverlauf (**tatsächlicher Netto-Zufluss auf die Sparkonten** inkl. aller
  Umbuchungen in beide Richtungen – 200 € aufs Tagesgeld und 50 € zurück
  ergeben 150 € gespart; zum Vergleich das rechnerische Sparpotenzial),
  Jahresvergleich pro Kategorie
- ✅ Design-Einstellungen (seit v1.0): **6 Farbschemata** (Hell, Ruhig/Waldgrün,
  Warm/Terrakotta, Ozean/Tiefblau, Beere/Aubergine, Kontrastreich für
  Barrierefreiheit) je mit eigenem Dark Mode, jedes Schema setzt die
  vollständige Palette statt nur den Akzent – Budget-Ampel und Warnfarben
  bleiben bewusst schema-unabhängig konstant
- ✅ Rückwirkende Regelanwendung (seit v1.0)

### v1.2 – Haushalts-Logik

- ✅ **Wiederkehrende Kostenpositionen** (4.7 b): Name, Zyklus, erwarteter
  Betrag, Erkennungstext für die Abbuchung; der Zahler ergibt sich automatisch
  aus dem Konto der erkannten Buchung. Automatische Erkennung per „Erkennung
  ausführen“, Verknüpfung jederzeit auch manuell setz- und lösbar.
- ✅ **Vorfinanzierungs-Abgleich**: für Positionen mit hinterlegtem
  Vorfinanzierungskonto vergleicht die App **Soll** (aufsummierte Erstattungen
  seit der letzten Abbuchung) gegen **Ist** (tatsächliche neue Abbuchung),
  zeigt die Abweichung mit Ampel und schlägt eine neue Monatsrate vor
  (letzte Abbuchung ÷ Zyklusmonate) – mit einem Klick übernehmbar.
- ✅ **Ampel-Übersicht** aller wiederkehrenden Positionen (Soll/Ist, nächste
  Fälligkeit) als eigene Seite und als Dashboard-Kachel
- ✅ **Saldo-Abgleich gegen Bank**: wo eine Bank einen laufenden Saldo je
  Buchung mitliefert (ING; Sparkasse liefert keinen), vergleicht die App den
  berechneten mit dem gemeldeten Kontostand und zeigt Abweichungen – erkennt
  fehlende Importe oder Lücken (*Einstellungen → Saldo-Abgleich*)
- ✅ **Einzahlungstransparenz gemeinsames Konto**: Einzahlungen je Monat nach
  Einzahler gruppiert (aus dem Gegenpartei-Feld des Bank-Exports), als
  gestapeltes Balkendiagramm im Dashboard

### v1.3 – Kategorien als Umbuchung

- ✅ **Kategorie „wie Umbuchung behandeln“**: Buchungen zählen nicht als
  Einnahme/Ausgabe, sondern wie eine Sparkonten-Bewegung (4.9) – für Fälle,
  in denen eine „echte“ Umbuchung (4.4) mangels Gegenbuchung nicht
  verknüpfbar ist, z.B. Sparplan-Ausführungen.
- ✅ **Optionales Umbuchungs-Zielkonto je Kategorie** (z.B. ein manuell
  angelegtes Depot ohne eigenen Bank-Feed): „Umbuchungen erkennen“ legt für
  noch unverknüpfte Buchungen dieser Kategorie automatisch die Gegenbuchung
  im Zielkonto an und verknüpft beide als echte Umbuchung – der Saldo des
  Zielkontos wächst dadurch tatsächlich mit, nicht nur die
  Dashboard-Auswertung der zahlenden Seite.
- ✅ Dashboard-Filter: mehrere Konten UND mehrere Kategorien gleichzeitig
  kombinierbar, Zeitraum defaultet auf den letzten abgeschlossenen Monat

### v1.4 – Getrenntes Dashboard & aufgeräumte Auswertungen

- ✅ **Bereiche „Gemeinsam / Persönlich / Gesamt“**: Haushalts- und Privatgeld
  beantworten unterschiedliche Fragen – eine gemeinsame Ausgabensumme aus
  Miete und privatem Kaffee sagt nichts. Konten tragen dafür ein explizites
  Flag **Haushaltskonto** (nicht aus der Zahl der Zugriffsberechtigten
  abgeleitet). Jeder Bereich hat sein **eigenes Kachel-Layout**; wer nur
  Zugriff auf Haushaltskonten hat (z.B. der Partner als Leser), sieht gar
  keinen Umschalter, sondern direkt nur diesen Bereich.
- ✅ **Zeitraum von den Verlaufs-Kacheln entkoppelt**: Kennzahlen und
  Kategorien folgen dem gewählten Zeitraum, Verläufe zeigen immer die
  letzten 12 Monate – vorher wurde aus jedem Liniendiagramm ein einzelner
  Punkt, sobald man auf einen Monat filterte.
- ✅ **Kennzahlen in einer Kachel** statt vier einzelner, jeweils mit
  **Veränderung gegenüber dem Vergleichszeitraum davor** (bei ganzen
  Monaten/Jahren kalendarisch, sonst gleich langer Zeitraum)
- ✅ **Einnahmen/Ausgaben/Bilanz in einem Diagramm** statt zweier fast
  gleicher Balkendiagramme; **Kategorien als waagerechte Balken** statt
  Donut (Längen vergleicht das Auge zuverlässiger als Kreissegmente);
  Fixkosten-Anteil in Prozent direkt an der Kachel
- ✅ Kontenliste mit **Summenzeile**, nach Haushalt/privat gruppiert

### v1.5 – Regelsuche, mehr Auswertungen, optionale lokale KI

- ✅ **Freitextsuche über die Regeln**: durchsucht Name, alle Textkriterien
  *und* die Zielkategorie – „Lebensmittel“ findet so auch die Regeln „Aldi“
  und „Rewe“, ohne den Händlernamen zu kennen
- ✅ **Sechs zusätzliche Dashboard-Kacheln**, frei zuschaltbar und je Bereich
  getrennt anordenbar:
  | Kachel | beantwortet |
  |---|---|
  | Monatsverlauf kumuliert | „Bin ich schneller unterwegs als im Vormonat?“ – tagesgenau, *während* der Monat läuft |
  | Budget-Fortschritt | Soll/Ist je Kategorie mit Ampel, direkt auf der Startseite |
  | Fixkosten-Sockel | „Wie viel vom Einkommen ist überhaupt frei verfügbar?“ |
  | Fällig in 30 Tagen | anstehende Abbuchungen inkl. Summe (Liquiditätsblick nach vorn) |
  | Kategorie-Trend | was ist über die Monate teurer geworden (Jahresvergleich ist dafür zu grob) |
  | Top-Empfänger | wohin das Geld jenseits der Kategorie fließt |
- ✅ **Optionale Anbindung einer lokalen Ollama-Instanz** (`OLLAMA_URL`,
  Standard: aus). Schlägt Kategorien für Buchungen vor, bei denen keine Regel
  greift. Bewusst eng gefasst: nur die eigene Instanz im eigenen Netz,
  übertragen werden nur Gegenpartei/Zweck/Betrag (keine IBANs, keine Salden),
  erfundene Kategorien werden verworfen, und **zugeordnet wird erst nach
  Bestätigung** – wie bei den Umbuchungs-Vorschlägen. Ohne Konfiguration
  erscheint die Funktion gar nicht erst; die App bleibt vollständig ohne KI
  nutzbar (Prinzip 6: die Fachlogik bleibt regelbasiert im Backend).

### v1.6 – Abrechnungsmonat & kontogebundene Budgets

- ✅ **Abrechnungsmonat („Finanzmonat")**: Wer sein Gehalt am 27. bekommt, lebt
  davon bis zum nächsten 27. – der Kalendermonat ist dafür das falsche Raster,
  bis zum Gehaltseingang sähe jeder laufende Monat tiefrot aus. Mit Starttag
  27 läuft der Zeitraum vom 27. bis zum 26. und heißt nach dem Monat, in dem
  er **endet**. Eine Einstellung, die **alle** Auswertungen gemeinsam trägt
  (Bilanz, Ausgaben, Sparquote, Sparkonten, Kategorie-Trend, kumulierter
  Verlauf, Jahresvergleich, Budgets, Quicklinks). **Starttag 1 = Kalendermonat**
  ist die Voreinstellung, bestehende Installationen ändern sich nicht.
- ✅ **Einzelzuordnung je Buchung**: Kommt das Gehalt wegen eines Wochenendes
  zwei Tage früher, lässt sich die Buchung in der Detailzeile einem anderen
  Abrechnungsmonat zuordnen – vorbelegt mit dem errechneten Monat, Abweichungen
  sind in der Liste gekennzeichnet. **Buchungsdatum, Betrag, Kontostand und der
  Saldo-Abgleich gegen die Bank bleiben unberührt**; gespeichert wird nur die
  Abweichung, damit sich beim Ändern des Starttags alles Übrige neu einordnet.
- ✅ **Budgets sind an ihr Konto gebunden**: Ein Budget aufs Girokonto erscheint
  nur im Bereich *Persönlich* und verbraucht sich ausschließlich an dessen
  Buchungen, eines aufs gemeinsame Konto entsprechend nur in *Gemeinsam*.
  Zuvor tauchten Budgets in jedem Bereich auf und zwei Budgets derselben
  Kategorie verdrängten sich gegenseitig – mit sichtbar falschen Zahlen.

### v1.7 – Klickbare Diagramme, schnellere Auswertungen, CI

- ✅ **Vom Diagramm in die Buchungsliste**: Ein Klick auf einen Balken, ein
  Kreissegment oder einen Punkt öffnet genau die Buchungen dahinter –
  *Ausgaben nach Kategorie* (Kategorie), *Einnahmen/Ausgaben im Verlauf* und
  *Bewegung der Sparkonten* (Abrechnungsmonat), *Kategorie-Trend* (beides),
  *Einzahlungen pro Person* (Einzahler + Monat). Der angezeigte Bereich
  (*Gemeinsam/Persönlich* samt Kontenfilter) wandert mit und ist in der Liste
  als abwählbarer Hinweis sichtbar – sonst zeigte die Liste mehr Buchungen an,
  als die angeklickte Zahl umfasst. Die Monatsgrenzen rechnet weiterhin das
  Backend aus, damit die Abrechnungsmonat-Regel nicht ein zweites Mal in
  JavaScript existiert.
- ✅ **Dashboard lädt mit deutlich weniger Datenbankabfragen**: Die Salden
  wurden je Konto einzeln in Python summiert und die Splitbuchungen je Buchung
  einzeln nachgeladen. Beides erledigt jetzt die Datenbank in einem Rutsch
  (`SUM ... GROUP BY` bzw. `selectinload`). Ein vollständiger Dashboard-Aufbau
  über alle Auswertungen brauchte auf den Demodaten **577 SELECTs, jetzt 39** –
  und der alte Wert wuchs mit jeder weiteren Buchung, der neue nicht.
- ✅ **Einzahlungen über mehrere gemeinsame Konten**: `/dashboard/deposits`
  nimmt wie alle übrigen Dashboard-Endpunkte mehrere Konten entgegen
  („Alle gemeinsamen Konten" in der Kachel); Einzahlungen einer Person zählen
  dann kontoübergreifend zusammen.
- ✅ **CI-Pipeline** (`.github/workflows/ci.yml`): Jeder Push und Pull Request
  prüft Backend-Tests (pytest), den Frontend-Build und dass die
  Alembic-Migrationen auf einer leeren Datenbank durchlaufen – Letzteres fiel
  sonst erst beim Deployment auf.

### v1.7.1 – Abrechnungsmonat je Nutzer

- ✅ **Jeder wählt seinen eigenen Abrechnungsmonat.** Bisher war der Starttag
  eine app-weite Einstellung, die nur ein Administrator ändern durfte – wer
  kein Administrator war, konnte schlicht nicht speichern. Der Zahltag ist
  aber nichts Gemeinsames: im selben Haushalt kann eine Person am 27. Gehalt
  bekommen und die andere am 1. Die Einstellung wirkt jetzt nur auf die
  **eigenen** Auswertungen (Dashboard, Budgets, Buchungsliste) und lässt die
  Ansicht der anderen unberührt.
- ✅ Wer noch nie etwas gewählt hat, erbt weiterhin die bisherige app-weite
  Voreinstellung – **bestehende Installationen ändern sich dadurch nicht**.
  Die Oberfläche kennzeichnet den geerbten Zustand als „noch nicht selbst
  gewählt“.
- ✅ Unverändert gilt: Buchungsdatum, Betrag, Kontostand und der Saldo-Abgleich
  gegen die Bank rechnen immer mit dem echten Datum.

### v1.7.2 – Umbuchungen sichtbar, Filter, Kurzanleitung

- ✅ **Kennzahlen zeigen Umbuchungen getrennt aus.** Ein Depot oder Tagesgeld
  bekommt sein Geld ausschließlich per Umbuchung – und die zählen bewusst
  weder als Einnahme noch als Ausgabe (sonst wäre jeder Sparbetrag doppelt in
  der Statistik). Die Kachel zeigte deshalb nur Nullen, obwohl Buchungen da
  waren. Jetzt steht die Netto-Bewegung als eigene Zahl daneben, mit einem
  Satz zur Erklärung und einem Link in die gefilterte Buchungsliste.
- ✅ **Buchungsliste filtert nach Art**: *Nur Einnahmen / Nur Ausgaben / Nur
  Umbuchungen* – mit **derselben** Einteilung wie das Dashboard, damit die
  Summe der Liste zur Zahl in der Kachel passt. Dazu Zeitraum-Schnellwahl
  (*Laufender / Letzter Zeitraum*, *Dieses Jahr*), die dem eingestellten
  Abrechnungsmonat folgt.
- ✅ **Kurzanleitung in den Einstellungen**: erklärt mit Skizzen den Ablauf
  (Import → Regeln → Auswertung), die vier Diagrammtypen und die Konzepte
  dahinter – Umbuchungen, Abrechnungsmonat, Bereichstrennung, Bedienung der
  Kacheln. Die Bilder sind eingebettete SVG-Zeichnungen statt Screenshots:
  sie übernehmen das Farbschema samt Dark Mode und veralten nicht bei jeder
  Layoutänderung.

### v1.7.3 – Budgets am Abrechnungsmonat und bearbeitbar

- ✅ **Budgets bearbeiten statt löschen und neu anlegen** (`PUT /budgets/{id}`):
  Betrag, Konto, Kategorie und Gültigkeitsdatum lassen sich am bestehenden
  Eintrag korrigieren. Das ergänzt die Versionierung, ersetzt sie nicht: eine
  Änderung, die erst ab einem Datum gelten soll, bleibt ein neuer Eintrag mit
  eigenem `valid_from` – sonst würde sich rückwirkend die Vergangenheit ändern.
- ✅ **Budgets folgen sichtbar dem Abrechnungsmonat.** Der Verbrauch zählte
  schon immer die richtige Periode, aber die Oberfläche schnitt den Monat aus
  dem Enddatum heraus (`"2026-08-30".slice(0,7)`) – mit verschobenem Starttag
  gehört der 30.08. bereits zum September, also traf sie den falschen Monat.
  Jetzt bestimmt das Backend die Periode (`date_in_period`), und Kachel wie
  Budgetseite schreiben den Zeitraum aus: *Abrechnungsmonat 2026-08
  (27.07.2026 – 26.08.2026)*.
- ✅ **Monatliche Budgets wandern mit**: In jeder Periode beginnt der Verbrauch
  wieder bei 0. Auf der Budgetseite lässt sich mit *‹ › · Laufender Zeitraum*
  durch die Perioden blättern, und eine Spalte **Rest** zeigt, was übrig ist.

### v1.7.4 – Sparquote in Euro, einstellbare Diagramme

- ✅ **Sparquote zeigt jetzt Euro statt nur Prozent.** „300 % Sparquote“ ist
  rechnerisch richtig und trotzdem nicht zu gebrauchen – die Zahl sagt nicht,
  um wie viel Geld es geht. Die Kachel zeigt standardmäßig **€** (gespart,
  Sparpotenzial, Einnahmen) und lässt sich mit einem Klick auf **%**
  umschalten.
- ✅ **Quoten über 100 % werden erklärt** statt kommentarlos stehen gelassen:
  *„2026-05: 161,8 % – das sind 4.450 € auf die Sparkonten bei 2.750 €
  Einnahmen. Mehr als 100 % heißt: das Geld kam nicht aus dem laufenden
  Einkommen, sondern lag schon da.“*
- ✅ **Diagramme einstellbar, wo es etwas ändert**: Zeitfenster der
  Verlaufs-Kacheln (6/12/24/36 Monate), Anzahl der Kategorien in *Ausgaben
  nach Kategorie* (Top 5/10/20/alle), Anzahl der Linien im *Kategorie-Trend*
  (3/5/8) und die Einheit der *Sparquote*. Die Einstellungen gehören zur
  jeweiligen Kachel und werden mit dem Layout gespeichert – pro Nutzer und
  pro Bereich.

### v1.7.5 – Sparquote bereinigt, Erklärungen beim Überfahren

- ✅ **Kein doppelt gezählter Euro mehr in der Sparquote.** Ein Zugang auf ein
  Sparkonto zählte bisher als Gespartes *und* als Einnahme – derselbe Betrag
  war damit Zähler und Teil des Nenners. Ein noch nicht verknüpfter Übertrag
  aufs Tagesgeld trieb die Quote so künstlich Richtung 100 % und darüber.
  Zugänge auf Sparkonten zählen jetzt nur noch als Gespartes. (In den
  *Kennzahlen* bleiben Zinsen weiterhin Einnahme – dort ist danach gefragt.)
- ✅ **Ohne Einnahmen gibt es keine Quote.** Statt „0 %“ – was sich wie „nichts
  gespart“ las, obwohl schlicht die Bezugsgröße fehlte – bleibt der Monat im
  Prozent-Diagramm jetzt leer.
- ✅ **Erklärungen beim Überfahren**: Schaltflächen, die sich nicht von selbst
  erklären, zeigen beim Daraufzeigen einen erklärenden Satz, der stehen
  bleibt, bis die Maus wieder weg ist. Der eingebaute `title`-Hinweis des
  Browsers taugte dafür nicht: er erscheint erst nach gut einer Sekunde,
  verschwindet nach wenigen von selbst wieder und lässt sich nicht gestalten.
  Rein über CSS gelöst (`data-tip`), also ohne JavaScript und ohne hängende
  Kästen nach einem Neuzeichnen; auf Touch-Geräten bleibt er aus.

### v1.7.6 – Kurzanleitung erklärt jede Kachel, Dashboard wird ruhiger

- ✅ **Ein Reiter je Kachel** in der Kurzanleitung (*Einstellungen → Jede Kachel
  im Einzelnen*): alle 17 Dashboard-Kacheln einzeln erklärt – was sie
  beantworten, worauf man achten muss, welche Fallstricke es gibt. Links die
  Liste, rechts der Text; ein kleines Symbol zeigt die Darstellungsart.
- ✅ **Dafür deutlich weniger Fließtext im Dashboard.** Die langen Absätze
  unter den Diagrammen lenkten vom Diagramm ab und wiederholten sich bei jedem
  Besuch. Geblieben sind nur noch berechnete Werte und kurze Hinweise; die
  Herleitung steht in der Anleitung. Ein Link *„Was zeigen die Kacheln? →“*
  über dem Raster führt direkt dorthin und klappt den Abschnitt auf.

### v1.8 – Konzepte begradigt, Vorausschau, Diagramme im Farbschema

**Konzeptfehler behoben**

- ✅ **„Einnahmen“ heißt überall dasselbe.** Kennzahlen und Sparquote zeigten
  für denselben Zeitraum verschiedene Beträge (2.500 € vs. 2.000 €). Die
  Sparquote weist jetzt beide Größen getrennt aus: `income` wie in den
  Kennzahlen, dazu `income_base` als Nenner der Prozentrechnung (ohne
  Sparzugänge – die sind ja der Zähler).
- ✅ **Gespartes kann das Sparpotenzial nicht mehr definitorisch übersteigen** –
  Überschuss und Potenzial rechnen mit derselben Einnahmengröße.
- ✅ **Monatsverlauf bestimmt die Periode nicht mehr selbst.** Wie bei den
  Budgets: `date_in_period` statt `"2026-08-30".slice(0,7)`, was bei
  verschobenem Starttag den falschen Monat traf.
- ✅ **Vergleichszeitraum kommt aus der Periodenregel.** Er wurde kalendarisch
  geschätzt und lag um einen Tag daneben (26.06.–26.07. statt 27.06.–26.07.);
  `/budgets/period/bounds` liefert die Vorperiode jetzt mit.
- ✅ **Schulden getrennt ausgewiesen**: eine Kreditkarte im Minus ist eine
  Schuld, kein negatives Guthaben. `assets_total` und `liabilities_total`
  neben dem unveränderten Nettovermögen.

**Neue Auswertungen**

- ✅ **Verfügbar bis Zahltag**: Saldo der Zahlungskonten minus die bis zum
  Periodenende noch anstehenden wiederkehrenden Abbuchungen, dazu ein Betrag
  pro Resttag. Die einzige Kachel, die nach vorn schaut. Variable Ausgaben
  werden bewusst **nicht** geschätzt – eine geratene Zahl wäre schlechter als
  gar keine.
- ✅ **Vermögensaufteilung**: wo das Geld gerade liegt (nur Guthaben; Schulden
  stehen als eigene Zahl darunter).
- ✅ **Einnahmen nach Quelle**: für Ausgaben gab es fünf Auswertungen, für
  Einnahmen nur eine Summe.
- ✅ **Auffällige Buchungen**: Ausgaben, die deutlich über dem **Median** beim
  selben Empfänger liegen. Median statt Mittelwert, weil ein Ausreißer den
  Mittelwert selbst nach oben zieht und sich darin versteckt.

**Nutzerfreundlichkeit**

- ✅ **Diagramme folgen dem Farbschema.** 25 fest verdrahtete Hex-Werte sind
  raus; die Palette kommt aus CSS-Variablen je Schema, im Dark Mode
  aufgehellt. Vorher blieben die Diagramme blau, während die Seite auf
  „Beere“ oder „Kontrastreich“ umschaltete. Die Ampelfarben bleiben wie
  bisher bewusst fest.
- ✅ **Kuratierte Standardauswahl** statt aller Kacheln beim ersten Start
  (8–10 je Bereich); der Rest steht oben als *+ Name* bereit.
- ✅ **Jede Kachel nennt ihren Zeitraum** in der Überschrift – so ist ablesbar,
  warum manche Kacheln auf den Filter reagieren und andere nicht.

### v1.8.1 – Sparbewegung: eine Regel statt zweier Kopien

- ✅ **Kennzahlen und Sparquote zeigten dieselbe Buchung mit umgekehrtem
  Vorzeichen.** Bei einer Kategorie „wie Umbuchung behandeln“ **ohne**
  hinterlegtes Zielkonto (z. B. ein Sparplan ohne mitgeführtes Depot) stand
  ein Sparbetrag von 250 € in den Kennzahlen als **−250 €** und in der
  Sparquote als **+250 €**. Richtig ist positiv: 250 € in einen Sparplan sind
  250 € gespart – der Buchungsbetrag ist negativ, weil das Geld das Girokonto
  verlässt, die Bedeutung ist die umgekehrte.
- ✅ **Ursache war doppelter Code**: beide Kacheln hatten je eine eigene Kopie
  derselben Regel, und nur eine davon drehte das Vorzeichen. Die Regel steht
  jetzt einmal in `savings_delta()` und wird von beiden benutzt – ein Test
  vergleicht die Zahlen beider Kacheln direkt miteinander, mit und ohne
  Zielkonto.

Datenmodell umfasst bereits alle Entitäten aus Kapitel 6 (auch ExchangeRates
für v2 – kein späterer Datenumbau nötig).

### Noch offen (nächste Stufe)

- **v2**: Mehrwährung mit EZB-Kursabruf (Modell vorhanden), Belege/Anhänge,
  Prognose kommender Fixkosten, Sparziele, Zugriff von unterwegs, native
  Mobile-Ansicht

## Projektstruktur

```
backend/
  app/
    api/          # /api/v1-Router (auth, users, accounts, categories, rules,
                  #  transactions, imports, transfers, dashboard, budgets,
                  #  recurring)
    services/     # csv_import (Parser + Mapping-Assistent), rules_engine,
                  #  transfers (Umbuchungserkennung), recurring
                  #  (Vorfinanzierungs-Abgleich), audit
    models.py     # Datenmodell Kapitel 6
    seed.py       # Admin, Basis-Kategorien, Sparkasse-/ING-Profile
  alembic/        # Migrationen (Prinzip 4)
  tests/          # Parser-Regressionstests mit Beispieldateien + API-Flow +
                  #  v1.1/v1.2
frontend/
  src/views/      # Dashboard, Buchungen, Import, Budgets, Kategorien, Regeln,
                  #  Wiederkehrend, Einstellungen
proxmox/          # LXC-Installer im Community-Skript-Stil
scripts/          # backup.sh / restore.sh / update.sh
docs/             # Anforderungsdokument + Installationsanleitung
```
