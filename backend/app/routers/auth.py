"""app/routers/auth.py — login endpoints.

Three doors into the SAME pupil account model:
  * /telegram      — Mini App inside Telegram (initData, HMAC verified)
  * /telegram-web  — Telegram Login Widget in a normal browser
  * /register + /login — email-free username/password account for pupils who
    have no Telegram at all (scrypt hashed, see app/passwords.py)
"""
import re
from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.db import get_db
from app.models import User
from app.passwords import hash_password, verify_password
from app.schemas import (
    TelegramLoginRequest,
    TokenResponse,
    WebPasswordLoginRequest,
    WebRegisterRequest,
)
from app.security import create_token
from app.telegram_auth import TelegramAuthError, verify_init_data, verify_web_login

router = APIRouter(prefix="/api/auth", tags=["auth"])

# Web login format: 3–32 chars, latin lowercase letters, digits and underscore.
LOGIN_RE = re.compile(r"^[a-z0-9_]{3,32}$")
MIN_PASSWORD_LEN = 6


def _auth_error(status_code: int, code: str, message_uz: str) -> HTTPException:
    """Structured error the frontend can branch on (detail.error)."""
    return HTTPException(
        status_code, detail={"error": code, "message_uz": message_uz}
    )


def _require_jwt_secret(settings: Settings) -> None:
    if not settings.JWT_SECRET:
        # jwt.encode crashes on an empty key; say so clearly instead of a 500.
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Server JWT_SECRET sozlanmagan — administratorga xabar bering.",
        )


def _issue_token(db: Session, tg_user: dict, settings: Settings) -> TokenResponse:
    """Upsert the Telegram user and return our JWT (shared by both logins)."""
    _require_jwt_secret(settings)

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


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
def register(body: WebRegisterRequest, db: Session = Depends(get_db)) -> TokenResponse:
    """Create a login/password account for a pupil without Telegram.

    The password is hashed with scrypt before storage; the plain text is never
    stored, logged or echoed back. The same JWT as Telegram pupils is issued,
    so grade selection / lessons / stars work identically afterwards.
    """
    settings = get_settings()
    _require_jwt_secret(settings)

    login = body.login.strip().lower()
    if not LOGIN_RE.match(login):
        raise _auth_error(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "invalid_login",
            "Login 3–32 belgi bo'lishi va faqat lotin harflari, raqamlar va _ dan iborat bo'lishi kerak.",
        )
    if len(body.password) < MIN_PASSWORD_LEN:
        raise _auth_error(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "weak_password",
            f"Parol kamida {MIN_PASSWORD_LEN} belgidan iborat bo'lishi kerak.",
        )
    first_name = body.first_name.strip() or login

    if db.scalar(select(User).where(User.login == login)) is not None:
        raise _auth_error(
            status.HTTP_409_CONFLICT,
            "login_taken",
            "Bu login allaqachon band. Boshqa login tanlang.",
        )

    user = User(
        telegram_id=None,  # web account: no Telegram identity at all
        login=login,
        password_hash=hash_password(body.password),
        first_name=first_name,
    )
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        # Two registers raced for the same login — the unique index decides.
        db.rollback()
        raise _auth_error(
            status.HTTP_409_CONFLICT,
            "login_taken",
            "Bu login allaqachon band. Boshqa login tanlang.",
        )
    return TokenResponse(access_token=create_token(user), first_name=user.first_name)


@router.post("/login", response_model=TokenResponse)
def password_login(
    body: WebPasswordLoginRequest, db: Session = Depends(get_db)
) -> TokenResponse:
    """Log in an existing web account. Wrong login and wrong password give the
    SAME generic error so the endpoint cannot be used to enumerate accounts."""
    settings = get_settings()
    _require_jwt_secret(settings)

    login = body.login.strip().lower()
    user = db.scalar(select(User).where(User.login == login))
    if user is None or not verify_password(body.password, user.password_hash):
        raise _auth_error(
            status.HTTP_401_UNAUTHORIZED,
            "invalid_credentials",
            "Login yoki parol noto'g'ri.",
        )
    return TokenResponse(access_token=create_token(user), first_name=user.first_name)


