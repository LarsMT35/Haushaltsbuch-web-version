"""Tests v1.5.2: Sparquote zählt den tatsächlichen Zufluss auf die Sparkonten.

Vorher wurde "Einnahmen − Ausgaben ÷ Einnahmen" ausgewiesen. Das zählte auch
Geld als gespart, das einfach auf dem Girokonto liegen blieb, und ignorierte
Umbuchungen komplett. Richtig ist der NETTO-Zufluss inkl. Rückbuchungen:
200 € aufs Tagesgeld, 50 € zurück aufs Giro = 150 € gespart.
"""
from datetime import date

from app.db import SessionLocal
from app.models import Transaction


def _account(client, h, name, typ, iban=""):
    return client.post("/api/v1/accounts", headers=h,
                       json={"name": name, "type": typ, "iban": iban}).json()


def _book(client, h, acc, d, amount, counterparty, category_id=None):
    return client.post("/api/v1/transactions", headers=h, json={
        "account_id": acc["id"], "booking_date": d, "amount": amount,
        "counterparty": counterparty, "purpose": "Test", "category_id": category_id}).json()


def _transfer(giro, other, d, amount, giro_iban, other_iban):
    """Beide Seiten einer Umbuchung direkt in der DB (mit IBAN-Beleg, damit
    die Erkennung sie verknüpft)."""
    with SessionLocal() as db:
        db.add(Transaction(account_id=giro["id"], booking_date=d, amount=-amount,
                           amount_ref=-amount, counterparty=other["name"],
                           counterparty_iban=other_iban, purpose="Umbuchung"))
        db.add(Transaction(account_id=other["id"], booking_date=d, amount=amount,
                           amount_ref=amount, counterparty=giro["name"],
                           counterparty_iban=giro_iban, purpose="Umbuchung"))
        db.commit()


def test_savings_rate_counts_net_inflow_including_return_transfer(client, auth_headers):
    """Der gemeldete Fall: 200 gespart, 50 zurückgebucht -> 150 Sparrate."""
    h = auth_headers
    GIRO_IBAN, TG_IBAN = "DE00V152GIRO000000001", "DE00V152TAGESGELD0002"
    giro = _account(client, h, "V152-Giro", "giro", GIRO_IBAN)
    tg = _account(client, h, "V152-Tagesgeld", "tagesgeld", TG_IBAN)
    cats = {c["name"]: c for c in client.get("/api/v1/categories", headers=h).json()}

    _book(client, h, giro, "2026-07-01", "3000.00", "Arbeitgeber", cats["Gehalt"]["id"])
    _book(client, h, giro, "2026-07-05", "-1000.00", "Vermieter", cats["Miete / Wohnen"]["id"])
    _transfer(giro, tg, date(2026, 7, 10), 200, GIRO_IBAN, TG_IBAN)      # 200 sparen
    _transfer(tg, giro, date(2026, 7, 20), 50, TG_IBAN, GIRO_IBAN)       # 50 zurück
    assert client.post("/api/v1/transfers/detect", headers=h).json()["linked"] == 2

    p = {"date_from": "2026-07-01", "date_to": "2026-07-31",
         "account_ids": [giro["id"], tg["id"]]}
    sr = client.get("/api/v1/dashboard/savings-rate", headers=h, params=p).json()
    i = sr["months"].index("2026-07")

    assert sr["saved"][i] == 150.0          # 200 hin, 50 zurück
    assert sr["rate"][i] == 5.0             # 150 von 3000 Einnahmen
    # Umbuchungen bleiben aus Einnahmen/Ausgaben heraus
    assert sr["income"][i] == 3000.0
    assert sr["expenses"][i] == 1000.0
    # Sparpotenzial weiterhin ausgewiesen, aber klar getrennt
    assert sr["surplus"][i] == 2000.0
    assert sr["surplus_rate"][i] == 66.7

    s = client.get("/api/v1/dashboard/summary", headers=h, params=p).json()
    assert s["expenses"] == 1000.0          # Umbuchung ist keine Ausgabe
    assert next(m["value"] for m in s["savings_movement"] if m["month"] == "2026-07") == 150.0


