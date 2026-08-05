"""Tests v1.5: Regel-Freitextsuche, neue Dashboard-Auswertungen,
optionale Ollama-Schnittstelle."""
import calendar
from datetime import date, timedelta


def _account(client, h, name, **kw):
    return client.post("/api/v1/accounts", headers=h,
                       json={"name": name, "type": kw.pop("type", "giro"), **kw}).json()


def _cats(client, h):
    return {c["name"]: c for c in client.get("/api/v1/categories", headers=h).json()}


# ------------------------------------------------------- Regel-Freitextsuche

def test_rule_search_matches_name_criteria_and_category(client, auth_headers):
    h = auth_headers
    cats = _cats(client, h)
    client.post("/api/v1/rules", headers=h, json={
        "name": "V15 Supermarkt Nord", "category_id": cats["Lebensmittel"]["id"],
        "counterparty_contains": "ZWIEBELHOF"})
    client.post("/api/v1/rules", headers=h, json={
        "name": "V15 Streamingdienst", "category_id": cats["Abos & Streaming"]["id"],
        "text_contains": "KLANGWERK", "iban_equals": "DE99V15SUCHE0001"})

    def names(**params):
        return [r["name"] for r in client.get("/api/v1/rules", headers=h, params=params).json()]

    # Name
    assert "V15 Supermarkt Nord" in names(q="supermarkt nord")
    # Kriterium Gegenpartei, Groß-/Kleinschreibung egal
    assert names(q="zwiebelhof") == ["V15 Supermarkt Nord"]
    # Kriterium Verwendungszweck
    assert names(q="klangwerk") == ["V15 Streamingdienst"]
    # IBAN
    assert names(q="V15SUCHE0001") == ["V15 Streamingdienst"]
    # Zielkategorie – findet Regeln, ohne den Händlernamen zu kennen
    assert "V15 Streamingdienst" in names(q="Abos & Streaming")
    # Treffer ohne Ergebnis liefert leere Liste statt aller Regeln
    assert names(q="gibtesnichtxyz") == []
    # ohne q weiterhin alles
    assert len(names()) >= 2


def test_rule_search_active_filter(client, auth_headers):
    h = auth_headers
    cats = _cats(client, h)
    r = client.post("/api/v1/rules", headers=h, json={
        "name": "V15 Inaktiv", "category_id": cats["Sonstiges"]["id"],
        "text_contains": "V15INAKTIVMARKER"}).json()
    client.put(f"/api/v1/rules/{r['id']}", headers=h, json={"active": False})

    assert client.get("/api/v1/rules", headers=h,
                      params={"q": "V15INAKTIVMARKER", "active": True}).json() == []
    hits = client.get("/api/v1/rules", headers=h,
                      params={"q": "V15INAKTIVMARKER", "active": False}).json()
    assert [x["name"] for x in hits] == ["V15 Inaktiv"]


# ------------------------------------------------- neue Dashboard-Kacheln

def test_cumulative_month_vs_previous(client, auth_headers):
    """Kumulierter Monatsverlauf: laufende Summe, Vormonat als Vergleich,
    Zukunft bleibt leer statt flach weiterzulaufen."""
    h = auth_headers
    acc = _account(client, h, "V15-Kumuliert")
    cats = _cats(client, h)
    lm = cats["Lebensmittel"]["id"]

    for d, amount in [("2026-03-05", "-40.00"), ("2026-03-20", "-60.00"),
                      ("2026-04-10", "-25.00"), ("2026-04-25", "-75.00")]:
        client.post("/api/v1/transactions", headers=h, json={
            "account_id": acc["id"], "booking_date": d, "amount": amount,
            "counterparty": "Markt", "category_id": lm})

    r = client.get("/api/v1/dashboard/cumulative", headers=h,
                   params={"month": "2026-04", "account_ids": [acc["id"]]}).json()
    assert r["month"] == "2026-04" and r["previous_month"] == "2026-03"
    assert len(r["days"]) == 30
    # laufende Summe April: ab dem 10. 25 €, ab dem 25. 100 €
    assert r["current"][8] == 0.0
    assert r["current"][9] == 25.0
    assert r["current"][24] == 100.0
    assert r["current"][-1] == 100.0
    # März als Vergleichslinie: ab dem 5. 40 €, ab dem 20. 100 €
    assert r["previous"][4] == 40.0
    assert r["previous"][19] == 100.0


