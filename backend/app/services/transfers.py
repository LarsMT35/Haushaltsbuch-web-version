"""Umbuchungserkennung (4.4).

Eine Überweisung Giro → Tagesgeld taucht in zwei CSV-Exporten auf (Abgang +
Zugang). Zusammengehörige Gegenbuchungen werden zu EINER Umbuchung verknüpft,
die in Einnahmen/Ausgaben nicht mitzählt.

Automatisch verknüpft wird nur der sichere Fall (Gegen-IBAN = IBAN eines
eigenen Kontos); alles andere landet als Vorschlag zur manuellen Bestätigung.
"""
from datetime import timedelta

from sqlalchemy.orm import Session

from ..models import Account, Transaction, Transfer

DATE_TOLERANCE_DAYS = 5


def _candidate_pairs(db: Session, account_ids: list[int]):
    """Paare (a, b): gegenläufiger gleicher Betrag, Datum ±Toleranz,
    verschiedene eigene Konten, beide noch unverknüpft."""
    txs = (
        db.query(Transaction)
        .filter(Transaction.account_id.in_(account_ids), Transaction.transfer_id.is_(None))
        .order_by(Transaction.booking_date.asc())
        .all()
    )
    negatives = [t for t in txs if t.amount < 0]
    positives = {t.id: t for t in txs if t.amount > 0}
    used: set[int] = set()
    pairs = []
    for a in negatives:
        for b in positives.values():
            if b.id in used or b.account_id == a.account_id:
                continue
            if b.amount != -a.amount:
                continue
            if abs((b.booking_date - a.booking_date).days) > DATE_TOLERANCE_DAYS:
                continue
            pairs.append((a, b))
            used.add(b.id)
            break
    return pairs


def _iban_match(db: Session, a: Transaction, b: Transaction) -> bool:
    acc_a = db.get(Account, a.account_id)
    acc_b = db.get(Account, b.account_id)
    a_iban = (a.counterparty_iban or "").replace(" ", "").upper()
    b_iban = (b.counterparty_iban or "").replace(" ", "").upper()
    return bool(
        (acc_b.iban and a_iban == acc_b.iban.replace(" ", "").upper())
        or (acc_a.iban and b_iban == acc_a.iban.replace(" ", "").upper())
    )


def auto_link_transfers(db: Session, account_ids: list[int]) -> int:
    """Sichere Fälle (IBAN-Beleg) automatisch verknüpfen. Rückgabe: Anzahl."""
    count = 0
    for a, b in _candidate_pairs(db, account_ids):
        if _iban_match(db, a, b):
            transfer = Transfer(is_auto=True)
            db.add(transfer)
            db.flush()
            a.transfer_id = transfer.id
            b.transfer_id = transfer.id
            count += 1
    db.commit()
    return count


def transfer_suggestions(db: Session, account_ids: list[int]) -> list[tuple[Transaction, Transaction]]:
    """Unsichere Kandidaten für die manuelle Bestätigung."""
    return [(a, b) for a, b in _candidate_pairs(db, account_ids) if not _iban_match(db, a, b)]


def link_manual(db: Session, a: Transaction, b: Transaction) -> Transfer:
    transfer = Transfer(is_auto=False)
    db.add(transfer)
    db.flush()
    a.transfer_id = transfer.id
    b.transfer_id = transfer.id
    db.commit()
    return transfer


def unlink(db: Session, transfer: Transfer) -> None:
    for tx in db.query(Transaction).filter(Transaction.transfer_id == transfer.id).all():
        tx.transfer_id = None
    db.delete(transfer)
    db.commit()
