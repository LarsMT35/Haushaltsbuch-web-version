"""Tests v1.7.1: Der Abrechnungsmonat gehört dem Nutzer, nicht der App.

Der Zahltag ist nichts Gemeinsames – im selben Haushalt kann eine Person am
27. Gehalt bekommen und die andere am 1. Vorher durfte ihn nur ein
Administrator app-weit setzen; jeder Nicht-Admin lief in ein 403 und konnte
schlicht nicht speichern.

Der heikelste Punkt ist die Trennung: die Wahl des einen darf die
Auswertungen des anderen unter keinen Umständen verschieben.
"""


def _account(client, h, name, **kw):
    return client.post("/api/v1/accounts", headers=h,
                       json={"name": name, "type": "giro", **kw}).json()


def _book(client, h, acc, d, amount, counterparty="Test"):
    return client.post("/api/v1/transactions", headers=h, json={
        "account_id": acc["id"], "booking_date": d, "amount": amount,
        "counterparty": counterparty, "purpose": "Test"}).json()


def _make_user(client, admin_h, username, password="geheim123"):
    """Zweiter, ausdrücklich NICHT administrativer Nutzer."""
    client.post("/api/v1/users", headers=admin_h, json={
        "username": username, "password": password, "display_name": username})
    users = client.get("/api/v1/users", headers=admin_h).json()
    uid = next(u["id"] for u in users if u["username"] == username)
    assert not next(u for u in users if u["id"] == uid).get("is_admin", False)
    token = client.post("/api/v1/auth/login",
                        data={"username": username, "password": password}).json()["access_token"]
    return uid, {"Authorization": f"Bearer {token}"}


# ------------------------------------------------------------ Speichern darf jeder

def test_non_admin_can_save_own_period(client, auth_headers):
    """Der eigentliche Fehler: als Nicht-Admin liess sich nichts speichern."""
    _uid, ph = _make_user(client, auth_headers, "v171user")

    r = client.put("/api/v1/budgets/period", headers=ph, json={"start_day": 27})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["start_day"] == 27
    assert body["is_own_choice"] is True
    # und bleibt erhalten
    assert client.get("/api/v1/budgets/period", headers=ph).json()["start_day"] == 27


def test_own_choice_flag_marks_inherited_default(client, auth_headers):
    """Ohne eigene Wahl gilt die app-weite Voreinstellung – das muss die
    Oberflaeche unterscheiden koennen, sonst behauptet sie eine Wahl,
    die nie getroffen wurde."""
    _uid, ph = _make_user(client, auth_headers, "v171geerbt")

    before = client.get("/api/v1/budgets/period", headers=ph).json()
    assert before["start_day"] == 1
    assert before["is_own_choice"] is False

    client.put("/api/v1/budgets/period", headers=ph, json={"start_day": 15})
    after = client.get("/api/v1/budgets/period", headers=ph).json()
    assert after["is_own_choice"] is True


def test_invalid_start_day_is_clamped(client, auth_headers):
    """Ueber 28 gaebe es Monate ohne diesen Tag – die Grenze bliebe uneindeutig."""
    _uid, ph = _make_user(client, auth_headers, "v171grenze")
    assert client.put("/api/v1/budgets/period", headers=ph,
                      json={"start_day": 31}).json()["start_day"] == 28
    assert client.put("/api/v1/budgets/period", headers=ph,
                      json={"start_day": 0}).json()["start_day"] == 1


# ------------------------------------------------------- Trennung zwischen Nutzern