def test_savings_rate_counts_depot_transfers(client, auth_headers):
    """Sparplan ins Depot über ein Umbuchungs-Zielkonto (v1.3b) zählt
    ebenfalls als Sparen, nicht als Ausgabe."""
    h = auth_headers
    giro = _account(client, h, "V152-D-Giro", "giro")
    depot = _account(client, h, "V152-D-Depot", "depot")
    cats = {c["name"]: c for c in client.get("/api/v1/categories", headers=h).json()}
    cat = client.post("/api/v1/categories", headers=h, json={
        "name": "V152-Sparplan", "scope": "personal",
        "transfer_target_account_id": depot["id"]}).json()

    _book(client, h, giro, "2026-08-01", "2500.00", "Arbeitgeber", cats["Gehalt"]["id"])
    _book(client, h, giro, "2026-08-12", "-250.00", "Broker", cat["id"])

    p = {"date_from": "2026-08-01", "date_to": "2026-08-31",
         "account_ids": [giro["id"], depot["id"]]}
    sr = client.get("/api/v1/dashboard/savings-rate", headers=h, params=p).json()
    i = sr["months"].index("2026-08")

    assert sr["saved"][i] == 250.0          # im Depot angekommen
    assert sr["rate"][i] == 10.0            # 250 von 2500
    assert sr["expenses"][i] == 0.0         # keine Ausgabe


def test_savings_rate_negative_when_savings_are_spent(client, auth_headers):
    """Wird mehr vom Sparkonto geholt als eingezahlt, ist die Quote negativ –
    das ist die ehrliche Aussage, kein Nullwert."""
    h = auth_headers
    GIRO_IBAN, TG_IBAN = "DE00V152NGIRO00000001", "DE00V152NTAGESGELD002"
    giro = _account(client, h, "V152-N-Giro", "giro", GIRO_IBAN)
    tg = _account(client, h, "V152-N-Tagesgeld", "tagesgeld", TG_IBAN)
    cats = {c["name"]: c for c in client.get("/api/v1/categories", headers=h).json()}

    _book(client, h, giro, "2026-09-01", "2000.00", "Arbeitgeber", cats["Gehalt"]["id"])
    _transfer(tg, giro, date(2026, 9, 15), 400, TG_IBAN, GIRO_IBAN)   # 400 vom Sparkonto
    client.post("/api/v1/transfers/detect", headers=h)

    sr = client.get("/api/v1/dashboard/savings-rate", headers=h, params={
        "date_from": "2026-09-01", "date_to": "2026-09-30",
        "account_ids": [giro["id"], tg["id"]]}).json()
    i = sr["months"].index("2026-09")
    assert sr["saved"][i] == -400.0
    assert sr["rate"][i] == -20.0


def test_savings_between_two_savings_accounts_is_not_new_saving(client, auth_headers):
    """Tagesgeld -> Depot ist Umschichtung, kein zusätzliches Sparen."""
    h = auth_headers
    TG_IBAN, DEPOT_IBAN = "DE00V152UTAGESGELD01", "DE00V152UDEPOT000002"
    tg = _account(client, h, "V152-U-Tagesgeld", "tagesgeld", TG_IBAN)
    depot = _account(client, h, "V152-U-Depot", "depot", DEPOT_IBAN)
    _transfer(tg, depot, date(2026, 10, 5), 500, TG_IBAN, DEPOT_IBAN)
    client.post("/api/v1/transfers/detect", headers=h)

    sr = client.get("/api/v1/dashboard/savings-rate", headers=h, params={
        "date_from": "2026-10-01", "date_to": "2026-10-31",
        "account_ids": [tg["id"], depot["id"]]}).json()
    i = sr["months"].index("2026-10")
    assert sr["saved"][i] == 0.0
