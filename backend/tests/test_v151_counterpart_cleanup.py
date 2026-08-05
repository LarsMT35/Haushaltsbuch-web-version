"""Regressionstests v1.5.1: automatisch erzeugte Gegenbuchungen dürfen nicht
als Saldo-Phantom im Zielkonto zurückbleiben.

Eine Gegenbuchung (Kategorie mit Umbuchungs-Zielkonto, v1.3b) ist abgeleitetes
Datum. Verschwindet ihre Quelle oder die Verknüpfung, muss sie mitgehen –
sonst zeigt z.B. das Depot dauerhaft zu viel an.
"""
from datetime import date

from app.db import SessionLocal
from app.models import ImportBatch, Transaction, User


def _account(client, h, name, **kw):
    return client.post("/api/v1/accounts", headers=h,
                       json={"name": name, "type": kw.pop("type", "giro"), **kw}).json()


def _balances(client, h):
    return {a["name"]: float(a["balance"]) for a in client.get("/api/v1/accounts", headers=h).json()}


def _setup(client, h, tag):
    """Giro + Depot + Sparplan-Kategorie mit Depot als Umbuchungs-Zielkonto."""
    giro = _account(client, h, f"{tag}-Giro")
    depot = _account(client, h, f"{tag}-Depot", type="depot")
    cat = client.post("/api/v1/categories", headers=h, json={
        "name": f"{tag}-Sparplan", "scope": "personal",
        "transfer_target_account_id": depot["id"]}).json()
    return giro, depot, cat


def test_import_rollback_removes_generated_counterpart(client, auth_headers):
    """Der ursprünglich gemeldete Fall: Rollback ließ die Depot-Gegenbuchung
    stehen, der Depot-Saldo blieb dauerhaft zu hoch."""
    h = auth_headers
    giro, depot, cat = _setup(client, h, "CP1")

    with SessionLocal() as db:
        uid = db.query(User).filter(User.is_admin.is_(True)).order_by(User.id).first().id
        batch = ImportBatch(filename="cp1.csv", user_id=uid, num_transactions=1)
        db.add(batch)
        db.flush()
        db.add(Transaction(account_id=giro["id"], booking_date=date(2026, 7, 10),
                           amount=-150, amount_ref=-150, counterparty="Broker",
                           purpose="Sparplan", category_id=cat["id"], import_batch_id=batch.id))
        db.commit()
        batch_id = batch.id

    assert client.post("/api/v1/transfers/detect", headers=h).json()["mirrored"] == 1
    assert _balances(client, h)[f"CP1-Depot"] == 150.0

    r = client.delete(f"/api/v1/imports/batches/{batch_id}", headers=h)
    assert r.json()["reverted"] is True

    # Depot ist wieder bei null, keine Buchung bleibt zurück
    assert _balances(client, h)["CP1-Depot"] == 0.0
    assert client.get("/api/v1/transactions", headers=h,
                      params={"account_id": depot["id"]}).json()["total"] == 0


def test_deleting_source_removes_generated_counterpart(client, auth_headers):
    h = auth_headers
    giro, depot, cat = _setup(client, h, "CP2")
    tx = client.post("/api/v1/transactions", headers=h, json={
        "account_id": giro["id"], "booking_date": "2026-07-11", "amount": "-90.00",
        "counterparty": "Broker", "purpose": "Sparplan", "category_id": cat["id"]}).json()

    assert _balances(client, h)["CP2-Depot"] == 90.0

    r = client.delete(f"/api/v1/transactions/{tx['id']}", headers=h)
    assert r.json()["counterparts_removed"] == 1
    assert _balances(client, h)["CP2-Depot"] == 0.0


def test_unlinking_transfer_removes_generated_counterpart(client, auth_headers):
    h = auth_headers
    giro, depot, cat = _setup(client, h, "CP3")
    client.post("/api/v1/transactions", headers=h, json={
        "account_id": giro["id"], "booking_date": "2026-07-12", "amount": "-70.00",
        "counterparty": "Broker", "purpose": "Sparplan", "category_id": cat["id"]})

    txs = client.get("/api/v1/transactions", headers=h,
                     params={"account_id": giro["id"]}).json()["items"]
    transfer_id = next(t["transfer_id"] for t in txs if t["transfer_id"])

    r = client.delete(f"/api/v1/transfers/{transfer_id}", headers=h)
    assert r.json()["counterparts_removed"] == 1
    assert _balances(client, h)["CP3-Depot"] == 0.0


