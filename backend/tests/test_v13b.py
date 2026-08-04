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
        "date_from": "2026-07-01", "date_to": "2026-07-31", "account_id": giro["id"]}).json()
    # nur die normale Ausgabe zählt als Ausgabe, nicht die Sparplan-Buchung
    assert s["expenses"] == 30.0
    # dafür zählt sie als Sparkonten-Bewegung
    july = next(m for m in s["savings_movement"] if m["month"] == "2026-07")
    assert july["value"] == -100.0
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
                           "account_id": giro["id"]}).json()
    idx = sr["months"].index("2026-07")
    assert sr["expenses"][idx] == 0.0  # Sparplan-Buchung nicht als Ausgabe

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
