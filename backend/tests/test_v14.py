"""Tests v1.4: getrenntes Dashboard für Haushalts- und Privatkonten.

Kernidee: "Gemeinsam" und "Persönlich" beantworten unterschiedliche Fragen,
deshalb eigene Kontenauswahl UND eigenes Kachel-Layout je Bereich (4.9.1).
"""


def _account(client, h, name, **kw):
    payload = {"name": name, "type": kw.pop("type", "giro"), **kw}
    return client.post("/api/v1/accounts", headers=h, json=payload).json()


def test_account_household_flag_roundtrip(client, auth_headers):
    h = auth_headers
    privat = _account(client, h, "V14-Privat")
    haushalt = _account(client, h, "V14-Haushalt", is_household=True)

    assert privat["is_household"] is False
    assert haushalt["is_household"] is True

    # nachträglich umschaltbar – auch zurück auf False (exclude_none darf
    # False nicht wegwerfen)
    r = client.put(f"/api/v1/accounts/{privat['id']}", headers=h, json={"is_household": True})
    assert r.json()["is_household"] is True
    r = client.put(f"/api/v1/accounts/{privat['id']}", headers=h, json={"is_household": False})
    assert r.json()["is_household"] is False

    # Flag ist unabhängig davon, wer Zugriff hat ("shared")
    listed = {a["name"]: a for a in client.get("/api/v1/accounts", headers=h).json()}
    assert listed["V14-Haushalt"]["is_household"] is True
    assert listed["V14-Haushalt"]["shared"] is False


def test_dashboard_scopes_balance_to_selected_accounts(client, auth_headers):
    """Im Bereich "Gemeinsam" muss das Vermögen das des Haushalts sein –
    nicht weiterhin die Summe über alle zugänglichen Konten."""
    h = auth_headers
    haushalt = _account(client, h, "V14-Scope-Haushalt", is_household=True,
                        opening_balance="1000.00", opening_balance_date="2026-01-01")
    privat = _account(client, h, "V14-Scope-Privat",
                      opening_balance="4000.00", opening_balance_date="2026-01-01")

    only_household = client.get("/api/v1/dashboard/summary", headers=h,
                                params={"account_ids": [haushalt["id"]]}).json()
    assert only_household["balance_total"] == 1000.0
    assert [a["name"] for a in only_household["accounts"]] == ["V14-Scope-Haushalt"]
    assert only_household["accounts"][0]["is_household"] is True

    both = client.get("/api/v1/dashboard/summary", headers=h,
                      params={"account_ids": [haushalt["id"], privat["id"]]}).json()
    assert both["balance_total"] == 5000.0


def _core(tiles):
    """Nur Kachel-ID und Sichtbarkeit vergleichen – Größenangaben kommen mit
    Standardwerten hinzu und sind nicht Gegenstand dieser Tests."""
    return [{"id": t["id"], "visible": t["visible"]} for t in tiles]


def _reset_layout():
    """Die Test-DB ist sessionweit geteilt – andere Tests hinterlassen dort
    bereits ein Layout. Für definierte Ausgangslage vorher entfernen."""
    from app.db import SessionLocal
    from app.models import DashboardLayout, User

    with SessionLocal() as db:
        admin = db.query(User).filter(User.is_admin.is_(True)).order_by(User.id).first()
        row = db.get(DashboardLayout, admin.id)
        if row is not None:
            db.delete(row)
            db.commit()


def test_dashboard_layout_per_mode(client, auth_headers):
    """Jeder Bereich merkt sich sein eigenes Kachel-Layout."""
    h = auth_headers
    _reset_layout()
    gemeinsam = [{"id": "kpis", "visible": True}, {"id": "networth", "visible": False}]
    persoenlich = [{"id": "kpis", "visible": True}, {"id": "networth", "visible": True}]

    assert client.put("/api/v1/dashboard/layout", headers=h, params={"mode": "gemeinsam"},
                      json={"tiles": gemeinsam}).status_code == 200
    assert client.put("/api/v1/dashboard/layout", headers=h, params={"mode": "persoenlich"},
                      json={"tiles": persoenlich}).status_code == 200

    assert _core(client.get("/api/v1/dashboard/layout", headers=h,
                            params={"mode": "gemeinsam"}).json()["tiles"]) == gemeinsam
    assert _core(client.get("/api/v1/dashboard/layout", headers=h,
                            params={"mode": "persoenlich"}).json()["tiles"]) == persoenlich
    # unbeschriebener Modus liefert leer -> Frontend nimmt sein Standardlayout
    assert client.get("/api/v1/dashboard/layout", headers=h,
                      params={"mode": "gesamt"}).json()["tiles"] == []

    r = client.get("/api/v1/dashboard/layout", headers=h, params={"mode": "quatsch"})
    assert r.status_code == 400


