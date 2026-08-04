"""Pydantic-Schemas der versionierten API (/api/v1)."""
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ------------------------------------------------------------------- Auth

class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserOut(ORMModel):
    id: int
    username: str
    display_name: str
    is_active: bool
    is_admin: bool


class UserCreate(BaseModel):
    username: str
    password: str
    display_name: str
    is_admin: bool = False


class UserUpdate(BaseModel):
    display_name: str | None = None
    password: str | None = None
    is_active: bool | None = None
    is_admin: bool | None = None


class PasswordChange(BaseModel):
    old_password: str
    new_password: str


class SettingsOut(ORMModel):
    color_scheme: str
    dark_mode: bool
    prefs: dict


class SettingsUpdate(BaseModel):
    color_scheme: str | None = None
    dark_mode: bool | None = None
    prefs: dict | None = None


# ------------------------------------------------------------------ Konten

class AccountRoleOut(ORMModel):
    user_id: int
    role: str


class AccountOut(ORMModel):
    id: int
    name: str
    type: str
    currency: str
    bank: str
    iban: str
    note: str
    opening_balance: Decimal
    opening_balance_date: date | None
    archived: bool
    my_role: str | None = None
    balance: Decimal | None = None
    shared: bool = False


class AccountCreate(BaseModel):
    name: str
    type: str = "giro"
    currency: str = "EUR"
    bank: str = ""
    iban: str = ""
    note: str = ""
    opening_balance: Decimal = Decimal("0")
    opening_balance_date: date | None = None


class AccountUpdate(BaseModel):
    name: str | None = None
    type: str | None = None
    bank: str | None = None
    iban: str | None = None
    note: str | None = None
    opening_balance: Decimal | None = None
    opening_balance_date: date | None = None
    archived: bool | None = None


class RoleAssign(BaseModel):
    user_id: int
    role: str  # owner / editor / reader


# -------------------------------------------------------------- Kategorien

class CategoryOut(ORMModel):
    id: int
    name: str
    parent_id: int | None
    scope: str
    account_id: int | None
    user_id: int | None
    is_fixed_cost: bool
    is_transfer_like: bool
    active: bool


class CategoryCreate(BaseModel):
    name: str
    parent_id: int | None = None
    scope: str = "global"
    account_id: int | None = None
    is_fixed_cost: bool = False
    is_transfer_like: bool = False


class CategoryUpdate(BaseModel):
    name: str | None = None
    parent_id: int | None = None
    is_fixed_cost: bool | None = None
    is_transfer_like: bool | None = None
    active: bool | None = None


class CategoryMerge(BaseModel):
    target_category_id: int


class RuleOut(ORMModel):
    id: int
    name: str
    priority: int
    active: bool
    category_id: int
    text_contains: str
    counterparty_contains: str
    iban_equals: str
    booking_text_contains: str
    amount_min: Decimal | None
    amount_max: Decimal | None
    account_id: int | None


class RuleCreate(BaseModel):
    name: str
    category_id: int
    priority: int = 100
    active: bool = True
    text_contains: str = ""
    counterparty_contains: str = ""
    iban_equals: str = ""
    booking_text_contains: str = ""
    amount_min: Decimal | None = None
    amount_max: Decimal | None = None
    account_id: int | None = None


class RuleUpdate(BaseModel):
    name: str | None = None
    category_id: int | None = None
    priority: int | None = None
    active: bool | None = None
    text_contains: str | None = None
    counterparty_contains: str | None = None
    iban_equals: str | None = None
    booking_text_contains: str | None = None
    amount_min: Decimal | None = None
    amount_max: Decimal | None = None
    account_id: int | None = None


# ---------------------------------------------------------------- Buchungen

class TagOut(ORMModel):
    id: int
    name: str


class SplitOut(ORMModel):
    id: int
    category_id: int
    amount: Decimal


class SplitIn(BaseModel):
    category_id: int
    amount: Decimal


class TransactionOut(ORMModel):
    id: int
    account_id: int
    booking_date: date
    value_date: date | None
    amount: Decimal
    currency: str
    amount_ref: Decimal
    counterparty: str
    counterparty_iban: str
    purpose: str
    booking_text: str
    category_id: int | None
    note: str
    import_batch_id: int | None
    is_manual: bool
    transfer_id: int | None
    bank_balance: Decimal | None
    splits: list[SplitOut] = []
    tags: list[TagOut] = []


class TransactionPage(BaseModel):
    total: int
    items: list[TransactionOut]


class ManualTransactionCreate(BaseModel):
    account_id: int
    booking_date: date
    amount: Decimal
    counterparty: str = ""
    purpose: str = ""
    category_id: int | None = None
    note: str = ""


