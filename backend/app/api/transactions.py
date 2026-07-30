"""Buchungen (4.4): Suche/Filter, manuelle Buchungen, eingeschränkte Änderbarkeit, Export."""
import csv
import io
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy import or_
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import accessible_account_ids, get_current_user, require_account_access
from ..models import Category, Tag, Transaction, TransactionSplit, TransactionTag, User
from ..schemas import (
    ManualTransactionCreate,
    SplitIn,
    TagOut,
    TransactionOut,
    TransactionPage,
    TransactionUpdate,
)
from ..services.audit import log

router = APIRouter(prefix="/transactions", tags=["transactions"])


def _filtered_query(db: Session, user: User, *, account_id: int | None, category_id: int | None,
                    date_from: date | None, date_to: date | None, text: str | None,
                    amount_min: float | None, amount_max: float | None,
                    unassigned: bool, include_transfers: bool, tag: str | None = None):
    ids = accessible_account_ids(db, user)
    q = db.query(Transaction).filter(Transaction.account_id.in_(ids))
    if account_id is not None:
        require_account_access(db, user, account_id, "reader")
        q = q.filter(Transaction.account_id == account_id)
    if category_id is not None:
        q = q.filter(Transaction.category_id == category_id)
    if date_from is not None:
        q = q.filter(Transaction.booking_date >= date_from)
    if date_to is not None:
        q = q.filter(Transaction.booking_date <= date_to)
    if text:
        like = f"%{text}%"
        q = q.filter(or_(Transaction.purpose.ilike(like), Transaction.counterparty.ilike(like),
                         Transaction.note.ilike(like), Transaction.counterparty_iban.ilike(like)))
    if amount_min is not None:
        q = q.filter(Transaction.amount >= amount_min)
    if amount_max is not None:
        q = q.filter(Transaction.amount <= amount_max)
    if unassigned:
        q = q.filter(Transaction.category_id.is_(None))
    if tag:
        q = (q.join(TransactionTag, TransactionTag.transaction_id == Transaction.id)
             .join(Tag, Tag.id == TransactionTag.tag_id)
             .filter(Tag.name == tag))
    if not include_transfers:
        pass  # Umbuchungen bleiben sichtbar, sind aber markiert (4.9.1)
    return q


FILTER_PARAMS = dict(account_id=None, category_id=None, date_from=None, date_to=None,
                     text=None, amount_min=None, amount_max=None)


