# Haushaltsbuch-App – Anforderungsdokument (v3, vollständig)

> Änderungen ggü. v1: Konsistenzfehler bereinigt, Machbarkeitsrisiken markiert, fehlende Kernfunktionen ergänzt (v.a. Umbuchungen, manuelle Buchungen, Anfangssaldo, Währungsumrechnung), Struktur auf Erweiterbarkeit ausgelegt (Kap. 3, 6, 7).
> Änderungen ggü. v2: Kategorien mit drei Geltungsbereichen (4.6), Import für jedes Konto inkl. automatischer Zielkonto-Erkennung (4.5), Kachel-Dashboard mit Drag & Drop sowie Design-/Farbschema-Einstellungen (4.9.1, 4.10) aus dem Mockup-Review ergänzt.

> **Verwendungshinweis:** Dieses Dokument ist als vollständige Grundlage für die Umsetzung gedacht – z.B. als Prompt/Kontext für ein KI-Coding-Tool. Kapitel 3 (Leitprinzipien), 6 (Datenmodell) und 7 (Stufenplan) sind bewusst so verfasst, dass sie direkt als Bauanleitung dienen können; Kapitel 9 listet, was vor dem eigentlichen Bauen noch zu klären ist.

---

## 1. Ausgangslage

Bisher: Excel-Mappe (`.xlsm`), pro Jahr eine Datei. Aufbau, der fachlich übernommen wird:

- **CSV Einlesen** → Rohimport von Bank-Exports
- **Kategorisieren** → Kategoriezuordnung per Schlüsselwort-Suche (`SEARCH`) im Verwendungszweck gegen Whitelist-Tabelle
- **Kategorien (Fix)** → Kategorien, die als "Fixkosten" gelten
- **Whitelisten** → ~20 Kategorien mit je einer Liste Erkennungs-Schlüsselwörter (Aldi/Lidl/Rewe → Lebensmittel)
- **Einträge** → Tabelle mit laufendem Saldo je Konto (Giro/Tagesgeld/Sparbuch/Vermögen), Konten als Spalten mit Index (0/1/2)
- **Dashboards (3x)** → Auswertungen inkl. Budget-Soll/Ist

**Probleme der bisherigen Lösung:**
1. CSV-Import manuell (Copy-Paste), Formeln hängen an Zeilenposition
2. Konten als Spalten-Hack statt echter Entitäten
3. Nur ein Bankformat praktikabel
4. Jahresgrenze = Dateigrenze → kein durchgehender Verlauf über Jahre

## 2. Ziel

Selbst gehostete Web-App als Ersatz für das Excel-Haushaltsbuch: echte Konten, Mehrbenutzerfähigkeit, flexibler Bank-Import, durchgehende Historie ohne Jahresschnitt.

---

## 3. Leitprinzipien für Erweiterbarkeit

Damit die App nachträglich erweitert und auf neuere Versionen gehoben werden kann, gelten folgende Grundsätze **verbindlich für alle folgenden Kapitel**:

1. **Konfiguration statt Code.** Alles, was sich fachlich ändern kann, liegt als Daten in der DB, nicht im Quelltext: Kategorien, Kategorisierungsregeln, Bank-Importprofile, Kontotypen, Budget-Schwellwerte, Zyklen. Eine neue Bank oder Kategorie darf **kein Deployment** erfordern.
2. **Rohdaten aufbewahren.** Zu jeder Buchung wird die ursprüngliche CSV-Zeile unverändert mitgespeichert. Damit lassen sich Parser- oder Regelverbesserungen später **rückwirkend** anwenden, ohne bei den Banken neu zu exportieren.
3. **Ableitbare Werte nicht doppelt speichern.** Salden, Monatssummen, Budget-Ausschöpfung werden aus Buchungen berechnet (ggf. als Cache mit Neuberechnungs-Möglichkeit). Kein zweiter Wahrheitsstand, der divergieren kann.
4. **Versioniertes DB-Schema mit Migrationen** (z.B. Alembic/Prisma Migrate). Schema-Änderungen laufen als Migrationsskripte, nie händisch → Upgrade = neues Image + Migration.
5. **Schichtentrennung.** Import-Adapter (je Bank) hinter einem gemeinsamen Interface; Kern-Domäne (Konten/Buchungen/Kategorien) kennt keine Bankformate; Frontend spricht nur über eine **versionierte API (`/api/v1`)** → Frontend austauschbar, Mobile-App später ohne Backend-Umbau möglich.
6. **Keine Fachlogik im Frontend.** Berechnungen (Salden, Budgets, Abgleiche) ausschließlich im Backend.
7. **Idempotenter, rückrollbarer Import.** Jeder Import ist ein Vorgang (Batch) mit eigener ID und kann komplett rückgängig gemacht werden.
8. **Rollen statt Sonderfälle.** Berechtigungen als Rollenmatrix, nicht als hartcodierter "Hauptnutzer" (siehe 4.1).
9. **Regressionstests für Import-Parser** mit echten Beispieldateien je Bank → Upgrades brechen bestehende Formate nicht.

