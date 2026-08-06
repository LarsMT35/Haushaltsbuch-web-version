"""Tests v1.6: Abrechnungsmonat ("Finanzmonat") und Budget-Kontobindung.

Wer sein Gehalt am 27. bekommt, lebt davon bis zum nächsten 27. Mit
`start_day = 27` läuft der Abrechnungsmonat vom 27. bis zum 26. und heißt nach
dem Monat, in dem er endet – das Gehalt ist damit das erste Ereignis der
Periode statt des letzten.

Das größte Risiko ist nicht die Rechnung selbst, sondern dass eine Auswertung
die Umstellung nicht mitmacht und zwei Kacheln sich widersprechen. Dagegen
prüft `test_all_endpoints_agree_on_period_boundaries`.
"""
import pytest

from app.services import periods


def _account(client, h, name, typ="giro", **kw):
    return client.post("/api/v1/accounts", headers=h,
                       json={"name": name, "type": typ, **kw}).json()


def _book(client, h, acc, d, amount, counterparty="Test", category_id=None):
    return client.post("/api/v1/transactions", headers=h, json={
        "account_id": acc["id"], "booking_date": d, "amount": amount,
        "counterparty": counterparty, "purpose": "Test", "category_id": category_id}).json()


def _cats(client, h):
    return {c["name"]: c for c in client.get("/api/v1/categories", headers=h).json()}


@pytest.fixture
def start_day_27(client, auth_headers):
    """Starttag auf 27 stellen und danach wieder auf den Kalendermonat zurück –
    die Test-DB ist sessionweit geteilt."""
    client.put("/api/v1/budgets/period", headers=auth_headers, json={"start_day": 27})
    yield 27
    client.put("/api/v1/budgets/period", headers=auth_headers, json={"start_day": 1})


# ------------------------------------------------------- reine Rechenlogik

@pytest.mark.parametrize("day,expected", [
    ("2026-07-26", "2026-07"),   # letzter Tag der Juli-Periode
    ("2026-07-27", "2026-08"),   # Zahltag startet die August-Periode
    ("2026-08-01", "2026-08"),
    ("2026-08-26", "2026-08"),
    ("2026-08-27", "2026-09"),
    ("2026-12-27", "2027-01"),   # Jahreswechsel
])
def test_period_key_with_shifted_start(day, expected):
    from datetime import date
    d = date(*(int(x) for x in day.split("-")))
    assert periods.period_key(d, 27) == expected


def test_period_key_start_day_one_is_calendar_month():
    from datetime import date
    for d in (date(2026, 1, 1), date(2026, 6, 15), date(2026, 12, 31)):
        assert periods.period_key(d, 1) == d.strftime("%Y-%m")


def test_period_bounds_and_range():
    from datetime import date
    assert periods.period_bounds("2026-08", 27) == (date(2026, 7, 27), date(2026, 8, 26))
    assert periods.period_bounds("2026-01", 27) == (date(2025, 12, 27), date(2026, 1, 26))
    assert periods.period_bounds("2026-02", 1) == (date(2026, 2, 1), date(2026, 2, 28))
    assert periods.period_range(date(2026, 7, 27), date(2026, 9, 5), 27) == \
        ["2026-08", "2026-09"]
    # der 27.09. startet bereits die Oktober-Periode
    assert periods.period_range(date(2026, 7, 27), date(2026, 9, 27), 27) == \
        ["2026-08", "2026-09", "2026-10"]


def test_start_day_is_clamped():
    assert periods.normalize_start_day(0) == 1
    assert periods.normalize_start_day(99) == 28   # darüber gäbe es Monate ohne den Tag
    assert periods.normalize_start_day("quatsch") == 1


# ------------------------------------------------------------- Endpunkte

