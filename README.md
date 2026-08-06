# Haushaltsbuch – Web-Version

Selbst gehostete Web-App als Ersatz für das Excel-Haushaltsbuch: echte Konten,
Mehrbenutzerfähigkeit, flexibler Bank-Import, durchgehende Historie ohne
Jahresschnitt. Grundlage ist das [Anforderungsdokument](docs/Anforderungen.md).

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
- ✅ Design-Einstellungen (Farbschemata + Dark Mode, seit v1.0)
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
