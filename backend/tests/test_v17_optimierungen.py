"""Tests v1.7: Salden-Aggregation, Einzahlungen über mehrere Konten,
Perioden-Grenzen für den Sprung vom Diagramm in die Buchungsliste.

Die Saldenrechnung lief vorher je Konto einzeln in Python und summiert jetzt
in der Datenbank. Das Ergebnis muss identisch bleiben – vor allem in den
Randfällen, die eine SUM()-Aggregation anders behandelt als eine leere
Python-Summe: Konten ohne Buchungen tauchen im GROUP BY überhaupt nicht auf.
"""
import pytest


def _account(client, h, name, typ="giro", **kw):
    return client.post("/api/v1/accounts", headers=h,
                       json={"name": name, "type": typ, **kw}).json()


def _book(client, h, acc, d, amount, counterparty="Test"):
    return client.post("/api/v1/transactions", headers=h, json={
        "account_id": acc["id"], "booking_date": d, "amount": amount,
        "counterparty": counterparty, "purpose": "Test"}).json()


@pytest.fixture
def start_day_27(client, auth_headers):
    client.put("/api/v1/budgets/period", headers=auth_headers, json={"start_day": 27})
    yield 27
    client.put("/api/v1/budgets/period", headers=auth_headers, json={"start_day": 1})


# ------------------------------------------------------ Salden-Aggregation

def test_balance_uses_opening_balance_for_account_without_transactions(client, auth_headers):
    """Ein Konto ohne jede Buchung fehlt in der GROUP-BY-Summe komplett – sein
    Anfangssaldo muss trotzdem im Gesamtvermögen landen."""
    h = auth_headers
    leer = _account(client, h, "V17-Ohne-Buchungen", opening_balance="1234.56",
                    opening_balance_date="2026-01-01")

    r = client.get("/api/v1/dashboard/summary", headers=h,
                   params={"account_ids": [leer["id"]],
                           "date_from": "2026-01-01", "date_to": "2026-12-31"})
    assert r.status_code == 200
    body = r.json()
    assert body["balance_total"] == 1234.56
    row = next(a for a in body["accounts"] if a["account_id"] == leer["id"])
    assert row["balance"] == 1234.56


def test_balance_sums_all_transactions_regardless_of_selected_range(client, auth_headers):
    """Der Kontostand ist ein Bestand: er zählt ALLE Buchungen, auch solche
    ausserhalb des angezeigten Zeitraums."""
    h = auth_headers
    giro = _account(client, h, "V17-Bestand", opening_balance="100.00",
                    opening_balance_date="2025-01-01")
    _book(client, h, giro, "2025-06-15", "-30.00")   # vor dem Zeitraum
    _book(client, h, giro, "2026-03-10", "250.00")   # im Zeitraum
    _book(client, h, giro, "2027-01-05", "-20.00")   # nach dem Zeitraum

    r = client.get("/api/v1/dashboard/summary", headers=h,
                   params={"account_ids": [giro["id"]],
                           "date_from": "2026-01-01", "date_to": "2026-12-31"})
    body = r.json()
    assert body["balance_total"] == 300.00          # 100 - 30 + 250 - 20
    assert body["income"] == 250.00                 # nur der gewählte Zeitraum


def test_networth_end_balance_matches_summary_balance(client, auth_headers):
    """Beide Endpunkte rechnen den Saldo eigenständig – sie dürfen sich nicht
    widersprechen, sonst zeigen zwei Kacheln nebeneinander andere Zahlen."""
    h = auth_headers
    giro = _account(client, h, "V17-Abgleich-Giro", opening_balance="500.00",
                    opening_balance_date="2026-01-01")
    tages = _account(client, h, "V17-Abgleich-Tagesgeld", typ="tagesgeld",
                     opening_balance="2000.00", opening_balance_date="2026-01-01")
    _book(client, h, giro, "2026-02-10", "-120.50")
    _book(client, h, giro, "2026-03-10", "80.00")
    _book(client, h, tages, "2026-03-15", "300.00")

    ids = [giro["id"], tages["id"]]
    params = {"account_ids": ids, "date_from": "2026-01-01", "date_to": "2026-04-30"}
    summary = client.get("/api/v1/dashboard/summary", headers=h, params=params).json()
    nw = client.get("/api/v1/dashboard/networth", headers=h, params=params).json()

    assert summary["balance_total"] == 2759.50      # 500 - 120.50 + 80 + 2000 + 300
    # Letzter Monatsend-Stand im Vermögensverlauf = aktueller Gesamtsaldo
    assert nw["total"][-1] == summary["balance_total"]


