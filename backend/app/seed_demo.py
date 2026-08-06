"""Demo-Daten für den Demo-Stack (docker-compose.demo.yml, Port 8181).

Läuft NUR, wenn SEED_DEMO_DATA=true gesetzt ist (config.py) – in der
Produktivinstallation bleibt das inaktiv. Idempotent: prüft vorab, ob die
Demo-Konten schon existieren.

Legt eine realistische ~6-Monats-Historie an (Gehalt, Fixkosten, Einkäufe,
eine per IBAN automatisch erkennbare Umbuchung, eine nur als Vorschlag
erkennbare Bargeldabhebung, Split, Tags, Regeln, ein Budget und eine
wiederkehrende Kostenposition), damit sich beim ersten Login sofort alle
Funktionen zeigen lassen.
"""
import calendar
import random
from datetime import date, timedelta
from decimal import Decimal

from dateutil.relativedelta import relativedelta
from sqlalchemy.orm import Session

from .models import (
    Account,
    AccountRole,
    Budget,
    Category,
    RecurringItem,
    Rule,
    Tag,
    Transaction,
    TransactionSplit,
    TransactionTag,
    User,
)
from .security import hash_password
from .services.recurring import auto_link_item
from .services.transfers import auto_link_transfers, auto_mirror_category_transfers

DEMO_GIRO_IBAN = "DE12500105170648489890"
DEMO_TAGESGELD_IBAN = "DE44500105170912345678"
DEMO_GEMEINSAM_IBAN = "DE77500105170987654321"


def _cat(db: Session, name: str) -> Category | None:
    return db.query(Category).filter(Category.name == name, Category.scope == "global").first()


