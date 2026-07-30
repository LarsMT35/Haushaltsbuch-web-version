"""Datenmodell nach Kapitel 6 des Anforderungsdokuments.

Alle Entitäten sind ab v1.0 angelegt (auch die, die erst in v1.1/v1.2 voll
genutzt werden), damit spätere Funktionen ohne Datenumbau andocken können.
"""
from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------- Benutzer

class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    display_name: Mapped[str] = mapped_column(String(128))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    settings: Mapped["UserSettings | None"] = relationship(back_populates="user", uselist=False)
    roles: Mapped[list["AccountRole"]] = relationship(back_populates="user")


class UserSettings(Base):
    __tablename__ = "user_settings"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), primary_key=True)
    color_scheme: Mapped[str] = mapped_column(String(32), default="hell")
    dark_mode: Mapped[bool] = mapped_column(Boolean, default=False)
    prefs: Mapped[dict] = mapped_column(JSON, default=dict)

    user: Mapped[User] = relationship(back_populates="settings")


class DashboardLayout(Base):
    __tablename__ = "dashboard_layouts"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), primary_key=True)
    # Liste der Kacheln inkl. Typ, Position, Größe, sichtbar/entfernt (4.9.1)
    tiles: Mapped[list] = mapped_column(JSON, default=list)


# ------------------------------------------------------------------ Konten

ROLE_OWNER = "owner"
ROLE_EDITOR = "editor"
ROLE_READER = "reader"
ROLE_RANK = {ROLE_READER: 1, ROLE_EDITOR: 2, ROLE_OWNER: 3}


class Account(Base):
    __tablename__ = "accounts"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(128))
    type: Mapped[str] = mapped_column(String(32), default="giro")  # giro/tagesgeld/sparbuch/depot/bargeld/kreditkarte
    currency: Mapped[str] = mapped_column(String(3), default="EUR")
    bank: Mapped[str] = mapped_column(String(128), default="")
    iban: Mapped[str] = mapped_column(String(34), default="", index=True)
    note: Mapped[str] = mapped_column(Text, default="")
    # Anfangssaldo + Stichtag sind Pflichtbestandteil des Modells (4.2)
    opening_balance: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0"))
    opening_balance_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    archived: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    account_roles: Mapped[list["AccountRole"]] = relationship(back_populates="account")


class AccountRole(Base):
    __tablename__ = "account_roles"
    __table_args__ = (UniqueConstraint("user_id", "account_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"), index=True)
    role: Mapped[str] = mapped_column(String(16))  # owner / editor / reader

    user: Mapped[User] = relationship(back_populates="roles")
    account: Mapped[Account] = relationship(back_populates="account_roles")


# -------------------------------------------------------------- Kategorien

SCOPE_GLOBAL = "global"
SCOPE_ACCOUNT = "account"
SCOPE_PERSONAL = "personal"


class Category(Base):
    __tablename__ = "categories"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(128))
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("categories.id"), nullable=True)
    # Geltungsbereich: global / kontobezogen / persönlich (4.6)
    scope: Mapped[str] = mapped_column(String(16), default=SCOPE_GLOBAL)
    account_id: Mapped[int | None] = mapped_column(ForeignKey("accounts.id"), nullable=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    is_fixed_cost: Mapped[bool] = mapped_column(Boolean, default=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True)

    parent: Mapped["Category | None"] = relationship(remote_side=[id])


class Rule(Base):
    __tablename__ = "rules"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(128))
    priority: Mapped[int] = mapped_column(Integer, default=100, index=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    category_id: Mapped[int] = mapped_column(ForeignKey("categories.id"))
    # Kriterien (AND-verknüpft, leer = nicht geprüft) – mehr als die alte Whitelist (4.6)
    text_contains: Mapped[str] = mapped_column(String(255), default="")       # Verwendungszweck
    counterparty_contains: Mapped[str] = mapped_column(String(255), default="")
    iban_equals: Mapped[str] = mapped_column(String(34), default="")
    booking_text_contains: Mapped[str] = mapped_column(String(255), default="")
    amount_min: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    amount_max: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    account_id: Mapped[int | None] = mapped_column(ForeignKey("accounts.id"), nullable=True)

    category: Mapped[Category] = relationship()


# ---------------------------------------------------------------- Buchungen

class Transfer(Base):
    """Verknüpft zwei Transactions als eine Umbuchung (4.4)."""

    __tablename__ = "transfers"

    id: Mapped[int] = mapped_column(primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    is_auto: Mapped[bool] = mapped_column(Boolean, default=False)


class Transaction(Base):
    __tablename__ = "transactions"

    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"), index=True)
    booking_date: Mapped[date] = mapped_column(Date, index=True)  # führend für Auswertungen (4.4)
    value_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    currency: Mapped[str] = mapped_column(String(3), default="EUR")
    amount_ref: Mapped[Decimal] = mapped_column(Numeric(14, 2))  # Betrag in Referenzwährung (4.3)
    counterparty: Mapped[str] = mapped_column(String(255), default="")
    counterparty_iban: Mapped[str] = mapped_column(String(34), default="", index=True)
    purpose: Mapped[str] = mapped_column(Text, default="")
    booking_text: Mapped[str] = mapped_column(String(255), default="")
    category_id: Mapped[int | None] = mapped_column(ForeignKey("categories.id"), nullable=True, index=True)
    note: Mapped[str] = mapped_column(Text, default="")
    import_batch_id: Mapped[int | None] = mapped_column(ForeignKey("import_batches.id"), nullable=True, index=True)
    raw_line: Mapped[str] = mapped_column(Text, default="")  # Rohzeile aufbewahren (Prinzip 2)
    dedup_hash: Mapped[str] = mapped_column(String(64), default="", index=True)
    is_manual: Mapped[bool] = mapped_column(Boolean, default=False)
    transfer_id: Mapped[int | None] = mapped_column(ForeignKey("transfers.id"), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    category: Mapped[Category | None] = relationship()
    account: Mapped[Account] = relationship()
    splits: Mapped[list["TransactionSplit"]] = relationship(back_populates="transaction", cascade="all, delete-orphan")
    tags: Mapped[list["Tag"]] = relationship(secondary="transaction_tags")


class TransactionSplit(Base):
    __tablename__ = "transaction_splits"

    id: Mapped[int] = mapped_column(primary_key=True)
    transaction_id: Mapped[int] = mapped_column(ForeignKey("transactions.id"), index=True)
    category_id: Mapped[int] = mapped_column(ForeignKey("categories.id"))
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2))

    transaction: Mapped[Transaction] = relationship(back_populates="splits")


class Tag(Base):
    __tablename__ = "tags"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(64), unique=True)


