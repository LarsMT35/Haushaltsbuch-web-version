"""Tests v1.1: Splitbuchungen, Tags, Budgets mit Ampel, Dashboard-Erweiterungen."""


def _setup_account(client, h, name="V11-Konto"):
    r = client.post("/api/v1/accounts", headers=h, json={
        "name": name, "type": "giro", "opening_balance": "100.00",
        "opening_balance_date": "2026-01-01"})
    return r.json()


def _cats(client, h):
    return {c["name"]: c for c in client.get("/api/v1/categories", headers=h).json()}


def test_splits(client, auth_headers):
    h = auth_headers
    acc = _setup_account(client, h, "Split-Konto")
    cats = _cats(client, h)
    r = client.post("/api/v1/transactions", headers=h, json={
        "account_id": acc["id"], "booking_date": "2026-07-05", "amount": "-50.00",
        "counterparty": "Supermarkt", "purpose": "Wocheneinkauf"})
    tx = r.json()

    # Summe muss stimmen
    r = client.put(f"/api/v1/transactions/{tx['id']}/splits", headers=h, json=[
        {"category_id": cats["Lebensmittel"]["id"], "amount": "-30.00"},
        {"category_id": cats["Drogerie"]["id"], "amount": "-15.00"}])
    assert r.status_code == 400

    r = client.put(f"/api/v1/transactions/{tx['id']}/splits", headers=h, json=[
        {"category_id": cats["Lebensmittel"]["id"], "amount": "-30.00"},
        {"category_id": cats["Drogerie"]["id"], "amount": "-20.00"}])
    assert r.status_code == 200
    assert len(r.json()["splits"]) == 2

    # Dashboard: Split zählt anteilig auf beide Kategorien
    s = client.get("/api/v1/dashboard/summary", headers=h,
                   params={"date_from": "2026-07-01", "date_to": "2026-07-31",
                           "account_ids": [acc["id"]]}).json()
    by_cat = {c["category_name"]: c["value"] for c in s["by_category"]}
    assert by_cat["Lebensmittel"] == 30.0
    assert by_cat["Drogerie"] == 20.0
    # gesplittete Buchung gilt als zugeordnet
    assert s["unassigned_count"] == 0

    # Split entfernen
    r = client.put(f"/api/v1/transactions/{tx['id']}/splits", headers=h, json=[])
    assert r.json()["splits"] == []


def test_tags(client, auth_headers):
    h = auth_headers
    acc = _setup_account(client, h, "Tag-Konto")
    r = client.post("/api/v1/transactions", headers=h, json={
        "account_id": acc["id"], "booking_date": "2026-06-01", "amount": "-99.00",
        "counterparty": "Hotel", "purpose": "Übernachtung"})
    tx = r.json()

    r = client.put(f"/api/v1/transactions/{tx['id']}/tags", headers=h,
                   json=["Urlaub Norwegen 2026", "Familie"])
    assert r.status_code == 200
    assert sorted(t["name"] for t in r.json()["tags"]) == ["Familie", "Urlaub Norwegen 2026"]

    # Filter nach Tag
    r = client.get("/api/v1/transactions", headers=h, params={"tag": "Urlaub Norwegen 2026"})
    assert r.json()["total"] == 1
    r = client.get("/api/v1/transactions/tags", headers=h)
    assert "Familie" in [t["name"] for t in r.json()]


def test_budget_ampel(client, auth_headers):
    h = auth_headers
    acc = _setup_account(client, h, "Budget-Konto")
    cats = _cats(client, h)

    # Budget 100 € ab Juni; Ausgaben Juli: 85 € → gelb (80–97 %)
    r = client.post("/api/v1/budgets", headers=h, json={
        "category_id": cats["Restaurant & Lieferdienst"]["id"], "amount": "100.00",
        "valid_from": "2026-06-01"})
    assert r.status_code == 200
    client.post("/api/v1/transactions", headers=h, json={
        "account_id": acc["id"], "booking_date": "2026-07-10", "amount": "-85.00",
        "counterparty": "Pizzeria", "category_id": cats["Restaurant & Lieferdienst"]["id"]})

    s = client.get("/api/v1/budgets/status", headers=h, params={"month": "2026-07", "account_id": acc["id"]}).json()
    row = next(r for r in s["rows"] if r["category_name"] == "Restaurant & Lieferdienst")
    assert row["spent"] == 85.0 and row["ampel"] == "gelb"

    # Budget-Versionierung: Erhöhung ab August ändert Juli nicht (4.8)
    client.post("/api/v1/budgets", headers=h, json={
        "category_id": cats["Restaurant & Lieferdienst"]["id"], "amount": "200.00",
        "valid_from": "2026-08-01"})
    s7 = client.get("/api/v1/budgets/status", headers=h, params={"month": "2026-07", "account_id": acc["id"]}).json()
    s8 = client.get("/api/v1/budgets/status", headers=h, params={"month": "2026-08", "account_id": acc["id"]}).json()
    get = lambda s: next(r for r in s["rows"] if r["category_name"] == "Restaurant & Lieferdienst")
    assert get(s7)["budget"] == 100.0
    assert get(s8)["budget"] == 200.0 and get(s8)["ampel"] == "gruen"

    # Schwellwerte konfigurierbar (Admin)
    r = client.put("/api/v1/budgets/thresholds", headers=h,
                   json={"green_below": 50, "red_from": 84})
    assert r.status_code == 200
    s = client.get("/api/v1/budgets/status", headers=h, params={"month": "2026-07", "account_id": acc["id"]}).json()
    assert get(s)["ampel"] == "rot"
    client.put("/api/v1/budgets/thresholds", headers=h, json={"green_below": 80, "red_from": 98})


def test_dashboard_extensions(client, auth_headers):
    h = auth_headers
    r = client.get("/api/v1/dashboard/networth", headers=h,
                   params={"date_from": "2026-01-01", "date_to": "2026-07-31"})
    nw = r.json()
    assert nw["months"][0] == "2026-01" and nw["months"][-1] == "2026-07"
    assert len(nw["total"]) == len(nw["months"])
    assert all(len(s["values"]) == len(nw["months"]) for s in nw["series"])

    r = client.get("/api/v1/dashboard/savings-rate", headers=h,
                   params={"date_from": "2026-01-01", "date_to": "2026-07-31"})
    sr = r.json()
    assert len(sr["rate"]) == 7

    r = client.get("/api/v1/dashboard/year-comparison", headers=h)
    yc = r.json()
    assert 2026 in yc["years"]
    assert all(len(row["values"]) == len(yc["years"]) for row in yc["rows"])


def test_dashboard_layout(client, auth_headers):
    h = auth_headers
    tiles = [{"id": "income", "visible": True}, {"id": "networth", "visible": False}]
    r = client.put("/api/v1/dashboard/layout", headers=h, json={"tiles": tiles})
    assert r.status_code == 200
    r = client.get("/api/v1/dashboard/layout", headers=h)
    assert r.json()["tiles"] == tiles
