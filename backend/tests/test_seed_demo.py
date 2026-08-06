"""Regressionstest für das Demo-Seed-Skript (nur im Demo-Stack aktiv,
docker-compose.demo.yml) – läuft hier unabhängig von SEED_DEMO_DATA, damit
Schemaänderungen es nicht unbemerkt kaputt machen."""
from datetime import date

from app import seed_demo
from app.db import SessionLocal
from app.models import Account, Category, RecurringItem, Rule, Tag, Transaction, Transfer, User


def test_seed_demo_creates_consistent_data(client, auth_headers):
    # 'client' Fixture stellt sicher, dass App-Lifespan (Base-Schema, Basis-Seed) bereits lief
    with SessionLocal() as db:
        seed_demo.run(db)

        accounts = db.query(Account).filter(Account.name.like("%(Demo)%")).all()
        assert {a.name for a in accounts} == {
            "Girokonto (Demo)", "Tagesgeld (Demo)", "Bargeld (Demo)",
            "Gemeinsames Konto (Demo)", "Depot (Demo)",
        }
        depot = next(a for a in accounts if a.name == "Depot (Demo)")

        assert db.query(User).filter(User.username == "partner").first() is not None

        # Abrechnungsmonat wird auf den Gehaltstag gelegt (v1.6). Diese Zusicherung
        # steht hier, weil nur dieser Test den Seed wirklich ausführt – danach ist
        # er idempotent und die conftest-Fixture setzt die Einstellung zurück.
        from app.models import AppSetting
        from app.services.periods import SETTING_KEY
        assert db.get(AppSetting, SETTING_KEY).value["start_day"] == 27

        # keine Zukunftsdaten
        future = db.query(Transaction).filter(Transaction.booking_date > date.today()).count()
        assert future == 0

        assert db.query(Transaction).count() > 100
        assert db.query(Transfer).count() > 0  # IBAN-Paar wurde automatisch verknüpft
        assert db.query(Rule).count() >= 40    # genug, damit die Regelsuche etwas zu suchen hat
        assert db.query(RecurringItem).filter(RecurringItem.name == "Netflix").first() is not None
        assert db.query(Tag).filter(Tag.name == "Urlaub 2026").first() is not None

        # v1.3b: Sparplan-Kategorie hat ein Umbuchungs-Zielkonto (Depot), die
        # meisten Ausführungen sind schon dorthin gegengebucht (eine bewusst
        # nicht, zum Live-Vorführen von "Umbuchungen erkennen") und heben den
        # Depot-Saldo über den Anfangssaldo 0 hinaus an
        kapitalertraege = db.query(Category).filter(Category.name == "Kapitalerträge").first()
        assert kapitalertraege is not None
        assert kapitalertraege.transfer_target_account_id == depot.id
        depot_balance = depot.opening_balance + sum(
            (t.amount for t in db.query(Transaction).filter(Transaction.account_id == depot.id).all()),
            0)
        assert depot_balance > 0
        unmirrored = (db.query(Transaction)
                     .filter(Transaction.category_id == kapitalertraege.id,
                            Transaction.transfer_id.is_(None)).count())
        assert unmirrored == 1

        # idempotent: zweiter Lauf legt nichts doppelt an
        count_before = db.query(Transaction).count()
        seed_demo.run(db)
        assert db.query(Transaction).count() == count_before


def test_seed_demo_dashboard_unassigned_reasonable(client, auth_headers):
    """Handlungsbedarf-Kachel soll nicht mit Dutzenden Einträgen überladen sein.
    Scope auf die Demo-Konten selbst (Mehrfachauswahl-Filter), da die geteilte
    Test-Datenbank auch Konten aus anderen Tests enthält."""
    with SessionLocal() as db:
        seed_demo.run(db)
        demo_account_ids = [a.id for a in db.query(Account).filter(Account.name.like("%(Demo)%")).all()]

    h = auth_headers
    s = client.get("/api/v1/dashboard/summary", headers=h,
                   params={"account_ids": demo_account_ids}).json()
    assert 0 < s["unassigned_count"] <= 10


