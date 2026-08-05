"""Optionale KI-Schnittstelle gegen eine lokale Ollama-Instanz (4.6).

Die App funktioniert vollständig ohne: ist `OLLAMA_URL` nicht gesetzt, melden
alle Endpunkte 503 und die Oberfläche blendet die Funktion aus. Die KI ordnet
nie selbst zu – sie liefert Vorschläge, die der Nutzer bestätigt (wie die
Umbuchungs-Vorschläge in 4.4).
"""
import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..config import settings
from ..db import get_db
from ..deps import accessible_account_ids, get_current_user
from ..models import Category, Transaction, User
from ..schemas import (
    AiCategorySuggestion,
    AiStatusOut,
    AiSuggestRequest,
    AiSuggestionsOut,
)
from ..services import ai
from ..services.audit import log
from .categories import visible_categories_query

router = APIRouter(prefix="/ai", tags=["ai"])


@router.get("/status", response_model=AiStatusOut)
def ai_status(user: User = Depends(get_current_user)):
    """Ob und welche lokale Instanz eingerichtet ist – die Oberfläche zeigt die
    KI-Funktionen nur, wenn hier `enabled` zurückkommt."""
    if not ai.is_enabled():
        return AiStatusOut(enabled=False, reachable=False,
                           detail="Nicht eingerichtet – OLLAMA_URL in der .env setzen.")
    try:
        models = ai.list_models()
    except Exception as exc:  # Instanz aus, falsche URL, Netz weg …
        return AiStatusOut(enabled=True, reachable=False, url=settings.ollama_url,
                           model=settings.ollama_model,
                           detail=f"Instanz nicht erreichbar: {exc}")
    installed = settings.ollama_model in models
    return AiStatusOut(
        enabled=True, reachable=True, url=settings.ollama_url,
        model=settings.ollama_model, models=models,
        detail=None if installed else
        f"Modell '{settings.ollama_model}' ist dort nicht installiert (ollama pull {settings.ollama_model}).")


def _require_ai():
    if not ai.is_enabled():
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE,
                            "Keine lokale KI eingerichtet (OLLAMA_URL nicht gesetzt)")


@router.post("/suggest-categories", response_model=AiSuggestionsOut)
def suggest_categories(payload: AiSuggestRequest,
                       user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Kategorievorschläge für noch nicht zugeordnete Buchungen.

    Greift dort, wo keine Regel passt (4.6). Übertragen werden nur Gegenpartei,
    Verwendungszweck und Betrag – keine IBANs oder Salden. Übernommen wird
    nichts automatisch; aus einem bestätigten Vorschlag lässt sich in der
    Buchungsliste wie gewohnt eine dauerhafte Regel machen.
    """
    _require_ai()
    ids = accessible_account_ids(db, user)
    if payload.account_ids:
        ids = [a for a in payload.account_ids if a in ids] or ids

    q = (db.query(Transaction)
         .filter(Transaction.account_id.in_(ids), Transaction.category_id.is_(None),
                 Transaction.transfer_id.is_(None))
         .order_by(Transaction.booking_date.desc()))
    txs = [t for t in q.limit(max(1, min(payload.limit, 50))).all() if not t.splits]
    if not txs:
        return AiSuggestionsOut(model=settings.ollama_model, suggestions=[],
                                detail="Keine unzugeordneten Buchungen gefunden.")

    categories = [c for c in visible_categories_query(db, user)
                  .filter(Category.active.is_(True)).all() if not c.is_transfer_like]
    if not categories:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Keine Kategorien vorhanden")
    by_name = {c.name: c for c in categories}

    payload_txs = [{"id": t.id, "counterparty": t.counterparty or "",
                    "purpose": (t.purpose or "")[:180], "amount": float(t.amount)}
                   for t in txs]
    try:
        raw = ai.suggest_categories(payload_txs, list(by_name))
    except httpx.HTTPError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY,
                            f"Lokale KI nicht erreichbar: {exc}") from exc
    except ValueError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY,
                            f"Antwort der KI unbrauchbar: {exc}") from exc

    tx_by_id = {t.id: t for t in txs}
    suggestions = []
    for item in raw:
        t = tx_by_id[item["id"]]
        cat = by_name[item["category"]]
        suggestions.append(AiCategorySuggestion(
            transaction_id=t.id, booking_date=t.booking_date,
            counterparty=t.counterparty, purpose=t.purpose, amount=float(t.amount),
            category_id=cat.id, category_name=cat.name,
            confidence=item["confidence"], reason=item["reason"]))

    log(db, user.id, "ai", "", "suggest_categories",
        {"asked": len(payload_txs), "suggested": len(suggestions), "model": settings.ollama_model})
    db.commit()
    return AiSuggestionsOut(model=settings.ollama_model, suggestions=suggestions,
                            detail=None if suggestions else
                            "Die KI hat sich bei keiner der Buchungen festgelegt.")