def test_cumulative_stops_at_today_for_current_month(client, auth_headers):
    h = auth_headers
    acc = _account(client, h, "V15-Kumuliert-Aktuell")
    today = date.today()
    if today.day < calendar.monthrange(today.year, today.month)[1]:
        r = client.get("/api/v1/dashboard/cumulative", headers=h,
                       params={"account_ids": [acc["id"]]}).json()
        assert r["current"][today.day - 1] is not None
        assert r["current"][today.day] is None  # morgen noch unbekannt


def test_category_trend_top_categories_per_month(client, auth_headers):
    h = auth_headers
    acc = _account(client, h, "V15-Trend")
    cats = _cats(client, h)
    gross, klein = cats["Miete / Wohnen"]["id"], cats["Drogerie"]["id"]

    for d, amount, cat in [("2026-02-01", "-800.00", gross), ("2026-03-01", "-900.00", gross),
                           ("2026-02-05", "-10.00", klein), ("2026-03-05", "-20.00", klein)]:
        client.post("/api/v1/transactions", headers=h, json={
            "account_id": acc["id"], "booking_date": d, "amount": amount,
            "counterparty": "Test", "category_id": cat})

    r = client.get("/api/v1/dashboard/category-trend", headers=h, params={
        "date_from": "2026-02-01", "date_to": "2026-03-31",
        "account_ids": [acc["id"]], "limit": 5}).json()
    assert r["months"] == ["2026-02", "2026-03"]
    rows = {row["category_name"]: row["values"] for row in r["rows"]}
    assert rows["Miete / Wohnen"] == [800.0, 900.0]
    assert rows["Drogerie"] == [10.0, 20.0]
    # nach Gesamtsumme sortiert -> die größte Kategorie zuerst
    assert r["rows"][0]["category_name"] == "Miete / Wohnen"

    # limit begrenzt die Reihen
    small = client.get("/api/v1/dashboard/category-trend", headers=h, params={
        "date_from": "2026-02-01", "date_to": "2026-03-31",
        "account_ids": [acc["id"]], "limit": 1}).json()
    assert len(small["rows"]) == 1


def test_top_counterparties(client, auth_headers):
    h = auth_headers
    acc = _account(client, h, "V15-Haendler")
    for d, amount, cp in [("2026-05-02", "-30.00", "Baumarkt Sued"),
                          ("2026-05-09", "-45.00", "Baumarkt Sued"),
                          ("2026-05-11", "-60.00", "Fahrradladen"),
                          ("2026-05-12", "1000.00", "Arbeitgeber")]:
        client.post("/api/v1/transactions", headers=h, json={
            "account_id": acc["id"], "booking_date": d, "amount": amount, "counterparty": cp})

    r = client.get("/api/v1/dashboard/top-counterparties", headers=h, params={
        "date_from": "2026-05-01", "date_to": "2026-05-31", "account_ids": [acc["id"]]}).json()
    rows = {x["counterparty"]: x for x in r["rows"]}
    assert rows["Baumarkt Sued"]["total"] == 75.0 and rows["Baumarkt Sued"]["count"] == 2
    assert rows["Fahrradladen"]["total"] == 60.0
    assert "Arbeitgeber" not in rows          # Einnahmen sind keine Ausgaben
    assert r["rows"][0]["counterparty"] == "Baumarkt Sued"  # absteigend sortiert


