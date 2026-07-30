"""End-to-End-Smoke-Test: Login → Konto → Import (Vorschau + Commit) →
Umbuchungserkennung → Dashboard → Rollback."""
import os

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")


def _upload(name):
    return {"file": (name, open(os.path.join(FIXTURES, name), "rb"), "text/csv")}


def test_full_import_flow(client, auth_headers):
    h = auth_headers

    # Konten anlegen (Giro Sparkasse + Tagesgeld ING) inkl. Anfangssaldo (4.2)
    r = client.post("/api/v1/accounts", headers=h, json={
        "name": "Girokonto", "type": "giro", "iban": "DE12500105170648489890",
        "bank": "Sparkasse", "opening_balance": "1000.00", "opening_balance_date": "2025-01-01"})
    assert r.status_code == 200, r.text
    giro = r.json()
    r = client.post("/api/v1/accounts", headers=h, json={
        "name": "Tagesgeld", "type": "tagesgeld", "iban": "DE44111122223333444455",
        "bank": "ING", "opening_balance": "5000.00", "opening_balance_date": "2025-01-01"})
    tagesgeld = r.json()

    # Profile sind geseedet
    profiles = {p["name"]: p for p in client.get("/api/v1/imports/profiles", headers=h).json()}
    assert "ING" in profiles and any("Sparkasse" in n for n in profiles)
    spk = next(p for n, p in profiles.items() if "Sparkasse" in n)

    # Regel anlegen: ALDI → Lebensmittel (4.6)
    cats = {c["name"]: c for c in client.get("/api/v1/categories", headers=h).json()}
    r = client.post("/api/v1/rules", headers=h, json={
        "name": "Aldi", "category_id": cats["Lebensmittel"]["id"], "text_contains": "ALDI"})
    assert r.status_code == 200

    # Vorschau Sparkasse: Zielkonto wird über IBAN erkannt, Regel greift (4.5)
    r = client.post("/api/v1/imports/preview", headers=h,
                    files=_upload("sparkasse_beispiel.csv"), data={"profile_id": spk["id"]})
    assert r.status_code == 200, r.text
    preview = r.json()
    assert preview["suggested_account_id"] == giro["id"]
    aldi_row = next(row for row in preview["rows"] if "ALDI" in row["purpose"])
    assert aldi_row["suggested_category_id"] == cats["Lebensmittel"]["id"]

    # Commit
    r = client.post("/api/v1/imports/commit", headers=h, json={
        "profile_id": spk["id"], "account_id": giro["id"],
        "filename": "sparkasse_beispiel.csv", "rows": preview["rows"]})
    assert r.status_code == 200, r.text
    batch1 = r.json()
    assert batch1["num_transactions"] == 5

    # Duplikaterkennung: gleiche Datei nochmal → alles als Duplikat markiert
    r = client.post("/api/v1/imports/preview", headers=h,
                    files=_upload("sparkasse_beispiel.csv"), data={"profile_id": spk["id"]})
    assert all(row["duplicate"] == "duplicate" for row in r.json()["rows"])

    # ING-Import auf Tagesgeld
    r = client.post("/api/v1/imports/preview", headers=h,
                    files=_upload("ing_beispiel.csv"), data={"profile_id": profiles["ING"]["id"]})
    ing_preview = r.json()
    assert ing_preview["suggested_account_id"] == tagesgeld["id"]
    r = client.post("/api/v1/imports/commit", headers=h, json={
        "profile_id": profiles["ING"]["id"], "account_id": tagesgeld["id"],
        "filename": "ing_beispiel.csv", "rows": ing_preview["rows"]})
    batch2 = r.json()
    assert batch2["num_transactions"] == 3

    # Umbuchungserkennung (4.4): -300 Giro ↔ +300 Tagesgeld, IBAN-belegt → auto verknüpft
    r = client.get("/api/v1/transactions", headers=h,
                   params={"text": "Uebertrag Tagesgeld"})
    txs = r.json()["items"]
    assert len(txs) == 2
    assert all(t["transfer_id"] is not None for t in txs)
    assert txs[0]["transfer_id"] == txs[1]["transfer_id"]

    # Dashboard: Umbuchung zählt nicht als Einnahme/Ausgabe
    r = client.get("/api/v1/dashboard/summary", headers=h,
                   params={"date_from": "2025-01-01", "date_to": "2026-12-31"})
    s = r.json()
    assert s["income"] == 2450.00 + 40.00
    assert round(s["expenses"], 2) == round(22.98 + 850.00 + 54.37 + 13.45, 2)
    # Salden: Anfangssaldo + Buchungen (Prinzip 3)
    balances = {a["name"]: a["balance"] for a in s["accounts"]}
    assert round(balances["Girokonto"], 2) == 1000 - 22.98 - 850 + 2450 - 300 - 54.37
    assert round(balances["Tagesgeld"], 2) == 5000 + 300 + 40 - 13.45

    # Suche & Export (4.11)
    r = client.get("/api/v1/transactions", headers=h, params={"text": "Miete"})
    assert r.json()["total"] == 1
    r = client.get("/api/v1/transactions/export.csv", headers=h)
    assert r.status_code == 200 and "Buchungstag" in r.text

    # Rollback (Prinzip 7): ING-Batch zurücknehmen löst auch die Umbuchung
    r = client.delete(f"/api/v1/imports/batches/{batch2['id']}", headers=h)
    assert r.json()["reverted"] is True
    r = client.get("/api/v1/transactions", headers=h, params={"account_id": tagesgeld["id"]})
    assert r.json()["total"] == 0
    r = client.get("/api/v1/transactions", headers=h, params={"text": "Uebertrag Tagesgeld"})
    assert all(t["transfer_id"] is None for t in r.json()["items"])