class TransactionUpdate(BaseModel):
    """Importierte Buchungen: nur Kategorie/Notiz änderbar (4.4).
    Manuelle Buchungen: zusätzlich Betrag/Datum/Gegenpartei/Zweck."""

    category_id: int | None = None
    note: str | None = None
    booking_date: date | None = None
    amount: Decimal | None = None
    counterparty: str | None = None
    purpose: str | None = None


class TransferLink(BaseModel):
    transaction_id_a: int
    transaction_id_b: int


class TransferSuggestion(BaseModel):
    transaction_a: TransactionOut
    transaction_b: TransactionOut


# ------------------------------------------------------------------ Import

class BankProfileOut(ORMModel):
    id: int
    name: str
    delimiter: str
    quotechar: str
    encoding: str
    skip_rows: int
    header_signature: str
    column_map: dict
    date_formats: list
    decimal_separator: str
    thousands_separator: str
    negate_amount: bool


class BankProfileCreate(BaseModel):
    name: str
    delimiter: str = ";"
    quotechar: str = '"'
    encoding: str = "utf-8-sig"
    skip_rows: int = 0
    header_signature: str = ""
    column_map: dict
    date_formats: list = ["%d.%m.%Y", "%d.%m.%y"]
    decimal_separator: str = ","
    thousands_separator: str = "."
    negate_amount: bool = False


class ParsedRow(BaseModel):
    row_number: int
    booking_date: date | None
    value_date: date | None
    amount: Decimal | None
    currency: str
    counterparty: str
    counterparty_iban: str
    purpose: str
    booking_text: str
    account_iban: str
    balance: Decimal | None = None
    raw_line: str
    dedup_hash: str
    duplicate: str = "new"  # new | suspect | duplicate
    suggested_category_id: int | None = None
    matched_rule_id: int | None = None
    error: str = ""
    include: bool = True


class ImportPreviewOut(BaseModel):
    profile_id: int
    filename: str
    suggested_account_id: int | None
    detected_ibans: list[str]
    rows: list[ParsedRow]


class ImportCommitIn(BaseModel):
    profile_id: int
    account_id: int
    filename: str
    rows: list[ParsedRow]


class ImportBatchOut(ORMModel):
    id: int
    filename: str
    user_id: int
    profile_id: int | None
    created_at: datetime
    num_transactions: int
    reverted: bool


class AnalyzeOut(BaseModel):
    encoding: str
    delimiter: str
    skip_rows: int
    header: list[str]
    sample_rows: list[list[str]]


# ------------------------------------------------------------------ Budgets

class BudgetOut(ORMModel):
    id: int
    category_id: int
    account_id: int | None
    amount: Decimal
    period: str
    valid_from: date


class BudgetCreate(BaseModel):
    category_id: int
    account_id: int | None = None
    amount: Decimal
    valid_from: date


class BudgetThresholds(BaseModel):
    """Ampel-Schwellwerte in Prozent, konfigurierbar (4.8)."""

    green_below: float = 80.0
    red_from: float = 98.0


class BudgetStatusRow(BaseModel):
    category_id: int
    category_name: str
    budget: float
    spent: float
    percent: float
    ampel: str  # gruen | gelb | rot


class BudgetStatusOut(BaseModel):
    month: str
    thresholds: BudgetThresholds
    rows: list[BudgetStatusRow]


# --------------------------------------------------------------- Dashboard

class MonthValue(BaseModel):
    month: str  # "2026-07"
    value: float


class CategoryValue(BaseModel):
    category_id: int | None
    category_name: str
    value: float
    is_fixed_cost: bool = False


class AccountBalance(BaseModel):
    account_id: int
    name: str
    type: str
    balance: float
    shared: bool = False


class DashboardSummary(BaseModel):
    date_from: date
    date_to: date
    income: float
    expenses: float
    balance_total: float
    unassigned_count: int
    accounts: list[AccountBalance]
    monthly_balance: list[MonthValue]
    monthly_expenses: list[MonthValue]
    by_category: list[CategoryValue]
    fixed_vs_variable: dict
    savings_movement: list[MonthValue]


class NetWorthSeries(BaseModel):
    account_id: int
    name: str
    values: list[float]  # Monatsend-Saldo je Monat


class NetWorthOut(BaseModel):
    months: list[str]
    series: list[NetWorthSeries]
    total: list[float]


class SavingsRateOut(BaseModel):
    months: list[str]
    income: list[float]
    expenses: list[float]
    rate: list[float]  # Prozent (Bilanz ÷ Einnahmen)


class YearComparisonRow(BaseModel):
    category_id: int | None
    category_name: str
    values: list[float]


