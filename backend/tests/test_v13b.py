"""Tests: Kategorie-Flag 'is_transfer_like' – Buchungen zählen wie eine
Umbuchung, auch ohne verknüpfte Gegenbuchung (z.B. Sparplan ohne Depot-Konto)."""
from datetime import date


def _account(client, h, name, **kw):
    return client.post("/api/v1/accounts", headers=h, json={"name": name, "type": kw.pop("type", "giro"), **kw}).json()


def test_transfer_like_category_excluded_from_income_expense(client, auth_headers):
    h = auth_headers
    giro = _account(client, h, "V13b-Giro")

    r = client.post("/api/v1/categories", headers=h, json={
        "name": "V13b-Aktien", "scope": "personal", "is_transfer_like": True})
    assert r.status_code == 200
    cat = r.json()
    assert cat["is_transfer_like"] is True

    client.post("/api/v1/transactions", headers=h, json={
        "account_id": giro["id"], "booking_date": "2026-07-10", "amount": "-100.00",
        "counterparty": "Broker", "purpose": "Sparplan ETF", "category_id": cat["id"]})
    # normale Ausgabe zum Vergleich
    client.post("/api/v1/transactions", headers=h, json={
        "account_id": giro["id"], "booking_date": "2026-07-11", "amount": "-30.00",
        "counterparty": "Supermarkt", "purpose": "Einkauf"})

    s = client.get("/api/v1/dashboard/summary", headers=h, params={
        "date_from": "2026-07-01", "date_to": "2026-07-31", "account_ids": [giro["id"]]}).json()
    # nur die normale Ausgabe zählt als Ausgabe, nicht die Sparplan-Buchung
    assert s["expenses"] == 30.0
    # dafür zählt sie als Sparkonten-Bewegung – und zwar POSITIV: 100 EUR in
    # einen Sparplan sind 100 EUR gespart. Der Betrag der Buchung ist negativ
    # (das Geld verlässt das Girokonto), die Bedeutung ist die umgekehrte.
    # Bis v1.8 stand hier -100: die Kennzahlen-Kachel drehte das Vorzeichen
    # nicht, die Sparquote schon – dieselbe Buchung erschien in zwei Kacheln
    # mit entgegengesetztem Vorzeichen (siehe savings_delta).
    july = next(m for m in s["savings_movement"] if m["month"] == "2026-07")
    assert july["value"] == 100.0
    # und taucht NICHT in "Ausgaben nach Kategorie" auf
    assert not any(c["category_name"] == "V13b-Aktien" for c in s["by_category"])


def test_transfer_like_category_still_affects_balance(client, auth_headers):
    h = auth_headers
    giro = _account(client, h, "V13b-Giro2", opening_balance="500.00", opening_balance_date="2026-01-01")
    cat = client.post("/api/v1/categories", headers=h, json={
        "name": "V13b-Aktien2", "scope": "personal", "is_transfer_like": True}).json()

    client.post("/api/v1/transactions", headers=h, json={
        "account_id": giro["id"], "booking_date": "2026-07-10", "amount": "-100.00",
        "counterparty": "Broker", "purpose": "Sparplan", "category_id": cat["id"]})

    accounts = client.get("/api/v1/accounts", headers=h).json()
    acc = next(a for a in accounts if a["id"] == giro["id"])
    assert float(acc["balance"]) == 400.0  # Saldo ist trotzdem korrekt reduziert


def test_transfer_like_category_excluded_from_budget(client, auth_headers):
    h = auth_headers
    giro = _account(client, h, "V13b-Giro3")
    cat = client.post("/api/v1/categories", headers=h, json={
        "name": "V13b-Aktien3", "scope": "personal", "is_transfer_like": True}).json()
    client.post("/api/v1/budgets", headers=h, json={
        "category_id": cat["id"], "amount": "50.00", "valid_from": "2026-01-01"})
    client.post("/api/v1/transactions", headers=h, json={
        "account_id": giro["id"], "booking_date": "2026-07-10", "amount": "-100.00",
        "counterparty": "Broker", "purpose": "Sparplan", "category_id": cat["id"]})

    status = client.get("/api/v1/budgets/status", headers=h, params={"month": "2026-07"}).json()
    row = next((r for r in status["rows"] if r["category_name"] == "V13b-Aktien3"), None)
    assert row is not None
    assert row["spent"] == 0.0  # zählt nicht als Budget-Verbrauch


