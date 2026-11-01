"""
app/security.py — JWT issuing + FastAPI dependencies.

Login flow: Mini App sends initData -> backend verifies signature ->
backend issues its own signed token. From then on the API trusts ONLY
its own token, never raw frontend data.
"""
from __future__ import annotations

import time

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.models import User

settings = get_settings()
bearer = HTTPBearer(auto_error=True)


def _unauthorized(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=detail)


def create_token(user: User) -> str:
    payload = {
        "sub": str(user.id),
        "tg": user.telegram_id,
        "exp": int(time.time()) + settings.JWT_EXPIRE_DAYS * 86400,
        "iat": int(time.time()),
    }
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def get_current_user(
    creds: HTTPAuthorizationCredentials = Depends(bearer),
    db: Session = Depends(get_db),
) -> User:
    try:
        payload = jwt.decode(creds.credentials, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])
    except jwt.PyJWTError:
        raise _unauthorized("Token yaroqsiz yoki muddati tugagan")
    user = db.get(User, int(payload["sub"]))
    if user is None:
        raise _unauthorized("Foydalanuvchi topilmadi")
    return user


def is_admin_user(user: User) -> bool:
    """One rule for 'is this person a teacher/admin', used by every router.

    Web accounts have telegram_id NULL, so they are never admin — the admin
    surface stays tied to the ids listed in ADMIN_TELEGRAM_IDS.
    """
    return user.telegram_id in get_settings().admin_id_set
