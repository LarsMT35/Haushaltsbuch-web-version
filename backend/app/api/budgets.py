"""Budgets mit Ampel (4.8).

Budgets sind ab Gültigkeitsdatum versioniert: eine Erhöhung ist ein neuer
Eintrag mit neuem valid_from und verändert die Vergangenheit nicht.
Ampel-Schwellwerte sind konfigurierbar (AppSetting), die Ampelfarben selbst
sind fest und schema-unabhängig (4.10).
"""
from datetime import date, timedelta
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import accessible_account_ids, get_current_user, require_account_access, require_admin
from ..models import Account, AppSetting, Budget, Category, Transaction, User
from ..schemas import (BudgetCreate, BudgetOut, BudgetStatusOut, BudgetStatusRow,
                       BudgetThresholds, PeriodSettingIn, PeriodSettingOut)
from ..services.audit import log
from ..services.periods import (SETTING_KEY as PERIOD_KEY, current_period,
                                effective_period, get_start_day, normalize_start_day,
                                period_bounds, period_key)

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
    """Soll/Ist je Budget für einen Abrechnungsmonat mit Ampel (4.8).

    Ein kontogebundenes Budget gilt **nur für dieses Konto**: es erscheint nur
    im zugehörigen Dashboard-Bereich und verbraucht sich ausschließlich an
    Buchungen dieses Kontos. Ein Budget ohne Konto gilt übergreifend und
    misst sich an allen Konten der aktuellen Auswahl.

    Splits zählen anteilig auf ihre Kategorie; Umbuchungen zählen nicht.
    `account_ids` (Mehrfachauswahl) hat Vorrang vor dem einzelnen `account_id`
    und trägt die Bereichstrennung des Dashboards mit (4.9.1).
    """
    start_day = get_start_day(db)
    first, last = period_bounds(month, start_day)

    ids = accessible_account_ids(db, user)
    if account_ids:
        filter_ids = [a for a in account_ids if a in ids] or ids
    elif account_id is not None and account_id in ids:
        filter_ids = [account_id]
    else:
        filter_ids = ids

    budgets = (db.query(Budget)
               .filter(Budget.valid_from <= last,
                       (Budget.account_id.is_(None)) | (Budget.account_id.in_(filter_ids)))
               .order_by(Budget.valid_from.asc())
               .all())
    # Versionierung (4.8): je (Kategorie, Konto) gewinnt das jüngste valid_from.
    # Konto gehört bewusst in den Schlüssel – sonst würde ein kontogebundenes
    # Budget ein übergreifendes derselben Kategorie stillschweigend verdrängen.
    effective: dict[tuple[int, int | None], Budget] = {}
    for b in budgets:
        effective[(b.category_id, b.account_id)] = b

    # Zeitraum großzügig laden und über den Abrechnungsmonat filtern: bei
    # verschobenem Starttag liegen die Ränder außerhalb des Kalendermonats.
    txs = (db.query(Transaction)
           .filter(Transaction.account_id.in_(filter_ids),
                   Transaction.booking_date >= first - timedelta(days=40),
                   Transaction.booking_date <= last + timedelta(days=40),
                   Transaction.transfer_id.is_(None))
           .all())
    all_categories = db.query(Category).all()
    transfer_like_ids = {c.id for c in all_categories if c.is_transfer_like}

    # Verbrauch je (Kategorie, Konto) statt nur je Kategorie – nur so kann ein
    # kontogebundenes Budget sich auch wirklich nur an seinem Konto messen.
    spent: dict[tuple[int, int], Decimal] = {}
    for t in txs:
        if effective_period(t, start_day) != month:
            continue
        parts = ([(s.category_id, s.amount) for s in t.splits]
                 if t.splits else [(t.category_id, t.amount_ref)])
        for cid, amount in parts:
            # Kategorien "wie Umbuchung behandeln" zählen wie echte Umbuchungen
            # nicht als Ausgabe (4.9), daher auch nicht als Budget-Verbrauch
            if cid is None or amount >= 0 or cid in transfer_like_ids:
                continue
            key = (cid, t.account_id)
            spent[key] = spent.get(key, Decimal("0")) + -amount

    th = get_thresholds(db)
    categories = {c.id: c.name for c in all_categories}
    account_names = {a.id: a.name for a in db.query(Account).filter(Account.id.in_(filter_ids)).all()}
    rows = []
    for (cid, acc_id), b in effective.items():
        if acc_id is None:
            used = float(sum((v for (c, _a), v in spent.items() if c == cid), Decimal("0")))
        else:
            used = float(spent.get((cid, acc_id), Decimal("0")))
        budget_amount = float(b.amount)
        percent = (used / budget_amount * 100) if budget_amount else 0.0
        ampel = "gruen" if percent < th.green_below else ("rot" if percent >= th.red_from else "gelb")
        rows.append(BudgetStatusRow(
            budget_id=b.id, category_id=cid, category_name=categories.get(cid, f"#{cid}"),
            account_id=acc_id, account_name=account_names.get(acc_id) if acc_id else None,
            budget=budget_amount, spent=used, percent=round(percent, 1), ampel=ampel))
    rows.sort(key=lambda r: -r.percent)
    return BudgetStatusOut(month=month, thresholds=th, rows=rows)


# ------------------------------------------------ Abrechnungsmonat (4.9)

def _period_out(day: int) -> PeriodSettingOut:
    current = current_period(day)
    cur_from, cur_to = period_bounds(current, day)
    previous = period_key(cur_from - timedelta(days=1), day)
    prev_from, prev_to = period_bounds(previous, day)
    return PeriodSettingOut(start_day=day, current_period=current,
                            current_from=cur_from, current_to=cur_to,
                            previous_period=previous,
                            previous_from=prev_from, previous_to=prev_to)

@router.get("/period", response_model=PeriodSettingOut)
def get_period_setting(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Starttag des Abrechnungsmonats. 1 = Kalendermonat."""
    return _period_out(get_start_day(db))


@router.put("/period", response_model=PeriodSettingOut)
def set_period_setting(payload: PeriodSettingIn, db: Session = Depends(get_db),
                       admin: User = Depends(require_admin)):
    """Starttag ändern – wirkt nur auf Auswertungen, nie auf Buchungsdaten.

    Da nur Abweichungen an den Buchungen gespeichert werden, ordnen sich alle
    übrigen Buchungen automatisch neu ein.
    """
    day = normalize_start_day(payload.start_day)
    setting = db.get(AppSetting, PERIOD_KEY)
    if setting is None:
        setting = AppSetting(key=PERIOD_KEY, value={})
        db.add(setting)
    setting.value = {"start_day": day}
    log(db, admin.id, "app_setting", PERIOD_KEY, "update", setting.value)
    db.commit()
    return _period_out(day)
