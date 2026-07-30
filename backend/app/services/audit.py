"""Änderungsprotokoll (4.1): wer hat wann was geändert."""
from sqlalchemy.orm import Session

from ..models import AuditLog


def log(db: Session, user_id: int | None, entity: str, entity_id, action: str, detail: dict | None = None):
    db.add(AuditLog(user_id=user_id, entity=entity, entity_id=str(entity_id),
                    action=action, detail=detail or {}))