def test_salary_at_month_end_counts_for_next_period(client, auth_headers, start_day_27):
    """Der gemeldete Fall: bis zum Gehaltseingang war die Bilanz immer negativ."""
    h = auth_headers
    giro = _account(client, h, "V16-Giro")
    cats = _cats(client, h)

    gehalt = _book(client, h, giro, "2026-07-27", "3000.00", "Arbeitgeber", cats["Gehalt"]["id"])
    _book(client, h, giro, "2026-07-20", "-200.00", "Markt", cats["Lebensmittel"]["id"])
    _book(client, h, giro, "2026-07-28", "-100.00", "Markt", cats["Lebensmittel"]["id"])
    _book(client, h, giro, "2026-08-10", "-300.00", "Vermieter", cats["Miete / Wohnen"]["id"])

    assert gehalt["financial_month"] == "2026-08"
    assert gehalt["financial_month_is_override"] is False

    s = client.get("/api/v1/dashboard/summary", headers=h, params={
        "date_from": "2026-06-01", "date_to": "2026-09-30", "account_ids": [giro["id"]]}).json()
    balance = {m["month"]: m["value"] for m in s["monthly_balance"]}
    # Gehalt + die Ausgaben ab dem 27. liegen zusammen in der August-Periode
    assert balance["2026-08"] == 2600.0
    assert balance["2026-07"] == -200.0


def test_manual_assignment_overrides_the_rule(client, auth_headers, start_day_27):
    """Kommt das Gehalt wegen eines Wochenendes früher, korrigiert man von Hand –
    ohne das Buchungsdatum anzufassen."""
    h = auth_headers
    giro = _account(client, h, "V16-Override")
    cats = _cats(client, h)
    # 25.07. läge nach der Regel noch im Juli
    tx = _book(client, h, giro, "2026-07-25", "3000.00", "Arbeitgeber", cats["Gehalt"]["id"])
    assert tx["financial_month"] == "2026-07"

    updated = client.put(f"/api/v1/transactions/{tx['id']}", headers=h,
                         json={"financial_month": "2026-08"}).json()
    assert updated["financial_month"] == "2026-08"
    assert updated["financial_month_is_override"] is True
    assert updated["booking_date"] == "2026-07-25"      # Datum unangetastet

    s = client.get("/api/v1/dashboard/summary", headers=h, params={
        "date_from": "2026-06-01", "date_to": "2026-09-30", "account_ids": [giro["id"]]}).json()
    assert {m["month"]: m["value"] for m in s["monthly_balance"]}["2026-08"] == 3000.0

    # Saldo und Kontostand bleiben unberührt – die Zuordnung ist reine Darstellung
    accs = client.get("/api/v1/accounts", headers=h).json()
    assert float(next(a for a in accs if a["id"] == giro["id"])["balance"]) == 3000.0

    # zurücksetzen stellt die Regel wieder her
    reset = client.put(f"/api/v1/transactions/{tx['id']}", headers=h,
                       json={"financial_month": None}).json()
    assert reset["financial_month"] == "2026-07"
    assert reset["financial_month_is_override"] is False


def test_invalid_financial_month_rejected(client, auth_headers):
    h = auth_headers
    giro = _account(client, h, "V16-Ungueltig")
    tx = _book(client, h, giro, "2026-07-10", "-10.00")
    r = client.put(f"/api/v1/transactions/{tx['id']}", headers=h,
                   json={"financial_month": "Juli 2026"})
    assert r.status_code == 400
    r = client.put(f"/api/v1/transactions/{tx['id']}", headers=h,
                   json={"financial_month": "2026-13"})
    assert r.status_code == 400