---

## 4. Fachliche Anforderungen

### 4.1 Benutzer, Rollen & Berechtigungen

- **Multi-User** mit Login (Benutzername/Passwort, Passwörter gehasht – z.B. argon2/bcrypt)
- Jeder Nutzer hat einen **eigenen Bereich**: eigene Konten, eigenes Dashboard
- **Berechtigungen pro Konto als Rollenmodell** (statt fest verdrahtetem "Haupt-User"):

  | Rolle | Rechte |
  |---|---|
  | Eigentümer | alles inkl. Konto löschen/archivieren, Rechte vergeben |
  | Bearbeiter | Buchungen importieren, kategorisieren, bearbeiten |
  | Leser | nur Ansicht, keine Änderungen |

  Aktuelle Belegung: gemeinsames Konto → du = Eigentümer/Bearbeiter, zweite Person = Leser. Ein späterer Wechsel (oder ein dritter Nutzer) ist damit reine Konfiguration.
- **Beliebig viele gemeinsame Konten möglich** (v1 nutzt eins, das Modell begrenzt es nicht) — korrigiert einen Widerspruch aus v1, wo an einer Stelle von genau einem gemeinsamen Konto ausgegangen wurde
- **Benutzerverwaltung**: Nutzer anlegen/deaktivieren, Passwort ändern/zurücksetzen. **Keine offene Selbstregistrierung** (Heimbetrieb, Einladung/Admin-Anlage)
- **Änderungsprotokoll** (wer hat wann was geändert), mindestens für gemeinsame Konten – wichtig für Transparenz, da nur eine Person schreibt und die andere mitliest

### 4.2 Konten

- Konten sind **eigene Entitäten** mit: Name, Typ (Giro, Tagesgeld, Sparbuch, Depot, Bargeld, Kreditkarte, …), Währung, Bank, IBAN (optional), Eigentümer/Rollen, Notiz
- **Anfangssaldo pflicht­fähig** *(in v1 nicht enthalten, ist aber zwingend)*: CSV-Exporte decken nur einen Zeitraum ab. Ohne Eröffnungssaldo zum Startdatum ist jeder berechnete Kontostand falsch.
- **Saldo-Abgleich**: wo die Bank einen Saldo mitliefert (ING tut das), wird der berechnete Saldo gegen den Bank-Saldo geprüft und eine Abweichung angezeigt → erkennt fehlende Importe oder Lücken
- **Konten anlegen** über die App, beliebig viele
- **Löschen ⇒ standardmäßig Archivieren** *(Präzisierung ggü. v1)*: Ein echtes Löschen würde Historie und Jahresvergleiche zerstören. Archivierte Konten verschwinden aus der aktiven Ansicht, Buchungen bleiben erhalten. Endgültiges Löschen nur als bewusste Extra-Aktion mit Warnung (inkl. Hinweis, wie viele Buchungen betroffen sind).

### 4.3 Währungen

*(neu – in v1 nur als Konto-Eigenschaft erwähnt, ohne Folgelogik)*

- Mehrwährungsfähigkeit gewünscht → hat Konsequenzen, die festgelegt werden müssen:
- **Referenzwährung** für alle Auswertungen: EUR
- Pro Buchung werden **Originalbetrag + Originalwährung** gespeichert, zusätzlich der **umgerechnete Betrag zum Buchungsdatum**
- Kursquelle: EZB-Tageskurse (frei verfügbar), lokal zwischengespeichert; ohne Internet fällt der Import auf "Kurs nachtragen" zurück statt zu scheitern
- Konsequenz für Dashboards/Budgets: Summen laufen immer über die Referenzwährung, Einzelbuchungen zeigen zusätzlich das Original
- Relevanz konkret: Norwegian Bank (Kreditkarte) ist der wahrscheinlichste Fremdwährungsfall

