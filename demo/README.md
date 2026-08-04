# Demo-Material

Gehört zum [Demo-Stack](../README.md#demo-instanz-zum-zeigenTesten)
(`scripts/demo-up.sh`, Port 8181, Login `test`/`test`).

## Was der Demo-Stack automatisch anlegt

Beim allerersten Start (`SEED_DEMO_DATA=true`, nur im Demo-Stack aktiv,
siehe `backend/app/seed_demo.py`) wird die leere Datenbank mit einer
realistischen ~6-Monats-Historie befüllt:

- **4 Konten**: Girokonto, Tagesgeld, Bargeld, ein gemeinsames Konto
- **2 Nutzer**: `test` (Eigentümer aller Konten) und `partner`/`partner123`
  (Leser auf dem gemeinsamen Konto) – zum Vorführen des Rollenmodells (4.1)
- **~150 Buchungen**: Gehalt, Miete, Nebenkosten, Abos, Lebensmittel,
  Tanken, Restaurant, u.v.m.
- Eine **automatisch erkannte Umbuchung** (Giro ↔ Tagesgeld, per IBAN) und
  eine **offene Umbuchungs-Vorschlag** (Bargeldabhebung) zum Live-Bestätigen
- Ein **Split-Beispiel**, ein **Tag** ("Urlaub 2026"), ein **Budget**
  (Lebensmittel), eine **wiederkehrende Kostenposition** (Netflix – bewusst
  noch nicht verknüpft, zum Live-Vorführen von „Erkennung ausführen")
- Eine Kategorie ist als **„wie Umbuchung behandeln"** markiert
  (Sparplan-Ausführungen, zeigt die v1.3-Funktion)
- **13 Kategorisierungsregeln** und **4 unzugeordnete Buchungen** (zeigt die
  „Handlungsbedarf"-Kachel)

## `beispiel_import_sparkasse.csv`

15 weitere, noch nicht importierte Umsätze im Sparkasse-CSV-Format für das
Demo-Girokonto – zum Live-Vorführen des Import-Ablaufs (Vorschau,
automatische Zielkonto-Erkennung per IBAN, Kategorie-Vorschläge über die
vorhandenen Regeln, Übernehmen).

**Vorführen:** Import → Datei hierher ziehen → Profil „Sparkasse" wählen →
Vorschau (Zielkonto wird automatisch erkannt, mehrere Zeilen bekommen schon
eine Kategorie vorgeschlagen) → Übernehmen.
