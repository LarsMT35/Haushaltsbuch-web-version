"""Regel-Engine (4.6): Nachfolger der Excel-Whitelisten.

Kriterien innerhalb einer Regel sind UND-verknüpft; bei mehreren passenden
Regeln gewinnt die mit der niedrigsten Prioritätszahl (explizite Reihenfolge
statt impliziter Spaltenreihenfolge wie in Excel).
"""
from decimal import Decimal

from sqlalchemy.orm import Session

from ..models import Rule


def load_rules(db: Session) -> list[Rule]:
    return (
        db.query(Rule)
        .filter(Rule.active.is_(True))
        .order_by(Rule.priority.asc(), Rule.id.asc())
        .all()
    )


def _contains(haystack: str, needle: str) -> bool:
    return needle.strip().lower() in (haystack or "").lower()


def match_rule(rule: Rule, *, purpose: str, counterparty: str, counterparty_iban: str,
               booking_text: str, amount: Decimal | None, account_id: int | None) -> bool:
    if rule.account_id is not None and rule.account_id != account_id:
        return False
    if rule.text_contains and not _contains(purpose, rule.text_contains):
        return False
    if rule.counterparty_contains and not _contains(counterparty, rule.counterparty_contains):
        return False
    if rule.iban_equals and rule.iban_equals.replace(" ", "").lower() != (counterparty_iban or "").replace(" ", "").lower():
        return False
    if rule.booking_text_contains and not _contains(booking_text, rule.booking_text_contains):
        return False
    if rule.amount_min is not None and (amount is None or amount < rule.amount_min):
        return False
    if rule.amount_max is not None and (amount is None or amount > rule.amount_max):
        return False
    # Regel ohne jedes Kriterium darf nie alles fangen
    has_criteria = any([rule.text_contains, rule.counterparty_contains, rule.iban_equals,
                        rule.booking_text_contains, rule.amount_min is not None,
                        rule.amount_max is not None])
    return has_criteria


def categorize(rules: list[Rule], **fields) -> Rule | None:
    """Erste passende Regel gewinnt (Regelpriorität, 4.6)."""
    for rule in rules:
        if match_rule(rule, **fields):
            return rule
    return None
