"""Kategorien mit drei Geltungsbereichen (4.6): global / kontobezogen / persönlich."""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import or_
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import accessible_account_ids, get_current_user, require_account_access
from ..models import Account, Category, Rule, Transaction, TransactionSplit, User
from ..schemas import (
    CategoryCreate,
    CategoryExportItem,
    CategoryImportResult,
    CategoryMerge,
    CategoryOut,
    CategoryUpdate,
)
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
    if cat.transfer_target_account_id:
        # ein Zielkonto macht eine Kategorie implizit "wie Umbuchung" (4.4/4.9)
        require_account_access(db, user, cat.transfer_target_account_id, "editor")
        cat.is_transfer_like = True
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
    data = payload.model_dump(exclude_none=True, exclude={"transfer_target_account_id"})
    for field, value in data.items():
        setattr(cat, field, value)
    # eigenes Feld, da null hier "Zielkonto entfernen" bedeutet statt
    # "nicht mitgeschickt" (im Unterschied zu den übrigen, per exclude_none
    # behandelten Feldern)
    if "transfer_target_account_id" in payload.model_fields_set:
        if payload.transfer_target_account_id is not None:
            require_account_access(db, user, payload.transfer_target_account_id, "editor")
            cat.is_transfer_like = True  # ein Zielkonto macht die Kategorie implizit "wie Umbuchung"
        cat.transfer_target_account_id = payload.transfer_target_account_id
        data["transfer_target_account_id"] = payload.transfer_target_account_id
    log(db, user.id, "category", cat.id, "update", data)
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


# --------------------------------------------------- Export / Import (4.11)

@router.get("/export", response_model=list[CategoryExportItem])
def export_categories(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Kategorien als portable JSON-Liste (Namen statt IDs, Prinzip 1) –
    z.B. für Backup oder Umzug auf eine andere Installation."""
    cats = visible_categories_query(db, user).all()
    by_id = {c.id: c for c in cats}
    account_ids = {c.account_id for c in cats if c.account_id}
    account_ids |= {c.transfer_target_account_id for c in cats if c.transfer_target_account_id}
    account_names = {a.id: a.name for a in db.query(Account).filter(Account.id.in_(account_ids)).all()} if account_ids else {}
    return [
        CategoryExportItem(
            name=c.name, parent_name=by_id[c.parent_id].name if c.parent_id in by_id else None,
            scope=c.scope, account_name=account_names.get(c.account_id),
            is_fixed_cost=c.is_fixed_cost, is_transfer_like=c.is_transfer_like,
            transfer_target_account_name=account_names.get(c.transfer_target_account_id),
            active=c.active,
        )
        for c in cats
    ]


@router.post("/import", response_model=CategoryImportResult)
def import_categories(payload: list[CategoryExportItem], user: User = Depends(get_current_user),
                      db: Session = Depends(get_db)):
    """Kategorien aus einer JSON-Liste einspielen – additiv und idempotent:
    bestehende Kategorien (nach Name+Geltungsbereich) werden nicht doppelt
    angelegt, ihr Fixkosten-Flag wird aber synchronisiert."""
    existing = {(c.name, c.scope): c for c in visible_categories_query(db, user).all()}
    account_ids = accessible_account_ids(db, user)
    accounts_by_name = {a.name: a for a in db.query(Account).filter(Account.id.in_(account_ids)).all()}

    created = updated_fixed = skipped_no_permission = skipped_no_account = skipped_existing = 0
    for item in payload:
        key = (item.name, item.scope)
        target_account = accounts_by_name.get(item.transfer_target_account_name or "")
        target_account_id = target_account.id if target_account else None
        if key in existing:
            cat = existing[key]
            changed = False
            if cat.is_fixed_cost != item.is_fixed_cost:
                cat.is_fixed_cost = item.is_fixed_cost
                changed = True
            if cat.is_transfer_like != item.is_transfer_like:
                cat.is_transfer_like = item.is_transfer_like
                changed = True
            # Zielkonto nur übernehmen, wenn es (unter diesem Namen) existiert
            # -- sonst bestehende Verknüpfung nicht stillschweigend loeschen,
            # z.B. weil das Depot auf dieser Installation anders heisst.
            if target_account_id and cat.transfer_target_account_id != target_account_id:
                cat.transfer_target_account_id = target_account_id
                changed = True
            if changed:
                updated_fixed += 1
            else:
                skipped_existing += 1
            continue
        if item.scope == "global" and not user.is_admin:
            skipped_no_permission += 1
            continue
        account_id = None
        if item.scope == "account":
            account = accounts_by_name.get(item.account_name or "")
            if account is None:
                skipped_no_account += 1
                continue
            account_id = account.id
        cat = Category(name=item.name, scope=item.scope, account_id=account_id,
                       user_id=user.id if item.scope == "personal" else None,
                       is_fixed_cost=item.is_fixed_cost, is_transfer_like=item.is_transfer_like,
                       transfer_target_account_id=target_account_id,
                       active=item.active)
        db.add(cat)
        db.flush()
        existing[key] = cat
        created += 1

    # Zweiter Durchgang: Ober-/Unterkategorie-Beziehung auflösen (4.6)
    for item in payload:
        if not item.parent_name:
            continue
        cat = existing.get((item.name, item.scope))
        parent = next((c for (n, s), c in existing.items() if n == item.parent_name), None)
        if cat and parent and cat.parent_id is None:
            cat.parent_id = parent.id

    log(db, user.id, "category", "", "import",
        {"created": created, "updated_fixed_cost": updated_fixed})
    db.commit()
    return CategoryImportResult(created=created, updated_fixed_cost=updated_fixed,
                                skipped_existing=skipped_existing,
                                skipped_no_permission=skipped_no_permission,
                                skipped_no_account=skipped_no_account)
