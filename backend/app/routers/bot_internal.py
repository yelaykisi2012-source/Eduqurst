"""
app/routers/bot_internal.py — a tiny endpoint for the Python bot only.

Why: the bot knows a pupil's telegram_id (Telegram gives it in every update)
but it does NOT have the pupil's Mini App JWT. To personalise /start
("Salom, Dilnoza! 3-sinf, 12 ⭐") it asks the backend directly.

Security: the caller must send the shared BOT_TOKEN in the X-Bot-Token
header. Only the bot and the backend know this secret, so strangers get 401.
This endpoint never exposes anything beyond the pupil's own public-ish stats
(first name, grade name, star/lesson counts).
"""
from __future__ import annotations

import hmac

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import gamification
from app.config import get_settings
from app.db import get_db
from app.grades import user_grade
from app.models import LessonProgress, User
from app.schemas import BotSummaryResponse

router = APIRouter(prefix="/api/internal", tags=["bot"])

_UNAUTHORIZED = HTTPException(
    status.HTTP_401_UNAUTHORIZED,
    detail={"error": "bad_bot_token", "message_uz": "Bot tokeni yaroqsiz."},
)


def require_bot_token(x_bot_token: str = Header(default="")) -> None:
    """Constant-time compare against our own BOT_TOKEN; 401 on any mismatch."""
    secret = get_settings().BOT_TOKEN
    if not secret or not x_bot_token or not hmac.compare_digest(x_bot_token, secret):
        raise _UNAUTHORIZED


@router.get("/pupil-summary", response_model=BotSummaryResponse, dependencies=[Depends(require_bot_token)])
def pupil_summary(
    telegram_id: int = Query(ge=1),
    db: Session = Depends(get_db),
) -> BotSummaryResponse:
    """Stats for /start personalisation. Unknown pupil => needs_onboarding=true
    (the bot then simply shows the plain welcome text — never invents data)."""
    user = db.scalar(select(User).where(User.telegram_id == telegram_id))
    if user is None:
        return BotSummaryResponse(known_user=False, needs_onboarding=True)

    grade = user_grade(db, user)
    viewed = db.scalar(
        select(func.count(LessonProgress.id)).where(
            LessonProgress.user_id == user.id, LessonProgress.lesson_viewed.is_(True)
        )
    ) or 0
    passed = db.scalar(
        select(func.count(LessonProgress.id)).where(
            LessonProgress.user_id == user.id, LessonProgress.passed.is_(True)
        )
    ) or 0
    return BotSummaryResponse(
        known_user=True,
        needs_onboarding=grade is None,
        first_name=user.first_name,
        grade_name=grade.name if grade else None,
        stars_total=gamification.stars_total(db, user.id),
        lessons_viewed=viewed,
        lessons_passed=passed,
    )
