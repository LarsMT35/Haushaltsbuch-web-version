"""Dashboard-Auswertungen (4.9).

Alle Berechnungen laufen im Backend (Prinzip 6) über die Referenzwährung.
Umbuchungen zählen in Einnahmen/Ausgaben nicht mit, bleiben aber in der
"Bewegung Sparkonten" sichtbar (4.4).
"""
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import accessible_account_ids, get_current_user, require_account_access
from ..models import Account, Category, DashboardLayout, Transaction, User
from ..schemas import (
    AccountBalance,
    CategoryValue,
    DashboardSummary,
    DepositorMonth,
    DepositsOut,
    LayoutOut,
    MonthValue,
    NetWorthOut,
    NetWorthSeries,
    SavingsRateOut,
    YearComparisonOut,
    YearComparisonRow,
)

router = APIRouter(prefix="/dashboard", tags=["dashboard"])

SAVINGS_TYPES = {"tagesgeld", "sparbuch", "depot"}


@router.get("/summary", response_model=DashboardSummary)
def summary(date_from: date | None = None, date_to: date | None = None,
            account_id: int | None = None, category_id: int | None = None,
            user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if date_to is None:
        date_to = date.today()
    if date_from is None:
        date_from = (date_to.replace(day=1) - timedelta(days=365)).replace(day=1)

    ids = accessible_account_ids(db, user)
    if account_id is not None and account_id in ids:
        filter_ids = [account_id]
    else:
        filter_ids = ids

    accounts = {a.id: a for a in db.query(Account).filter(Account.id.in_(ids), Account.archived.is_(False)).all()}
    categories = {c.id: c for c in db.query(Category).all()}

    txs = (db.query(Transaction)
           .filter(Transaction.account_id.in_(filter_ids),
                   Transaction.booking_date >= date_from,
                   Transaction.booking_date <= date_to)
           .all())
    if category_id is not None:
        txs = [t for t in txs if t.category_id == category_id]

    income = Decimal("0")
    expenses = Decimal("0")
    unassigned = 0
    monthly_in: dict[str, Decimal] = defaultdict(Decimal)
    monthly_out: dict[str, Decimal] = defaultdict(Decimal)
    by_cat: dict[int | None, Decimal] = defaultdict(Decimal)
    fixed = {"income_fixed": Decimal("0"), "income_variable": Decimal("0"),
             "expenses_fixed": Decimal("0"), "expenses_variable": Decimal("0")}
    savings: dict[str, Decimal] = defaultdict(Decimal)

    for t in txs:
        month = t.booking_date.strftime("%Y-%m")
        acc = accounts.get(t.account_id)
        cat = categories.get(t.category_id) if t.category_id else None
        if t.transfer_id or (cat and cat.is_transfer_like):
            # Echte Umbuchung ODER Kategorie "wie Umbuchung behandeln" (z.B.
            # Sparplan-Ausführung ohne mitgeführtes Depot-Konto): nicht in
            # Einnahmen/Ausgaben, aber Sparkonten-Bewegung (4.9). Bei
            # Kategorie-Markierung unabhängig vom Kontotyp der zahlenden
            # Seite, da das Ziel (z.B. Depot) oft gar nicht selbst geführt wird.
            if (acc and acc.type in SAVINGS_TYPES) or (cat and cat.is_transfer_like):
                savings[month] += t.amount_ref
            continue
        if t.amount_ref >= 0:
            income += t.amount_ref
            monthly_in[month] += t.amount_ref
        else:
            expenses += -t.amount_ref
            monthly_out[month] += -t.amount_ref
            # Splitbuchungen zählen anteilig auf ihre Kategorien (4.4)
            parts = ([(s.category_id, s.amount) for s in t.splits]
                     if t.splits else [(t.category_id, t.amount_ref)])
            for cid, amount in parts:
                if amount < 0:
                    by_cat[cid] += -amount
        key = ("income" if t.amount_ref >= 0 else "expenses") + ("_fixed" if cat and cat.is_fixed_cost else "_variable")
        fixed[key] += abs(t.amount_ref)
        if t.category_id is None and not t.splits:
            unassigned += 1
        if acc and acc.type in SAVINGS_TYPES:
            savings[month] += t.amount_ref

    months = sorted(set(list(monthly_in) + list(monthly_out) + list(savings)))
    balances = []
    total = Decimal("0")
    for a in accounts.values():
        bal = (a.opening_balance or Decimal("0")) + sum(
            (t.amount for t in db.query(Transaction).filter(Transaction.account_id == a.id).all()),
            Decimal("0"))
        total += bal
        balances.append(AccountBalance(account_id=a.id, name=a.name, type=a.type,
                                       balance=float(bal), shared=len(a.account_roles) > 1))

    def cat_name(cid: int | None) -> str:
        if cid is None:
            return "Nicht zugeordnet"
        return categories[cid].name if cid in categories else f"#{cid}"

    return DashboardSummary(
        date_from=date_from, date_to=date_to,
        income=float(income), expenses=float(expenses), balance_total=float(total),
        unassigned_count=unassigned,
        accounts=sorted(balances, key=lambda b: b.name),
        monthly_balance=[MonthValue(month=m, value=float(monthly_in[m] - monthly_out[m])) for m in months],
        monthly_expenses=[MonthValue(month=m, value=float(monthly_out[m])) for m in months],
        by_category=sorted(
            [CategoryValue(category_id=cid, category_name=cat_name(cid), value=float(v),
                           is_fixed_cost=bool(cid and categories.get(cid) and categories[cid].is_fixed_cost))
             for cid, v in by_cat.items()],
            key=lambda c: -c.value),
        fixed_vs_variable={k: float(v) for k, v in fixed.items()},
        savings_movement=[MonthValue(month=m, value=float(savings[m])) for m in months],
    )


def _month_range(date_from: date, date_to: date) -> list[str]:
    months = []
    y, m = date_from.year, date_from.month
    while (y, m) <= (date_to.year, date_to.month):
        months.append(f"{y:04d}-{m:02d}")
        m += 1
        if m > 12:
            y, m = y + 1, 1
    return months


@router.get("/networth", response_model=NetWorthOut)
def networth(date_from: date | None = None, date_to: date | None = None,
             user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Vermögensverlauf pro Konto als Monatsend-Saldo (4.9) – berechnet aus
    Anfangssaldo + Buchungen (Prinzip 3)."""
    if date_to is None:
        date_to = date.today()
    if date_from is None:
        date_from = date_to.replace(day=1).replace(year=date_to.year - 1)
    months = _month_range(date_from, date_to)

    ids = accessible_account_ids(db, user)
    accounts = db.query(Account).filter(Account.id.in_(ids), Account.archived.is_(False)).all()
    series = []
    totals = [Decimal("0")] * len(months)
    for a in accounts:
        txs = (db.query(Transaction.booking_date, Transaction.amount)
               .filter(Transaction.account_id == a.id)
               .order_by(Transaction.booking_date.asc())
               .all())
        # Saldo vor dem ersten angefragten Monat
        running = (a.opening_balance or Decimal("0")) + sum(
            (amt for d, amt in txs if d.strftime("%Y-%m") < months[0]), Decimal("0"))
        values = []
        i = 0
        txs_in_range = [(d.strftime("%Y-%m"), amt) for d, amt in txs if d.strftime("%Y-%m") >= months[0]]
        for month in months:
            while i < len(txs_in_range) and txs_in_range[i][0] <= month:
                running += txs_in_range[i][1]
                i += 1
            values.append(running)
        series.append(NetWorthSeries(account_id=a.id, name=a.name,
                                     values=[float(v) for v in values]))
        totals = [t + v for t, v in zip(totals, values)]
    return NetWorthOut(months=months, series=sorted(series, key=lambda s: s.name),
                       total=[float(t) for t in totals])


@router.get("/savings-rate", response_model=SavingsRateOut)
def savings_rate(date_from: date | None = None, date_to: date | None = None,
                 account_id: int | None = None,
                 user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Sparquote im Zeitverlauf (4.9): Bilanz ÷ Einnahmen je Monat, ohne Umbuchungen
    (echte wie auch Kategorien mit "wie Umbuchung behandeln")."""
    if date_to is None:
        date_to = date.today()
    if date_from is None:
        date_from = date_to.replace(day=1).replace(year=date_to.year - 1)
    ids = accessible_account_ids(db, user)
    filter_ids = [account_id] if account_id is not None and account_id in ids else ids
    transfer_like_ids = {cid for (cid,) in db.query(Category.id).filter(Category.is_transfer_like.is_(True)).all()}
    txs = (db.query(Transaction)
           .filter(Transaction.account_id.in_(filter_ids),
                   Transaction.booking_date >= date_from,
                   Transaction.booking_date <= date_to,
                   Transaction.transfer_id.is_(None))
           .all())
    months = _month_range(date_from, date_to)
    inc = {m: Decimal("0") for m in months}
    out = {m: Decimal("0") for m in months}
    for t in txs:
        if t.category_id in transfer_like_ids:
            continue
        m = t.booking_date.strftime("%Y-%m")
        if m not in inc:
            continue
        if t.amount_ref >= 0:
            inc[m] += t.amount_ref
        else:
            out[m] += -t.amount_ref
    rate = [float((inc[m] - out[m]) / inc[m] * 100) if inc[m] else 0.0 for m in months]
    return SavingsRateOut(months=months, income=[float(inc[m]) for m in months],
                          expenses=[float(out[m]) for m in months],
                          rate=[round(r, 1) for r in rate])


@router.get("/year-comparison", response_model=YearComparisonOut)
def year_comparison(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Jahresvergleich der Ausgaben pro Kategorie (4.9) – möglich durch die
    durchgehende Historie ohne Jahresschnitt. Kategorien mit "wie Umbuchung
    behandeln" zählen hier nicht als Ausgabe, wie echte Umbuchungen auch."""
    ids = accessible_account_ids(db, user)
    txs = (db.query(Transaction)
           .filter(Transaction.account_id.in_(ids), Transaction.transfer_id.is_(None))
           .all())
    all_categories = db.query(Category).all()
    categories = {c.id: c.name for c in all_categories}
    transfer_like_ids = {c.id for c in all_categories if c.is_transfer_like}
    per: dict[tuple[int | None, int], Decimal] = defaultdict(Decimal)
    years: set[int] = set()
    for t in txs:
        if t.category_id in transfer_like_ids and not t.splits:
            continue
        year = t.booking_date.year
        parts = ([(s.category_id, s.amount) for s in t.splits]
                 if t.splits else [(t.category_id, t.amount_ref)])
        for cid, amount in parts:
            if amount >= 0 or cid in transfer_like_ids:
                continue
            per[(cid, year)] += -amount
            years.add(year)
    year_list = sorted(years)
    cat_ids = {cid for (cid, _y) in per}
    rows = []
    for cid in cat_ids:
        values = [float(per.get((cid, y), Decimal("0"))) for y in year_list]
        name = "Nicht zugeordnet" if cid is None else categories.get(cid, f"#{cid}")
        rows.append(YearComparisonRow(category_id=cid, category_name=name, values=values))
    rows.sort(key=lambda r: -sum(r.values))
    return YearComparisonOut(years=year_list, rows=rows)


@router.get("/deposits", response_model=DepositsOut)
def deposits(account_id: int, date_from: date | None = None, date_to: date | None = None,
             user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Einzahlungs-Transparenz fürs gemeinsame Konto (4.9): eingehende
    Buchungen (keine Umbuchungen) je Monat nach Gegenpartei gruppiert – auf
    Bank-Exports ist das direkt der Auftraggeber/Einzahler."""
    require_account_access(db, user, account_id, "reader")
    if date_to is None:
        date_to = date.today()
    if date_from is None:
        date_from = date_to.replace(day=1).replace(year=date_to.year - 1)
    months = _month_range(date_from, date_to)

    txs = (db.query(Transaction)
           .filter(Transaction.account_id == account_id,
                   Transaction.booking_date >= date_from,
                   Transaction.booking_date <= date_to,
                   Transaction.transfer_id.is_(None),
                   Transaction.amount > 0)
           .all())

    per_month: dict[str, dict[str, Decimal]] = {m: defaultdict(Decimal) for m in months}
    depositors: set[str] = set()
    for t in txs:
        m = t.booking_date.strftime("%Y-%m")
        if m not in per_month:
            continue
        name = t.counterparty.strip() or "Unbekannt"
        per_month[m][name] += t.amount_ref
        depositors.add(name)

    series = [DepositorMonth(month=m, values={d: float(per_month[m].get(d, Decimal("0"))) for d in depositors})
              for m in months]
    return DepositsOut(account_id=account_id, months=months,
                       depositors=sorted(depositors), series=series)


@router.get("/layout", response_model=LayoutOut)
def get_layout(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Kachel-Layout pro Nutzer (4.9.1): Reihenfolge + Sichtbarkeit."""
    layout = db.get(DashboardLayout, user.id)
    return LayoutOut(tiles=layout.tiles if layout else [])


@router.put("/layout", response_model=LayoutOut)
def set_layout(payload: LayoutOut, user: User = Depends(get_current_user),
               db: Session = Depends(get_db)):
    layout = db.get(DashboardLayout, user.id)
    if layout is None:
        layout = DashboardLayout(user_id=user.id, tiles=[])
        db.add(layout)
    layout.tiles = [t.model_dump() for t in payload.tiles]
    db.commit()
    return payload