@router.get("", response_model=TransactionPage)
def list_transactions(account_id: int | None = None, category_id: int | None = None,
                      date_from: date | None = None, date_to: date | None = None,
                      text: str | None = None, amount_min: float | None = None,
                      amount_max: float | None = None, unassigned: bool = False,
                      tag: str | None = None,
                      limit: int = Query(100, le=500), offset: int = 0,
                      user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    q = _filtered_query(db, user, account_id=account_id, category_id=category_id,
                        date_from=date_from, date_to=date_to, text=text,
                        amount_min=amount_min, amount_max=amount_max,
                        unassigned=unassigned, include_transfers=True, tag=tag)
    total = q.count()
    items = (q.order_by(Transaction.booking_date.desc(), Transaction.id.desc())
             .offset(offset).limit(limit).all())
    return TransactionPage(total=total, items=items)


@router.post("", response_model=TransactionOut)
def create_manual(payload: ManualTransactionCreate,
                  user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Manuelle Buchung (4.4) – z.B. Bargeldausgaben vom Bargeld-Konto."""
    account = require_account_access(db, user, payload.account_id, "editor")
    tx = Transaction(
        account_id=account.id, booking_date=payload.booking_date, value_date=payload.booking_date,
        amount=payload.amount, currency=account.currency, amount_ref=payload.amount,
        counterparty=payload.counterparty, purpose=payload.purpose,
        category_id=payload.category_id, note=payload.note, is_manual=True,
    )
    db.add(tx)
    db.flush()
    log(db, user.id, "transaction", tx.id, "create_manual", {"amount": str(tx.amount)})
    db.commit()
    return tx


@router.put("/{transaction_id}", response_model=TransactionOut)
def update_transaction(transaction_id: int, payload: TransactionUpdate,
                       user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    tx = db.get(Transaction, transaction_id)
    if tx is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Buchung nicht gefunden")
    require_account_access(db, user, tx.account_id, "editor")
    data = payload.model_dump(exclude_unset=True)
    # Importierte Buchungen: Betrag/Datum/Gegenpartei unveränderlich (4.4)
    protected = {"booking_date", "amount", "counterparty", "purpose"}
    if not tx.is_manual and protected & data.keys():
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            "Bei importierten Buchungen sind nur Kategorie und Notiz änderbar")
    if "category_id" in data and data["category_id"] is not None:
        cat = db.get(Category, data["category_id"])
        if cat is None:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Kategorie nicht gefunden")
        # Persönliche Kategorie darf nicht auf ein geteiltes Konto (4.6)
        if cat.scope == "personal" and len(tx.account.account_roles) > 1:
            raise HTTPException(status.HTTP_400_BAD_REQUEST,
                                "Persönliche Kategorie auf gemeinsamem Konto nicht erlaubt – "
                                "Kategorie zuerst auf kontobezogen hochstufen")
    for field, value in data.items():
        setattr(tx, field, value)
    if tx.is_manual and "amount" in data:
        tx.amount_ref = tx.amount
    log(db, user.id, "transaction", tx.id, "update", {k: str(v) for k, v in data.items()})
    db.commit()
    return tx


@router.delete("/{transaction_id}")
def delete_transaction(transaction_id: int, user: User = Depends(get_current_user),
                       db: Session = Depends(get_db)):
    tx = db.get(Transaction, transaction_id)
    if tx is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Buchung nicht gefunden")
    require_account_access(db, user, tx.account_id, "editor")
    if not tx.is_manual:
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            "Importierte Buchungen werden über den Import-Rollback entfernt")
    log(db, user.id, "transaction", tx.id, "delete", {})
    db.delete(tx)
    db.commit()
    return {"ok": True}


@router.put("/{transaction_id}/splits", response_model=TransactionOut)
def set_splits(transaction_id: int, splits: list[SplitIn],
               user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Splitbuchung (4.4): eine Buchung auf mehrere Kategorien aufteilen.
    Leere Liste entfernt den Split. Teilbeträge müssen den Buchungsbetrag ergeben."""
    tx = db.get(Transaction, transaction_id)
    if tx is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Buchung nicht gefunden")
    require_account_access(db, user, tx.account_id, "editor")
    if splits:
        total = sum((s.amount for s in splits), start=tx.amount * 0)
        if total != tx.amount:
            raise HTTPException(status.HTTP_400_BAD_REQUEST,
                                f"Teilbeträge ({total}) müssen den Buchungsbetrag ({tx.amount}) ergeben")
        for s in splits:
            if db.get(Category, s.category_id) is None:
                raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Kategorie {s.category_id} nicht gefunden")
    db.query(TransactionSplit).filter(TransactionSplit.transaction_id == tx.id).delete()
    for s in splits:
        db.add(TransactionSplit(transaction_id=tx.id, category_id=s.category_id, amount=s.amount))
    log(db, user.id, "transaction", tx.id, "split", {"parts": len(splits)})
    db.commit()
    db.refresh(tx)
    return tx


@router.put("/{transaction_id}/tags", response_model=TransactionOut)
def set_tags(transaction_id: int, tag_names: list[str],
             user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Tags als leichte Zweitdimension neben Kategorien (4.4), z.B. "Urlaub 2026"."""
    tx = db.get(Transaction, transaction_id)
    if tx is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Buchung nicht gefunden")
    require_account_access(db, user, tx.account_id, "editor")
    db.query(TransactionTag).filter(TransactionTag.transaction_id == tx.id).delete()
    for raw in tag_names:
        name = raw.strip()
        if not name:
            continue
        tag = db.query(Tag).filter(Tag.name == name).first()
        if tag is None:
            tag = Tag(name=name)
            db.add(tag)
            db.flush()
        db.add(TransactionTag(transaction_id=tx.id, tag_id=tag.id))
    log(db, user.id, "transaction", tx.id, "tags", {"tags": tag_names})
    db.commit()
    db.refresh(tx)
    return tx


@router.get("/tags", response_model=list[TagOut])
def list_tags(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return db.query(Tag).order_by(Tag.name).all()


@router.get("/export.csv")
def export_csv(account_id: int | None = None, category_id: int | None = None,
               date_from: date | None = None, date_to: date | None = None,
               text: str | None = None,
               user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """CSV-Export (4.11) – Datenhoheit: Daten kommen auch wieder heraus."""
    q = _filtered_query(db, user, account_id=account_id, category_id=category_id,
                        date_from=date_from, date_to=date_to, text=text,
                        amount_min=None, amount_max=None, unassigned=False,
                        include_transfers=True)
    rows = q.order_by(Transaction.booking_date.asc()).all()
    categories = {c.id: c.name for c in db.query(Category).all()}
    buf = io.StringIO()
    writer = csv.writer(buf, delimiter=";")
    writer.writerow(["Buchungstag", "Valuta", "Konto", "Betrag", "Währung", "Gegenpartei",
                     "Gegen-IBAN", "Verwendungszweck", "Buchungstext", "Kategorie", "Notiz",
                     "Umbuchung", "Manuell"])
    for t in rows:
        writer.writerow([
            t.booking_date.isoformat(), t.value_date.isoformat() if t.value_date else "",
            t.account.name, str(t.amount).replace(".", ","), t.currency, t.counterparty,
            t.counterparty_iban, t.purpose, t.booking_text,
            categories.get(t.category_id, ""), t.note,
            "ja" if t.transfer_id else "", "ja" if t.is_manual else "",
        ])
    buf.seek(0)
    return StreamingResponse(iter([buf.getvalue().encode("utf-8-sig")]), media_type="text/csv",
                             headers={"Content-Disposition": "attachment; filename=buchungen.csv"})
