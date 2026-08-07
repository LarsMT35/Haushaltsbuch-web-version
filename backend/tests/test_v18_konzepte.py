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


# ----------------------------- Sparbewegung: EINE Regel für alle Kacheln

@pytest.mark.parametrize("mit_zielkonto", [True, False])
def test_savings_movement_identical_in_kpi_and_rate(client, auth_headers, mit_zielkonto):
    """Die Zahl "Umbuchungen (Sparkonten)" in den Kennzahlen und der Balken
    "tatsaechlich gespart" in der Sparquote sind dieselbe Groesse - sie
    muessen fuer denselben Zeitraum denselben Wert liefern.

    Ohne hinterlegtes Zielkonto drehte frueher nur EINE der beiden Kacheln das
    Vorzeichen: derselbe Sparplan stand als -250 EUR in den Kennzahlen und als
    +250 EUR in der Sparquote.
    """
    h = auth_headers
    suffix = "mit" if mit_zielkonto else "ohne"
    giro = _acc(client, h, f"V18-SD-Giro-{suffix}", opening_balance="5000",
                opening_balance_date="2026-01-01")
    depot = _acc(client, h, f"V18-SD-Depot-{suffix}", typ="depot",
                 opening_balance="0", opening_balance_date="2026-01-01")
    cat = client.post("/api/v1/categories", headers=h, json={
        "name": f"V18-Sparplan-{suffix}", "scope": "personal", "is_transfer_like": True,
        "transfer_target_account_id": depot["id"] if mit_zielkonto else None}).json()

    _tx(client, h, giro, "2026-09-05", "4000.00", "Gehalt")
    _tx(client, h, giro, "2026-09-10", "-250.00", "Sparplan", cat=cat["id"])

    p = {"date_from": "2026-09-01", "date_to": "2026-09-30",
         "account_ids": [giro["id"], depot["id"]]}
    kpi = client.get("/api/v1/dashboard/summary", headers=h, params=p).json()
    sq = client.get("/api/v1/dashboard/savings-rate", headers=h, params=p).json()
    i = sq["months"].index("2026-09")

    bewegung = sum(m["value"] for m in kpi["savings_movement"])
    assert bewegung == sq["saved"][i], "Kennzahlen und Sparquote widersprechen sich"
    # 250 EUR in einen Sparplan sind 250 EUR gespart – positiv, in beiden Faellen
    assert bewegung == 250.0


def test_savings_delta_does_not_double_count_both_sides(client, auth_headers):
    """Mit Zielkonto entsteht eine Gegenbuchung im Depot. Zahlende und
    empfangende Seite duerfen sich weder aufheben noch verdoppeln."""
    h = auth_headers
    giro = _acc(client, h, "V18-Doppel-Giro", opening_balance="5000",
                opening_balance_date="2026-01-01")
    depot = _acc(client, h, "V18-Doppel-Depot", typ="depot",
                 opening_balance="0", opening_balance_date="2026-01-01")
    cat = client.post("/api/v1/categories", headers=h, json={
        "name": "V18-Doppel-Sparplan", "scope": "personal", "is_transfer_like": True,
        "transfer_target_account_id": depot["id"]}).json()
    _tx(client, h, giro, "2026-10-10", "-300.00", "Sparplan", cat=cat["id"])

    p = {"date_from": "2026-10-01", "date_to": "2026-10-31",
         "account_ids": [giro["id"], depot["id"]]}
    kpi = client.get("/api/v1/dashboard/summary", headers=h, params=p).json()
    bewegung = sum(m["value"] for m in kpi["savings_movement"])
    assert bewegung == 300.0            # einmal, nicht 0 und nicht 600
    # und der Depot-Saldo ist tatsaechlich gewachsen
    depot_row = next(a for a in kpi["accounts"] if a["account_id"] == depot["id"])
    assert depot_row["balance"] == 300.0


# ------------------- Sparkonto-Erkennung: Kontotyp und Archivierung (v1.8.2)

def test_archived_savings_account_still_counts_as_saving(client, auth_headers):
    """Archivieren blendet ein Konto aus, loescht aber nichts. Frueher fiel eine
    Sparbuchung damit aus den Kennzahlen heraus (die Sparquote zaehlte sie
    weiter) - Archivieren haette die Historie umgeschrieben."""
    h = auth_headers
    giro = _acc(client, h, "V182-Giro", opening_balance="5000",
                opening_balance_date="2026-01-01")
    depot = _acc(client, h, "V182-Depot", typ="depot", opening_balance="0",
                 opening_balance_date="2026-01-01")
    cat = client.post("/api/v1/categories", headers=h, json={
        "name": "V182-Sparplan", "scope": "personal", "is_transfer_like": True,
        "transfer_target_account_id": depot["id"]}).json()
    _tx(client, h, giro, "2026-11-05", "-300.00", "Sparplan", cat=cat["id"])

    p = {"date_from": "2026-11-01", "date_to": "2026-11-30",
         "account_ids": [giro["id"], depot["id"]]}
    vorher = client.get("/api/v1/dashboard/summary", headers=h, params=p).json()
    assert sum(m["value"] for m in vorher["savings_movement"]) == 300.0

    client.delete(f"/api/v1/accounts/{depot['id']}", headers=h)      # archivieren

    nachher = client.get("/api/v1/dashboard/summary", headers=h, params=p).json()
    sq = client.get("/api/v1/dashboard/savings-rate", headers=h, params=p).json()
    assert sum(m["value"] for m in nachher["savings_movement"]) == 300.0
    assert sum(sq["saved"]) == 300.0            # beide Kacheln weiterhin einig
    # das archivierte Konto taucht aber nicht mehr in der Saldenliste auf
    assert depot["id"] not in [a["account_id"] for a in nachher["accounts"]]


def test_non_savings_target_account_is_flagged(client, auth_headers):
    """Zeigt eine "wie Umbuchung"-Kategorie auf ein Girokonto statt auf ein
    Sparkonto, zaehlt das Geld weder als Ausgabe noch als Sparen - es
    verschwindet lautlos. Die Kategorienliste muss das kenntlich machen
    koennen, also den Typ des Zielkontos mitliefern."""
    h = auth_headers
    giro = _acc(client, h, "V182-Ziel-Giro", opening_balance="5000",
                opening_balance_date="2026-01-01")
    falsch = _acc(client, h, "V182-Depot-falsch-angelegt", typ="giro",
                  opening_balance="0", opening_balance_date="2026-01-01")
    cat = client.post("/api/v1/categories", headers=h, json={
        "name": "V182-Aktien", "scope": "personal", "is_transfer_like": True,
        "transfer_target_account_id": falsch["id"]}).json()
    _tx(client, h, giro, "2026-12-05", "-400.00", "Sparplan", cat=cat["id"])

    zeile = next(c for c in client.get("/api/v1/categories", headers=h).json()
                 if c["id"] == cat["id"])
    assert zeile["transfer_target_type"] == "giro"          # -> Oberflaeche warnt
    assert zeile["transfer_target_name"] == "V182-Depot-falsch-angelegt"

    # ... und genau das ist der Effekt: nichts zaehlt als Sparen
    s = client.get("/api/v1/dashboard/summary", headers=h, params={
        "date_from": "2026-12-01", "date_to": "2026-12-31",
        "account_ids": [giro["id"], falsch["id"]]}).json()
    assert sum(m["value"] for m in s["savings_movement"]) == 0.0
    assert s["expenses"] == 0.0                             # als Umbuchung auch keine Ausgabe