def test_transfer_like_category_excluded_from_savings_rate_and_year_comparison(client, auth_headers):
    h = auth_headers
    giro = _account(client, h, "V13b-Giro4")
    cat = client.post("/api/v1/categories", headers=h, json={
        "name": "V13b-Aktien4", "scope": "personal", "is_transfer_like": True}).json()
    client.post("/api/v1/transactions", headers=h, json={
        "account_id": giro["id"], "booking_date": "2026-07-10", "amount": "-100.00",
        "counterparty": "Broker", "purpose": "Sparplan", "category_id": cat["id"]})
    client.post("/api/v1/transactions", headers=h, json={
        "account_id": giro["id"], "booking_date": "2026-07-15", "amount": "2000.00",
        "counterparty": "Arbeitgeber", "purpose": "Gehalt"})

    sr = client.get("/api/v1/dashboard/savings-rate", headers=h,
                    params={"date_from": "2026-07-01", "date_to": "2026-07-31",
                           "account_ids": [giro["id"]]}).json()
    idx = sr["months"].index("2026-07")
    assert sr["expenses"][idx] == 0.0  # Sparplan-Buchung nicht als Ausgabe
    # ohne mitgeführtes Zielkonto IST die Abbuchung der Sparbetrag – sie zählt
    # deshalb positiv in die Sparquote, nicht negativ
    assert sr["saved"][idx] == 100.0
    assert sr["rate"][idx] == 5.0  # 100 von 2000 Einnahmen

    yc = client.get("/api/v1/dashboard/year-comparison", headers=h).json()
    assert not any(row["category_name"] == "V13b-Aktien4" for row in yc["rows"])


def test_category_export_import_preserves_transfer_like_flag(client, auth_headers):
    h = auth_headers
    client.post("/api/v1/categories", headers=h, json={
        "name": "V13b-ExportTest", "scope": "personal", "is_transfer_like": True})

    exported = client.get("/api/v1/categories/export", headers=h).json()
    item = next(c for c in exported if c["name"] == "V13b-ExportTest")
    assert item["is_transfer_like"] is True

    # Flag ändern und re-importieren -> wird synchronisiert
    item["is_transfer_like"] = False
    r = client.post("/api/v1/categories/import", headers=h, json=[item])
    assert r.json()["updated_fixed_cost"] == 1

    cats = client.get("/api/v1/categories", headers=h).json()
    cat = next(c for c in cats if c["name"] == "V13b-ExportTest")
    assert cat["is_transfer_like"] is False


def test_category_export_import_preserves_transfer_target_account(client, auth_headers):
    """Export referenziert das Zielkonto per Name (Prinzip 1, portabel
    zwischen Installationen), Import löst es beim Einspielen wieder auf."""
    h = auth_headers
    depot = _account(client, h, "V13b-ExportDepot", type="depot")
    cat = client.post("/api/v1/categories", headers=h, json={
        "name": "V13b-ExportSparplan", "scope": "personal",
        "transfer_target_account_id": depot["id"]}).json()

    exported = client.get("/api/v1/categories/export", headers=h).json()
    item = next(c for c in exported if c["name"] == "V13b-ExportSparplan")
    assert item["transfer_target_account_name"] == "V13b-ExportDepot"

    # auf einer "frischen" Installation ohne dieses Konto einspielen ->
    # Kategorie wird trotzdem angelegt, nur ohne Zielkonto-Verknüpfung
    item["name"] = "V13b-ExportSparplan-2"
    item["transfer_target_account_name"] = "Unbekanntes Konto"
    r = client.post("/api/v1/categories/import", headers=h, json=[item])
    assert r.json()["created"] == 1
    cats = client.get("/api/v1/categories", headers=h).json()
    cat2 = next(c for c in cats if c["name"] == "V13b-ExportSparplan-2")
    assert cat2["transfer_target_account_id"] is None
    assert cat2["is_transfer_like"] is True  # Flag selbst bleibt erhalten


def test_dashboard_summary_multi_account_and_category_filter(client, auth_headers):
    """Mehrere Konten UND mehrere Kategorien gleichzeitig auswählbar (Startseite-Filter)."""
    h = auth_headers
    a1 = _account(client, h, "V13b-Multi-A")
    a2 = _account(client, h, "V13b-Multi-B")
    a3 = _account(client, h, "V13b-Multi-C")
    cats = {c["name"]: c for c in client.get("/api/v1/categories", headers=h).json()}
    lebensmittel = cats["Lebensmittel"]["id"]
    drogerie = cats["Drogerie"]["id"]
    elektronik = cats["Elektronik"]["id"]

    for acc, cat_id, amount in [
        (a1, lebensmittel, "-10.00"), (a2, drogerie, "-20.00"),
        (a3, elektronik, "-40.00"), (a1, elektronik, "-5.00"),
    ]:
        client.post("/api/v1/transactions", headers=h, json={
            "account_id": acc["id"], "booking_date": "2026-07-10", "amount": amount,
            "counterparty": "Test", "category_id": cat_id})

    # nur A1+A2, nur Lebensmittel+Drogerie -> A3 und Elektronik-Buchung auf A1 raus
    s = client.get("/api/v1/dashboard/summary", headers=h, params={
        "date_from": "2026-07-01", "date_to": "2026-07-31",
        "account_ids": [a1["id"], a2["id"]], "category_ids": [lebensmittel, drogerie]}).json()
    assert round(s["expenses"], 2) == 30.0
    names = {c["category_name"] for c in s["by_category"]}
    assert names == {"Lebensmittel", "Drogerie"}