def run(db: Session) -> None:
    if db.query(Account).filter(Account.name == "Girokonto (Demo)").first():
        return  # schon befüllt

    admin = db.query(User).filter(User.is_admin.is_(True)).order_by(User.id).first()
    if admin is None:
        return

    today = date.today()
    start = today - relativedelta(months=6)

    def month_day(base_month: date, day: int) -> date | None:
        """Datum im Monat `base_month` (1. des Monats) am gewünschten Tag,
        auf Monatslänge begrenzt. None, wenn das in der Zukunft läge
        (relevant für den laufenden Monat)."""
        last_day = calendar.monthrange(base_month.year, base_month.month)[1]
        d = date(base_month.year, base_month.month, min(day, last_day))
        return d if d <= today else None

    giro = Account(name="Girokonto (Demo)", type="giro", bank="Musterbank", iban=DEMO_GIRO_IBAN,
                   opening_balance=Decimal("2500.00"), opening_balance_date=start)
    tagesgeld = Account(name="Tagesgeld (Demo)", type="tagesgeld", bank="Musterbank",
                        iban=DEMO_TAGESGELD_IBAN, opening_balance=Decimal("8000.00"),
                        opening_balance_date=start)
    bargeld = Account(name="Bargeld (Demo)", type="bargeld",
                      opening_balance=Decimal("60.00"), opening_balance_date=start)
    gemeinsam = Account(name="Gemeinsames Konto (Demo)", type="giro", bank="Musterbank",
                        iban=DEMO_GEMEINSAM_IBAN, opening_balance=Decimal("1200.00"),
                        opening_balance_date=start, is_household=True)
    # Kein eigener Bank-Feed (kein CSV-Import), nur die automatischen
    # Gegenbuchungen der Sparplan-Kategorie (v1.3b) – zeigt, dass "wie
    # Umbuchung behandeln" mit Zielkonto den Saldo tatsächlich fortschreibt.
    depot = Account(name="Depot (Demo)", type="depot", bank="Online Broker",
                    opening_balance=Decimal("0.00"), opening_balance_date=start)
    db.add_all([giro, tagesgeld, bargeld, gemeinsam, depot])
    db.flush()

    db.add_all([
        AccountRole(user_id=admin.id, account_id=giro.id, role="owner"),
        AccountRole(user_id=admin.id, account_id=tagesgeld.id, role="owner"),
        AccountRole(user_id=admin.id, account_id=bargeld.id, role="owner"),
        AccountRole(user_id=admin.id, account_id=gemeinsam.id, role="owner"),
        AccountRole(user_id=admin.id, account_id=depot.id, role="owner"),
    ])

    # Zweiter Demo-Nutzer, um Mehrbenutzer-/Rollenmodell zu zeigen (4.1)
    partner = db.query(User).filter(User.username == "partner").first()
    if partner is None:
        partner = User(username="partner", password_hash=hash_password("partner123"),
                       display_name="Partner (Demo)", is_admin=False)
        db.add(partner)
        db.flush()
    db.add(AccountRole(user_id=partner.id, account_id=gemeinsam.id, role="reader"))

    lebensmittel = _cat(db, "Lebensmittel")
    drogerie = _cat(db, "Drogerie")
    restaurant = _cat(db, "Restaurant & Lieferdienst")
    miete = _cat(db, "Miete / Wohnen")
    nebenkosten = _cat(db, "Nebenkosten & Energie")
    internet = _cat(db, "Internet & Mobilfunk")
    versicherungen = _cat(db, "Versicherungen")
    abos = _cat(db, "Abos & Streaming")
    auto = _cat(db, "Auto & Kraftstoff")
    freizeit = _cat(db, "Freizeit & Sport")
    gesundheit = _cat(db, "Gesundheit & Apotheke")
    kleidung = _cat(db, "Kleidung")
    elektronik = _cat(db, "Elektronik")
    gehalt = _cat(db, "Gehalt")
    bargeldauszahlung = _cat(db, "Bargeldauszahlung")
    kapitalertraege = _cat(db, "Kapitalerträge")
    sonstiges = _cat(db, "Sonstiges")

    # "Kapitalerträge" hier als Demo für "wie Umbuchung behandeln" (v1.3)
    # mit echtem Umbuchungs-Zielkonto (v1.3b): Sparplan-Ausführungen
    # bekommen automatisch eine Gegenbuchung im Depot, dessen Saldo dadurch
    # tatsächlich mitwächst.
    if kapitalertraege:
        kapitalertraege.is_transfer_like = True
        kapitalertraege.transfer_target_account_id = depot.id

    rng = random.Random(42)  # reproduzierbare Demo-Daten

    def add_tx(account, d: date, amount, counterparty, purpose, category=None,
               iban="", manual=False):
        tx = Transaction(
            account_id=account.id, booking_date=d, value_date=d,
            amount=Decimal(str(amount)), currency="EUR", amount_ref=Decimal(str(amount)),
            counterparty=counterparty, counterparty_iban=iban, purpose=purpose,
            category_id=category.id if category else None, is_manual=manual,
        )
        db.add(tx)
        return tx

    lebensmittel_shops = ["ALDI SUED", "REWE", "EDEKA", "LIDL"]
    drogerie_shops = ["dm-drogerie markt", "ROSSMANN"]
    restaurant_shops = ["Lieferando", "Restaurant Zur Post", "Pizzeria Roma"]
    tankstellen = ["Aral Tankstelle", "Shell Station"]

    for m in range(6, -1, -1):
        base_month = today.replace(day=1) - relativedelta(months=m)

        for day, amount, cp, purpose, cat in [
            (27, 2650.00, "Arbeitgeber GmbH", f"Gehalt {base_month.strftime('%m/%Y')}", gehalt),
            (3, -780.00, "Hausverwaltung Musterstadt", "Miete inkl. Nebenkosten", miete),
            (5, -95.00, "Stadtwerke Musterstadt", "Abschlag Strom/Gas", nebenkosten),
            (7, -34.99, "Telekom Deutschland", "Mobilfunk & Internet", internet),
            (8, -42.50, "Allianz Versicherung", "Haftpflicht/Hausrat", versicherungen),
            (10, -12.99, "Netflix", "Netflix Abo", abos),
            (10, -9.99, "Spotify", "Spotify Premium", abos),
            (12, -150.00, "Online Broker", "Ausführung Sparplan ETF MSCI World", kapitalertraege),
            (18, -100.00, "Eigenes Bargeldkonto", "Bargeldauszahlung", bargeldauszahlung),
        ]:
            d = month_day(base_month, day)
            if d:
                add_tx(giro, d, amount, cp, purpose, cat)

        # Umbuchung Giro -> Tagesgeld, per IBAN automatisch erkennbar (4.4)
        d = month_day(base_month, 15)
        if d:
            add_tx(giro, d, -300.00, "Eigenes Tagesgeldkonto", "Sparen", iban=DEMO_TAGESGELD_IBAN)
            add_tx(tagesgeld, d, 300.00, "Eigenes Girokonto", "Sparen", iban=DEMO_GIRO_IBAN)

        # In jedem zweiten Monat ein Teil zurück aufs Giro. Zeigt, dass die
        # Sparquote (v1.5.2) netto rechnet: 300 hin, 80 zurück = 220 gespart.
        if m % 2 == 0:
            d = month_day(base_month, 24)
            if d:
                add_tx(tagesgeld, d, -80.00, "Eigenes Girokonto", "Rückbuchung",
                      iban=DEMO_GIRO_IBAN)
                add_tx(giro, d, 80.00, "Eigenes Tagesgeldkonto", "Rückbuchung",
                      iban=DEMO_TAGESGELD_IBAN)

        # Bargeldabhebung Gegenseite (manuell, ohne IBAN -> landet als
        # Umbuchungs-Vorschlag zum manuellen Bestätigen, nicht automatisch)
        d = month_day(base_month, 18)
        if d:
            add_tx(bargeld, d, 100.00, "Abhebung Girokonto", "Bargeldauszahlung",
                  bargeldauszahlung, manual=True)
        d = month_day(base_month, 20)
        if d:
            add_tx(bargeld, d, -round(rng.uniform(8, 22), 2), "Bäckerei", "Frühstück",
                  freizeit, manual=True)

        # Lebensmittel: 4x im Monat
        for day in (2, 9, 16, 23):
            d = month_day(base_month, day)
            if d:
                add_tx(giro, d, -round(rng.uniform(18, 85), 2), rng.choice(lebensmittel_shops),
                      "Kartenzahlung", lebensmittel)

        d = month_day(base_month, 14)
        if d:
            add_tx(giro, d, -round(rng.uniform(8, 24), 2), rng.choice(drogerie_shops),
                  "Kartenzahlung", drogerie)

        for day in rng.sample(range(1, 27), rng.randint(1, 3)):
            d = month_day(base_month, day)
            if d:
                add_tx(giro, d, -round(rng.uniform(14, 48), 2), rng.choice(restaurant_shops),
                      "Kartenzahlung", restaurant)

        d = month_day(base_month, rng.randint(4, 24))
        if d:
            add_tx(giro, d, -round(rng.uniform(45, 78), 2), rng.choice(tankstellen),
                  "Kartenzahlung", auto)

        # Gemeinsames Konto: Einzahlungen beider Nutzer + eine gemeinsame Ausgabe.
        # Der aktuellste Monat bleibt bewusst unkategorisiert (realistischer
        # "Handlungsbedarf"-Fall), ältere Monate sind schon einsortiert.
        d = month_day(base_month, 4)
        if d:
            deposit_cat = None if m == 0 else sonstiges
            add_tx(gemeinsam, d, 400.00, "Max Mustermann", "Einzahlung gemeinsames Konto", deposit_cat)
            add_tx(gemeinsam, d, 350.00, "Partner Musterfrau", "Einzahlung gemeinsames Konto", deposit_cat)
        d = month_day(base_month, 10)
        if d:
            add_tx(gemeinsam, d, -85.00, "REWE", "Gemeinsamer Einkauf", lebensmittel)

    # Ein paar Extras: Gesundheit, Kleidung, Elektronik, unzugeordnete Buchungen
    # (für die Handlungsbedarf-Kachel), Split, Tags
    add_tx(giro, today - timedelta(days=40), -28.50, "Apotheke am Markt", "Rezept", gesundheit)
    add_tx(giro, today - timedelta(days=33), -89.90, "H&M", "Kleidung", kleidung)
    add_tx(giro, today - timedelta(days=20), -349.00, "Saturn", "Kopfhörer", elektronik)
    add_tx(giro, today - timedelta(days=5), -17.30, "Unbekannter Zahlungsempfänger", "Kartenzahlung")
    add_tx(giro, today - timedelta(days=3), -6.80, "Kiosk", "Kartenzahlung")

    split_tx = add_tx(giro, today - timedelta(days=9), -64.30, "REWE", "Kartenzahlung")
    db.flush()
    if lebensmittel and drogerie:
        db.add_all([
            TransactionSplit(transaction_id=split_tx.id, category_id=lebensmittel.id, amount=Decimal("-48.30")),
            TransactionSplit(transaction_id=split_tx.id, category_id=drogerie.id, amount=Decimal("-16.00")),
        ])

    urlaub_tag = Tag(name="Urlaub 2026")
    db.add(urlaub_tag)
    db.flush()
    urlaub_tx1 = add_tx(giro, today - timedelta(days=45), -68.00, "Hotel Seeblick", "Übernachtung", restaurant)
    urlaub_tx2 = add_tx(giro, today - timedelta(days=44), -32.00, "Restaurant am Hafen", "Abendessen", restaurant)
    db.flush()
    db.add_all([
        TransactionTag(transaction_id=urlaub_tx1.id, tag_id=urlaub_tag.id),
        TransactionTag(transaction_id=urlaub_tx2.id, tag_id=urlaub_tag.id),
    ])

    db.commit()

    # Regeln, damit die Regeln-Ansicht nicht leer ist und die Fake-Import-CSV
    # gleich Kategorien vorschlägt
    # Bewusst reichlich Regeln: die Freitextsuche in der Regelansicht (v1.5)
    # zeigt ihren Nutzen erst, wenn die Liste nicht mehr auf einen Blick passt.
    rule_defs = [
        ("Aldi", lebensmittel), ("Rewe", lebensmittel), ("Edeka", lebensmittel), ("Lidl", lebensmittel),
        ("Penny", lebensmittel), ("Netto Marken", lebensmittel), ("Kaufland", lebensmittel),
        ("Bäckerei", lebensmittel), ("Metzgerei", lebensmittel), ("Wochenmarkt", lebensmittel),
        ("dm-drogerie", drogerie), ("Rossmann", drogerie), ("Müller Drogerie", drogerie),
        ("Netflix", abos), ("Spotify", abos), ("Disney", abos), ("Zeitung", abos),
        ("Aral", auto), ("Shell", auto), ("Esso", auto), ("Total Energies", auto),
        ("Werkstatt", auto), ("TÜV", auto),
        ("Telekom", internet), ("Vodafone", internet), ("1&1", internet),
        ("Allianz", versicherungen), ("HUK", versicherungen), ("Debeka", versicherungen),
        ("Lieferando", restaurant), ("Pizzeria", restaurant), ("Restaurant", restaurant),
        ("Apotheke", gesundheit), ("Zahnarzt", gesundheit),
        ("Deutsche Bahn", _cat(db, "ÖPNV & Bahn")), ("Stadtwerke", nebenkosten),
        ("Fitnessstudio", freizeit), ("Kino", freizeit),
        ("H&M", kleidung), ("Zalando", kleidung),
        ("Saturn", elektronik), ("MediaMarkt", elektronik),
    ]
    for kw, cat in rule_defs:
        if cat and not db.query(Rule).filter(Rule.text_contains == kw).first():
            db.add(Rule(name=f"Demo: {kw}", category_id=cat.id, text_contains=kw))

    # Mehrere Budgets, damit die Budget-Fortschritt-Kachel (v1.5) alle drei
    # Ampelfarben zeigt statt einer einzelnen Zeile.
    budget_defs = [
        (lebensmittel, "400.00"), (restaurant, "120.00"), (auto, "90.00"),
        (drogerie, "40.00"), (freizeit, "80.00"),
        # Abschlag liegt fest bei 95 -> zuverlässig über Budget, damit auch
        # die rote Ampel vorkommt und nicht nur grün/gelb
        (nebenkosten, "90.00"),
    ]
    for cat, amount in budget_defs:
        if cat:
            db.add(Budget(category_id=cat.id, amount=Decimal(amount), period="month",
                          valid_from=start))

    # Wiederkehrende Kostenpositionen (v1.2). Die meisten werden unten
    # automatisch verknüpft, damit die Kachel "Fällig in den nächsten 30 Tagen"
    # (v1.5) echte Fälligkeiten zeigt. Netflix bleibt bewusst unverknüpft,
    # um "Erkennung ausführen" live vorführen zu können.
    recurring_defs = [
        ("Netflix", 1, "12.99", abos, "Netflix"),
        ("Miete", 1, "780.00", miete, "Hausverwaltung"),
        ("Strom/Gas Abschlag", 1, "95.00", nebenkosten, "Stadtwerke"),
        ("Mobilfunk & Internet", 1, "34.99", internet, "Telekom"),
        ("Haftpflicht/Hausrat", 1, "42.50", versicherungen, "Allianz"),
    ]
    recurring_items = {}
    for name, cycle, amount, cat, match in recurring_defs:
        if not cat:
            continue
        item = RecurringItem(name=name, cycle_months=cycle, expected_amount=Decimal(amount),
                             paying_account_id=giro.id, category_id=cat.id, match_text=match)
        db.add(item)
        recurring_items[name] = item

    db.commit()

    # alle außer Netflix verknüpfen -> sie bekommen dadurch eine nächste
    # Fälligkeit und tauchen in der Fälligkeiten-Kachel auf
    for name, item in recurring_items.items():
        if name != "Netflix":
            auto_link_item(db, item)
    db.commit()

    # Umbuchungserkennung für die per IBAN eindeutigen Paare (Giro<->Tagesgeld);
    # die Bargeldabhebung bleibt bewusst offen als Vorschlag zum Live-Vorführen.
    account_ids = [giro.id, tagesgeld.id, bargeld.id, gemeinsam.id, depot.id]
    auto_link_transfers(db, account_ids)

    # Die jüngste Sparplan-Buchung bleibt bewusst noch ohne Depot-Gegenbuchung,
    # damit sich "Umbuchungen erkennen" live vorführen lässt (Depot-Saldo
    # wächst sichtbar nach dem Klick, statt schon fertig verknüpft zu sein).
    held_back = None
    if kapitalertraege:
        held_back = (db.query(Transaction)
                     .filter(Transaction.account_id == giro.id,
                            Transaction.category_id == kapitalertraege.id,
                            Transaction.transfer_id.is_(None))
                     .order_by(Transaction.booking_date.desc()).first())
        if held_back:
            held_back.category_id = None

    auto_mirror_category_transfers(db, account_ids)

    if held_back:
        held_back.category_id = kapitalertraege.id
        db.commit()
