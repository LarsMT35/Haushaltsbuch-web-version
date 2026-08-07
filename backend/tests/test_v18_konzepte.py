"""Tests v1.8: bereinigte Konzepte und die drei neuen Auswertungen.

Der rote Faden: zwei Kacheln nebeneinander duerfen nie dieselbe Groesse
unterschiedlich benennen oder unterschiedlich rechnen. Genau daran ist die
Sparquote gescheitert (zwei verschiedene "Einnahmen"), und genau das pruefen
die ersten Tests hier ab.
"""
import pytest


def _acc(client, h, name, typ="giro", **kw):
    return client.post("/api/v1/accounts", headers=h,
                       json={"name": name, "type": typ, **kw}).json()


def _tx(client, h, acc, d, amount, cp="Test", cat=None):
    return client.post("/api/v1/transactions", headers=h, json={
        "account_id": acc["id"], "booking_date": d, "amount": amount,
        "counterparty": cp, "purpose": cp, "category_id": cat}).json()


@pytest.fixture
def start_day_27(client, auth_headers):
    client.put("/api/v1/budgets/period", headers=auth_headers, json={"start_day": 27})
    yield 27
    client.put("/api/v1/budgets/period", headers=auth_headers, json={"start_day": 1})


# ------------------------------------------------- Konzepte (1a-1e)

def test_savings_rate_income_matches_kpi_income(client, auth_headers):
    """Die Kachel "Sparquote" und die Kachel "Kennzahlen" standen mit zwei
    verschiedenen Zahlen unter derselben Beschriftung nebeneinander."""
    h = auth_headers
    giro = _acc(client, h, "V18-Giro", opening_balance="0", opening_balance_date="2026-01-01")
    tg = _acc(client, h, "V18-Tagesgeld", typ="tagesgeld",
              opening_balance="0", opening_balance_date="2026-01-01")
    _tx(client, h, giro, "2026-04-01", "2000.00", "Gehalt")
    _tx(client, h, tg, "2026-04-15", "500.00", "Zinsen")

    p = {"date_from": "2026-04-01", "date_to": "2026-04-30",
         "account_ids": [giro["id"], tg["id"]]}
    kpi = client.get("/api/v1/dashboard/summary", headers=h, params=p).json()
    sq = client.get("/api/v1/dashboard/savings-rate", headers=h, params=p).json()
    i = sq["months"].index("2026-04")

    assert sq["income"][i] == kpi["income"]      # gleiche Beschriftung, gleiche Zahl
    assert sq["income_base"][i] == 2000.0        # Nenner der Quote bleibt bereinigt


def test_saved_never_exceeds_surplus_by_definition(client, auth_headers):
    """Frueher konnte das Gesparte ueber dem Sparpotenzial liegen, ohne dass
    jemand mehr gespart haette - weil Zinsen im Zaehler standen, aber nicht im
    Potenzial. Das Diagramm behauptete damit etwas Falsches."""
    h = auth_headers
    tg = _acc(client, h, "V18-Nur-Zinsen", typ="tagesgeld",
              opening_balance="0", opening_balance_date="2026-01-01")
    _tx(client, h, tg, "2026-07-10", "80.00", "Zinsgutschrift")

    r = client.get("/api/v1/dashboard/savings-rate", headers=h, params={
        "date_from": "2026-07-01", "date_to": "2026-07-31",
        "account_ids": [tg["id"]]}).json()
    i = r["months"].index("2026-07")
    assert r["saved"][i] == 80.0
    assert r["surplus"][i] >= r["saved"][i]     # Potenzial enthaelt den Zufluss jetzt auch


def test_cumulative_resolves_period_from_a_date(client, auth_headers, start_day_27):
    """Wie bei den Budgets: der 30.08. gehoert zum September. Ein Abschneiden
    auf '2026-08' traf den falschen Zeitraum."""
    h = auth_headers
    r = client.get("/api/v1/dashboard/cumulative", headers=h,
                   params={"date_in_period": "2026-08-30"}).json()
    assert r["month"] == "2026-09"
    r = client.get("/api/v1/dashboard/cumulative", headers=h,
                   params={"date_in_period": "2026-08-26"}).json()
    assert r["month"] == "2026-08"


