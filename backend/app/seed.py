"""Startdaten: Admin-Konto, Basis-Kategorien, Importprofile Sparkasse + ING.

Alles davon ist Konfiguration in der DB (Prinzip 1) und kann in der App
geändert werden – der Seed läuft nur, wenn die jeweilige Tabelle leer ist.
"""
from sqlalchemy.orm import Session

from .config import settings
from .models import BankProfile, Category, User, UserSettings
from .security import hash_password

BASE_CATEGORIES = [
    # (Name, fix)
    ("Lebensmittel", False), ("Drogerie", False), ("Restaurant & Lieferdienst", False),
    ("Kleidung", False), ("Haushalt & Möbel", False), ("Elektronik", False),
    ("Miete / Wohnen", True), ("Nebenkosten & Energie", True), ("Internet & Mobilfunk", True),
    ("Versicherungen", True), ("Rundfunkbeitrag", True), ("Abos & Streaming", True),
    ("Auto & Kraftstoff", False), ("Motorrad", False), ("ÖPNV & Bahn", False),
    ("Gesundheit & Apotheke", False), ("Freizeit & Sport", False), ("Urlaub & Reisen", False),
    ("Geschenke & Spenden", False), ("Gehalt", False), ("Kapitalerträge", False),
    ("Bargeldauszahlung", False), ("Gebühren & Zinsen", True), ("Sonstiges", False),
]


def seed_admin(db: Session) -> None:
    if db.query(User).count() > 0:
        return
    admin = User(username=settings.admin_username,
                 password_hash=hash_password(settings.admin_password),
                 display_name=settings.admin_display_name, is_admin=True)
    db.add(admin)
    db.flush()
    db.add(UserSettings(user_id=admin.id))
    db.commit()


def seed_categories(db: Session) -> None:
    if db.query(Category).count() > 0:
        return
    for name, fixed in BASE_CATEGORIES:
        db.add(Category(name=name, scope="global", is_fixed_cost=fixed))
    db.commit()


def seed_bank_profiles(db: Session) -> None:
    """Referenzformate aus der Analyse der Beispiel-Exporte (4.5.1)."""
    if db.query(BankProfile).count() > 0:
        return
    db.add(BankProfile(
        name="Sparkasse (CSV-CAMT)",
        delimiter=";", quotechar='"', encoding="utf-8-sig", skip_rows=0,
        column_map={
            "account_iban": "Auftragskonto",
            "booking_date": "Buchungstag",
            "value_date": "Valutadatum",
            "booking_text": "Buchungstext",
            "purpose": "Verwendungszweck",
            "counterparty": "Beguenstigter/Zahlungspflichtiger",
            "counterparty_iban": "Kontonummer/IBAN",
            "amount": "Betrag",
            "currency": "Waehrung",
        },
        # 2-stelliges UND 4-stelliges Jahr – ältere Exporte nutzen das volle Datum
        date_formats=["%d.%m.%y", "%d.%m.%Y"],
        decimal_separator=",", thousands_separator=".",
    ))
    db.add(BankProfile(
        name="ING",
        delimiter=";", quotechar='"', encoding="cp1252",
        # Metadatenkopf variabler Länge → Kopfzeile per Signatur finden
        header_signature="Buchung;Valuta",
        # Positional: zwei Spalten heißen "Währung" (Saldo + Betrag, 4.5.1)
        column_map={
            "booking_date": 0,
            "value_date": 1,
            "counterparty": 2,
            "booking_text": 3,
            "purpose": 4,
            "balance": 5,
            "amount": 7,
            "currency": 8,
        },
        date_formats=["%d.%m.%Y"],
        decimal_separator=",", thousands_separator=".",
    ))
    db.commit()


def run_all(db: Session) -> None:
    seed_admin(db)
    seed_categories(db)
    seed_bank_profiles(db)