def test_dashboard_layout_legacy_format_survives(client, auth_headers):
    """Vor v1.4 gespeicherte Layouts sind eine blanke Liste – die muss beim
    Umstieg für jeden Modus weiter gelten statt verloren zu gehen."""
    from app.db import SessionLocal
    from app.models import DashboardLayout, User

    h = auth_headers
    legacy = [{"id": "by_category", "visible": False}]
    with SessionLocal() as db:
        admin = db.query(User).filter(User.is_admin.is_(True)).order_by(User.id).first()
        row = db.get(DashboardLayout, admin.id)
        if row is None:
            row = DashboardLayout(user_id=admin.id)
            db.add(row)
        row.tiles = legacy          # altes Format wiederherstellen
        db.commit()

    for m in ("gemeinsam", "persoenlich", "gesamt"):
        assert _core(client.get("/api/v1/dashboard/layout", headers=h,
                                params={"mode": m}).json()["tiles"]) == legacy

    # erstes Speichern überführt es ins Modus-Format, ohne die anderen zu leeren
    client.put("/api/v1/dashboard/layout", headers=h, params={"mode": "gemeinsam"},
               json={"tiles": [{"id": "kpis", "visible": True}]})
    assert _core(client.get("/api/v1/dashboard/layout", headers=h,
                            params={"mode": "persoenlich"}).json()["tiles"]) == legacy


def test_partner_sees_only_household_accounts(client, auth_headers):
    """Der Partner hat nur auf gemeinsame Konten eine Rolle – er darf die
    privaten Konten weder sehen noch über das Dashboard auswerten (4.1)."""
    h = auth_headers
    haushalt = _account(client, h, "V14-Partner-Haushalt", is_household=True,
                        opening_balance="500.00", opening_balance_date="2026-01-01")
    privat = _account(client, h, "V14-Partner-Privat",
                      opening_balance="9999.00", opening_balance_date="2026-01-01")

    client.post("/api/v1/users", headers=h, json={
        "username": "v14partner", "password": "geheim123", "display_name": "V14 Partner"})
    users = client.get("/api/v1/users", headers=h).json()
    partner_id = next(u["id"] for u in users if u["username"] == "v14partner")
    client.put(f"/api/v1/accounts/{haushalt['id']}/roles", headers=h,
               json={"user_id": partner_id, "role": "reader"})

    token = client.post("/api/v1/auth/login",
                        data={"username": "v14partner", "password": "geheim123"}).json()["access_token"]
    ph = {"Authorization": f"Bearer {token}"}

    visible = client.get("/api/v1/accounts", headers=ph).json()
    assert [a["name"] for a in visible] == ["V14-Partner-Haushalt"]
    assert visible[0]["is_household"] is True

    # Dashboard des Partners kennt nur das Haushaltskonto
    s = client.get("/api/v1/dashboard/summary", headers=ph).json()
    assert s["balance_total"] == 500.0
    assert [a["name"] for a in s["accounts"]] == ["V14-Partner-Haushalt"]

    # ein untergeschobenes fremdes Konto erweitert den Zugriff nicht
    s = client.get("/api/v1/dashboard/summary", headers=ph,
                   params={"account_ids": [privat["id"]]}).json()
    assert privat["name"] not in [a["name"] for a in s["accounts"]]


def test_dashboard_layout_keeps_tile_sizes(client, auth_headers):
    """Kachelgrößen (Breite in Rasterspalten, Höhe in Pixeln) müssen die
    Speicherung überstehen – sonst wäre jede gezogene Größe nach dem
    Neuladen wieder weg."""
    h = auth_headers
    _reset_layout()
    tiles = [
        {"id": "kpis", "visible": True, "w": 2, "h": 260},
        {"id": "cashflow", "visible": True, "w": 4, "h": 520},
        {"id": "networth", "visible": False},          # ohne Größenangabe
    ]
    r = client.put("/api/v1/dashboard/layout", headers=h,
                   params={"mode": "gesamt"}, json={"tiles": tiles})
    assert r.status_code == 200

    stored = client.get("/api/v1/dashboard/layout", headers=h,
                        params={"mode": "gesamt"}).json()["tiles"]
    by_id = {t["id"]: t for t in stored}
    assert (by_id["kpis"]["w"], by_id["kpis"]["h"]) == (2, 260)
    assert (by_id["cashflow"]["w"], by_id["cashflow"]["h"]) == (4, 520)
    # ohne Angabe bleibt 0 = "Standard für diesen Kacheltyp"
    assert (by_id["networth"]["w"], by_id["networth"]["h"]) == (0, 0)

    # Layouts aus der Zeit vor den Größen bleiben gültig; fehlende Felder
    # werden mit ihren Standardwerten ergänzt (w/h seit v1.6, opts seit v1.7.4)
    legacy = [{"id": "kpis", "visible": True}]
    client.put("/api/v1/dashboard/layout", headers=h,
               params={"mode": "persoenlich"}, json={"tiles": legacy})
    back = client.get("/api/v1/dashboard/layout", headers=h,
                      params={"mode": "persoenlich"}).json()["tiles"]
    assert back == [{"id": "kpis", "visible": True, "w": 0, "h": 0, "opts": {}}]