def test_liabilities_are_reported_separately(client, auth_headers):
    """Eine Kreditkarte im Minus ist eine Schuld, kein negatives Guthaben. Das
    Nettovermoegen bleibt gleich, aber beides muss benennbar sein."""
    h = auth_headers
    giro = _acc(client, h, "V18-Verm-Giro", opening_balance="3000.00",
                opening_balance_date="2026-01-01")
    kk = _acc(client, h, "V18-Kreditkarte", typ="kreditkarte",
              opening_balance="-800.00", opening_balance_date="2026-01-01")

    s = client.get("/api/v1/dashboard/summary", headers=h, params={
        "date_from": "2026-01-01", "date_to": "2026-12-31",
        "account_ids": [giro["id"], kk["id"]]}).json()
    assert s["balance_total"] == 2200.0          # netto wie bisher
    assert s["assets_total"] == 3000.0
    assert s["liabilities_total"] == 800.0


# ------------------------------------------------- Neue Auswertungen (Block 3)

def test_forecast_counts_only_spending_accounts_and_known_charges(client, auth_headers):
    """Sparkonten sind nicht zum Ausgeben da und gehoeren nicht in "verfuegbar".
    Geschaetzt wird nichts: nur Saldo minus bereits terminierte Abbuchungen."""
    h = auth_headers
    giro = _acc(client, h, "V18-F-Giro", opening_balance="1500.00",
                opening_balance_date="2026-01-01")
    _acc(client, h, "V18-F-Tagesgeld", typ="tagesgeld",
         opening_balance="9000.00", opening_balance_date="2026-01-01")

    r = client.get("/api/v1/dashboard/forecast", headers=h,
                   params={"account_ids": [giro["id"]]}).json()
    assert r["balance_spending"] == 1500.0        # ohne die 9000 vom Tagesgeld
    assert r["accounts"] == ["V18-F-Giro"]
    assert r["available"] == r["balance_spending"] - r["upcoming_total"]
    assert r["period_from"] <= r["period_to"]


def test_income_sources_groups_by_counterparty(client, auth_headers):
    h = auth_headers
    giro = _acc(client, h, "V18-Quellen", opening_balance="0",
                opening_balance_date="2026-01-01")
    _tx(client, h, giro, "2026-05-01", "3000.00", "Arbeitgeber")
    _tx(client, h, giro, "2026-05-02", "1000.00", "Arbeitgeber")
    _tx(client, h, giro, "2026-05-03", "200.00", "Nebenjob")
    _tx(client, h, giro, "2026-05-04", "-90.00", "Supermarkt")   # Ausgabe zaehlt nicht

    r = client.get("/api/v1/dashboard/income-sources", headers=h, params={
        "date_from": "2026-05-01", "date_to": "2026-05-31",
        "account_ids": [giro["id"]]}).json()
    assert r["total"] == 4200.0
    top = r["rows"][0]
    assert top["counterparty"] == "Arbeitgeber"
    assert top["total"] == 4000.0                 # beide Gehaelter zusammengefasst
    assert round(top["share"]) == 95


def test_outliers_use_median_and_need_enough_history(client, auth_headers):
    """Median statt Mittelwert: ein einzelner Ausreisser zieht den Mittelwert
    selbst nach oben und versteckt sich darin. Und ohne genug Vergleichswerte
    gibt es keine Aussage."""
    h = auth_headers
    giro = _acc(client, h, "V18-Ausreisser", opening_balance="0",
                opening_balance_date="2026-01-01")
    for tag in ("02", "09", "16", "23"):
        _tx(client, h, giro, f"2026-03-{tag}", "-50.00", "Werkstatt V18")
    _tx(client, h, giro, "2026-03-27", "-600.00", "Werkstatt V18")
    # Zweiter Empfaenger mit zu wenig Historie -> darf NICHT auffallen
    _tx(client, h, giro, "2026-03-05", "-20.00", "Selten V18")
    _tx(client, h, giro, "2026-03-06", "-900.00", "Selten V18")

    r = client.get("/api/v1/dashboard/outliers", headers=h, params={
        "date_from": "2026-03-01", "date_to": "2026-03-31",
        "account_ids": [giro["id"]]}).json()
    namen = [x["counterparty"] for x in r["rows"]]
    assert "Werkstatt V18" in namen
    assert "Selten V18" not in namen              # nur zwei Buchungen = keine Aussage

    row = next(x for x in r["rows"] if x["counterparty"] == "Werkstatt V18")
    assert row["median"] == 50.0
    assert row["amount"] == 600.0
    assert row["factor"] == 12.0
