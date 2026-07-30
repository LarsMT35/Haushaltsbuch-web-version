"""Kategorien mit drei Geltungsbereichen (4.6): global / kontobezogen / persönlich."""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import or_
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import accessible_account_ids, get_current_user, require_account_access
from ..models import Category, Rule, Transaction, TransactionSplit, User
from ..schemas import CategoryCreate, CategoryMerge, CategoryOut, CategoryUpdate
from ..services.audit import log

router = APIRouter(prefix="/categories", tags=["categories"])


def visible_categories_query(db: Session, user: User):
    account_ids = accessible_account_ids(db, user)
    return db.query(Category).filter(
        or_(
            Category.scope == "global",
            Category.user_id == user.id,
            Category.account_id.in_(account_ids) if account_ids else False,
        )
    )


@router.get("", response_model=list[CategoryOut])
def list_categories(include_inactive: bool = False,
                    user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    q = visible_categories_query(db, user)
    if not include_inactive:
        q = q.filter(Category.active.is_(True))
    return q.order_by(Category.name).all()


@router.post("", response_model=CategoryOut)
def create_category(payload: CategoryCreate, user: User = Depends(get_current_user),
                    db: Session = Depends(get_db)):
    if payload.scope not in ("global", "account", "personal"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Unbekannter Geltungsbereich")
    cat = Category(**payload.model_dump())
    if payload.scope == "account":
        if not payload.account_id:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Kontobezogene Kategorie braucht ein Konto")
        require_account_access(db, user, payload.account_id, "editor")
    elif payload.scope == "personal":
        cat.account_id = None
        cat.user_id = user.id
    elif payload.scope == "global" and not user.is_admin:
        # globale Kategorien betreffen alle Nutzer → nur Admin
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Globale Kategorien legt nur der Admin an")
    db.add(cat)
    db.flush()
    log(db, user.id, "category", cat.id, "create", {"name": cat.name, "scope": cat.scope})
    db.commit()
    return cat


def _editable_category(db: Session, user: User, category_id: int) -> Category:
    cat = db.get(Category, category_id)
    if cat is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Kategorie nicht gefunden")
    if cat.scope == "global" and not user.is_admin:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Globale Kategorien ändert nur der Admin")
    if cat.scope == "personal" and cat.user_id != user.id and not user.is_admin:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Fremde persönliche Kategorie")
    if cat.scope == "account":
        require_account_access(db, user, cat.account_id, "editor")
    return cat


@router.put("/{category_id}", response_model=CategoryOut)
def update_category(category_id: int, payload: CategoryUpdate,
                    user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    cat = _editable_category(db, user, category_id)
    for field, value in payload.model_dump(exclude_none=True).items():
        setattr(cat, field, value)
    log(db, user.id, "category", cat.id, "update", payload.model_dump(exclude_none=True, mode="json"))
    db.commit()
    return cat


@router.post("/{category_id}/merge", response_model=CategoryOut)
def merge_category(category_id: int, payload: CategoryMerge,
                   user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Kategorien zusammenführen ohne Datenverlust (4.6): alle Buchungen,
    Splits und Regeln wandern zur Zielkategorie, die Quelle wird deaktiviert."""
    source = _editable_category(db, user, category_id)
    target = db.get(Category, payload.target_category_id)
    if target is None or target.id == source.id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Ungültige Zielkategorie")
    db.query(Transaction).filter(Transaction.category_id == source.id).update({"category_id": target.id})
    db.query(TransactionSplit).filter(TransactionSplit.category_id == source.id).update({"category_id": target.id})
    db.query(Rule).filter(Rule.category_id == source.id).update({"category_id": target.id})
    db.query(Category).filter(Category.parent_id == source.id).update({"parent_id": target.id})
    source.active = False
    log(db, user.id, "category", source.id, "merge", {"target": target.id})
    db.commit()
    return target
