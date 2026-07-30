"""Import (4.5): Profile, Mapping-Assistent, Vorschau, Duplikate, Batch + Rollback."""
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import accessible_account_ids, get_current_user, require_account_access
from ..models import Account, BankProfile, ImportBatch, Transaction, Transfer, User
from ..schemas import (
    AnalyzeOut,
    BankProfileCreate,
    BankProfileOut,
    ImportBatchOut,
    ImportCommitIn,
    ImportPreviewOut,
    ParsedRow,
)
from ..services.audit import log
from ..services.csv_import import analyze_csv, parse_csv
from ..services.rules_engine import categorize, load_rules
from ..services.transfers import auto_link_transfers

router = APIRouter(prefix="/imports", tags=["imports"])


# ------------------------------------------------------------------ Profile

@router.get("/profiles", response_model=list[BankProfileOut])
def list_profiles(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return db.query(BankProfile).order_by(BankProfile.name).all()


@router.post("/profiles", response_model=BankProfileOut)
def create_profile(payload: BankProfileCreate, user: User = Depends(get_current_user),
                   db: Session = Depends(get_db)):
    """Neues Importprofil – Ergebnis des Mapping-Assistenten wird hier gespeichert."""
    if db.query(BankProfile).filter(BankProfile.name == payload.name).first():
        raise HTTPException(status.HTTP_409_CONFLICT, "Profilname existiert bereits")
    profile = BankProfile(**payload.model_dump())
    db.add(profile)
    db.flush()
    log(db, user.id, "bank_profile", profile.id, "create", {"name": profile.name})
    db.commit()
    return profile


@router.post("/analyze", response_model=AnalyzeOut)
def analyze(file: UploadFile = File(...), user: User = Depends(get_current_user)):
    """Mapping-Assistent Schritt 1: unbekannte CSV → erkannte Struktur (4.5)."""
    try:
        return analyze_csv(file.file.read())
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))


# ----------------------------------------------------------------- Vorschau

@router.post("/preview", response_model=ImportPreviewOut)
def preview(file: UploadFile = File(...), profile_id: int = Form(...),
            account_id: int | None = Form(None),
            user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    profile = db.get(BankProfile, profile_id)
    if profile is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Importprofil nicht gefunden")
    try:
        result = parse_csv(file.file.read(), profile)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))

    # Zielkonto automatisch über IBAN erkennen (4.5)
    suggested_account_id = account_id
    if suggested_account_id is None and result["detected_ibans"]:
        my_ids = accessible_account_ids(db, user)
        for iban in result["detected_ibans"]:
            acc = (db.query(Account)
                   .filter(func.replace(Account.iban, " ", "") == iban, Account.id.in_(my_ids))
                   .first())
            if acc:
                suggested_account_id = acc.id
                break

    # Duplikate: Anzahl gleicher Buchungen je Hash vergleichen statt stumpf
    # verwerfen – echte Doppelungen kommen vor (4.5)
    rules = load_rules(db)
    hashes = [r["dedup_hash"] for r in result["rows"] if r["dedup_hash"]]
    db_counts: dict[str, int] = {}
    if hashes and suggested_account_id:
        q = (db.query(Transaction.dedup_hash, func.count(Transaction.id))
             .filter(Transaction.account_id == suggested_account_id,
                     Transaction.dedup_hash.in_(hashes))
             .group_by(Transaction.dedup_hash))
        db_counts = dict(q.all())

    seen_in_file: dict[str, int] = {}
    rows_out: list[ParsedRow] = []
    for r in result["rows"]:
        h = r["dedup_hash"]
        occurrence = seen_in_file.get(h, 0)
        seen_in_file[h] = occurrence + 1
        duplicate = "new"
        include = True
        if h and h in db_counts:
            if occurrence < db_counts[h]:
                duplicate = "duplicate"
                include = False
            else:
                duplicate = "suspect"  # mehr Vorkommen als in der DB → bestätigen lassen
        rule = None
        if not r["error"] and r["amount"] is not None:
            rule = categorize(rules, purpose=r["purpose"], counterparty=r["counterparty"],
                              counterparty_iban=r["counterparty_iban"],
                              booking_text=r["booking_text"], amount=r["amount"],
                              account_id=suggested_account_id)
        rows_out.append(ParsedRow(
            **r, duplicate=duplicate, include=include and not r["error"],
            suggested_category_id=rule.category_id if rule else None,
            matched_rule_id=rule.id if rule else None,
        ))

    return ImportPreviewOut(profile_id=profile.id, filename=file.filename or "import.csv",
                            suggested_account_id=suggested_account_id,
                            detected_ibans=result["detected_ibans"], rows=rows_out)


# ------------------------------------------------------------------- Commit

@router.post("/commit", response_model=ImportBatchOut)
def commit(payload: ImportCommitIn, user: User = Depends(get_current_user),
           db: Session = Depends(get_db)):
    account = require_account_access(db, user, payload.account_id, "editor")
    profile = db.get(BankProfile, payload.profile_id)
    batch = ImportBatch(filename=payload.filename, user_id=user.id,
                        profile_id=profile.id if profile else None)
    db.add(batch)
    db.flush()

    count = 0
    for row in payload.rows:
        if not row.include or row.error or row.booking_date is None or row.amount is None:
            continue
        db.add(Transaction(
            account_id=account.id, booking_date=row.booking_date, value_date=row.value_date,
            amount=row.amount, currency=row.currency or account.currency,
            amount_ref=row.amount,  # EUR-Konten 1:1; Fremdwährung: Kurslogik ab v2 (4.3)
            counterparty=row.counterparty, counterparty_iban=row.counterparty_iban,
            purpose=row.purpose, booking_text=row.booking_text,
            category_id=row.suggested_category_id, import_batch_id=batch.id,
            raw_line=row.raw_line, dedup_hash=row.dedup_hash,
        ))
        count += 1
    batch.num_transactions = count
    log(db, user.id, "import_batch", batch.id, "commit",
        {"file": batch.filename, "count": count, "account_id": account.id})
    db.commit()

    # Umbuchungserkennung über alle zugänglichen Konten (4.4)
    auto_link_transfers(db, accessible_account_ids(db, user))
    db.refresh(batch)
    return batch


# ------------------------------------------------------------------ Batches

@router.get("/batches", response_model=list[ImportBatchOut])
def list_batches(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return db.query(ImportBatch).order_by(ImportBatch.created_at.desc()).limit(100).all()


@router.delete("/batches/{batch_id}", response_model=ImportBatchOut)
def rollback(batch_id: int, user: User = Depends(get_current_user),
             db: Session = Depends(get_db)):
    """Import komplett rückgängig machen (Prinzip 7)."""
    batch = db.get(ImportBatch, batch_id)
    if batch is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Import-Vorgang nicht gefunden")
    if batch.reverted:
        return batch
    txs = db.query(Transaction).filter(Transaction.import_batch_id == batch.id).all()
    if txs:
        require_account_access(db, user, txs[0].account_id, "editor")
    for tx in txs:
        if tx.transfer_id:  # Umbuchungs-Verknüpfung sauber auflösen
            transfer = db.get(Transfer, tx.transfer_id)
            for other in db.query(Transaction).filter(Transaction.transfer_id == transfer.id).all():
                other.transfer_id = None
            db.delete(transfer)
        db.delete(tx)
    batch.reverted = True
    log(db, user.id, "import_batch", batch.id, "rollback", {"count": len(txs)})
    db.commit()
    return batch
