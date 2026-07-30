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
from ..deps import accessible_account_ids, get_current_user
from ..models import Account, Category, Transaction, User
from ..schemas import (
    AccountBalance,
    CategoryValue,
    DashboardSummary,
    MonthValue,
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
        if t.transfer_id:
            # Umbuchung: nicht in Einnahmen/Ausgaben, aber Sparkonten-Bewegung (4.9)
            if acc and acc.type in SAVINGS_TYPES:
                savings[month] += t.amount_ref
            continue
        if t.amount_ref >= 0:
            income += t.amount_ref
            monthly_in[month] += t.amount_ref
        else:
            expenses += -t.amount_ref
            monthly_out[month] += -t.amount_ref
            by_cat[t.category_id] += -t.amount_ref
        cat = categories.get(t.category_id) if t.category_id else None
        key = ("income" if t.amount_ref >= 0 else "expenses") + ("_fixed" if cat and cat.is_fixed_cost else "_variable")
        fixed[key] += abs(t.amount_ref)
        if t.category_id is None:
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
