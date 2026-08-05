"""Budgets mit Ampel (4.8).

Budgets sind ab Gültigkeitsdatum versioniert: eine Erhöhung ist ein neuer
Eintrag mit neuem valid_from und verändert die Vergangenheit nicht.
Ampel-Schwellwerte sind konfigurierbar (AppSetting), die Ampelfarben selbst
sind fest und schema-unabhängig (4.10).
"""
import calendar
from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import accessible_account_ids, get_current_user, require_account_access, require_admin
from ..models import AppSetting, Budget, Category, Transaction, User
from ..schemas import BudgetCreate, BudgetOut, BudgetStatusOut, BudgetStatusRow, BudgetThresholds
from ..services.audit import log

router = APIRouter(prefix="/budgets", tags=["budgets"])

THRESHOLD_KEY = "budget_thresholds"


def get_thresholds(db: Session) -> BudgetThresholds:
    setting = db.get(AppSetting, THRESHOLD_KEY)
    if setting is None:
        return BudgetThresholds()
    return BudgetThresholds(**setting.value)


@router.get("", response_model=list[BudgetOut])
def list_budgets(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    ids = accessible_account_ids(db, user)
    q = db.query(Budget).filter((Budget.account_id.is_(None)) | (Budget.account_id.in_(ids)))
    return q.order_by(Budget.category_id, Budget.valid_from.desc()).all()


@router.post("", response_model=BudgetOut)
def create_budget(payload: BudgetCreate, user: User = Depends(get_current_user),
                  db: Session = Depends(get_db)):
    if db.get(Category, payload.category_id) is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Kategorie nicht gefunden")
    if payload.account_id is not None:
        require_account_access(db, user, payload.account_id, "editor")
    budget = Budget(**payload.model_dump(), period="month")
    db.add(budget)
    db.flush()
    log(db, user.id, "budget", budget.id, "create",
        {"category_id": budget.category_id, "amount": str(budget.amount)})
    db.commit()
    return budget


@router.delete("/{budget_id}")
def delete_budget(budget_id: int, user: User = Depends(get_current_user),
                  db: Session = Depends(get_db)):
    budget = db.get(Budget, budget_id)
    if budget is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Budget nicht gefunden")
    if budget.account_id is not None:
        require_account_access(db, user, budget.account_id, "editor")
    log(db, user.id, "budget", budget.id, "delete", {})
    db.delete(budget)
    db.commit()
    return {"ok": True}


@router.get("/thresholds", response_model=BudgetThresholds)
def thresholds(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return get_thresholds(db)


@router.put("/thresholds", response_model=BudgetThresholds)
def set_thresholds(payload: BudgetThresholds, db: Session = Depends(get_db),
                   admin: User = Depends(require_admin)):
    setting = db.get(AppSetting, THRESHOLD_KEY)
    if setting is None:
        setting = AppSetting(key=THRESHOLD_KEY, value={})
        db.add(setting)
    setting.value = payload.model_dump()
    log(db, admin.id, "app_setting", THRESHOLD_KEY, "update", setting.value)
    db.commit()
    return payload


@router.get("/status", response_model=BudgetStatusOut)
def budget_status(month: str = Query(..., pattern=r"^\d{4}-\d{2}$"),
                  account_id: int | None = None,
                  account_ids: list[int] | None = Query(None),
                  user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Soll/Ist je Kategorie für einen Monat mit Ampel (4.8).

    Splits zählen anteilig auf ihre Kategorie; Umbuchungen zählen nicht.
    `account_ids` (Mehrfachauswahl) hat Vorrang vor dem einzelnen `account_id`
    und trägt die Bereichstrennung des Dashboards mit (4.9.1).
    """
    year, mon = int(month[:4]), int(month[5:7])
    first = date(year, mon, 1)
    last = date(year, mon, calendar.monthrange(year, mon)[1])

    ids = accessible_account_ids(db, user)
    if account_ids:
        filter_ids = [a for a in account_ids if a in ids] or ids
    elif account_id is not None and account_id in ids:
        filter_ids = [account_id]
    else:
        filter_ids = ids
    scoped = filter_ids is not ids

    # Gültiges Budget je (Kategorie, Konto): jüngstes valid_from <= Monatsende
    budgets = (db.query(Budget)
               .filter(Budget.valid_from <= last,
                       (Budget.account_id.is_(None)) | (Budget.account_id.in_(ids)))
               .order_by(Budget.valid_from.asc())
               .all())
    effective: dict[int, Budget] = {}
    for b in budgets:
        # kontogebundene Budgets nur, wenn ihr Konto in der Auswahl liegt
        if scoped and b.account_id is not None and b.account_id not in filter_ids:
            continue
        effective[b.category_id] = b  # spätere valid_from überschreibt frühere

    txs = (db.query(Transaction)
           .filter(Transaction.account_id.in_(filter_ids),
                   Transaction.booking_date >= first,
                   Transaction.booking_date <= last,
                   Transaction.transfer_id.is_(None))
           .all())
    all_categories = db.query(Category).all()
    transfer_like_ids = {c.id for c in all_categories if c.is_transfer_like}
    spent: dict[int, Decimal] = {}
    for t in txs:
        parts = ([(s.category_id, s.amount) for s in t.splits]
                 if t.splits else [(t.category_id, t.amount_ref)])
        for cid, amount in parts:
            # Kategorien "wie Umbuchung behandeln" zählen wie echte Umbuchungen
            # nicht als Ausgabe (4.9), daher auch nicht als Budget-Verbrauch
            if cid is None or amount >= 0 or cid in transfer_like_ids:
                continue
            spent[cid] = spent.get(cid, Decimal("0")) + -amount

    th = get_thresholds(db)
    categories = {c.id: c.name for c in all_categories}
    rows = []
    for cid, b in effective.items():
        used = float(spent.get(cid, Decimal("0")))
        budget_amount = float(b.amount)
        percent = (used / budget_amount * 100) if budget_amount else 0.0
        ampel = "gruen" if percent < th.green_below else ("rot" if percent >= th.red_from else "gelb")
        rows.append(BudgetStatusRow(category_id=cid, category_name=categories.get(cid, f"#{cid}"),
                                    budget=budget_amount, spent=used,
                                    percent=round(percent, 1), ampel=ampel))
    rows.sort(key=lambda r: -r.percent)
    return BudgetStatusOut(month=month, thresholds=th, rows=rows)
