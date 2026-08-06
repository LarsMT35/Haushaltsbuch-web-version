"""Tests v1.7.2: Filter der Buchungsliste nach Einnahme / Ausgabe / Umbuchung.

Der Filter muss GENAU dieselbe Einteilung verwenden wie das Dashboard,
sonst zeigt die gefilterte Liste andere Betraege als die Kachel, aus der man
hineingeklickt hat. "Umbuchung" ist dabei beides: eine echte Gegenbuchung
(transfer_id) und eine Kategorie, die als "wie Umbuchung behandeln" markiert
ist - genau daran haengt der Fall, dass ein Depot 0 EUR Einnahmen anzeigt,
obwohl Buchungen darauf liegen.
"""


def _account(client, h, name, typ="giro", **kw):
    return client.post("/api/v1/accounts", headers=h,
                       json={"name": name, "type": typ, **kw}).json()


def _book(client, h, acc, d, amount, counterparty="Test", category_id=None):
    return client.post("/api/v1/transactions", headers=h, json={
        "account_id": acc["id"], "booking_date": d, "amount": amount,
        "counterparty": counterparty, "purpose": counterparty,
        "category_id": category_id}).json()


def _list(client, h, **params):
    r = client.get("/api/v1/transactions", headers=h, params=params)
    assert r.status_code == 200, r.text
    return r.json()


def test_direction_splits_income_expense_transfer(client, auth_headers):
    h = auth_headers
    giro = _account(client, h, "V172-Giro", opening_balance="1000",
                    opening_balance_date="2026-01-01")
    depot = _account(client, h, "V172-Depot", typ="depot", opening_balance="0",
                     opening_balance_date="2026-01-01")

    cats = client.get("/api/v1/categories", headers=h).json()
    kapital = next(c for c in cats if "Kapital" in c["name"])
    client.put(f"/api/v1/categories/{kapital['id']}", headers=h,
               json={"is_transfer_like": True, "transfer_target_account_id": depot["id"]})

    _book(client, h, giro, "2026-03-02", "2500.00", "V172 Gehalt")
    _book(client, h, giro, "2026-03-05", "-80.00", "V172 Supermarkt")
    _book(client, h, giro, "2026-03-10", "-250.00", "V172 Sparplan",
          category_id=kapital["id"])          # zaehlt als Umbuchung
    client.post("/api/v1/transfers/detect", headers=h)

    rng = {"date_from": "2026-03-01", "date_to": "2026-03-31",
           "account_ids": [giro["id"], depot["id"]]}

    einnahmen = _list(client, h, **rng, direction="income")
    assert [t["counterparty"] for t in einnahmen["items"]] == ["V172 Gehalt"]

    ausgaben = _list(client, h, **rng, direction="expense")
    assert [t["counterparty"] for t in ausgaben["items"]] == ["V172 Supermarkt"]

    umbuchungen = _list(client, h, **rng, direction="transfer")
    zwecke = {t["purpose"] for t in umbuchungen["items"]}
    assert any("Sparplan" in z for z in zwecke)
    # Gegenbuchung im Depot gehoert ebenfalls dazu
    assert any("Automatische Gegenbuchung" in z for z in zwecke)
    assert "V172 Gehalt" not in {t["counterparty"] for t in umbuchungen["items"]}


def test_direction_matches_dashboard_numbers(client, auth_headers):
    """Kernzusage: die Summe der gefilterten Liste entspricht der Kachel."""
    h = auth_headers
    giro = _account(client, h, "V172-Abgleich", opening_balance="0",
                    opening_balance_date="2026-01-01")
    _book(client, h, giro, "2026-04-02", "3000.00", "V172A Gehalt")
    _book(client, h, giro, "2026-04-06", "-120.00", "V172A Laden")
    _book(client, h, giro, "2026-04-09", "-30.50", "V172A Kiosk")

    rng = {"date_from": "2026-04-01", "date_to": "2026-04-30"}
    s = client.get("/api/v1/dashboard/summary", headers=h,
                   params={**rng, "account_ids": [giro["id"]]}).json()

    aus = _list(client, h, **rng, account_ids=[giro["id"]], direction="expense")
    summe = sum(-float(t["amount"]) for t in aus["items"])
    assert round(summe, 2) == round(s["expenses"], 2) == 150.50

    ein = _list(client, h, **rng, account_ids=[giro["id"]], direction="income")
    assert round(sum(float(t["amount"]) for t in ein["items"]), 2) == round(s["income"], 2)


def test_depot_shows_transfers_but_no_income(client, auth_headers):
    """Der gemeldete Fall: auf dem Depot liegen Buchungen, Einnahmen sind
    trotzdem 0 - weil alles Umbuchungen sind. Die Bewegung muss aber
    sichtbar bleiben, sonst wirkt das Konto leer."""
    h = auth_headers
    giro = _account(client, h, "V172-D-Giro", opening_balance="5000",
                    opening_balance_date="2026-01-01")
    depot = _account(client, h, "V172-D-Depot", typ="depot", opening_balance="0",
                     opening_balance_date="2026-01-01")
    cats = client.get("/api/v1/categories", headers=h).json()
    kapital = next(c for c in cats if "Kapital" in c["name"])
    client.put(f"/api/v1/categories/{kapital['id']}", headers=h,
               json={"is_transfer_like": True, "transfer_target_account_id": depot["id"]})
    for i in range(3):
        _book(client, h, giro, "2026-05-31", "-250.00", f"V172D Sparplan {i}",
              category_id=kapital["id"])
    client.post("/api/v1/transfers/detect", headers=h)

    rng = {"date_from": "2026-05-01", "date_to": "2026-05-31"}
    s = client.get("/api/v1/dashboard/summary", headers=h,
                   params={**rng, "account_ids": [depot["id"]]}).json()
    assert s["income"] == 0.0 and s["expenses"] == 0.0        # korrekt: keine Einnahme
    assert s["balance_total"] == 750.0                        # Geld ist trotzdem da
    bewegung = sum(m["value"] for m in s["savings_movement"])
    assert bewegung == 750.0                                  # und sichtbar als Bewegung

    # ... und ueber den Filter auch in der Liste auffindbar
    ums = _list(client, h, **rng, account_ids=[depot["id"]], direction="transfer")
    assert ums["total"] == 3
    assert _list(client, h, **rng, account_ids=[depot["id"]], direction="income")["total"] == 0


def test_direction_rejects_unknown_value(client, auth_headers):
    r = client.get("/api/v1/transactions", headers=auth_headers,
                   params={"direction": "quatsch"})
    assert r.status_code == 422
