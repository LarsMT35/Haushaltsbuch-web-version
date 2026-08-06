"""Buchungen (4.4): Suche/Filter, manuelle Buchungen, eingeschränkte Änderbarkeit, Export."""
import csv
import io
import re
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
from ..services.periods import effective_period, get_start_day
from ..services.transfers import auto_link_transfers, auto_mirror_category_transfers, detach

router = APIRouter(prefix="/transactions", tags=["transactions"])


def _out(tx: Transaction, start_day: int) -> TransactionOut:
    """Buchung samt WIRKSAMEM Abrechnungsmonat ausgeben (4.9): die Oberfläche
    zeigt das Feld immer vorbelegt, markiert aber eine manuelle Abweichung."""
    out = TransactionOut.model_validate(tx)
    out.financial_month = effective_period(tx, start_day)
    out.financial_month_is_override = tx.financial_month is not None
    return out


def _filtered_query(db: Session, user: User, *, account_id: int | None, category_id: int | None,
                    date_from: date | None, date_to: date | None, text: str | None,
                    amount_min: float | None, amount_max: float | None,
                    unassigned: bool, include_transfers: bool, tag: str | None = None,
                    account_ids: list[int] | None = None):
    ids = accessible_account_ids(db, user)
    q = db.query(Transaction).filter(Transaction.account_id.in_(ids))
    if account_ids:
        # Bereichsfilter aus dem Dashboard ("Gemeinsam" = mehrere Konten): ohne
        # ihn zeigte der Sprung aus einem Diagramm mehr Buchungen an, als die
        # angeklickte Zahl umfasst. Nicht zugängliche IDs fallen still weg.
        q = q.filter(Transaction.account_id.in_([a for a in account_ids if a in ids]))
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
                      tag: str | None = None, account_ids: list[int] | None = Query(None),
                      limit: int = Query(100, le=500), offset: int = 0,
                      user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    q = _filtered_query(db, user, account_id=account_id, category_id=category_id,
                        date_from=date_from, date_to=date_to, text=text,
                        amount_min=amount_min, amount_max=amount_max,
                        unassigned=unassigned, include_transfers=True, tag=tag,
                        account_ids=account_ids)
    total = q.count()
    items = (q.order_by(Transaction.booking_date.desc(), Transaction.id.desc())
             .offset(offset).limit(limit).all())
    start_day = get_start_day(db)
    return TransactionPage(total=total, items=[_out(t, start_day) for t in items])


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
    # Umbuchungserkennung auch bei manuellen Buchungen (4.4) – z.B. eine per
    # Hand erfasste Bargeldabhebung soll genauso automatisch mit der
    # passenden Giro-Abbuchung verknüpft werden wie beim CSV-Import.
    ids = accessible_account_ids(db, user)
    auto_link_transfers(db, ids)
    auto_mirror_category_transfers(db, ids)
    db.refresh(tx)
    return _out(tx, get_start_day(db))


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
    if data.get("financial_month"):
        fm = str(data["financial_month"])
        if not re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", fm):
            raise HTTPException(status.HTTP_400_BAD_REQUEST,
                                "Abrechnungsmonat muss im Format JJJJ-MM angegeben werden")
    if "category_id" in data and data["category_id"] is not None:
        cat = db.get(Category, data["category_id"])
        if cat is None:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Kategorie nicht gefunden")
        # Persönliche Kategorie darf nicht auf ein geteiltes Konto (4.6)
        if cat.scope == "personal" and len(tx.account.account_roles) > 1:
            raise HTTPException(status.HTTP_400_BAD_REQUEST,
                                "Persönliche Kategorie auf gemeinsamem Konto nicht erlaubt – "
                                "Kategorie zuerst auf kontobezogen hochstufen")
    # Wechselt die Kategorie weg von einer mit Umbuchungs-Zielkonto, verliert
    # die automatische Gegenbuchung ihre Grundlage und muss weg (4.4)
    old_category_id = tx.category_id
    for field, value in data.items():
        setattr(tx, field, value)
    if tx.is_manual and "amount" in data:
        tx.amount_ref = tx.amount
    if "category_id" in data and data["category_id"] != old_category_id and tx.transfer_id:
        old_cat = db.get(Category, old_category_id) if old_category_id else None
        if old_cat is not None and old_cat.transfer_target_account_id:
            detach(db, tx)
    log(db, user.id, "transaction", tx.id, "update", {k: str(v) for k, v in data.items()})
    db.commit()
    # neue Kategorie kann ihrerseits ein Zielkonto haben -> Gegenbuchung anlegen
    if "category_id" in data and data["category_id"] != old_category_id:
        auto_mirror_category_transfers(db, accessible_account_ids(db, user))
        db.refresh(tx)
    return _out(tx, get_start_day(db))


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
    # abgeleitete Gegenbuchung im Zielkonto mitnehmen (4.4), sonst bliebe
    # dort eine Buchung ohne Gegenstück stehen
    dropped = detach(db, tx)
    log(db, user.id, "transaction", tx.id, "delete", {"counterparts_removed": dropped})
    db.delete(tx)
    db.commit()
    return {"ok": True, "counterparts_removed": dropped}


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
    return _out(tx, get_start_day(db))


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
    return _out(tx, get_start_day(db))


@router.get("/tags", response_model=list[TagOut])
def list_tags(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return db.query(Tag).order_by(Tag.name).all()


@router.get("/export.csv")
def export_csv(account_id: int | None = None, category_id: int | None = None,
               date_from: date | None = None, date_to: date | None = None,
               text: str | None = None, account_ids: list[int] | None = Query(None),
               user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """CSV-Export (4.11) – Datenhoheit: Daten kommen auch wieder heraus."""
    q = _filtered_query(db, user, account_id=account_id, category_id=category_id,
                        date_from=date_from, date_to=date_to, text=text,
                        amount_min=None, amount_max=None, unassigned=False,
                        include_transfers=True, account_ids=account_ids)
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
