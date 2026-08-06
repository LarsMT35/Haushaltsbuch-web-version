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
from ..models import Account, AppSetting, Budget, Category, Transaction, User, UserSettings
from ..schemas import (BudgetCreate, BudgetOut, BudgetStatusOut, BudgetStatusRow,
                       BudgetThresholds, BudgetUpdate, PeriodBoundsOut,
                       PeriodSettingIn, PeriodSettingOut)
from ..services.audit import log
from ..services.periods import (SETTING_KEY as PERIOD_KEY, current_period,
                                effective_period, get_start_day, normalize_start_day,
                                period_bounds, period_key, range_condition)

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
def budget_status(month: str | None = Query(None, pattern=r"^\d{4}-\d{2}$"),
                  date_in_period: date | None = None,
                  account_id: int | None = None,
                  account_ids: list[int] | None = Query(None),
                  user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Soll/Ist je Budget für einen Abrechnungsmonat mit Ampel (4.8).

    Der Zeitraum lässt sich auf drei Arten angeben, absteigend spezifisch:
    `month` (fertiger Periodenschlüssel), `date_in_period` (irgendein Datum –
    das Backend bestimmt die zugehörige Periode) oder gar nichts (laufende
    Periode). `date_in_period` gibt es, damit die Oberfläche aus einem
    gewählten Zeitraum nicht selbst einen Periodenschlüssel rechnen muss:
    mit verschobenem Starttag gehört der 30.08. bereits zum September, ein
    bloßes Abschneiden der ersten sieben Zeichen träfe den falschen Monat.

    Ein kontogebundenes Budget gilt **nur für dieses Konto**: es erscheint nur
    im zugehörigen Dashboard-Bereich und verbraucht sich ausschließlich an
    Buchungen dieses Kontos. Ein Budget ohne Konto gilt übergreifend und
    misst sich an allen Konten der aktuellen Auswahl.

    Splits zählen anteilig auf ihre Kategorie; Umbuchungen zählen nicht.
    `account_ids` (Mehrfachauswahl) hat Vorrang vor dem einzelnen `account_id`
    und trägt die Bereichstrennung des Dashboards mit (4.9.1).
    """
    start_day = get_start_day(db, user)
    if month is None:
        month = (period_key(date_in_period, start_day) if date_in_period is not None
                 else current_period(start_day))
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

    # Auch von Hand zugeordnete Buchungen einsammeln – deren Buchungsdatum kann
    # beliebig weit außerhalb des Zeitraums liegen (services/periods.py).
    txs = (db.query(Transaction)
           .filter(Transaction.account_id.in_(filter_ids),
                   Transaction.transfer_id.is_(None),
                   range_condition(first, last, start_day))
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
    return BudgetStatusOut(month=month, date_from=first, date_to=last,
                           thresholds=th, rows=rows)


# ------------------------------------------------ Abrechnungsmonat (4.9)

def _period_out(day: int, is_own_choice: bool = False) -> PeriodSettingOut:
    current = current_period(day)
    cur_from, cur_to = period_bounds(current, day)
    previous = period_key(cur_from - timedelta(days=1), day)
    prev_from, prev_to = period_bounds(previous, day)
    return PeriodSettingOut(start_day=day, current_period=current,
                            current_from=cur_from, current_to=cur_to,
                            previous_period=previous,
                            previous_from=prev_from, previous_to=prev_to,
                            is_own_choice=is_own_choice)

@router.get("/period", response_model=PeriodSettingOut)
def get_period_setting(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Eigener Starttag des Abrechnungsmonats. 1 = Kalendermonat."""
    settings = db.get(UserSettings, user.id)
    return _period_out(get_start_day(db, user),
                       is_own_choice=settings is not None and settings.period_start_day is not None)


@router.get("/period/bounds", response_model=PeriodBoundsOut)
def get_period_bounds(month: str, db: Session = Depends(get_db),
                      user: User = Depends(get_current_user)):
    """Erster und letzter Tag eines Abrechnungsmonats ("YYYY-MM").

    Klickt man im Dashboard auf einen Monat, muss daraus ein Datumsbereich für
    die Buchungsliste werden. Die Umrechnung bleibt bewusst im Backend, damit
    die Periodenregel nicht ein zweites Mal in JavaScript existiert (Prinzip 6).
    """
    try:
        first, last = period_bounds(month, get_start_day(db, user))
    except (ValueError, TypeError):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                            detail="Monat muss das Format YYYY-MM haben.")
    return PeriodBoundsOut(month=month, date_from=first, date_to=last)


@router.put("/period", response_model=PeriodSettingOut)
def set_period_setting(payload: PeriodSettingIn, db: Session = Depends(get_db),
                       user: User = Depends(get_current_user)):
    """Eigenen Starttag setzen – wirkt nur auf die eigenen Auswertungen.

    Seit v1.7.1 wählt das jeder für sich: der Zahltag ist nichts, was ein
    Administrator für andere festlegen kann. Buchungsdaten, Kontostände und
    der Saldo-Abgleich bleiben in jedem Fall unberührt; da an den Buchungen
    nur Abweichungen gespeichert sind, ordnet sich alles Übrige neu ein.
    """
    day = normalize_start_day(payload.start_day)
    settings = db.get(UserSettings, user.id)
    if settings is None:
        settings = UserSettings(user_id=user.id)
        db.add(settings)
    settings.period_start_day = day
    log(db, user.id, "user_settings", str(user.id), "period", {"start_day": day})
    db.commit()
    return _period_out(day, is_own_choice=True)


# ACHTUNG, Reihenfolge: dieser Pfad muss NACH allen festen PUT-Pfaden stehen
# (/thresholds, /period). FastAPI prüft die Routen in Registrierungsreihenfolge –
# weiter oben verschluckte "/{budget_id}" die festen Pfade und versuchte,
# "thresholds" als Zahl zu lesen (422).
@router.put("/{budget_id}", response_model=BudgetOut)
def update_budget(budget_id: int, payload: BudgetUpdate,
                  user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Bestehendes Budget korrigieren.

    Bewusst ergaenzend zur Versionierung (4.8), nicht als Ersatz: einen
    Vertipper im Betrag will man richtigstellen, ohne eine zweite Version
    anzulegen, die es nie gab. Eine Aenderung, die erst ab einem Datum gelten
    soll, bleibt ein neuer Eintrag mit eigenem valid_from – sonst wuerde sich
    rueckwirkend die Vergangenheit aendern.
    """
    budget = db.get(Budget, budget_id)
    if budget is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Budget nicht gefunden")
    if budget.account_id is not None:
        require_account_access(db, user, budget.account_id, "editor")

    data = payload.model_dump(exclude_unset=True)
    if "category_id" in data and db.get(Category, data["category_id"]) is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Kategorie nicht gefunden")
    if data.get("account_id") is not None:
        # auch das ZIEL muss einem gehoeren, sonst liesse sich ein Budget auf
        # ein fremdes Konto umhaengen
        require_account_access(db, user, data["account_id"], "editor")
    if "amount" in data and data["amount"] <= 0:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Betrag muss groesser als 0 sein")

    for field, value in data.items():
        setattr(budget, field, value)
    log(db, user.id, "budget", budget.id, "update",
        {k: str(v) for k, v in data.items()})
    db.commit()
    db.refresh(budget)
    return budget
