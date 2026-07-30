"""Wiederkehrende Kostenpositionen & Vorfinanzierungs-Abgleich (4.7 b).

Komplexeste Funktion des Systems: sie führt bis zu drei Buchungsströme über
zwei Konten zusammen (Abbuchung, Vorfinanzierungs-Dauerauftrag, monatliche
Erstattung) und baut auf der Umbuchungserkennung (4.4) auf. Die automatische
Erkennung ist deshalb bewusst ein Vorschlag – jede Verknüpfung lässt sich
genauso manuell setzen oder wieder lösen (Machbarkeitshinweis 4.7).
"""
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from dateutil.relativedelta import relativedelta
from sqlalchemy.orm import Session

from ..models import RecurringItem, RecurringLink, Transaction

AMPEL_GREEN_BELOW = 5.0   # Abweichung < 5 % vom Soll → grün
AMPEL_RED_FROM = 20.0     # Abweichung >= 20 % vom Soll → rot


def _text_match(tx: Transaction, needle: str) -> bool:
    if not needle.strip():
        return False
    n = needle.strip().lower()
    return n in (tx.counterparty or "").lower() or n in (tx.purpose or "").lower()


def _linked_transaction_ids(db: Session, item_id: int, role: str) -> set[int]:
    return {
        tid for (tid,) in db.query(RecurringLink.transaction_id)
        .filter(RecurringLink.recurring_item_id == item_id, RecurringLink.role == role)
        .all()
    }


def auto_link_item(db: Session, item: RecurringItem) -> tuple[int, int]:
    """Verknüpft noch unverknüpfte Kandidaten-Buchungen mit dieser Position.

    Kandidaten für "charge": Buchungen auf dem zahlenden Konto, deren
    Gegenpartei/Zweck match_text enthält (analog Rule-Matching, 4.6).
    Kandidaten für "reimbursement": Buchungen auf dem Vorfinanzierungskonto,
    die reimbursement_match_text enthalten.
    """
    charges_linked = 0
    reimbursements_linked = 0

    if item.paying_account_id and item.match_text.strip():
        already = _linked_transaction_ids(db, item.id, "charge")
        candidates = (db.query(Transaction)
                      .filter(Transaction.account_id == item.paying_account_id,
                              Transaction.transfer_id.is_(None),
                              ~Transaction.id.in_(already) if already else True)
                      .all())
        for tx in candidates:
            if _text_match(tx, item.match_text):
                db.add(RecurringLink(recurring_item_id=item.id, transaction_id=tx.id,
                                     role="charge", is_auto=True))
                charges_linked += 1

    if item.reimbursement_account_id and item.reimbursement_match_text.strip():
        already = _linked_transaction_ids(db, item.id, "reimbursement")
        candidates = (db.query(Transaction)
                      .filter(Transaction.account_id == item.reimbursement_account_id,
                              ~Transaction.id.in_(already) if already else True)
                      .all())
        for tx in candidates:
            if _text_match(tx, item.reimbursement_match_text):
                db.add(RecurringLink(recurring_item_id=item.id, transaction_id=tx.id,
                                     role="reimbursement", is_auto=True))
                reimbursements_linked += 1

    db.commit()
    return charges_linked, reimbursements_linked


def auto_link_all(db: Session, account_ids: list[int]) -> tuple[int, int]:
    items = (db.query(RecurringItem)
             .filter(RecurringItem.active.is_(True))
             .filter(RecurringItem.paying_account_id.in_(account_ids)
                     | RecurringItem.reimbursement_account_id.in_(account_ids))
             .all())
    total_c = total_r = 0
    for item in items:
        c, r = auto_link_item(db, item)
        total_c += c
        total_r += r
    return total_c, total_r


@dataclass
class ItemStatus:
    last_charge: Transaction | None
    is_prefinanced: bool
    soll: Decimal | None
    ist: Decimal | None
    suggested_rate: Decimal | None
    deviation_pct: float | None
    next_due_estimate: date | None


def compute_status(db: Session, item: RecurringItem) -> ItemStatus:
    """Soll (aufsummierte Erstattungen seit der letzten Abbuchung) gegen Ist
    (tatsächliche neue Abbuchung) – siehe 4.7 b."""
    charges = (db.query(Transaction)
               .join(RecurringLink, RecurringLink.transaction_id == Transaction.id)
               .filter(RecurringLink.recurring_item_id == item.id, RecurringLink.role == "charge")
               .order_by(Transaction.booking_date.desc())
               .all())
    last_charge = charges[0] if charges else None
    prev_charge = charges[1] if len(charges) > 1 else None
    is_prefinanced = bool(item.reimbursement_account_id)

    soll = ist = suggested_rate = None
    deviation_pct = None

    if last_charge is not None:
        ist = -last_charge.amount if last_charge.amount < 0 else last_charge.amount
        suggested_rate = (ist / item.cycle_months) if item.cycle_months else None

        if is_prefinanced:
            since = prev_charge.booking_date if prev_charge else date(1970, 1, 1)
            reimbursements = (db.query(Transaction)
                              .join(RecurringLink, RecurringLink.transaction_id == Transaction.id)
                              .filter(RecurringLink.recurring_item_id == item.id,
                                      RecurringLink.role == "reimbursement",
                                      Transaction.booking_date > since,
                                      Transaction.booking_date <= last_charge.booking_date)
                              .all())
            soll = sum((abs(t.amount) for t in reimbursements), Decimal("0"))
            if soll:
                deviation_pct = float(abs(ist - soll) / soll * 100)

    next_due = None
    if last_charge is not None:
        next_due = last_charge.booking_date + relativedelta(months=item.cycle_months)

    return ItemStatus(last_charge=last_charge, is_prefinanced=is_prefinanced,
                      soll=soll, ist=ist, suggested_rate=suggested_rate,
                      deviation_pct=deviation_pct, next_due_estimate=next_due)


def ampel_for(deviation_pct: float | None) -> str:
    if deviation_pct is None:
        return "gruen"
    if deviation_pct < AMPEL_GREEN_BELOW:
        return "gruen"
    if deviation_pct < AMPEL_RED_FROM:
        return "gelb"
    return "rot"
