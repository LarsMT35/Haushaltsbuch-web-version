# Demo-Material

Gehört zum [Demo-Stack](../README.md#demo-instanz-zum-zeigenTesten)
(`scripts/demo-up.sh`, Port 8181, Login `test`/`test`).

## Was der Demo-Stack automatisch anlegt

Beim allerersten Start (`SEED_DEMO_DATA=true`, nur im Demo-Stack aktiv,
siehe `backend/app/seed_demo.py`) wird die leere Datenbank mit einer
realistischen ~6-Monats-Historie befüllt:

- **5 Konten**: Girokonto, Tagesgeld, Bargeld, ein Depot (alle privat) und ein
  gemeinsames Konto, das als **Haushaltskonto** markiert ist – damit lässt
  sich der Dashboard-Umschalter „Gemeinsam / Persönlich / Gesamt“ (v1.4)
  direkt vorführen
- **2 Nutzer**: `test` (Eigentümer aller Konten) und `partner`/`partner123`
  (Leser auf dem gemeinsamen Konto) – zum Vorführen des Rollenmodells (4.1).
  Meldet man sich als `partner` an, gibt es keinen Bereichs-Umschalter,
  sondern nur den gemeinsamen Haushalt zu sehen.
- **~150 Buchungen**: Gehalt, Miete, Nebenkosten, Abos, Lebensmittel,
  Tanken, Restaurant, u.v.m.
- Eine **automatisch erkannte Umbuchung** (Giro ↔ Tagesgeld, per IBAN) und
  eine **offene Umbuchungs-Vorschlag** (Bargeldabhebung) zum Live-Bestätigen
- Ein **Split-Beispiel**, ein **Tag** ("Urlaub 2026"), ein **Budget**
  (Lebensmittel), eine **wiederkehrende Kostenposition** (Netflix – bewusst
  noch nicht verknüpft, zum Live-Vorführen von „Erkennung ausführen")
- Die Kategorie **„Kapitalerträge"** ist als **„wie Umbuchung behandeln"**
  markiert und hat das **Depot als Umbuchungs-Zielkonto** hinterlegt (v1.3b):
  Sparplan-Ausführungen bekommen automatisch eine Gegenbuchung im Depot,
  dessen Saldo dadurch tatsächlich mitwächst. Die jüngste Ausführung ist
  bewusst noch nicht gegengebucht – Button **„Umbuchungen erkennen"** in der
  Buchungsliste klicken, um live zu sehen, wie sich der Depot-Saldo erhöht.
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