def test_networth_per_account_series_unaffected_by_other_accounts(client, auth_headers):
    """Die Buchungen werden jetzt in einer Abfrage für alle Konten geholt und
    danach aufgeteilt – dabei darf nichts ins falsche Konto rutschen."""
    h = auth_headers
    a = _account(client, h, "V17-Trenn-A", opening_balance="0", opening_balance_date="2026-01-01")
    b = _account(client, h, "V17-Trenn-B", opening_balance="0", opening_balance_date="2026-01-01")
    _book(client, h, a, "2026-02-05", "100.00")
    _book(client, h, b, "2026-02-06", "700.00")

    nw = client.get("/api/v1/dashboard/networth", headers=h,
                    params={"account_ids": [a["id"], b["id"]],
                            "date_from": "2026-02-01", "date_to": "2026-02-28"}).json()
    by_name = {s["name"]: s["values"] for s in nw["series"]}
    assert by_name["V17-Trenn-A"][-1] == 100.00
    assert by_name["V17-Trenn-B"][-1] == 700.00


# -------------------------------------------- Einzahlungen über mehrere Konten

def test_deposits_aggregates_multiple_accounts(client, auth_headers):
    """Zwei gemeinsame Konten: Einzahlungen derselben Person zählen zusammen."""
    h = auth_headers
    haupt = _account(client, h, "V17-Gemeinsam-1")
    neben = _account(client, h, "V17-Gemeinsam-2")
    _book(client, h, haupt, "2026-05-02", "300.00", "Person A")
    _book(client, h, neben, "2026-05-03", "200.00", "Person A")
    _book(client, h, neben, "2026-05-04", "150.00", "Person B")
    _book(client, h, haupt, "2026-05-05", "-40.00", "Supermarkt")   # Ausgabe zählt nicht

    params = {"date_from": "2026-05-01", "date_to": "2026-05-31"}
    beide = client.get("/api/v1/dashboard/deposits", headers=h,
                       params={**params, "account_ids": [haupt["id"], neben["id"]]}).json()
    assert set(beide["account_ids"]) == {haupt["id"], neben["id"]}
    assert set(beide["depositors"]) == {"Person A", "Person B"}
    mai = next(s for s in beide["series"] if s["month"] == "2026-05")
    assert mai["values"]["Person A"] == 500.00      # über beide Konten summiert
    assert mai["values"]["Person B"] == 150.00

    # Einzelnes Konto liefert weiterhin nur dessen Einzahlungen
    einzeln = client.get("/api/v1/dashboard/deposits", headers=h,
                         params={**params, "account_ids": [haupt["id"]]}).json()
    mai_einzeln = next(s for s in einzeln["series"] if s["month"] == "2026-05")
    assert mai_einzeln["values"]["Person A"] == 300.00
    assert "Person B" not in einzeln["depositors"]


def test_deposits_ignores_accounts_without_access(client, auth_headers):
    """Fremde Konto-IDs dürfen keine fremden Einzahlungen sichtbar machen."""
    h = auth_headers
    eigen = _account(client, h, "V17-Zugriff-Eigen")
    _book(client, h, eigen, "2026-05-02", "80.00", "Person A")

    r = client.get("/api/v1/dashboard/deposits", headers=h,
                   params={"account_ids": [eigen["id"], 999999],
                           "date_from": "2026-05-01", "date_to": "2026-05-31"})
    assert r.status_code == 200
    assert 999999 not in r.json()["account_ids"]


