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
  manuelles Verknüpfen/Auflösen
- ✅ Manuelle Buchungen / Bargeld-Konto
- ✅ Dashboard: Kennzahlen, Monatsbilanz, Monatsausgaben, Kategorie-Donut,
  fix/variabel, Sparkonten-Bewegung, Top-Ausgaben, Filter-Chips, Warnkachel
  für nicht zugeordnete Buchungen, freier Zeitraum, mobiltauglich
- ✅ Suche & CSV-Export, Änderungsprotokoll (AuditLog), Backup-Skripte

### v1.1 – Komfort

- ✅ **Splitbuchungen**: eine Buchung auf mehrere Kategorien aufteilen
  (Summenprüfung, anteilige Auswertung in Dashboard und Budgets)
- ✅ **Tags** als zweite Dimension (frei vergebbar, Filter in der Buchungsliste)
- ✅ **Budgets mit Ampel**: monatlich je Kategorie, ab Gültigkeitsdatum
  versioniert, Schwellwerte konfigurierbar, Ampelfarben schema-unabhängig
- ✅ **Kachel-Dashboard**: Kacheln per Drag & Drop anordnen, aus-/einblenden –
  Layout wird pro Nutzer gespeichert
- ✅ **Erweiterte Dashboards**: Vermögensverlauf pro Konto, Sparquote im
  Zeitverlauf, Jahresvergleich pro Kategorie
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