def test_seed_demo_fills_the_new_dashboard_tiles(client, auth_headers):
    """Die Demo soll die Kacheln aus v1.5 auch tatsächlich füllen – eine leere
    Kachel taugt nicht zum Vorführen."""
    from datetime import date, timedelta

    with SessionLocal() as db:
        seed_demo.run(db)
        demo_ids = [a.id for a in db.query(Account).filter(Account.name.like("%(Demo)%")).all()]
        private_ids = [a.id for a in db.query(Account)
                       .filter(Account.name.like("%(Demo)%"), Account.is_household.is_(False)).all()]

    h = auth_headers
    last_month = (date.today().replace(day=1) - timedelta(days=1)).strftime("%Y-%m")

    # Budget-Fortschritt: mehrere Zeilen und mehr als eine Ampelfarbe
    rows = client.get("/api/v1/budgets/status", headers=h,
                      params={"month": last_month, "account_ids": demo_ids}).json()["rows"]
    assert len(rows) >= 5
    assert len({r["ampel"] for r in rows}) >= 2

    # Fälligkeiten: mindestens eine verknüpfte Position mit nächstem Termin,
    # Netflix bleibt bewusst unverknüpft (zum Vorführen von "Erkennung ausführen")
    recurring = client.get("/api/v1/recurring-items/status", headers=h).json()["rows"]
    with_due = [r for r in recurring if r["next_due_estimate"]]
    assert len(with_due) >= 3
    netflix = next(r for r in recurring if r["name"] == "Netflix")
    assert netflix["next_due_estimate"] is None

    # Sparquote: echter Netto-Zufluss, in manchen Monaten durch eine
    # Rückbuchung gemindert – sonst wäre die v1.5.2-Logik nicht sichtbar
    sr = client.get("/api/v1/dashboard/savings-rate", headers=h,
                    params={"account_ids": private_ids}).json()
    saved = [v for v in sr["saved"] if v]
    assert saved and all(v > 0 for v in saved)
    assert len(set(saved)) > 1          # Rückbuchungsmonate weichen ab

    # Kategorie-Trend und Top-Empfänger haben Inhalt
    trend = client.get("/api/v1/dashboard/category-trend", headers=h,
                       params={"account_ids": demo_ids, "limit": 5}).json()
    assert len(trend["rows"]) >= 3
    tc = client.get("/api/v1/dashboard/top-counterparties", headers=h,
                    params={"account_ids": demo_ids, "limit": 10}).json()
    assert len(tc["rows"]) >= 5

    # Regelsuche findet über die Zielkategorie, nicht nur über den Namen
    hits = client.get("/api/v1/rules", headers=h, params={"q": "Lebensmittel"}).json()
    assert len(hits) >= 5


def test_seed_demo_shows_financial_month_and_bound_budgets(client, auth_headers):
    """Die Demo soll den Abrechnungsmonat (v1.6) vorführbar machen: Starttag am
    Gehaltstag, ein früher eingegangenes Gehalt von Hand korrigiert, und
    Budgets, die an ihr Konto gebunden sind."""
    with SessionLocal() as db:
        seed_demo.run(db)
        accounts = db.query(Account).filter(Account.name.like("%(Demo)%")).all()
    household = [a.id for a in accounts if a.is_household]
    private = [a.id for a in accounts if not a.is_household]

    h = auth_headers
    # Der Seed setzt den Starttag auf 27; die conftest-Fixture stellt vor jedem
    # Test den Kalendermonat wieder her, damit die Reihenfolge nichts entscheidet.
    period = client.put("/api/v1/budgets/period", headers=h, json={"start_day": 27}).json()
    assert period["start_day"] == 27

    # Gehälter: Regel greift, ein Monat ist von Hand zugeordnet
    salaries = client.get("/api/v1/transactions", headers=h,
                          params={"text": "Gehalt", "limit": 20}).json()["items"]
    salaries = [t for t in salaries if t["counterparty"] == "Arbeitgeber GmbH"]
    assert salaries, "keine Gehaltsbuchungen in den Demodaten"
    overridden = [t for t in salaries if t["financial_month_is_override"]]
    assert len(overridden) == 1
    early = overridden[0]
    assert early["booking_date"].endswith("-25")          # kam zwei Tage früher
    assert early["financial_month"] > early["booking_date"][:7]

    # ein Gehalt vom 27. fällt nach der Regel in den Folgemonat
    regular = next(t for t in salaries if t["booking_date"].endswith("-27"))
    assert regular["financial_month"] > regular["booking_date"][:7]
    assert regular["financial_month_is_override"] is False

    # Budgets erscheinen nur im Bereich ihres Kontos
    def rows(ids):
        return client.get("/api/v1/budgets/status", headers=h, params={
            "month": period["previous_period"], "account_ids": ids}).json()["rows"]

    gemeinsam = rows(household)
    persoenlich = rows(private)
    assert all(r["account_name"] == "Gemeinsames Konto (Demo)" for r in gemeinsam)
    assert all(r["account_name"] == "Girokonto (Demo)" for r in persoenlich)
    # dieselbe Kategorie mit zwei kontogebundenen Budgets verdrängt sich nicht
    gesamt = rows(household + private)
    lebensmittel = [r for r in gesamt if r["category_name"] == "Lebensmittel"]
    assert len(lebensmittel) == 2
    assert {r["budget"] for r in lebensmittel} == {150.0, 400.0}
