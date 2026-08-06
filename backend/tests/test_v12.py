"""Tests v1.2: wiederkehrende Kostenpositionen, Vorfinanzierungs-Abgleich,
Saldo-Abgleich gegen Bank, Einzahlungstransparenz."""
from decimal import Decimal


def _account(client, h, name, **kw):
    payload = {"name": name, "type": kw.pop("type", "giro"), **kw}
    return client.post("/api/v1/accounts", headers=h, json=payload).json()


def _tx(client, h, account_id, booking_date, amount, counterparty="", purpose="", balance=None):
    r = client.post("/api/v1/transactions", headers=h, json={
        "account_id": account_id, "booking_date": booking_date, "amount": str(amount),
        "counterparty": counterparty, "purpose": purpose})
    return r.json()


def test_recurring_item_basic_detection_and_status(client, auth_headers):
    h = auth_headers
    giro = _account(client, h, "V12-Giro", opening_balance="1000.00", opening_balance_date="2025-01-01")

    # 3 jährliche ADAC-Abbuchungen simulieren (manuell, um Zyklus zu testen)
    _tx(client, h, giro["id"], "2024-03-01", "-54.00", "ADAC e.V.", "Mitgliedsbeitrag")
    _tx(client, h, giro["id"], "2025-03-01", "-54.00", "ADAC e.V.", "Mitgliedsbeitrag")
    _tx(client, h, giro["id"], "2026-03-01", "-59.00", "ADAC e.V.", "Mitgliedsbeitrag")

    r = client.post("/api/v1/recurring-items", headers=h, json={
        "name": "ADAC", "cycle_months": 12, "expected_amount": "54.00",
        "paying_account_id": giro["id"], "match_text": "ADAC"})
    assert r.status_code == 200
    item = r.json()
    assert item["match_text"] == "ADAC"

    r = client.post(f"/api/v1/recurring-items/{item['id']}/detect", headers=h)
    assert r.json()["charges_linked"] == 3

    # erneutes Detect verknüpft nichts doppelt
    r = client.post(f"/api/v1/recurring-items/{item['id']}/detect", headers=h)
    assert r.json()["charges_linked"] == 0

    r = client.get(f"/api/v1/recurring-items/{item['id']}/links", headers=h)
    links = r.json()
    assert len(links) == 3
    assert all(link["role"] == "charge" for link in links)

    r = client.get("/api/v1/recurring-items/status", headers=h)
    row = next(row for row in r.json()["rows"] if row["name"] == "ADAC")
    assert row["last_charge_date"] == "2026-03-01"
    assert row["last_charge_amount"] == 59.0
    assert row["is_prefinanced"] is False
    assert row["next_due_estimate"] == "2027-03-01"
    assert row["suggested_rate"] == 59.0 / 12
    # nicht vorfinanziert -> kein Soll/Ist-Vergleich, aber trotzdem grün
    assert row["soll"] is None and row["ampel"] == "gruen"


def test_recurring_item_manual_link_and_unlink(client, auth_headers):
    h = auth_headers
    giro = _account(client, h, "V12-Giro2")
    tx = _tx(client, h, giro["id"], "2026-01-15", "-19.99", "Streaminganbieter", "Abo")

    r = client.post("/api/v1/recurring-items", headers=h, json={
        "name": "Streaming-Abo", "cycle_months": 1, "expected_amount": "19.99",
        "paying_account_id": giro["id"]})  # kein match_text -> keine Automatik
    item = r.json()

    r = client.post(f"/api/v1/recurring-items/{item['id']}/detect", headers=h)
    assert r.json()["charges_linked"] == 0  # ohne match_text kein Auto-Match

    # manuelle Verknüpfung als Rückfallebene (Machbarkeitshinweis 4.7)
    r = client.post(f"/api/v1/recurring-items/{item['id']}/links", headers=h,
                    json={"transaction_id": tx["id"], "role": "charge"})
    assert r.status_code == 200
    link_id = r.json()["id"]
    assert r.json()["is_auto"] is False

    # doppelte Verknüpfung derselben Rolle abgelehnt
    r = client.post(f"/api/v1/recurring-items/{item['id']}/links", headers=h,
                    json={"transaction_id": tx["id"], "role": "charge"})
    assert r.status_code == 409

    r = client.delete(f"/api/v1/recurring-items/links/{link_id}", headers=h)
    assert r.status_code == 200
    r = client.get(f"/api/v1/recurring-items/{item['id']}/links", headers=h)
    assert r.json() == []


