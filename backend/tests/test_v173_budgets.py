"""Tests v1.7.3: Budgets am Abrechnungsmonat und Bearbeiten bestehender Eintraege.

Ein monatliches Budget muss in jeder Periode wieder bei 0 anfangen und dabei
GENAU den Zeitraum zaehlen, den der Abrechnungsmonat umfasst - sonst rutscht
der Verbrauch der letzten Julitage in den falschen Monat.

Der zweite Punkt ist das Bearbeiten: bisher gab es nur Anlegen und Loeschen,
ein Vertipper im Betrag zwang zum Neuanlegen.
"""
import pytest


def _account(client, h, name, **kw):
    return client.post("/api/v1/accounts", headers=h,
                       json={"name": name, "type": "giro", **kw}).json()


def _cat(client, h, name="Lebensmittel"):
    return next(c for c in client.get("/api/v1/categories", headers=h).json()
                if c["name"] == name)


def _book(client, h, acc, d, amount, cat_id):
    return client.post("/api/v1/transactions", headers=h, json={
        "account_id": acc["id"], "booking_date": d, "amount": amount,
        "counterparty": "Laden", "purpose": "x", "category_id": cat_id}).json()


@pytest.fixture
def start_day_27(client, auth_headers):
    client.put("/api/v1/budgets/period", headers=auth_headers, json={"start_day": 27})
    yield 27
    client.put("/api/v1/budgets/period", headers=auth_headers, json={"start_day": 1})


# ------------------------------------------------- Abrechnungsmonat & Reset

def test_budget_counts_billing_period_and_resets(client, auth_headers, start_day_27):
    """Buchungen vom 28.07. und 02.08. gehoeren beide zur August-Periode
    (27.07.-26.08.); der 28.08. beginnt schon die naechste und faengt bei 0 an."""
    h = auth_headers
    giro = _account(client, h, "V173-Giro", opening_balance="0",
                    opening_balance_date="2026-01-01")
    cat = _cat(client, h)
    client.post("/api/v1/budgets", headers=h, json={
        "category_id": cat["id"], "account_id": giro["id"],
        "amount": "400.00", "valid_from": "2026-01-01"})

    _book(client, h, giro, "2026-07-28", "-120.00", cat["id"])
    _book(client, h, giro, "2026-08-02", "-90.00", cat["id"])
    _book(client, h, giro, "2026-08-28", "-50.00", cat["id"])

    def spent(month):
        s = client.get("/api/v1/budgets/status", headers=h,
                       params={"month": month, "account_ids": [giro["id"]]}).json()
        row = next((r for r in s["rows"] if r["category_id"] == cat["id"]), None)
        return s, (row["spent"] if row else 0.0)

    s_aug, aug = spent("2026-08")
    assert (s_aug["date_from"], s_aug["date_to"]) == ("2026-07-27", "2026-08-26")
    assert aug == 210.0                       # 120 + 90, ueber den Monatswechsel hinweg

    s_sep, sep = spent("2026-09")
    assert (s_sep["date_from"], s_sep["date_to"]) == ("2026-08-27", "2026-09-26")
    assert sep == 50.0                        # neue Periode faengt wieder bei 0 an

    _s_jul, jul = spent("2026-07")
    assert jul == 0.0


def test_status_resolves_period_from_a_date(client, auth_headers, start_day_27):
    """Die Oberflaeche soll aus einem Zeitraum keinen Periodenschluessel
    rechnen muessen: der 30.08. gehoert bereits zum September, ein
    Abschneiden auf '2026-08' traefe den falschen Monat."""
    h = auth_headers
    s = client.get("/api/v1/budgets/status", headers=h,
                   params={"date_in_period": "2026-08-30"}).json()
    assert s["month"] == "2026-09"
    assert (s["date_from"], s["date_to"]) == ("2026-08-27", "2026-09-26")

    s = client.get("/api/v1/budgets/status", headers=h,
                   params={"date_in_period": "2026-08-26"}).json()
    assert s["month"] == "2026-08"


def test_status_without_arguments_uses_current_period(client, auth_headers):
    from app.services.periods import current_period
    s = client.get("/api/v1/budgets/status", headers=auth_headers).json()
    assert s["month"] == current_period(1)


# ----------------------------------------------------------- Bearbeiten

def test_budget_can_be_edited(client, auth_headers):
    h = auth_headers
    giro = _account(client, h, "V173-Edit", opening_balance="0",
                    opening_balance_date="2026-01-01")
    cat = _cat(client, h)
    b = client.post("/api/v1/budgets", headers=h, json={
        "category_id": cat["id"], "amount": "40.00", "valid_from": "2026-02-01"}).json()

    r = client.put(f"/api/v1/budgets/{b['id']}", headers=h,
                   json={"amount": "400.00", "account_id": giro["id"]})
    assert r.status_code == 200, r.text
    assert r.json()["amount"] == "400.00"
    assert r.json()["account_id"] == giro["id"]

    # und wirkt sich sofort auf die Auswertung aus
    s = client.get("/api/v1/budgets/status", headers=h,
                   params={"month": "2026-03", "account_ids": [giro["id"]]}).json()
    row = next(r for r in s["rows"] if r["category_id"] == cat["id"])
    assert row["budget"] == 400.0


def test_edit_keeps_versioning_intact(client, auth_headers):
    """Zwei Versionen derselben Kategorie: das Bearbeiten der einen darf die
    andere nicht anfassen - sonst waere die Historie stillschweigend weg."""
    h = auth_headers
    cat = _cat(client, h, "Drogerie")
    alt = client.post("/api/v1/budgets", headers=h, json={
        "category_id": cat["id"], "amount": "50.00", "valid_from": "2026-01-01"}).json()
    neu = client.post("/api/v1/budgets", headers=h, json={
        "category_id": cat["id"], "amount": "80.00", "valid_from": "2026-06-01"}).json()

    client.put(f"/api/v1/budgets/{alt['id']}", headers=h, json={"amount": "55.00"})

    alle = {b["id"]: b for b in client.get("/api/v1/budgets", headers=h).json()}
    assert alle[alt["id"]]["amount"] == "55.00"
    assert alle[neu["id"]]["amount"] == "80.00"      # unveraendert
    assert alle[alt["id"]]["valid_from"] == "2026-01-01"


def test_edit_rejects_invalid_input(client, auth_headers):
    h = auth_headers
    cat = _cat(client, h)
    b = client.post("/api/v1/budgets", headers=h, json={
        "category_id": cat["id"], "amount": "100.00", "valid_from": "2026-01-01"}).json()

    assert client.put(f"/api/v1/budgets/{b['id']}", headers=h,
                      json={"amount": "0"}).status_code == 400
    assert client.put(f"/api/v1/budgets/{b['id']}", headers=h,
                      json={"category_id": 999999}).status_code == 400
    assert client.put("/api/v1/budgets/999999", headers=h,
                      json={"amount": "10"}).status_code == 404
