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
- Ein **Split-Beispiel**, ein **Tag** ("Urlaub 2026")
- **6 Budgets** über alle drei Ampelfarben verteilt (der Nebenkosten-Abschlag
  liegt bewusst über Budget) – für die Kachel *Budget-Fortschritt*
- **5 wiederkehrende Kostenpositionen**; vier davon verknüpft, damit die
  Kachel *Fällig in den nächsten 30 Tagen* echte Termine zeigt. Netflix
  bleibt bewusst unverknüpft, um „Erkennung ausführen" live vorzuführen.
- Die Kategorie **„Kapitalerträge"** ist als **„wie Umbuchung behandeln"**
  markiert und hat das **Depot als Umbuchungs-Zielkonto** hinterlegt (v1.3b):
  Sparplan-Ausführungen bekommen automatisch eine Gegenbuchung im Depot,
  dessen Saldo dadurch tatsächlich mitwächst. Die jüngste Ausführung ist
  bewusst noch nicht gegengebucht – Button **„Umbuchungen erkennen"** in der
  Buchungsliste klicken, um live zu sehen, wie Depot-Saldo *und* Sparquote
  des Monats nach oben springen.
- **Monatliche Umbuchung aufs Tagesgeld (300 €), in jedem zweiten Monat 80 €
  zurück aufs Giro** – zeigt, dass die Sparquote netto rechnet (v1.5.2) und
  nicht jeden nicht ausgegebenen Euro als gespart zählt
- **Über 40 Kategorisierungsregeln** – genug, damit die **Freitextsuche** in
  der Regelansicht (v1.5) ihren Zweck zeigt: „Lebensmittel" findet alle
  Supermarkt-Regeln, ohne dass man die Händlernamen kennt
- **4 unzugeordnete Buchungen** (zeigt die „Handlungsbedarf"-Kachel)

## `beispiel_import_sparkasse.csv`

15 weitere, noch nicht importierte Umsätze im Sparkasse-CSV-Format für das
Demo-Girokonto – zum Live-Vorführen des Import-Ablaufs (Vorschau,
automatische Zielkonto-Erkennung per IBAN, Kategorie-Vorschläge über die
vorhandenen Regeln, Übernehmen).

**Vorführen:** Import → Datei hierher ziehen → Profil „Sparkasse" wählen →
Vorschau (Zielkonto wird automatisch erkannt, mehrere Zeilen bekommen schon
eine Kategorie vorgeschlagen) → Übernehmen.

## Demodaten erneuern

Das Seed-Skript läuft **nur in eine leere Datenbank** und ist ansonsten
idempotent – ein bestehender Demo-Stack bekommt neue Inhalte also nicht
automatisch. Nach einem Update mit erweiterten Demodaten:

```bash
scripts/demo-down.sh --reset   # stoppt und löscht die Demo-Datenbank
scripts/demo-up.sh             # baut neu und befüllt frisch
```

Die produktive Installation ist davon nicht berührt: der Demo-Stack hat eine
eigene Datenbank, ein eigenes Volume und einen eigenen Compose-Projektnamen.

## Kurzer Rundgang zum Vorführen

1. **Startseite** – oben zwischen *Gemeinsam / Persönlich / Gesamt* wechseln;
   jeder Bereich hat eigene Kacheln und ein eigenes Layout.
2. **Handlungsbedarf** – vier unzugeordnete Buchungen, „Jetzt zuordnen".
3. **Umbuchungen erkennen** (Buchungen) – legt die fehlende Depot-Gegenbuchung
   an; Depot-Saldo und Sparquote des Monats steigen sichtbar.
4. **Mögliche Umbuchungen** – die Bargeldabhebung als Vorschlag bestätigen.
5. **Budgets** – auf der Startseite die Ampel von grün bis rot.
6. **Regeln** – „Lebensmittel" ins Suchfeld: findet alle Supermarkt-Regeln.
7. **Wiederkehrend** – „Erkennung ausführen" verknüpft Netflix nachträglich.
8. **Import** – die Beispiel-CSV wie oben beschrieben einspielen.