def test_prefinance_abgleich(client, auth_headers):
    """Vorfinanzierungs-Abgleich (4.7 b): Soll = Summe Erstattungen seit
    letzter Abbuchung, Ist = tatsächliche neue Abbuchung."""
    h = auth_headers
    persoenlich = _account(client, h, "V12-Persoenlich")
    gemeinsam = _account(client, h, "V12-Gemeinsam")

    r = client.post("/api/v1/recurring-items", headers=h, json={
        "name": "Rundfunkbeitrag", "cycle_months": 3, "expected_amount": "55.08",
        "paying_account_id": persoenlich["id"], "match_text": "Rundfunk",
        "reimbursement_account_id": gemeinsam["id"], "reimbursement_match_text": "Erstattung Rundfunk"})
    item = r.json()

    # Vorherige Abbuchung (Referenzpunkt), dann 3 monatliche Erstattungen, dann neue Abbuchung
    _tx(client, h, persoenlich["id"], "2026-01-05", "-55.08", "Rundfunk Beitragsservice")
    _tx(client, h, gemeinsam["id"], "2026-02-01", "-18.36", "Max Mustermann", "Erstattung Rundfunk")
    _tx(client, h, gemeinsam["id"], "2026-03-01", "-18.36", "Max Mustermann", "Erstattung Rundfunk")
    _tx(client, h, gemeinsam["id"], "2026-04-01", "-18.36", "Max Mustermann", "Erstattung Rundfunk")
    _tx(client, h, persoenlich["id"], "2026-04-05", "-58.00", "Rundfunk Beitragsservice")  # Erhöhung

    r = client.post(f"/api/v1/recurring-items/{item['id']}/detect", headers=h)
    body = r.json()
    assert body["charges_linked"] == 2
    assert body["reimbursements_linked"] == 3

    r = client.get("/api/v1/recurring-items/status", headers=h)
    row = next(row for row in r.json()["rows"] if row["name"] == "Rundfunkbeitrag")
    assert row["is_prefinanced"] is True
    assert row["ist"] == 58.0
    assert row["soll"] == round(18.36 * 3, 2)
    assert row["deviation"] is not None and row["deviation"] > 0
    # Abweichung (58 vs 55.08) < 20% -> nicht rot, aber > 5% -> nicht grün
    assert row["ampel"] == "gelb"

    # Rate manuell anpassen (Empfehlung aus 4.7 b: Rate rechtzeitig anpassen)
    # (Frontend rundet auf Cent, bevor es an die API schickt)
    r = client.put(f"/api/v1/recurring-items/{item['id']}", headers=h,
                   json={"current_rate": str(round(row["suggested_rate"], 2))})
    assert r.status_code == 200
    assert Decimal(r.json()["current_rate"]) == Decimal(str(round(58.0 / 3, 2)))


def test_balance_check(client, auth_headers):
    h = auth_headers
    acc = _account(client, h, "Saldo-Konto", opening_balance="100.00", opening_balance_date="2026-01-01")

    # Bank-Saldo aus Import: bank_balance wird beim Commit gesetzt, nicht über
    # die manuelle Buchungs-API - wir simulieren daher direkt per Import-Commit.
    r = client.get("/api/v1/imports/profiles", headers=h)
    profiles = {p["name"]: p for p in r.json()}
    spk = next(p for n, p in profiles.items() if "Sparkasse" in n)

    rows = [
        {"row_number": 1, "booking_date": "2026-02-01", "value_date": "2026-02-01",
         "amount": "50.00", "currency": "EUR", "counterparty": "Gehalt", "counterparty_iban": "",
         "purpose": "Gehalt", "booking_text": "", "account_iban": "", "balance": "150.00",
         "raw_line": "x", "dedup_hash": "h1", "include": True},
        {"row_number": 2, "booking_date": "2026-02-05", "value_date": "2026-02-05",
         "amount": "-20.00", "currency": "EUR", "counterparty": "Shop", "counterparty_iban": "",
         "purpose": "Einkauf", "booking_text": "", "account_iban": "",
         # absichtlich falscher Bank-Saldo -> simuliert eine Import-Lücke
         "balance": "100.00",
         "raw_line": "y", "dedup_hash": "h2", "include": True},
    ]
    r = client.post("/api/v1/imports/commit", headers=h, json={
        "profile_id": spk["id"], "account_id": acc["id"], "filename": "test.csv", "rows": rows})
    assert r.status_code == 200

    r = client.get(f"/api/v1/accounts/{acc['id']}/balance-check", headers=h)
    body = r.json()
    assert body["checked_count"] == 2
    # erste Zeile stimmt (100 + 50 = 150), zweite weicht ab (130 berechnet vs 100 gemeldet)
    assert len(body["rows"]) == 1
    assert body["rows"][0]["computed_balance"] == 130.0
    assert body["rows"][0]["bank_balance"] == 100.0
    assert round(body["rows"][0]["deviation"], 2) == 30.0


def test_deposits_transparency(client, auth_headers):
    h = auth_headers
    gemeinsam = _account(client, h, "Deposits-Gemeinsam")
    _tx(client, h, gemeinsam["id"], "2026-05-01", "300.00", "Person A", "Einzahlung")
    _tx(client, h, gemeinsam["id"], "2026-05-03", "250.00", "Person B", "Einzahlung")
    _tx(client, h, gemeinsam["id"], "2026-06-01", "300.00", "Person A", "Einzahlung")
    _tx(client, h, gemeinsam["id"], "2026-05-10", "-40.00", "Supermarkt")  # Ausgabe, zählt nicht

    r = client.get("/api/v1/dashboard/deposits", headers=h, params={
        "account_ids": [gemeinsam["id"]], "date_from": "2026-05-01", "date_to": "2026-06-30"})
    body = r.json()
    assert set(body["depositors"]) == {"Person A", "Person B"}
    may = next(s for s in body["series"] if s["month"] == "2026-05")
    assert may["values"]["Person A"] == 300.0
    assert may["values"]["Person B"] == 250.0
    june = next(s for s in body["series"] if s["month"] == "2026-06")
    assert june["values"]["Person A"] == 300.0
