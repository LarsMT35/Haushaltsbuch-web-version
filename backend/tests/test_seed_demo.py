"""Regressionstest für das Demo-Seed-Skript (nur im Demo-Stack aktiv,
docker-compose.demo.yml) – läuft hier unabhängig von SEED_DEMO_DATA, damit
Schemaänderungen es nicht unbemerkt kaputt machen."""
from datetime import date

from app import seed_demo
from app.db import SessionLocal
from app.models import Account, RecurringItem, Rule, Tag, Transaction, Transfer, User


def test_seed_demo_creates_consistent_data(client, auth_headers):
    # 'client' Fixture stellt sicher, dass App-Lifespan (Base-Schema, Basis-Seed) bereits lief
    with SessionLocal() as db:
        seed_demo.run(db)

        accounts = db.query(Account).filter(Account.name.like("%(Demo)%")).all()
        assert {a.name for a in accounts} == {
            "Girokonto (Demo)", "Tagesgeld (Demo)", "Bargeld (Demo)", "Gemeinsames Konto (Demo)",
        }

        assert db.query(User).filter(User.username == "partner").first() is not None

        # keine Zukunftsdaten
        future = db.query(Transaction).filter(Transaction.booking_date > date.today()).count()
        assert future == 0

        assert db.query(Transaction).count() > 100
        assert db.query(Transfer).count() > 0  # IBAN-Paar wurde automatisch verknüpft
        assert db.query(Rule).count() >= 10
        assert db.query(RecurringItem).filter(RecurringItem.name == "Netflix").first() is not None
        assert db.query(Tag).filter(Tag.name == "Urlaub 2026").first() is not None

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
