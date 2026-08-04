"""Kategorisierungsregeln (4.6) inkl. rückwirkender Neuanwendung."""
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import accessible_account_ids, get_current_user
from ..models import Account, Category, Rule, Transaction, User
from ..schemas import RuleCreate, RuleExportItem, RuleImportResult, RuleOut, RuleUpdate
from ..services.audit import log
from ..services.rules_engine import categorize, load_rules

router = APIRouter(prefix="/rules", tags=["rules"])


@router.get("", response_model=list[RuleOut])
def list_rules(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return db.query(Rule).order_by(Rule.priority.asc(), Rule.id.asc()).all()


@router.post("", response_model=RuleOut)
def create_rule(payload: RuleCreate, user: User = Depends(get_current_user),
                db: Session = Depends(get_db)):
    rule = Rule(**payload.model_dump())
    db.add(rule)
    db.flush()
    log(db, user.id, "rule", rule.id, "create", {"name": rule.name})
    db.commit()
    return rule


@router.put("/{rule_id}", response_model=RuleOut)
def update_rule(rule_id: int, payload: RuleUpdate,
                user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rule = db.get(Rule, rule_id)
    if rule is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Regel nicht gefunden")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(rule, field, value)
    log(db, user.id, "rule", rule.id, "update", payload.model_dump(exclude_unset=True, mode="json"))
    db.commit()
    return rule


@router.delete("/{rule_id}")
def delete_rule(rule_id: int, user: User = Depends(get_current_user),
                db: Session = Depends(get_db)):
    rule = db.get(Rule, rule_id)
    if rule is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Regel nicht gefunden")
    log(db, user.id, "rule", rule.id, "delete", {"name": rule.name})
    db.delete(rule)
    db.commit()
    return {"ok": True}


@router.post("/reapply")
def reapply_rules(only_unassigned: bool = Query(True),
                  user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Regeln rückwirkend auf bestehende Buchungen anwenden (4.6, Prinzip 2)."""
    account_ids = accessible_account_ids(db, user)
    rules = load_rules(db)
    q = db.query(Transaction).filter(Transaction.account_id.in_(account_ids))
    if only_unassigned:
        q = q.filter(Transaction.category_id.is_(None))
    changed = 0
    for tx in q.all():
        rule = categorize(rules, purpose=tx.purpose, counterparty=tx.counterparty,
                          counterparty_iban=tx.counterparty_iban, booking_text=tx.booking_text,
                          amount=tx.amount, account_id=tx.account_id)
        if rule and tx.category_id != rule.category_id:
            tx.category_id = rule.category_id
            changed += 1
    log(db, user.id, "rule", "", "reapply", {"changed": changed})
    db.commit()
    return {"changed": changed}


# --------------------------------------------------- Export / Import (4.11)

@router.get("/export", response_model=list[RuleExportItem])
def export_rules(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Regeln als portable JSON-Liste (Namen statt IDs, Prinzip 1) – z.B. für
    Backup oder um eine Regelsammlung auf eine andere Installation zu übertragen."""
    rules = db.query(Rule).order_by(Rule.priority.asc(), Rule.id.asc()).all()
    cat_names = {c.id: c.name for c in db.query(Category).all()}
    acc_names = {a.id: a.name for a in db.query(Account).all()}
    return [
        RuleExportItem(
            name=r.name, category_name=cat_names.get(r.category_id, ""), priority=r.priority,
            active=r.active, text_contains=r.text_contains,
            counterparty_contains=r.counterparty_contains, iban_equals=r.iban_equals,
            booking_text_contains=r.booking_text_contains, amount_min=r.amount_min,
            amount_max=r.amount_max, account_name=acc_names.get(r.account_id),
        )
        for r in rules
    ]


@router.post("/import", response_model=RuleImportResult)
def import_rules(payload: list[RuleExportItem], user: User = Depends(get_current_user),
                 db: Session = Depends(get_db)):
    """Regeln aus einer JSON-Liste einspielen – additiv und idempotent:
    identische Regeln (gleiche Kategorie + gleiche Kriterien) werden
    übersprungen statt doppelt angelegt."""
    cat_by_name = {c.name: c for c in db.query(Category).all()}
    account_ids = accessible_account_ids(db, user)
    acc_by_name = {a.name: a for a in db.query(Account).filter(Account.id.in_(account_ids)).all()}

    def key_of(category_id, text, counterparty, iban, booking_text, amin, amax, account_id):
        return (category_id, text.lower(), counterparty.lower(), iban.lower(),
               booking_text.lower(), amin, amax, account_id)

    existing_keys = {
        key_of(r.category_id, r.text_contains, r.counterparty_contains, r.iban_equals,
              r.booking_text_contains, r.amount_min, r.amount_max, r.account_id)
        for r in db.query(Rule).all()
    }

    created = skipped_duplicate = skipped_no_category = skipped_no_account = 0
    for item in payload:
        category = cat_by_name.get(item.category_name)
        if category is None:
            skipped_no_category += 1
            continue
        account_id = None
        if item.account_name:
            account = acc_by_name.get(item.account_name)
            if account is None:
                skipped_no_account += 1
                continue
            account_id = account.id
        key = key_of(category.id, item.text_contains, item.counterparty_contains, item.iban_equals,
                    item.booking_text_contains, item.amount_min, item.amount_max, account_id)
        if key in existing_keys:
            skipped_duplicate += 1
            continue
        db.add(Rule(
            name=item.name, category_id=category.id, priority=item.priority, active=item.active,
            text_contains=item.text_contains, counterparty_contains=item.counterparty_contains,
            iban_equals=item.iban_equals, booking_text_contains=item.booking_text_contains,
            amount_min=item.amount_min, amount_max=item.amount_max, account_id=account_id,
        ))
        existing_keys.add(key)
        created += 1

    log(db, user.id, "rule", "", "import", {"created": created})
    db.commit()
    return RuleImportResult(created=created, skipped_duplicate=skipped_duplicate,
                            skipped_no_category=skipped_no_category,
                            skipped_no_account=skipped_no_account)