### 4.4 Buchungen

*(größtenteils neu – v1 beschrieb faktisch nur importierte Buchungen)*

- **Umbuchungen zwischen eigenen Konten** *(kritische Lücke in v1)*: Eine Überweisung von Giro → Tagesgeld erscheint in **zwei** CSV-Exporten (Abgang + Zugang). Ohne Behandlung zählt die App das als Ausgabe **und** Einnahme und verfälscht jede Auswertung. Notwendig:
  - Erkennung zusammengehöriger Gegenbuchungen (gleicher Betrag, gegenläufiges Vorzeichen, Datum ±wenige Tage, beteiligte IBANs)
  - Verknüpfung zu **einer** Umbuchung, die in Einnahmen/Ausgaben **nicht** mitzählt, aber in "Bewegung Sparkonten" sichtbar bleibt
  - Manuelles Verknüpfen/Auflösen als Fallback, wenn die Automatik danebenliegt
  - Betrifft auch: die monatliche Erstattung vom gemeinsamen Konto und die "Ausgleich"-Überweisungen zwischen euch
- **Manuelle Buchungen** *(fehlte komplett)*: Nicht alles kommt aus der Bank – Bargeldausgaben insbesondere. Bisher endete Bargeld in der Kategorie "Bargeldauszahlung" und war danach unsichtbar. Vorschlag: Bargeld als eigenes Konto führen, Abhebung = Umbuchung Giro → Bargeld, Ausgaben davon manuell erfassen. Manuelle Buchungen sind voll bearbeitbar.
- **Splitbuchungen**: eine Buchung auf mehrere Kategorien aufteilen (z.B. Supermarkt-Beleg mit Lebensmitteln + Drogerie + Katze)
- **Änderbarkeit importierter Buchungen**: Betrag/Datum/Gegenkonto bleiben unveränderlich (sonst stimmt der Abgleich mit der Bank nicht mehr); änderbar sind Kategorie, Notiz, Tags, Split, Umbuchungs-Verknüpfung
- **Tags** als leichtgewichtige zweite Dimension neben Kategorien (z.B. "Urlaub Norwegen 2026", "Umzug") – verhindert, dass die Kategorienliste für Sonderfälle aufgebläht wird
- **Belege/Anhänge** (PDF/Foto an Buchung) – optional, für spätere Version
- **Maßgebliches Datum**: Buchungstag (nicht Valutadatum) ist für Auswertungen führend; beide werden gespeichert

### 4.5 Import

- **Import ist für jedes Konto möglich** – nicht nur fürs Girokonto: persönliche Konten, Sparkonten, Kreditkarte **und das gemeinsame Konto** laufen über denselben Weg. Voraussetzung ist lediglich die Rolle Bearbeiter/Eigentümer auf dem Zielkonto (4.1).
- **Zielkonto automatisch erkennen**: Beide analysierten Formate liefern die Konto-IBAN mit (Sparkasse in der Spalte `Auftragskonto`, ING im Metadaten-Kopf). Stimmt sie mit einem hinterlegten Konto überein, schlägt die App das Zielkonto selbst vor; sonst wird es beim Import ausgewählt. Enthält eine Datei mehrere Konten, werden die Buchungen anhand der IBAN automatisch aufgeteilt.
- **Mehrere Banken mit unterschiedlichen CSV-Formaten**: Sparkasse, Volksbank, ING-DiBa, Norwegian Bank (Kreditkarte)
- **Importprofile als Daten**, nicht als Code (siehe Prinzip 1): Trennzeichen, Encoding, Anzahl Kopfzeilen, Spaltenzuordnung, Datums- und Zahlenformat, Vorzeichenlogik
- **Mapping-Assistent in der Oberfläche** *(neu)*: Unbekannte CSV hochladen → App zeigt erkannte Spalten → Nutzer ordnet zu und speichert das als neues Profil. Damit ist die App **nicht davon abhängig**, dass alle Formate vorab bekannt sind – löst insbesondere das offene Problem Volksbank/Norwegian Bank.
- **Import als Vorgang (Batch)** *(neu)*: jeder Import wird protokolliert (Datei, Zeitpunkt, Profil, Anzahl Buchungen) und ist **komplett rückgängig machbar**. Ohne das wird ein Fehlimport mit falschem Mapping zur Handarbeit.
- **Vorschau vor Übernahme**: erkannte Buchungen, zugeordnete Kategorien und Duplikate werden vor dem Schreiben angezeigt
- **Duplikatserkennung**: kein Bankformat liefert eine eindeutige Transaktions-ID → Erkennung über Hash aus Datum + Betrag + Gegenkonto/IBAN + Verwendungszweck.
  *Einschränkung, die berücksichtigt werden muss:* echte Doppelungen kommen vor (zweimal derselbe Betrag beim selben Händler am selben Tag). Deshalb wird nicht stumpf verworfen, sondern **die Anzahl gleicher Buchungen je Tag verglichen** und Verdachtsfälle in der Vorschau zur Bestätigung vorgelegt.