def test_users_do_not_affect_each_other(client, auth_headers):
    """Kernzusage: zwei Nutzer, zwei Zeitraeume, dieselben Buchungen."""
    admin_h = auth_headers
    _uid, ph = _make_user(client, auth_headers, "v171getrennt")

    a = client.put("/api/v1/budgets/period", headers=admin_h, json={"start_day": 1}).json()
    b = client.put("/api/v1/budgets/period", headers=ph, json={"start_day": 27}).json()
    assert (a["start_day"], b["start_day"]) == (1, 27)

    # Der Admin darf sich durch die Wahl des anderen nicht verschoben haben
    assert client.get("/api/v1/budgets/period", headers=admin_h).json()["start_day"] == 1
    assert client.get("/api/v1/budgets/period", headers=ph).json()["start_day"] == 27

    # Gleicher Monat, unterschiedliche Grenzen
    admin_bounds = client.get("/api/v1/budgets/period/bounds", headers=admin_h,
                              params={"month": "2026-05"}).json()
    partner_bounds = client.get("/api/v1/budgets/period/bounds", headers=ph,
                                params={"month": "2026-05"}).json()
    assert (admin_bounds["date_from"], admin_bounds["date_to"]) == ("2026-05-01", "2026-05-31")
    assert (partner_bounds["date_from"], partner_bounds["date_to"]) == ("2026-04-27", "2026-05-26")


def test_same_transaction_lands_in_different_periods_per_user(client, auth_headers):
    """Dieselbe Buchung, zwei Nutzer: der 28.04. ist fuer den einen der April,
    fuer den anderen schon der Mai. Die Buchung selbst aendert sich nicht."""
    admin_h = auth_headers
    giro = _account(client, admin_h, "V171-Geteilt", opening_balance="0",
                    opening_balance_date="2026-01-01")
    _book(client, admin_h, giro, "2026-04-28", "2500.00", "Arbeitgeber")

    users = client.get("/api/v1/users", headers=admin_h).json()
    partner_id = next((u["id"] for u in users if u["username"] == "v171sicht"), None)
    if partner_id is None:
        _pid, ph = _make_user(client, admin_h, "v171sicht")
        partner_id = _pid
    else:
        token = client.post("/api/v1/auth/login",
                            data={"username": "v171sicht", "password": "geheim123"}).json()["access_token"]
        ph = {"Authorization": f"Bearer {token}"}
    client.put(f"/api/v1/accounts/{giro['id']}/roles", headers=admin_h,
               json={"user_id": partner_id, "role": "reader"})

    client.put("/api/v1/budgets/period", headers=admin_h, json={"start_day": 1})
    client.put("/api/v1/budgets/period", headers=ph, json={"start_day": 27})

    def month_of(headers):
        items = client.get("/api/v1/transactions", headers=headers,
                           params={"text": "Arbeitgeber", "limit": 50}).json()["items"]
        tx = next(t for t in items if t["booking_date"] == "2026-04-28")
        assert tx["amount"] == "2500.00"          # Daten bleiben unberuehrt
        assert tx["financial_month_is_override"] is False
        return tx["financial_month"]

    assert month_of(admin_h) == "2026-04"
    assert month_of(ph) == "2026-05"


def test_dashboard_follows_own_period(client, auth_headers):
    """Nicht nur die Buchungsliste – auch die Auswertung muss der eigenen
    Einteilung folgen, sonst widersprechen sich zwei Ansichten."""
    admin_h = auth_headers
    giro = _account(client, admin_h, "V171-Dashboard", opening_balance="0",
                    opening_balance_date="2026-01-01")
    _book(client, admin_h, giro, "2026-06-28", "-100.00", "Laden")

    client.put("/api/v1/budgets/period", headers=admin_h, json={"start_day": 27})
    s = client.get("/api/v1/dashboard/summary", headers=admin_h, params={
        "account_ids": [giro["id"]], "date_from": "2026-06-01", "date_to": "2026-07-31"}).json()
    months = [m["month"] for m in s["monthly_expenses"] if m["value"]]
    assert months == ["2026-07"]                  # 28.06. gehoert zur Juli-Periode

    client.put("/api/v1/budgets/period", headers=admin_h, json={"start_day": 1})
    s = client.get("/api/v1/dashboard/summary", headers=admin_h, params={
        "account_ids": [giro["id"]], "date_from": "2026-06-01", "date_to": "2026-07-31"}).json()
    months = [m["month"] for m in s["monthly_expenses"] if m["value"]]
    assert months == ["2026-06"]                  # als Kalendermonat wieder Juni