def test_budget_status_accepts_multiple_accounts(client, auth_headers):
    """Budget-Kachel muss der Bereichstrennung des Dashboards folgen können."""
    h = auth_headers
    a1 = _account(client, h, "V15-Budget-A")
    a2 = _account(client, h, "V15-Budget-B")
    cats = _cats(client, h)
    cat = cats["Freizeit & Sport"]["id"]
    client.post("/api/v1/budgets", headers=h, json={
        "category_id": cat, "amount": "300.00", "valid_from": "2026-01-01"})

    for acc, amount in [(a1, "-50.00"), (a2, "-70.00")]:
        client.post("/api/v1/transactions", headers=h, json={
            "account_id": acc["id"], "booking_date": "2026-09-10", "amount": amount,
            "counterparty": "Verein", "category_id": cat})

    def spent(**params):
        s = client.get("/api/v1/budgets/status", headers=h,
                       params={"month": "2026-09", **params}).json()
        return next(r for r in s["rows"] if r["category_id"] == cat)["spent"]

    assert spent(account_id=a1["id"]) == 50.0
    assert spent(account_ids=[a1["id"]]) == 50.0
    assert spent(account_ids=[a1["id"], a2["id"]]) == 120.0


# ------------------------------------------------- Ollama-Schnittstelle

def test_ai_disabled_by_default(client, auth_headers):
    """Ohne OLLAMA_URL ist die Funktion aus – die App bleibt voll nutzbar."""
    h = auth_headers
    r = client.get("/api/v1/ai/status", headers=h).json()
    assert r["enabled"] is False and r["reachable"] is False
    assert "OLLAMA_URL" in r["detail"]

    r = client.post("/api/v1/ai/suggest-categories", headers=h, json={"limit": 5})
    assert r.status_code == 503


def test_ai_suggestions_reject_hallucinated_categories(monkeypatch):
    """Erfundene Kategorien und fremde Buchungs-IDs werden verworfen, statt
    ungeprüft übernommen zu werden."""
    from app.services import ai

    txs = [{"id": 1, "counterparty": "Aldi", "purpose": "Einkauf", "amount": -20.0},
           {"id": 2, "counterparty": "Shell", "purpose": "Tanken", "amount": -60.0}]
    categories = ["Lebensmittel", "Auto & Kraftstoff"]

    monkeypatch.setattr(ai, "complete_json", lambda *a, **k: {"suggestions": [
        {"id": 1, "category": "lebensmittel", "confidence": 0.9, "reason": "Supermarkt"},
        {"id": 2, "category": "Ausgedachte Kategorie", "confidence": 1.0, "reason": "erfunden"},
        {"id": 999, "category": "Lebensmittel", "confidence": 1.0, "reason": "fremde ID"},
        {"id": 2, "category": "Auto & Kraftstoff", "confidence": 5.0, "reason": "Tankstelle"},
    ]})
    out = ai.suggest_categories(txs, categories)

    assert [o["id"] for o in out] == [1, 2]
    assert out[0]["category"] == "Lebensmittel"      # Schreibweise normalisiert
    assert out[1]["category"] == "Auto & Kraftstoff"
    assert out[1]["confidence"] == 1.0               # auf 0..1 begrenzt


def test_ai_extract_json_tolerates_markdown_fences():
    from app.services import ai
    assert ai._extract_json('```json\n{"a": 1}\n```') == {"a": 1}
    assert ai._extract_json('Gerne! {"a": 2} – passt das?') == {"a": 2}


def test_ai_status_reports_unreachable_instance(monkeypatch, client, auth_headers):
    from app.config import settings
    from app.services import ai

    monkeypatch.setattr(settings, "ollama_url", "http://127.0.0.1:59999")

    def boom():
        raise RuntimeError("Connection refused")
    monkeypatch.setattr(ai, "list_models", boom)

    r = client.get("/api/v1/ai/status", headers=auth_headers).json()
    assert r["enabled"] is True and r["reachable"] is False
    assert "nicht erreichbar" in r["detail"]