- **Rohzeile speichern** (Prinzip 2)
- **Historische Daten**: Altbestand kommt aus den **rohen Jahres-CSV-Exporten der Banken**, nicht aus der Excel-Datei → gleicher Mechanismus wie im Laufbetrieb, kein Sonder-Importer nötig
- Upload per Drag & Drop

#### 4.5.1 Bank-Formate – Analyse der Beispiel-Exporte

| | Sparkasse | ING |
|---|---|---|
| Trennzeichen | Semikolon | Semikolon |
| Felder gequotet | ja, durchgängig | nein |
| Header-Position | Zeile 1 | erst nach 8 Metadaten-Zeilen + 1 Erklärtext-Zeile |
| Datumsformat | `TT.MM.JJ` (2-stelliges Jahr, z.B. `24.07.26`); ältere Exporte mit vollem Datum → Parser muss beides können | `TT.MM.JJJJ` |
| Betragsformat | Dezimalkomma (`-22,98`) | Dezimalkomma + Tausenderpunkt (`1.000,00`) |
| Encoding | vermutlich UTF-8 (zu verifizieren) | Umlaute zerschossen ("W hrung") → ISO-8859-1/Windows-1252; Encoding muss erkannt/konfigurierbar sein, sonst brechen Schlüsselwort-Treffer bei Umlauten |
| Fallstrick | – | **zwei Spalten heißen "Währung"** (Saldo und Betrag) → Zuordnung über Spaltenposition, nicht über Namen |
| Nutzbare Zusatzinfo | Buchungstext, Gläubiger-ID, Mandatsreferenz, Begünstigter, Gegen-IBAN, BIC | Auftraggeber/Empfänger, laufender Saldo (für Abgleich nach 4.2) |

Volksbank und Norwegian Bank: Formate noch offen. Genossenschaftsbanken nutzen meist ein sparkassenähnliches Schema; bei Norwegian Bank (Kreditkarte) ist unklar, ob überhaupt CSV oder nur PDF angeboten wird. **Durch den Mapping-Assistenten (4.5) ist das kein Blocker mehr** – nur PDF-Only wäre einer, dann bliebe manuelle Erfassung oder ein späterer PDF-Parser.

### 4.6 Kategorien & Regeln

- **Kategorien haben einen Geltungsbereich** – drei Stufen statt der starren Zweiteilung aus v1:

  | Geltungsbereich | Sichtbar für | Zweck |
  |---|---|---|
  | global | alle Nutzer | Basis-Kategorien (die bestehenden ~20) |
  | kontobezogen | alle Nutzer mit Zugriff auf dieses Konto | **eigene Kategorien für das gemeinsame Konto**, z.B. "Haushalt", "Urlaubskasse" |
  | persönlich | nur der anlegende Nutzer | private Ergänzungen im eigenen Bereich |