def test_dashboard_networth_and_year_comparison_multi_account_filter(client, auth_headers):
    h = auth_headers
    a1 = _account(client, h, "V13b-NW-A", opening_balance="100.00", opening_balance_date="2026-01-01")
    a2 = _account(client, h, "V13b-NW-B", opening_balance="200.00", opening_balance_date="2026-01-01")

    nw_all = client.get("/api/v1/dashboard/networth", headers=h,
                        params={"date_from": "2026-01-01", "date_to": "2026-01-31"}).json()
    names_all = {s["name"] for s in nw_all["series"]}
    assert "V13b-NW-A" in names_all and "V13b-NW-B" in names_all

    nw_filtered = client.get("/api/v1/dashboard/networth", headers=h,
                             params={"date_from": "2026-01-01", "date_to": "2026-01-31",
                                    "account_ids": [a1["id"]]}).json()
    names_filtered = {s["name"] for s in nw_filtered["series"]}
    assert names_filtered == {"V13b-NW-A"}


def test_transfers_detect_endpoint_manual_trigger(client, auth_headers):
    """'Umbuchungen erkennen'-Button in der Buchungsliste (4.4): POST
    /transfers/detect verknüpft auch Gegenbuchungen, die (z.B. aus
    Altbeständen) ohne den Auto-Link-Hook der Buchungserstellung entstanden
    sind – nicht nur implizit nach Import/manueller Buchung."""
    from app.db import SessionLocal
    from app.models import Transaction

    # Ungewöhnlicher Betrag, damit die (session-weite, geteilte) Test-DB keine
    # zufällig gleich hohe Gegenbuchung aus einem anderen Test beisteuert.
    AMOUNT = "733.19"

    h = auth_headers
    giro = client.post("/api/v1/accounts", headers=h, json={
        "name": "V13b-Detect-Giro", "type": "giro", "iban": "DE00TESTDETECTGIRO0001"}).json()
    tagesgeld = client.post("/api/v1/accounts", headers=h, json={
        "name": "V13b-Detect-Tagesgeld", "type": "tagesgeld", "iban": "DE00TESTDETECTTG00002"}).json()

    # Direkt in der DB anlegen (am Auto-Link-Hook von POST /transactions vorbei),
    # um den Fall "noch unverknüpfte Gegenbuchung" zu simulieren.
    with SessionLocal() as db:
        db.add(Transaction(account_id=giro["id"], booking_date=date(2026, 7, 5),
                           amount=f"-{AMOUNT}", amount_ref=f"-{AMOUNT}", counterparty="Tagesgeld",
                           counterparty_iban=tagesgeld["iban"], purpose="Uebertrag", is_manual=True))
        db.add(Transaction(account_id=tagesgeld["id"], booking_date=date(2026, 7, 6),
                           amount=AMOUNT, amount_ref=AMOUNT, counterparty="Girokonto",
                           counterparty_iban=giro["iban"], purpose="Uebertrag", is_manual=True))
        db.commit()

    before = client.get("/api/v1/transactions", headers=h,
                        params={"account_id": giro["id"]}).json()["items"]
    assert all(t["transfer_id"] is None for t in before)

    r = client.post("/api/v1/transfers/detect", headers=h)
    assert r.status_code == 200
    assert r.json()["linked"] == 1

    after = client.get("/api/v1/transactions", headers=h,
                       params={"account_id": giro["id"]}).json()["items"]
    tx = next(t for t in after if t["purpose"] == "Uebertrag")
    assert tx["transfer_id"] is not None

    # erneuter Aufruf: bereits verknüpftes Paar wird nicht doppelt gezählt (idempotent)
    r = client.post("/api/v1/transfers/detect", headers=h)
    assert r.json()["linked"] == 0