def test_all_endpoints_agree_on_period_boundaries(client, auth_headers, start_day_27):
    """Ein Datensatz durch alle Auswertungen – sie müssen identisch gruppieren.
    Andernfalls widersprechen sich zwei Kacheln auf derselben Startseite."""
    h = auth_headers
    giro = _account(client, h, "V16-Konsistenz")
    cats = _cats(client, h)
    lm = cats["Lebensmittel"]["id"]

    # jeweils direkt vor und nach der Periodengrenze
    _book(client, h, giro, "2026-07-26", "-40.00", "Markt", lm)    # Juli-Periode
    _book(client, h, giro, "2026-07-27", "-60.00", "Markt", lm)    # August-Periode
    client.post("/api/v1/budgets", headers=h, json={
        "category_id": lm, "account_id": giro["id"], "amount": "1000.00",
        "valid_from": "2026-01-01"})

    p = {"date_from": "2026-06-01", "date_to": "2026-09-30", "account_ids": [giro["id"]]}

    s = client.get("/api/v1/dashboard/summary", headers=h, params=p).json()
    summary_expenses = {m["month"]: m["value"] for m in s["monthly_expenses"]}

    trend = client.get("/api/v1/dashboard/category-trend", headers=h,
                       params={**p, "limit": 5}).json()
    trend_row = next(r for r in trend["rows"] if r["category_name"] == "Lebensmittel")
    trend_expenses = dict(zip(trend["months"], trend_row["values"]))

    budget_juli = client.get("/api/v1/budgets/status", headers=h, params={
        "month": "2026-07", "account_ids": [giro["id"]]}).json()["rows"]
    budget_august = client.get("/api/v1/budgets/status", headers=h, params={
        "month": "2026-08", "account_ids": [giro["id"]]}).json()["rows"]

    for label, juli, august in [
        ("summary", summary_expenses.get("2026-07"), summary_expenses.get("2026-08")),
        ("category_trend", trend_expenses.get("2026-07"), trend_expenses.get("2026-08")),
        ("budget", next(r["spent"] for r in budget_juli if r["category_id"] == lm),
                   next(r["spent"] for r in budget_august if r["category_id"] == lm)),
    ]:
        assert juli == 40.0, f"{label}: Juli erwartet 40.00, war {juli}"
        assert august == 60.0, f"{label}: August erwartet 60.00, war {august}"

    # kumulierter Verlauf beginnt am echten Periodenstart
    cum = client.get("/api/v1/dashboard/cumulative", headers=h, params={
        "month": "2026-08", "account_ids": [giro["id"]]}).json()
    assert cum["date_from"] == "2026-07-27"
    assert cum["date_to"] == "2026-08-26"
    assert cum["days"][0] == 27
    assert cum["previous_month"] == "2026-07"


def test_year_comparison_follows_the_period(client, auth_headers, start_day_27):
    """Eine Buchung am 27.12. gehört zur Januar-Periode – und damit ins Folgejahr."""
    h = auth_headers
    giro = _account(client, h, "V16-Jahreswechsel")
    cats = _cats(client, h)
    _book(client, h, giro, "2025-12-27", "-70.00", "Markt", cats["Elektronik"]["id"])

    yc = client.get("/api/v1/dashboard/year-comparison", headers=h,
                    params={"account_ids": [giro["id"]]}).json()
    row = next(r for r in yc["rows"] if r["category_name"] == "Elektronik")
    assert dict(zip(yc["years"], row["values"]))[2026] == 70.0


def test_setting_defaults_to_calendar_month(client, auth_headers):
    """Ohne Konfiguration bleibt alles wie bisher – bestehende Installationen
    ändern sich durch das Update nicht."""
    r = client.get("/api/v1/budgets/period", headers=auth_headers).json()
    assert r["start_day"] == 1
    from datetime import date
    today = date.today()
    assert r["current_period"] == today.strftime("%Y-%m")
    assert r["current_from"].endswith("-01")


# --------------------------------------------------- Budget-Kontobindung

