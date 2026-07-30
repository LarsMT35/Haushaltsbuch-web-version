"""Kategorisierungsregeln (4.6) inkl. rückwirkender Neuanwendung."""
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import accessible_account_ids, get_current_user
from ..models import Rule, Transaction, User
from ..schemas import RuleCreate, RuleOut, RuleUpdate
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
