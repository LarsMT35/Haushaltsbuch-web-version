"""Wiederkehrende Kostenpositionen & Vorfinanzierungs-Abgleich (4.7 b)."""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import accessible_account_ids, get_current_user, require_account_access
from ..models import Category, RecurringItem, RecurringLink, Transaction, User
from ..schemas import (
    RecurringDetectResult,
    RecurringItemCreate,
    RecurringItemOut,
    RecurringItemUpdate,
    RecurringLinkIn,
    RecurringLinkOut,
    RecurringStatusOut,
    RecurringStatusRow,
)
from ..services.audit import log
from ..services.recurring import ampel_for, auto_link_all, auto_link_item, compute_status

router = APIRouter(prefix="/recurring-items", tags=["recurring"])


def _visible_items(db: Session, user: User):
    ids = accessible_account_ids(db, user)
    return (db.query(RecurringItem)
            .filter((RecurringItem.paying_account_id.is_(None)) | (RecurringItem.paying_account_id.in_(ids)))
            .order_by(RecurringItem.name))


@router.get("", response_model=list[RecurringItemOut])
def list_items(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return _visible_items(db, user).all()


@router.post("", response_model=RecurringItemOut)
def create_item(payload: RecurringItemCreate, user: User = Depends(get_current_user),
                db: Session = Depends(get_db)):
    if payload.category_id and db.get(Category, payload.category_id) is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Kategorie nicht gefunden")
    if payload.paying_account_id:
        require_account_access(db, user, payload.paying_account_id, "editor")
    if payload.reimbursement_account_id:
        require_account_access(db, user, payload.reimbursement_account_id, "editor")
    item = RecurringItem(**payload.model_dump())
    db.add(item)
    db.flush()
    log(db, user.id, "recurring_item", item.id, "create", {"name": item.name})
    db.commit()
    return item


@router.put("/{item_id}", response_model=RecurringItemOut)
def update_item(item_id: int, payload: RecurringItemUpdate,
                user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    item = db.get(RecurringItem, item_id)
    if item is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Position nicht gefunden")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(item, field, value)
    log(db, user.id, "recurring_item", item.id, "update", payload.model_dump(exclude_unset=True, mode="json"))
    db.commit()
    return item


@router.delete("/{item_id}")
def delete_item(item_id: int, user: User = Depends(get_current_user),
                db: Session = Depends(get_db)):
    item = db.get(RecurringItem, item_id)
    if item is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Position nicht gefunden")
    db.query(RecurringLink).filter(RecurringLink.recurring_item_id == item.id).delete()
    log(db, user.id, "recurring_item", item.id, "delete", {"name": item.name})
    db.delete(item)
    db.commit()
    return {"ok": True}


@router.post("/detect", response_model=RecurringDetectResult)
def detect(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Automatische Erkennung neuer Abbuchungen/Erstattungen für alle aktiven
    Positionen – Ergebnis ist ein Vorschlag, jede Verknüpfung bleibt auch
    manuell änderbar (Machbarkeitshinweis 4.7)."""
    c, r = auto_link_all(db, accessible_account_ids(db, user))
    log(db, user.id, "recurring_item", "", "detect", {"charges": c, "reimbursements": r})
    db.commit()
    return RecurringDetectResult(charges_linked=c, reimbursements_linked=r)


@router.post("/{item_id}/detect", response_model=RecurringDetectResult)
def detect_one(item_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    item = db.get(RecurringItem, item_id)
    if item is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Position nicht gefunden")
    c, r = auto_link_item(db, item)
    return RecurringDetectResult(charges_linked=c, reimbursements_linked=r)


@router.get("/{item_id}/links", response_model=list[RecurringLinkOut])
def list_links(item_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return (db.query(RecurringLink).filter(RecurringLink.recurring_item_id == item_id)
            .join(Transaction).order_by(Transaction.booking_date.desc()).all())


@router.post("/{item_id}/links", response_model=RecurringLinkOut)
def link_manual(item_id: int, payload: RecurringLinkIn,
               user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Manuelles Verknüpfen einer Buchung – Rückfallebene, wenn die Automatik
    danebenliegt oder gar nicht erst greift (Machbarkeitshinweis 4.7)."""
    item = db.get(RecurringItem, item_id)
    if item is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Position nicht gefunden")
    if payload.role not in ("charge", "reimbursement"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "role muss charge oder reimbursement sein")
    tx = db.get(Transaction, payload.transaction_id)
    if tx is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Buchung nicht gefunden")
    require_account_access(db, user, tx.account_id, "editor")
    existing = (db.query(RecurringLink)
                .filter(RecurringLink.transaction_id == tx.id, RecurringLink.role == payload.role)
                .first())
    if existing:
        raise HTTPException(status.HTTP_409_CONFLICT, "Buchung ist für diese Rolle bereits verknüpft")
    link = RecurringLink(recurring_item_id=item_id, transaction_id=tx.id,
                         role=payload.role, is_auto=False)
    db.add(link)
    log(db, user.id, "recurring_link", item_id, "link_manual",
        {"transaction_id": tx.id, "role": payload.role})
    db.commit()
    db.refresh(link)
    return link


@router.delete("/links/{link_id}")
def unlink(link_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    link = db.get(RecurringLink, link_id)
    if link is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Verknüpfung nicht gefunden")
    log(db, user.id, "recurring_link", link_id, "unlink", {})
    db.delete(link)
    db.commit()
    return {"ok": True}


@router.get("/status", response_model=RecurringStatusOut)
def status_overview(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Ampel-Übersicht Soll/Ist über alle aktiven Positionen (4.9)."""
    rows = []
    for item in _visible_items(db, user).filter(RecurringItem.active.is_(True)).all():
        s = compute_status(db, item)
        rows.append(RecurringStatusRow(
            id=item.id, name=item.name, cycle_months=item.cycle_months,
            expected_amount=float(item.expected_amount), is_prefinanced=s.is_prefinanced,
            last_charge_date=s.last_charge.booking_date if s.last_charge else None,
            last_charge_amount=float(s.ist) if s.ist is not None else None,
            next_due_estimate=s.next_due_estimate,
            soll=float(s.soll) if s.soll is not None else None,
            ist=float(s.ist) if s.ist is not None else None,
            deviation=float(s.ist - s.soll) if s.ist is not None and s.soll is not None else None,
            suggested_rate=float(s.suggested_rate) if s.suggested_rate is not None else None,
            ampel=ampel_for(s.deviation_pct),
        ))
    rows.sort(key=lambda r: {"rot": 0, "gelb": 1, "gruen": 2}[r.ampel])
    return RecurringStatusOut(rows=rows)
