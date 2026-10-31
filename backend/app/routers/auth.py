"""app/routers/auth.py — Telegram login endpoints (Mini App + web widget)."""
from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.db import get_db
from app.models import User
from app.schemas import TelegramLoginRequest, TokenResponse
from app.security import create_token
from app.telegram_auth import TelegramAuthError, verify_init_data, verify_web_login

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _issue_token(db: Session, tg_user: dict, settings: Settings) -> TokenResponse:
    """Upsert the Telegram user and return our JWT (shared by both logins)."""
    if not settings.JWT_SECRET:
        # jwt.encode crashes on an empty key; say so clearly instead of a 500.
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Server JWT_SECRET sozlanmagan — administratorga xabar bering.",
        )

    telegram_id = int(tg_user["id"])
    user = db.scalar(select(User).where(User.telegram_id == telegram_id))
    if user is None:
        user = User(
            telegram_id=telegram_id,
            username=tg_user.get("username"),
            first_name=tg_user.get("first_name", ""),
            last_name=tg_user.get("last_name"),
        )
        db.add(user)
        db.flush()
    else:
        # Keep name fresh if the child changed it in Telegram.
        user.username = tg_user.get("username") or user.username
        user.first_name = tg_user.get("first_name", user.first_name)

    db.commit()
    return TokenResponse(access_token=create_token(user), first_name=user.first_name)


@router.post("/telegram", response_model=TokenResponse)
def telegram_login(body: TelegramLoginRequest, db: Session = Depends(get_db)) -> TokenResponse:
    """Verify initData signature with OUR bot token, then upsert the pupil."""
    settings = get_settings()
    try:
        tg_user = verify_init_data(body.init_data, settings.BOT_TOKEN)
    except TelegramAuthError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail=str(exc))
    return _issue_token(db, tg_user, settings)


@router.post("/telegram-web", response_model=TokenResponse)
def telegram_web_login(
    body: dict[str, Any] = Body(...), db: Session = Depends(get_db)
) -> TokenResponse:
    """Telegram Login Widget callback (browser, OUTSIDE Telegram).

    The widget hands the page {id, first_name, ..., auth_date, hash}; the hash
    is HMAC-SHA256 with SHA256(bot_token) as key. Never trust the fields until
    that hash is verified here.
    """
    settings = get_settings()
    try:
        tg_user = verify_web_login(body, settings.BOT_TOKEN)
    except TelegramAuthError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail=str(exc))
    return _issue_token(db, tg_user, settings)