# ------------------------------------- Bereichsfilter der Buchungsliste (Klick)

def test_transactions_filter_by_multiple_accounts(client, auth_headers):
    """Der Sprung aus einem Diagramm reicht den ganzen Bereich weiter – die
    Liste muss dieselbe Grundmenge zeigen wie die angeklickte Zahl."""
    h = auth_headers
    a = _account(client, h, "V17-Bereich-A")
    b = _account(client, h, "V17-Bereich-B")
    c = _account(client, h, "V17-Bereich-C")
    _book(client, h, a, "2026-07-01", "-10.00", "Laden A")
    _book(client, h, b, "2026-07-02", "-20.00", "Laden B")
    _book(client, h, c, "2026-07-03", "-30.00", "Laden C")

    params = {"date_from": "2026-07-01", "date_to": "2026-07-31"}
    body = client.get("/api/v1/transactions", headers=h,
                      params={**params, "account_ids": [a["id"], b["id"]]}).json()
    namen = {t["counterparty"] for t in body["items"]}
    assert namen == {"Laden A", "Laden B"}
    assert body["total"] == 2


def test_transactions_scope_and_single_account_combine(client, auth_headers):
    """Bereich begrenzt, das Auswahlfeld verfeinert – beide zusammen ergeben
    die Schnittmenge, nicht die Vereinigung."""
    h = auth_headers
    a = _account(client, h, "V17-Kombi-A")
    b = _account(client, h, "V17-Kombi-B")
    _book(client, h, a, "2026-08-01", "-10.00", "Kombi A")
    _book(client, h, b, "2026-08-02", "-20.00", "Kombi B")

    body = client.get("/api/v1/transactions", headers=h, params={
        "date_from": "2026-08-01", "date_to": "2026-08-31",
        "account_ids": [a["id"], b["id"]], "account_id": a["id"]}).json()
    assert {t["counterparty"] for t in body["items"]} == {"Kombi A"}


def test_transactions_scope_ignores_foreign_accounts(client, auth_headers):
    h = auth_headers
    eigen = _account(client, h, "V17-Bereich-Eigen")
    _book(client, h, eigen, "2026-09-01", "-5.00", "Eigen")

    r = client.get("/api/v1/transactions", headers=h, params={
        "date_from": "2026-09-01", "date_to": "2026-09-30",
        "account_ids": [eigen["id"], 999999]})
    assert r.status_code == 200
    assert {t["counterparty"] for t in r.json()["items"]} == {"Eigen"}


# ----------------------------------------------------- Perioden-Grenzen (Klick)

def test_period_bounds_calendar_month(client, auth_headers):
    r = client.get("/api/v1/budgets/period/bounds", headers=auth_headers,
                   params={"month": "2026-05"})
    assert r.status_code == 200
    assert r.json() == {"month": "2026-05", "date_from": "2026-05-01", "date_to": "2026-05-31",
                        "previous_month": "2026-04", "previous_from": "2026-04-01",
                        "previous_to": "2026-04-30"}


def test_period_bounds_shifted_month(client, auth_headers, start_day_27):
    """Mit Starttag 27 läuft der Mai-Abrechnungsmonat vom 27.04. bis 26.05."""
    r = client.get("/api/v1/budgets/period/bounds", headers=auth_headers,
                   params={"month": "2026-05"})
    body = r.json()
    assert body["date_from"] == "2026-04-27"
    assert body["date_to"] == "2026-05-26"
    # Vorperiode: exakt anschliessend, nicht kalendarisch geschaetzt
    assert body["previous_month"] == "2026-04"
    assert (body["previous_from"], body["previous_to"]) == ("2026-03-27", "2026-04-26")


def test_period_bounds_rejects_invalid_month(client, auth_headers):
    for bad in ["2026-13", "Unsinn", "2026"]:
        r = client.get("/api/v1/budgets/period/bounds", headers=auth_headers,
                       params={"month": bad})
        assert r.status_code == 422, bad