class TransactionTag(Base):
    __tablename__ = "transaction_tags"
    __table_args__ = (UniqueConstraint("transaction_id", "tag_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    transaction_id: Mapped[int] = mapped_column(ForeignKey("transactions.id"), index=True)
    tag_id: Mapped[int] = mapped_column(ForeignKey("tags.id"), index=True)


# ------------------------------------------------------------------ Import

class BankProfile(Base):
    """Importprofil als Daten, nicht als Code (Prinzip 1, 4.5)."""

    __tablename__ = "bank_profiles"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(128), unique=True)
    delimiter: Mapped[str] = mapped_column(String(4), default=";")
    quotechar: Mapped[str] = mapped_column(String(1), default='"')
    encoding: Mapped[str] = mapped_column(String(32), default="utf-8-sig")
    skip_rows: Mapped[int] = mapped_column(Integer, default=0)
    # alternativ zu skip_rows: Zeilen überspringen, bis eine Zeile so beginnt (ING-Metadatenkopf)
    header_signature: Mapped[str] = mapped_column(String(128), default="")
    # Spaltenzuordnung: Feldname -> Spaltenname (str) oder Spaltenindex (int).
    # Index nötig, wenn Spaltennamen doppelt vorkommen (ING: zweimal "Währung", 4.5.1)
    column_map: Mapped[dict] = mapped_column(JSON, default=dict)
    date_formats: Mapped[list] = mapped_column(JSON, default=lambda: ["%d.%m.%Y", "%d.%m.%y"])
    decimal_separator: Mapped[str] = mapped_column(String(1), default=",")
    thousands_separator: Mapped[str] = mapped_column(String(1), default=".")
    negate_amount: Mapped[bool] = mapped_column(Boolean, default=False)


class ImportBatch(Base):
    """Jeder Import ist ein protokollierter, komplett rückrollbarer Vorgang (Prinzip 7)."""

    __tablename__ = "import_batches"

    id: Mapped[int] = mapped_column(primary_key=True)
    filename: Mapped[str] = mapped_column(String(255))
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    profile_id: Mapped[int | None] = mapped_column(ForeignKey("bank_profiles.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    num_transactions: Mapped[int] = mapped_column(Integer, default=0)
    reverted: Mapped[bool] = mapped_column(Boolean, default=False)

    profile: Mapped[BankProfile | None] = relationship()
    user: Mapped[User] = relationship()


# ---------------------------------------------------- Budget & Wiederkehrend

class Budget(Base):
    __tablename__ = "budgets"

    id: Mapped[int] = mapped_column(primary_key=True)
    category_id: Mapped[int] = mapped_column(ForeignKey("categories.id"))
    account_id: Mapped[int | None] = mapped_column(ForeignKey("accounts.id"), nullable=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    period: Mapped[str] = mapped_column(String(16), default="month")
    valid_from: Mapped[date] = mapped_column(Date)  # versioniert ab Gültigkeitsdatum (4.8)


class RecurringItem(Base):
    __tablename__ = "recurring_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(128))
    cycle_months: Mapped[int] = mapped_column(Integer, default=12)
    expected_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0"))
    paying_account_id: Mapped[int | None] = mapped_column(ForeignKey("accounts.id"), nullable=True)
    category_id: Mapped[int | None] = mapped_column(ForeignKey("categories.id"), nullable=True)
    prefinance_note: Mapped[str] = mapped_column(Text, default="")
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class ExchangeRate(Base):
    __tablename__ = "exchange_rates"
    __table_args__ = (UniqueConstraint("currency_from", "currency_to", "rate_date"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    currency_from: Mapped[str] = mapped_column(String(3))
    currency_to: Mapped[str] = mapped_column(String(3))
    rate_date: Mapped[date] = mapped_column(Date)
    rate: Mapped[Decimal] = mapped_column(Numeric(16, 6))


# ------------------------------------------------------------- Konfiguration

class AppSetting(Base):
    """App-weite Konfiguration als Daten (Prinzip 1), z.B. Budget-Schwellwerte."""

    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[dict] = mapped_column(JSON, default=dict)


# --------------------------------------------------------------------- Audit

class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    entity: Mapped[str] = mapped_column(String(64))
    entity_id: Mapped[str] = mapped_column(String(64), default="")
    action: Mapped[str] = mapped_column(String(32))
    detail: Mapped[dict] = mapped_column(JSON, default=dict)