def test_account_bound_budget_only_counts_its_own_account(client, auth_headers):
    """Ein Budget auf dem Girokonto darf sich nicht an Buchungen anderer
    Konten verbrauchen – und nur im passenden Bereich erscheinen."""
    h = auth_headers
    haus = _account(client, h, "V16-Haushalt", is_household=True)
    priv = _account(client, h, "V16-Privat")
    cats = _cats(client, h)
    cat = cats["Motorrad"]["id"]

    client.post("/api/v1/budgets", headers=h, json={
        "category_id": cat, "account_id": priv["id"], "amount": "150.00",
        "valid_from": "2026-01-01"})
    client.post("/api/v1/budgets", headers=h, json={
        "category_id": cat, "account_id": haus["id"], "amount": "300.00",
        "valid_from": "2026-01-01"})

    _book(client, h, priv, "2026-11-05", "-90.00", "Verein", cat)
    _book(client, h, haus, "2026-11-06", "-120.00", "Verein", cat)

    def rows(ids):
        return [r for r in client.get("/api/v1/budgets/status", headers=h, params={
            "month": "2026-11", "account_ids": ids}).json()["rows"] if r["category_id"] == cat]

    # Bereich "Persönlich": nur das Privatkonto-Budget, verbraucht nur dort
    r_priv = rows([priv["id"]])
    assert len(r_priv) == 1
    assert (r_priv[0]["budget"], r_priv[0]["spent"]) == (150.0, 90.0)
    assert r_priv[0]["account_name"] == "V16-Privat"

    # Bereich "Gemeinsam": nur das Haushaltskonto-Budget
    r_haus = rows([haus["id"]])
    assert len(r_haus) == 1
    assert (r_haus[0]["budget"], r_haus[0]["spent"]) == (300.0, 120.0)

    # Bereich "Gesamt": beide, jedes mit seinem eigenen Verbrauch – vorher
    # verdrängten sie sich gegenseitig und einer maß am falschen Konto
    r_all = rows([priv["id"], haus["id"]])
    assert len(r_all) == 2
    assert sorted((r["budget"], r["spent"]) for r in r_all) == [(150.0, 90.0), (300.0, 120.0)]


def test_global_budget_still_spans_the_current_selection(client, auth_headers):
    """Ein Budget ohne Konto gilt übergreifend und misst sich an allen Konten
    der aktuellen Auswahl."""
    h = auth_headers
    a = _account(client, h, "V16-Global-A")
    b = _account(client, h, "V16-Global-B")
    cats = _cats(client, h)
    cat = cats["Geschenke & Spenden"]["id"]
    client.post("/api/v1/budgets", headers=h, json={
        "category_id": cat, "amount": "200.00", "valid_from": "2026-01-01"})
    _book(client, h, a, "2026-11-10", "-30.00", "Laden", cat)
    _book(client, h, b, "2026-11-11", "-50.00", "Laden", cat)

    def spent(ids):
        rows = client.get("/api/v1/budgets/status", headers=h, params={
            "month": "2026-11", "account_ids": ids}).json()["rows"]
        return next(r["spent"] for r in rows if r["category_id"] == cat)

    assert spent([a["id"]]) == 30.0
    assert spent([a["id"], b["id"]]) == 80.0