class YearComparisonOut(BaseModel):
    years: list[int]
    rows: list[YearComparisonRow]


class LayoutTile(BaseModel):
    id: str
    visible: bool = True


class LayoutOut(BaseModel):
    tiles: list[LayoutTile]


# ------------------------------------------------- Wiederkehrende Kosten (4.7 b)

class RecurringItemOut(ORMModel):
    id: int
    name: str
    cycle_months: int
    expected_amount: Decimal
    paying_account_id: int | None
    category_id: int | None
    match_text: str
    reimbursement_account_id: int | None
    reimbursement_match_text: str
    current_rate: Decimal | None
    prefinance_note: str
    active: bool


class RecurringItemCreate(BaseModel):
    name: str
    cycle_months: int = 12
    expected_amount: Decimal = Decimal("0")
    paying_account_id: int | None = None
    category_id: int | None = None
    match_text: str = ""
    reimbursement_account_id: int | None = None
    reimbursement_match_text: str = ""
    current_rate: Decimal | None = None
    prefinance_note: str = ""


class RecurringItemUpdate(BaseModel):
    name: str | None = None
    cycle_months: int | None = None
    expected_amount: Decimal | None = None
    paying_account_id: int | None = None
    category_id: int | None = None
    match_text: str | None = None
    reimbursement_account_id: int | None = None
    reimbursement_match_text: str | None = None
    current_rate: Decimal | None = None
    prefinance_note: str | None = None
    active: bool | None = None


class RecurringLinkOut(ORMModel):
    id: int
    recurring_item_id: int
    transaction_id: int
    role: str
    is_auto: bool
    transaction: TransactionOut


class RecurringLinkIn(BaseModel):
    transaction_id: int
    role: str  # charge | reimbursement


class RecurringStatusRow(BaseModel):
    """Soll/Ist-Status einer wiederkehrenden Kostenposition (4.7 b, 4.9).

    Bei vorfinanzierten Positionen: Soll = aufsummierte Erstattungen seit der
    letzten Abbuchung, Ist = tatsächliche neue Abbuchung. Ampel schlägt bei
    größerer Abweichung Alarm, damit die Rate rechtzeitig angepasst wird.
    """

    id: int
    name: str
    cycle_months: int
    expected_amount: float
    is_prefinanced: bool
    last_charge_date: date | None
    last_charge_amount: float | None
    next_due_estimate: date | None
    soll: float | None  # nur bei Vorfinanzierung
    ist: float | None
    deviation: float | None  # ist - soll
    suggested_rate: float | None  # letzte Abbuchung ÷ Zyklusmonate
    ampel: str  # gruen | gelb | rot


class RecurringStatusOut(BaseModel):
    rows: list[RecurringStatusRow]


class RecurringDetectResult(BaseModel):
    charges_linked: int
    reimbursements_linked: int


# ------------------------------------------------------- Saldo-Abgleich (4.2)

class BalanceCheckRow(BaseModel):
    transaction_id: int
    booking_date: date
    counterparty: str
    computed_balance: float
    bank_balance: float
    deviation: float


class BalanceCheckOut(BaseModel):
    account_id: int
    checked_count: int
    rows: list[BalanceCheckRow]  # nur Abweichungen oberhalb der Toleranz


# ------------------------------------------ Einzahlungstransparenz (4.9)

class DepositorMonth(BaseModel):
    month: str
    values: dict[str, float]  # Gegenpartei -> Summe


class DepositsOut(BaseModel):
    account_id: int
    months: list[str]
    depositors: list[str]
    series: list[DepositorMonth]


# --------------------------------------------------- Export / Import (4.11)
# Referenzierung über Namen statt IDs, damit Export/Import auch zwischen
# unterschiedlichen Installationen funktioniert (z.B. Umzug, Vorlage teilen).

class CategoryExportItem(BaseModel):
    name: str
    parent_name: str | None = None
    scope: str
    account_name: str | None = None
    is_fixed_cost: bool
    is_transfer_like: bool = False
    active: bool


class CategoryImportResult(BaseModel):
    created: int
    updated_fixed_cost: int
    skipped_existing: int
    skipped_no_permission: int
    skipped_no_account: int


class RuleExportItem(BaseModel):
    name: str
    category_name: str
    priority: int
    active: bool
    text_contains: str
    counterparty_contains: str
    iban_equals: str
    booking_text_contains: str
    amount_min: Decimal | None
    amount_max: Decimal | None
    account_name: str | None = None


class RuleImportResult(BaseModel):
    created: int
    skipped_duplicate: int
    skipped_no_category: int
    skipped_no_account: int


class BankProfileImportResult(BaseModel):
    created: int
    skipped_existing: int
