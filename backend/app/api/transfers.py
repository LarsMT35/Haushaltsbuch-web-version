"""Umbuchungen (4.4): Vorschläge, manuelles Verknüpfen und Auflösen."""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import accessible_account_ids, get_current_user, require_account_access
from ..models import Transaction, Transfer, User
from ..schemas import TransferLink, TransferSuggestion
from ..services.audit import log
from ..services import transfers as svc

router = APIRouter(prefix="/transfers", tags=["transfers"])


@router.get("/suggestions", response_model=list[TransferSuggestion])
def suggestions(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    pairs = svc.transfer_suggestions(db, accessible_account_ids(db, user))
    return [TransferSuggestion(transaction_a=a, transaction_b=b) for a, b in pairs]


@router.post("/detect")
def detect(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    linked = svc.auto_link_transfers(db, accessible_account_ids(db, user))
    return {"linked": linked}


@router.post("/link")
def link(payload: TransferLink, user: User = Depends(get_current_user),
         db: Session = Depends(get_db)):
    a = db.get(Transaction, payload.transaction_id_a)
    b = db.get(Transaction, payload.transaction_id_b)
    if a is None or b is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Buchung nicht gefunden")
    require_account_access(db, user, a.account_id, "editor")
    require_account_access(db, user, b.account_id, "editor")
    if a.transfer_id or b.transfer_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Buchung ist bereits verknüpft")
    if a.account_id == b.account_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Umbuchung braucht zwei verschiedene Konten")
    transfer = svc.link_manual(db, a, b)
    log(db, user.id, "transfer", transfer.id, "link", {"a": a.id, "b": b.id})
    db.commit()
    return {"transfer_id": transfer.id}


@router.delete("/{transfer_id}")
def unlink(transfer_id: int, user: User = Depends(get_current_user),
           db: Session = Depends(get_db)):
    transfer = db.get(Transfer, transfer_id)
    if transfer is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Umbuchung nicht gefunden")
    tx = db.query(Transaction).filter(Transaction.transfer_id == transfer.id).first()
    if tx:
        require_account_access(db, user, tx.account_id, "editor")
    svc.unlink(db, transfer)
    log(db, user.id, "transfer", transfer_id, "unlink", {})
    db.commit()
    return {"ok": True}