- Damit lassen sich **für das gemeinsame Konto eigene Kategorien anlegen**, ohne den Widerspruch aus v1: sie gehören zum Konto, nicht zu einer Person, und sind deshalb auch für die lesende Person sichtbar und in ihren Auswertungen korrekt beschriftet.
- Eine **persönliche** Kategorie darf dagegen nicht auf ein gemeinsames Konto gebucht werden – die andere Person sähe sonst eine Bezeichnung, die es in ihrem Bereich nicht gibt. Die App bietet in dem Fall an, die Kategorie in den kontobezogenen Bereich hochzustufen.
- **Regeln** (Nachfolger der Whitelisten) mit mehr Kriterien als bisher: nicht nur Verwendungszweck, sondern auch **Empfänger/Auftraggeber, Gegen-IBAN, Buchungstext, Betragsbereich, Konto**. IBAN-Regeln sind deutlich treffsicherer als Textsuche – und genau das nutzt ihr ohnehin schon zur Zuordnung, wer eine Position zahlt.
- **Regelpriorität**: Regeln haben eine definierte Reihenfolge; bei mehreren Treffern gewinnt die erste. In Excel war das implizit die Spaltenreihenfolge – in der App wird es explizit und sortierbar.
- **Hybrid bei Nichterkennung**: Schnellzuordnung direkt in der Import-Vorschau, ansonsten "Nicht zugeordnet" und späteres Nachsortieren. Aus einer manuellen Zuordnung kann per Klick eine neue Regel entstehen ("künftig immer so").
- **Kategorien umbenennen und zusammenführen** ohne Datenverlust
- **Ober-/Unterkategorien** *(neu, aber bereits angelegt)*: "Motorrad KTM" und "Motorrad gesamt" in der alten Mappe deuten schon auf Hierarchiebedarf hin. Zweistufig genügt.
- **Rückwirkende Neuanwendung** von Regeln auf bereits importierte Buchungen (möglich dank Prinzip 2)

### 4.7 Fixkosten & wiederkehrende Kostenpositionen

*(in v1 unter "Budgets" – gehört fachlich getrennt, da es kein Budget ist)*

Zwei unterschiedliche Dinge, die in v1 sprachlich vermischt waren:

**a) Fixkosten-Kennzeichen** (Auswertungsmerkmal)
- Kategorien bzw. Empfänger können als "fix" markiert werden → Dashboards trennen fixe von variablen Kosten
- Erkennung über Empfänger/Stichwort, nicht über Betrag, da Fixkosten schwanken (Nebenkostennachzahlung, Preiserhöhung)
- Ausreißer bleiben sichtbar, statt im Fixkosten-Topf zu verschwinden

**b) Wiederkehrende Kostenposition** (eigene Entität)
- Beispiele: ADAC (jährlich), Rundfunkbeitrag (quartalsweise), Netflix / Amazon Prime / Spotify (monatlich oder jährlich)
- Eigenschaften: Name, Zyklus, erwarteter Betrag, zahlendes Konto, zugeordnete Regel/Kategorie, Vorfinanzierungs-Verknüpfung
- **Zahler ergibt sich automatisch** aus dem Konto/der IBAN der Original-Abbuchung – keine manuelle "wer zahlt was"-Liste
- **Vorfinanzierungs-Abgleich**: Ein Teil dieser Positionen wird monatlich anteilig über das gemeinsame Konto vorfinanziert (Dauerauftrag "Fixkosten" hin, monatliche Erstattung zurück, Rate = letzte Abbuchung ÷ Monate im Zyklus). Die App vergleicht **Soll (aufsummierte Erstattungen seit der letzten Abbuchung)** gegen **Ist (tatsächliche neue Abbuchung)** und meldet Abweichungen, damit die Rate rechtzeitig angepasst wird.
- Positionen sind frei anlegbar, ohne Code-Änderung

> **Machbarkeitshinweis:** Das ist die komplexeste Funktion des Systems, weil sie drei getrennte Buchungsströme über zwei Konten hinweg zusammenführt (Abbuchung, Einzahlung, Erstattung) und auf funktionierender Umbuchungserkennung (4.4) aufsetzt. Empfehlung: erst Kern bauen, diese Funktion in einer späteren Version – und die Verknüpfung von Anfang an auch **manuell setzbar** machen, damit sie nicht an der Automatik hängt.

### 4.8 Budgets

- **Monatliche Budgets pro Kategorie**, Schwerpunkt gemeinsames Konto; technisch auch für persönliche Konten möglich (noch zu entscheiden, ob in v1 genutzt)
- **Ampel nach Ausschöpfung**: grün < 80 %, gelb/orange 80–97 %, rot ≥ 98 %
- Soll/Ist-Vergleich pro Kategorie im Dashboard (entspricht dem bestehenden "Monatliches Budget vs. Ausgaben")
- Schwellwerte sind **konfigurierbar**, nicht fest verdrahtet (Prinzip 1)
- Budgets sind ab Gültigkeitsdatum versioniert, damit eine spätere Erhöhung nicht die Vergangenheit rückwirkend verändert

### 4.9 Dashboards

Pro Nutzer ein eigenes Dashboard. Übernommen aus Excel:

