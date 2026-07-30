"""Benutzerverwaltung (4.1): Anlage nur durch Admin, keine Selbstregistrierung."""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import require_admin
from ..models import User
from ..schemas import UserCreate, UserOut, UserUpdate
from ..security import hash_password
from ..services.audit import log

router = APIRouter(prefix="/users", tags=["users"], dependencies=[Depends(require_admin)])


@router.get("", response_model=list[UserOut])
def list_users(db: Session = Depends(get_db)):
    return db.query(User).order_by(User.username).all()


@router.post("", response_model=UserOut)
def create_user(payload: UserCreate, db: Session = Depends(get_db),
                admin: User = Depends(require_admin)):
    if db.query(User).filter(User.username == payload.username).first():
        raise HTTPException(status.HTTP_409_CONFLICT, "Benutzername existiert bereits")
    user = User(username=payload.username, password_hash=hash_password(payload.password),
                display_name=payload.display_name, is_admin=payload.is_admin)
    db.add(user)
    db.flush()
    log(db, admin.id, "user", user.id, "create", {"username": user.username})
    db.commit()
    return user


@router.put("/{user_id}", response_model=UserOut)
def update_user(user_id: int, payload: UserUpdate, db: Session = Depends(get_db),
                admin: User = Depends(require_admin)):
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Benutzer nicht gefunden")
    data = payload.model_dump(exclude_none=True)
    if "password" in data:
        user.password_hash = hash_password(data.pop("password"))
    for field, value in data.items():
        setattr(user, field, value)
    log(db, admin.id, "user", user.id, "update", {k: str(v) for k, v in data.items()})
    db.commit()
    return user