def test_unlinking_real_pair_keeps_both_bookings(client, auth_headers):
    """Gegenprobe: eine von Hand erfasste Gegenbuchung ist KEIN abgeleitetes
    Datum und muss beim Auflösen erhalten bleiben."""
    h = auth_headers
    a = _account(client, h, "CP4-A", iban="DE00CP4A0000000001")
    b = _account(client, h, "CP4-B", type="tagesgeld", iban="DE00CP4B0000000002")
    client.post("/api/v1/transactions", headers=h, json={
        "account_id": a["id"], "booking_date": "2026-07-05", "amount": "-411.23",
        "counterparty": "Tagesgeld", "purpose": "Uebertrag"})
    client.post("/api/v1/transactions", headers=h, json={
        "account_id": b["id"], "booking_date": "2026-07-05", "amount": "411.23",
        "counterparty": "Giro", "purpose": "Uebertrag"})

    txs = client.get("/api/v1/transactions", headers=h,
                     params={"account_id": a["id"]}).json()["items"]
    pair = [t for t in txs if t["transfer_id"]]
    if pair:  # wurde als Vorschlag erkannt und verknüpft
        r = client.delete(f"/api/v1/transfers/{pair[0]['transfer_id']}", headers=h)
        assert r.json()["counterparts_removed"] == 0
    # beide Buchungen existieren weiterhin
    assert client.get("/api/v1/transactions", headers=h,
                      params={"account_id": a["id"]}).json()["total"] == 1
    assert client.get("/api/v1/transactions", headers=h,
                      params={"account_id": b["id"]}).json()["total"] == 1


def test_changing_category_away_removes_counterpart(client, auth_headers):
    """Wechselt die Kategorie weg vom Sparplan, verliert die Gegenbuchung
    ihre Grundlage."""
    h = auth_headers
    giro, depot, cat = _setup(client, h, "CP5")
    other = {c["name"]: c for c in client.get("/api/v1/categories", headers=h).json()}["Sonstiges"]
    tx = client.post("/api/v1/transactions", headers=h, json={
        "account_id": giro["id"], "booking_date": "2026-07-13", "amount": "-55.00",
        "counterparty": "Broker", "purpose": "Sparplan", "category_id": cat["id"]}).json()
    assert _balances(client, h)["CP5-Depot"] == 55.0

    client.put(f"/api/v1/transactions/{tx['id']}", headers=h, json={"category_id": other["id"]})
    assert _balances(client, h)["CP5-Depot"] == 0.0
    assert client.get("/api/v1/transactions", headers=h,
                      params={"account_id": depot["id"]}).json()["total"] == 0

    # und wieder zurück: Gegenbuchung entsteht erneut
    client.put(f"/api/v1/transactions/{tx['id']}", headers=h, json={"category_id": cat["id"]})
    assert _balances(client, h)["CP5-Depot"] == 55.0


def test_detect_cleans_up_orphans_from_older_versions(client, auth_headers):
    """Bestände vor v1.5.1 können bereits verwaiste Gegenbuchungen enthalten –
    'Umbuchungen erkennen' räumt sie weg."""
    h = auth_headers
    depot = _account(client, h, "CP6-Depot", type="depot")
    with SessionLocal() as db:
        db.add(Transaction(account_id=depot["id"], booking_date=date(2026, 6, 1),
                           amount=200, amount_ref=200, counterparty="Girokonto",
                           purpose="Automatische Gegenbuchung: Sparplan",
                           is_manual=True, is_auto_counterpart=True))
        db.commit()
    assert _balances(client, h)["CP6-Depot"] == 200.0

    r = client.post("/api/v1/transfers/detect", headers=h).json()
    assert r["cleaned"] == 1
    assert _balances(client, h)["CP6-Depot"] == 0.0

    # zweiter Aufruf findet nichts mehr
    assert client.post("/api/v1/transfers/detect", headers=h).json()["cleaned"] == 0