| Diagrammtyp | Inhalt |
|---|---|
| Balken | Monatliche Bilanz (Einnahmen – Ausgaben) |
| Balken | Monatliche Gesamtausgaben |
| Drilldown/Filter | Einzelne Kategorie nach Monat |
| Donut | fix/variabel × Einnahmen/Ausgaben (ohne Umbuchungen) |
| Donut | Umbuchungen Giro ↔ Sparkonten (Sparen vs. Auslagen) |
| Balken | Monatliche Bewegung der Sparkonten |
| Balken | Monatliches Budget vs. Ausgaben |

Ergänzend (bestätigt):
- Vermögensverlauf pro Konto als Linie über die Zeit
- Einzahlungen pro Person aufs gemeinsame Konto im Zeitverlauf
- Ampel-Übersicht der wiederkehrenden Kostenpositionen (Soll/Ist)
- Sparquote im Zeitverlauf (Anteil am Einkommen)
- Top-Ausgaben im Zeitraum
- Jahresvergleich pro Kategorie (möglich durch durchgehende Historie)

Zusätzlich: **frei wählbarer Zeitraum** statt fester Monats-/Jahresraster, und **mobiltaugliche Darstellung** (Zugriff vom Handy ist explizit gewünscht).

#### 4.9.1 Aufbau & Bedienung (aus Mockup-Review festgelegt)

- **Kachel-Dashboard**: Jede Auswertung (Kennzahl, Diagramm, Liste) ist eine eigenständige Kachel in einem Raster. Kacheln lassen sich **per Drag & Drop verschieben, entfernen und wieder hinzufügen** – kein festverdrahtetes Layout wie in Excel.
- **Layout ist pro Nutzer gespeichert** (nicht global): Anordnung, sichtbare/entfernte Kacheln. Zahlt direkt auf Prinzip 1 ein – eine neue Kachelart ist später ein zusätzlicher Kacheltyp in der Konfiguration, kein Umbau des Layouts.
- **Kontenliste als feste Randspalte** (links), analog zur Kontenübersicht aus dem ersten Entwurf – dauerhaft sichtbar, kein eigener Tab nötig. Persönliche Konten und gemeinsame Konten sind darin sichtbar getrennt.
- **Filter als Chip-Leiste** über dem Kachelraster (Konto, Kategorie, Zeitraum) statt Excel-Slicer-Optik, aber mit derselben Funktion: **eine Auswahl filtert alle Kacheln gleichzeitig**, nicht Diagramm für Diagramm einzeln wie in den alten Pivots.
- **Buchungen mit Handlungsbedarf werden nicht versteckt**: nicht zugeordnete Buchungen zeigen einen auffälligen "zuordnen"-Hinweis statt still in einer Kategorie zu verschwinden; Umbuchungen werden neutral/grau markiert statt als Ein- oder Ausgabe eingefärbt.
- **Warnkacheln** (z.B. Vorfinanzierungs-Abweichung nach 4.7 b) sind farblich abgesetzt (Warnfarbe), damit sie im Raster auffallen, ohne den Rest der Optik zu bestimmen.

### 4.10 Design & Benutzereinstellungen

*(neu, aus Mockup-Review)*

- **Einstellungen über ein Zahnrad-Symbol neben dem Benutzer-Avatar** (rechts oben, neben Import/Suche) – öffnet ein Menü, keine eigene Unterseite nötig für die grundlegenden Optionen
- **Farbschema wählbar**, mehrere vordefinierte Paletten (helle/ruhige/sachliche/warme Variante o.ä.), pro Nutzer einstellbar – beide Nutzer können unterschiedliche Farbschemata haben
- **Feste Ausnahme, nicht verhandelbar**: die Budget-Ampel (grün/gelb-orange/rot, siehe 4.8) und Warnfarben ändern sich **nicht** mit dem Farbschema, damit ihre Bedeutung immer eindeutig bleibt
- Dunkles Design als weitere Einstellung
- Einstellungen sind Daten pro `User` (siehe Datenmodell), kein Deployment für ein neues Farbschema nötig

### 4.11 Suche, Export, Datenhoheit

*(neu)*
- Volltextsuche und Filter über alle Buchungen (Zeitraum, Konto, Kategorie, Betragsbereich, Text)
- **Export als CSV/Excel** – bewusst als Schutz vor Bindung an die eigene App; wer aus Excel kommt, will Daten auch wieder herausbekommen
- Vollständiger Datenbank-Export/Import für Umzug oder Wiederherstellung