def test_manual_assignment_is_visible_in_its_period_range(client, auth_headers, start_day_27):
    """Regression: Die Endpunkte filterten per SQL nach Buchungsdatum und
    gruppierten erst danach nach Abrechnungsmonat. Ein am 25.07. eingegangenes,
    dem August zugeordnetes Gehalt fiel damit aus dem August-Zeitraum
    (27.07.–26.08.) heraus – also genau aus der Ansicht, für die die Zuordnung
    gedacht ist. Die Startseite zeigte 0 € Einnahmen statt 3000 €.
    """
    h = auth_headers
    giro = _account(client, h, "V16-Rangefix")
    cats = _cats(client, h)

    tx = _book(client, h, giro, "2026-07-25", "3000.00", "Arbeitgeber", cats["Gehalt"]["id"])
    client.put(f"/api/v1/transactions/{tx['id']}", headers=h, json={"financial_month": "2026-08"})
    _book(client, h, giro, "2026-08-10", "-300.00", "Vermieter", cats["Miete / Wohnen"]["id"])
    _book(client, h, giro, "2026-07-20", "-50.00", "Markt", cats["Lebensmittel"]["id"])

    per = client.get("/api/v1/budgets/period", headers=h).json()

    def summary(date_from, date_to):
        return client.get("/api/v1/dashboard/summary", headers=h, params={
            "date_from": date_from, "date_to": date_to, "account_ids": [giro["id"]]}).json()

    # August-Periode: das zugeordnete Gehalt zählt mit, obwohl es davor gebucht wurde
    august = summary(per["current_from"], per["current_to"])
    assert august["income"] == 3000.0
    assert august["expenses"] == 300.0

    # Juli-Periode: es taucht NICHT zusätzlich hier auf
    juli = summary(per["previous_from"], per["previous_to"])
    assert juli["income"] == 0.0
    assert juli["expenses"] == 50.0

    # Teilzeitraum: wer ausdrücklich den 5.–20.08. abfragt, will den Ausschnitt
    # sehen – nicht ein Gehalt vom 25.07., nur weil es dem August zugeordnet ist
    teil = summary("2026-08-05", "2026-08-20")
    assert teil["income"] == 0.0
    assert teil["expenses"] == 300.0


def test_manual_assignment_reaches_budget_and_trend(client, auth_headers, start_day_27):
    """Dieselbe Lücke gab es im Budget-Status und im Kategorie-Trend."""
    h = auth_headers
    giro = _account(client, h, "V16-Rangefix2")
    cats = _cats(client, h)
    cat = cats["Elektronik"]["id"]
    client.post("/api/v1/budgets", headers=h, json={
        "category_id": cat, "account_id": giro["id"], "amount": "500.00",
        "valid_from": "2026-01-01"})

    # weit außerhalb des August-Zeitraums gebucht, aber dorthin zugeordnet
    tx = _book(client, h, giro, "2026-05-02", "-120.00", "Saturn", cat)
    client.put(f"/api/v1/transactions/{tx['id']}", headers=h, json={"financial_month": "2026-08"})

    rows = client.get("/api/v1/budgets/status", headers=h, params={
        "month": "2026-08", "account_ids": [giro["id"]]}).json()["rows"]
    assert next(r["spent"] for r in rows if r["category_id"] == cat) == 120.0
    # im Mai zählt sie folgerichtig nicht mehr
    rows_mai = client.get("/api/v1/budgets/status", headers=h, params={
        "month": "2026-05", "account_ids": [giro["id"]]}).json()["rows"]
    assert next((r["spent"] for r in rows_mai if r["category_id"] == cat), 0.0) == 0.0

    per = client.get("/api/v1/budgets/period", headers=h).json()
    trend = client.get("/api/v1/dashboard/category-trend", headers=h, params={
        "date_from": "2026-01-01", "date_to": per["current_to"],
        "account_ids": [giro["id"]], "limit": 10}).json()
    row = next(r for r in trend["rows"] if r["category_name"] == "Elektronik")
    per_month = dict(zip(trend["months"], row["values"]))
    assert per_month["2026-08"] == 120.0
    assert per_month.get("2026-05", 0.0) == 0.0


def test_covered_periods_only_counts_fully_contained_ones():
    from datetime import date
    from app.services.periods import covered_periods
    # deckt die August-Periode (27.07.–26.08.) vollständig ab
    assert "2026-08" in covered_periods(date(2026, 7, 27), date(2026, 8, 26), 27)
    # Ausschnitt daraus: nicht abgedeckt
    assert covered_periods(date(2026, 8, 5), date(2026, 8, 20), 27) == set()
    # Kalendermonat als Voreinstellung verhält sich unverändert
    assert covered_periods(date(2026, 8, 1), date(2026, 8, 31), 1) == {"2026-08"}
