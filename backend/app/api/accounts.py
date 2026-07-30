"""Konten (4.2): echte Entitäten mit Rollen, Anfangssaldo und Archivierung."""
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import account_role, accessible_account_ids, get_current_user, require_account_access
from ..models import Account, AccountRole, Transaction, User
from ..schemas import AccountCreate, AccountOut, AccountUpdate, RoleAssign
from ..services.audit import log

router = APIRouter(prefix="/accounts", tags=["accounts"])


def _balance(db: Session, account: Account) -> Decimal:
    """Saldo wird berechnet, nicht gespeichert (Prinzip 3)."""
    total = (
        db.query(func.coalesce(func.sum(Transaction.amount), 0))
        .filter(Transaction.account_id == account.id)
        .scalar()
    )
    return (account.opening_balance or Decimal("0")) + Decimal(str(total))


def _to_out(db: Session, user: User, account: Account) -> AccountOut:
    out = AccountOut.model_validate(account)
    out.my_role = account_role(db, user, account.id)
    out.balance = _balance(db, account)
    out.shared = len(account.account_roles) > 1
    return out


@router.get("", response_model=list[AccountOut])
def list_accounts(include_archived: bool = Query(False),
                  user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ids = accessible_account_ids(db, user)
    q = db.query(Account).filter(Account.id.in_(ids))
    if not include_archived:
        q = q.filter(Account.archived.is_(False))
    return [_to_out(db, user, a) for a in q.order_by(Account.name).all()]


@router.post("", response_model=AccountOut)
def create_account(payload: AccountCreate, user: User = Depends(get_current_user),
                   db: Session = Depends(get_db)):
    account = Account(**payload.model_dump())
    db.add(account)
    db.flush()
    # Wer ein Konto anlegt, ist sein Eigentümer (Rollenmodell 4.1)
    db.add(AccountRole(user_id=user.id, account_id=account.id, role="owner"))
    log(db, user.id, "account", account.id, "create", {"name": account.name})
    db.commit()
    return _to_out(db, user, account)


@router.put("/{account_id}", response_model=AccountOut)
def update_account(account_id: int, payload: AccountUpdate,
                   user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    data = payload.model_dump(exclude_none=True)
    min_role = "owner" if "archived" in data else "editor"
    account = require_account_access(db, user, account_id, min_role)
    for field, value in data.items():
        setattr(account, field, value)
    log(db, user.id, "account", account.id, "update", {k: str(v) for k, v in data.items()})
    db.commit()
    return _to_out(db, user, account)


@router.delete("/{account_id}")
def delete_account(account_id: int, force: bool = Query(False),
                   user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Löschen ⇒ standardmäßig Archivieren (4.2). Endgültig nur mit force=true."""
    account = require_account_access(db, user, account_id, "owner")
    tx_count = db.query(func.count(Transaction.id)).filter(Transaction.account_id == account_id).scalar()
    if not force:
        account.archived = True
        log(db, user.id, "account", account.id, "archive", {})
        db.commit()
        return {"archived": True, "transactions_affected": tx_count}
    db.query(Transaction).filter(Transaction.account_id == account_id).delete()
    db.query(AccountRole).filter(AccountRole.account_id == account_id).delete()
    log(db, user.id, "account", account.id, "delete", {"transactions_deleted": tx_count})
    db.delete(account)
    db.commit()
    return {"deleted": True, "transactions_affected": tx_count}


@router.get("/{account_id}/roles", response_model=list[RoleAssign])
def list_roles(account_id: int, user: User = Depends(get_current_user),
               db: Session = Depends(get_db)):
    require_account_access(db, user, account_id, "reader")
    return [RoleAssign(user_id=r.user_id, role=r.role)
            for r in db.query(AccountRole).filter(AccountRole.account_id == account_id).all()]


@router.put("/{account_id}/roles", response_model=list[RoleAssign])
def assign_role(account_id: int, payload: RoleAssign,
                user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    require_account_access(db, user, account_id, "owner")
    if payload.role not in ("owner", "editor", "reader", "none"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Unbekannte Rolle")
    existing = (db.query(AccountRole)
                .filter(AccountRole.account_id == account_id, AccountRole.user_id == payload.user_id)
                .first())
    if payload.role == "none":
        if existing:
            db.delete(existing)
    elif existing:
        existing.role = payload.role
    else:
        db.add(AccountRole(user_id=payload.user_id, account_id=account_id, role=payload.role))
    log(db, user.id, "account_role", account_id, "assign",
        {"user_id": payload.user_id, "role": payload.role})
    db.commit()
    return [RoleAssign(user_id=r.user_id, role=r.role)
            for r in db.query(AccountRole).filter(AccountRole.account_id == account_id).all()]
