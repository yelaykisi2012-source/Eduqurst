"""app/streaks.py — daily learning streak.

A "day" is the Asia/Tashkent calendar day (UTC+5, no DST), so the streak flips
at local midnight instead of 05:00. The streak counts consecutive local days
with at least one meaningful action: opening the app or the bot, opening a
lesson, or submitting a quiz. Same-day activity is idempotent.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.models import User

STREAK_TZ = timezone(timedelta(hours=5))


def local_today(now: datetime | None = None) -> date:
    """Current date in Asia/Tashkent (injectable for tests)."""
    moment = now or datetime.now(STREAK_TZ)
    return moment.astimezone(STREAK_TZ).date()


def touch(db: Session, user: User, today: date | None = None) -> bool:
    """Register activity for `user` today. Returns True when state changed.

    Callers commit the session (touch only stages the change).
    """
    day = today or local_today()
    if user.last_active_date == day:
        return False

    if user.last_active_date is not None and (day - user.last_active_date).days == 1:
        user.current_streak = (user.current_streak or 0) + 1
    else:
        # First activity ever, a missed day, or a clock skew → start over.
        user.current_streak = 1

    user.last_active_date = day
    user.max_streak = max(user.max_streak or 0, user.current_streak)
    db.add(user)
    return True