def test_transfer_target_account_creates_real_mirror_booking(client, auth_headers):
    """v1.3b: Kategorie mit hinterlegtem Umbuchungs-Zielkonto (z.B. Depot ohne
    eigenen Bank-Feed) erzeugt eine echte Gegenbuchung dort, der Saldo des
    Zielkontos passt sich an, und die Sparkonten-Bewegung zählt nicht mehr
    doppelt (zahlende + Depot-Seite)."""
    h = auth_headers
    giro = _account(client, h, "V13b-Mirror-Giro")
    depot = _account(client, h, "V13b-Mirror-Depot", type="depot")

    cat = client.post("/api/v1/categories", headers=h, json={
        "name": "V13b-Sparplan", "scope": "personal",
        "transfer_target_account_id": depot["id"]}).json()
    # ein Zielkonto macht die Kategorie implizit "wie Umbuchung" (ohne extra Flag)
    assert cat["is_transfer_like"] is True
    assert cat["transfer_target_account_id"] == depot["id"]

    # die Gegenbuchung entsteht schon automatisch beim Anlegen der manuellen
    # Buchung (wie bei einer normalen Umbuchung, 4.4) – kein manueller
    # Trigger nötig, genau wie bei auto_link_transfers
    client.post("/api/v1/transactions", headers=h, json={
        "account_id": giro["id"], "booking_date": "2026-07-12", "amount": "-150.00",
        "counterparty": "Broker", "purpose": "Ausführung Sparplan", "category_id": cat["id"]})

    # Saldo des Depots wächst durch die automatische Gegenbuchung mit (4.9)
    accs = client.get("/api/v1/accounts", headers=h).json()
    assert float(next(a for a in accs if a["id"] == depot["id"])["balance"]) == 150.0

    # in der Buchungsliste des Depots taucht die Gegenbuchung real auf und
    # ist als Umbuchung verknüpft
    depot_txs = client.get("/api/v1/transactions", headers=h,
                           params={"account_id": depot["id"]}).json()["items"]
    assert len(depot_txs) == 1
    assert depot_txs[0]["amount"] == "150.00"
    assert depot_txs[0]["transfer_id"] is not None

    # Sparkonten-Bewegung zählt jetzt nur noch einmal (Depot-Seite), nicht
    # mehr zusätzlich die zahlende Giro-Seite gegenläufig dazu
    s = client.get("/api/v1/dashboard/summary", headers=h, params={
        "date_from": "2026-07-01", "date_to": "2026-07-31",
        "account_ids": [giro["id"], depot["id"]]}).json()
    july = next(m for m in s["savings_movement"] if m["month"] == "2026-07")
    assert july["value"] == 150.0

    # manueller Button "Umbuchungen erkennen" bleibt idempotent (relevant für
    # Altbestände oder rückwirkend per Regel gesetzte Kategorien, die keinen
    # Erstellungs-Hook durchlaufen haben) – keine doppelte Gegenbuchung
    r = client.post("/api/v1/transfers/detect", headers=h)
    assert r.json()["mirrored"] == 0
    depot_txs = client.get("/api/v1/transactions", headers=h,
                           params={"account_id": depot["id"]}).json()["items"]
    assert len(depot_txs) == 1


def test_transfer_target_account_backfills_existing_transactions(client, auth_headers):
    """Der eigentlich gemeldete Fall: die Kategorie war schon vorher 'wie
    Umbuchung' auf Altbestand gesetzt, erst danach wird ein Zielkonto
    ergänzt – 'Umbuchungen erkennen' muss die Altbuchungen nachträglich
    ins Depot gegenbuchen, nicht nur künftige."""
    h = auth_headers
    giro = _account(client, h, "V13b-Backfill-Giro")
    depot = _account(client, h, "V13b-Backfill-Depot", type="depot")

    cat = client.post("/api/v1/categories", headers=h, json={
        "name": "V13b-Backfill-Sparplan", "scope": "personal", "is_transfer_like": True}).json()

    for d, amount in [("2026-05-12", "-100.00"), ("2026-06-12", "-120.00"), ("2026-07-12", "-140.00")]:
        client.post("/api/v1/transactions", headers=h, json={
            "account_id": giro["id"], "booking_date": d, "amount": amount,
            "counterparty": "Broker", "purpose": "Sparplan", "category_id": cat["id"]})

    # noch kein Zielkonto -> keine Gegenbuchungen
    assert client.get("/api/v1/transactions", headers=h,
                      params={"account_id": depot["id"]}).json()["total"] == 0

    r = client.put(f"/api/v1/categories/{cat['id']}", headers=h,
                   json={"transfer_target_account_id": depot["id"]})
    assert r.json()["transfer_target_account_id"] == depot["id"]

    r = client.post("/api/v1/transfers/detect", headers=h)
    assert r.json()["mirrored"] == 3

    depot_page = client.get("/api/v1/transactions", headers=h, params={"account_id": depot["id"]}).json()
    assert depot_page["total"] == 3
    accs = client.get("/api/v1/accounts", headers=h).json()
    assert float(next(a for a in accs if a["id"] == depot["id"])["balance"]) == 360.0