def test_manual_booking_and_immutability(client, auth_headers):
    h = auth_headers
    r = client.post("/api/v1/accounts", headers=h, json={"name": "Bargeld", "type": "bargeld"})
    bargeld = r.json()
    r = client.post("/api/v1/transactions", headers=h, json={
        "account_id": bargeld["id"], "booking_date": "2026-07-20",
        "amount": "-12.50", "counterparty": "Kiosk", "purpose": "Eis"})
    assert r.status_code == 200
    tx = r.json()
    assert tx["is_manual"] is True

    # Manuelle Buchung: Betrag änderbar
    r = client.put(f"/api/v1/transactions/{tx['id']}", headers=h, json={"amount": "-13.00"})
    assert r.status_code == 200

    # Importierte Buchung: Betrag NICHT änderbar (4.4)
    r = client.get("/api/v1/transactions", headers=h, params={"text": "Miete"})
    imported = r.json()["items"][0]
    r = client.put(f"/api/v1/transactions/{imported['id']}", headers=h, json={"amount": "-1.00"})
    assert r.status_code == 400
    # Kategorie/Notiz dagegen schon
    r = client.put(f"/api/v1/transactions/{imported['id']}", headers=h, json={"note": "geprüft"})
    assert r.status_code == 200


def test_roles_and_visibility(client, auth_headers):
    h = auth_headers
    # Zweiten Nutzer anlegen (nur Admin, keine Selbstregistrierung 4.1)
    r = client.post("/api/v1/users", headers=h, json={
        "username": "partner", "password": "geheim123", "display_name": "Partner"})
    assert r.status_code == 200
    partner_id = r.json()["id"]

    r = client.post("/api/v1/accounts", headers=h, json={"name": "Gemeinsam", "type": "giro"})
    gemeinsam = r.json()

    # Partner als Leser aufs gemeinsame Konto
    r = client.put(f"/api/v1/accounts/{gemeinsam['id']}/roles", headers=h,
                   json={"user_id": partner_id, "role": "reader"})
    assert r.status_code == 200

    # Partner-Login: sieht das Konto, darf aber nicht buchen
    r = client.post("/api/v1/auth/login", data={"username": "partner", "password": "geheim123"})
    ph = {"Authorization": f"Bearer {r.json()['access_token']}"}
    names = [a["name"] for a in client.get("/api/v1/accounts", headers=ph).json()]
    assert "Gemeinsam" in names
    r = client.post("/api/v1/transactions", headers=ph, json={
        "account_id": gemeinsam["id"], "booking_date": "2026-07-01", "amount": "-5"})
    assert r.status_code == 403