---

## 5. Technik & Betrieb

- **Zielumgebung**: Proxmox-Server (LXC oder VM) als Laufzeit, Synology NAS als Backup-Ziel. Empfehlung: Anwendung als Docker-Compose-Stack auf Proxmox, Datenbank-Sicherung aufs NAS – trennt Rechenlast und Datensicherung sauber.
- **Zugriff im Heimnetz**, auch mobil. Auch ohne Internetfreigabe sinnvoll: **HTTPS im LAN** und Session-Handling, da es sich um Finanzdaten mit Mehrbenutzer-Login handelt. Zugriff von unterwegs später über VPN/Tailscale nachrüstbar, ohne die App zu ändern.
- **Datenbank**: PostgreSQL (mehrbenutzerfähig, robuste Migrationen). SQLite wäre für einen Einzelnutzer ausreichend, passt aber schlechter zu Mehrbenutzerbetrieb und späterem Wachstum.
- **Backup** *(offener Punkt aus v1, hier konkretisiert)*: automatisierter täglicher DB-Dump aufs NAS, Aufbewahrung mehrerer Generationen, **automatischer Dump unmittelbar vor jeder Schema-Migration**, und mindestens einmal ein getesteter Rücksicherungs-Durchlauf – ein Backup, das nie zurückgespielt wurde, ist kein Backup.
- **Upgrade-Weg**: neues Container-Image ziehen → Migration läuft automatisch → bei Fehler Rückfall auf vorheriges Image + Dump. Versionsnummer in der Oberfläche sichtbar.

---

## 6. Datenmodell – Grundstruktur

Bewusst so geschnitten, dass spätere Funktionen andocken können, ohne Bestehendes umzubauen:

| Entität | Zweck / wichtige Felder |
|---|---|
| `User` | Login, Passwort-Hash, Anzeigename, aktiv |
| `AccountRole` | User × Konto × Rolle (Eigentümer/Bearbeiter/Leser) → ersetzt Sonderfall "Hauptnutzer" |
| `Account` | Name, Typ, Währung, Bank, IBAN, Anfangssaldo + Stichtag, archiviert (ja/nein) |
| `Transaction` | Konto, Buchungstag, Valutadatum, Betrag, Währung, Betrag in Referenzwährung, Gegenpartei, Gegen-IBAN, Verwendungszweck, Buchungstext, Kategorie, Notiz, Import-Batch, **Rohzeile**, Dedup-Hash |
| `TransactionSplit` | Teilbeträge einer Buchung auf mehrere Kategorien |
| `Transfer` | verknüpft zwei `Transaction` als eine Umbuchung |
| `Category` | Name, Oberkategorie, Geltungsbereich (global / kontobezogen / persönlich) + zugehöriges Konto bzw. Nutzer, Fixkosten-Flag, aktiv |
| `Tag` / `TransactionTag` | freie Zweitdimension |
| `Rule` | Kriterien (Text, IBAN, Empfänger, Betragsbereich, Konto), Zielkategorie, Priorität, aktiv |
| `BankProfile` | Importprofil: Trennzeichen, Encoding, Kopfzeilen, Spaltenzuordnung, Datums-/Zahlenformat |
| `ImportBatch` | Datei, Zeitpunkt, Nutzer, Profil, Anzahl Buchungen, rückrollbar |
| `Budget` | Kategorie, Konto/Bereich, Betrag, Periode, gültig ab |
| `RecurringItem` | wiederkehrende Kostenposition: Zyklus, erwarteter Betrag, zahlendes Konto, Vorfinanzierungs-Verknüpfung |
| `ExchangeRate` | Währungspaar, Datum, Kurs |
| `AuditLog` | wer, wann, was geändert |
| `DashboardLayout` | User, Liste der Kacheln inkl. Typ, Position, Größe, sichtbar/entfernt |
| `UserSettings` | User, Farbschema, Dunkles Design, weitere Anzeigepräferenzen |

---

## 7. Umsetzung in Stufen

Bewusst so geschnitten, dass jede Stufe für sich nutzbar ist:

**v1.0 – Kern (macht Excel bereits ersetzbar)**
Login & Rollen · Konten inkl. Anfangssaldo · CSV-Import mit Mapping-Assistent, Vorschau, Dedup, Rollback · Kategorien & Regeln · Umbuchungserkennung · manuelle Buchungen/Bargeld · Basis-Dashboard · Suche & Export · Backup

