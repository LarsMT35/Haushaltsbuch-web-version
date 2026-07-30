from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from .db import get_db
from .models import Account, AccountRole, ROLE_RANK, User
from .security import decode_access_token

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")


def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> User:
    user_id = decode_access_token(token)
    if user_id is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Ungültige oder abgelaufene Sitzung")
    user = db.get(User, user_id)
    if user is None or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Benutzer nicht gefunden oder deaktiviert")
    return user


def require_admin(user: User = Depends(get_current_user)) -> User:
    if not user.is_admin:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Nur für Administratoren")
    return user


def account_role(db: Session, user: User, account_id: int) -> str | None:
    if user.is_admin:
        return "owner"
    role = (
        db.query(AccountRole)
        .filter(AccountRole.user_id == user.id, AccountRole.account_id == account_id)
        .first()
    )
    return role.role if role else None


def require_account_access(db: Session, user: User, account_id: int, min_role: str = "reader") -> Account:
    account = db.get(Account, account_id)
    if account is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Konto nicht gefunden")
    role = account_role(db, user, account_id)
    if role is None or ROLE_RANK[role] < ROLE_RANK[min_role]:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Keine ausreichende Berechtigung für dieses Konto")
    return account


def accessible_account_ids(db: Session, user: User) -> list[int]:
    if user.is_admin:
        return [a.id for a in db.query(Account.id).all()]
    return [r.account_id for r in db.query(AccountRole).filter(AccountRole.user_id == user.id).all()]