**v1.1 – Komfort**
Splitbuchungen · Tags · Budgets mit Ampel · erweiterte Dashboards (Vermögensverlauf, Sparquote, Top-Ausgaben, Jahresvergleich) · rückwirkende Regelanwendung · anpassbares Kachel-Dashboard (Drag & Drop) · Design-Einstellungen (Farbschema, Dark Mode)

**v1.2 – Haushalts-Logik**
Wiederkehrende Kostenpositionen · Vorfinanzierungs-Abgleich · Einzahlungs-Transparenz gemeinsames Konto · Saldo-Abgleich gegen Bank

**v2 – optional**
Mehrwährung mit automatischem Kursabruf · Belege/Anhänge · Prognose kommender Fixkosten · Sparziele · Zugriff von unterwegs · native Mobile-Ansicht

*(Mehrwährung ist im Datenmodell ab v1.0 vorgesehen, aber erst ab v2 mit automatischem Kursabruf ausgebaut – so entsteht später kein Datenumbau.)*

---

## 8. Ergebnis der Prüfung

**Behobene Widersprüche**
1. "Ein gemeinsames Konto" vs. Konten mit Eigentümer-Eigenschaft → Rollenmodell, beliebig viele geteilte Konten
2. "Nur der Haupt-User darf bearbeiten" als Person hartcodiert → Rolle
3. Budget-Kapitel erklärte Periodik und Schwellwerte für geklärt und zugleich für offen → bereinigt
4. Persönliche Kategorien vs. gemeinsames Konto (lesende Person sähe unbekannte Kategorien) → dreistufiger Geltungsbereich: global / kontobezogen / persönlich, sodass eigene Kategorien fürs gemeinsame Konto möglich sind
5. Fixkosten-Kennzeichen und wiederkehrende Kostenposition waren sprachlich vermischt → getrennt (4.7 a/b)

**Geschlossene Lücken**
6. Umbuchungen zwischen eigenen Konten (Doppelzählung als Einnahme *und* Ausgabe)
7. Anfangssaldo pro Konto – ohne ihn ist jeder Kontostand falsch
8. Manuelle Buchungen / Bargeld
9. Währungsumrechnung samt Referenzwährung und Kursquelle
10. Import-Batch mit Rollback und Vorschau
11. Grenzen der Duplikatserkennung (echte Doppelbuchungen)
12. Kontolöschung → Archivierung statt Historienverlust
13. Regelpriorität bei Mehrfachtreffern
14. Suche, Export, Benutzerverwaltung, Änderungsprotokoll, Backup-Konkretisierung

**Machbarkeit**
- Der Kern (v1.0) ist unkritisch und mit Standardtechnik gut umsetzbar.
- Einziges echtes Außenrisiko: das Exportformat der Norwegian Bank. Falls dort nur PDF angeboten wird, braucht es manuelle Erfassung oder später einen PDF-Parser. Der Mapping-Assistent entschärft alle CSV-Fälle.
- Anspruchsvollste Funktion: Vorfinanzierungs-Abgleich (4.7 b) – deshalb bewusst nach hinten geplant und mit manueller Verknüpfung als Rückfallebene.

---

## 9. Offene Punkte

- Beispiel-Exporte Volksbank und Norwegian Bank (kein Blocker mehr, aber hilfreich); bei Norwegian Bank zuerst klären: gibt es überhaupt CSV?
- Budgets: nur gemeinsames Konto oder auch persönliche Konten in v1?
- Liegen die alten Jahres-CSVs noch vor, oder müssen sie neu exportiert werden? (Banken halten Umsätze oft nur begrenzt vor – lohnt sich, früh zu prüfen)
- Bargeld als eigenes Konto führen – gewünscht?
- Technologiewahl im Detail (Backend-Sprache/Framework, Frontend)

## 10. Nächste Schritte

1. Offene Punkte aus Kapitel 9 klären
2. Technologiestack festlegen und Projektgerüst aufsetzen (Container, DB, Migrationen)
3. Datenmodell aus Kapitel 6 als erste Migration umsetzen
4. Import-Pipeline mit Sparkasse und ING als Referenzformaten bauen (inkl. Tests)
5. Kategorisierung + Kern-Dashboard
6. Altbestand über Jahres-CSVs einspielen
