"""app/parents.py — parent linking + the weekly Telegram digest data.

Flow (bot-only, no website UI):
1. The pupil opens /parent in the bot and gets a short one-time code
   (15 minutes). The code lives on the pupil row, never in the URL.
2. The parent opens the same bot and sends /start <code>; the bot calls
   /api/internal/parent/link with the parent's Telegram id.
3. Every Sunday evening the bot asks for the weekly digest grouped by parent
   and sends one message with each linked child's progress.

Privacy: the digest exposes only counts and first names — the same data the
pupil already sees in the profile — and only to the Telegram account the
pupil explicitly linked.
"""
from __future__ import annotations

import secrets
from datetime import date, datetime, time, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.leaderboard import LEAGUE_TZ, week_bounds
from app.models import LessonProgress, QuizAttempt, StarLedger, User

CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # no 0/O, 1/I confusion
CODE_LENGTH = 6
CODE_TTL = timedelta(minutes=15)


class ParentLinkError(Exception):
    """User-facing linking problem (`code` feeds the bot's Uzbek message)."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def _aware(moment: datetime | None) -> datetime | None:
    """SQLite returns naive datetimes; treat stored values as UTC."""
    if moment is not None and moment.tzinfo is None:
        return moment.replace(tzinfo=timezone.utc)
    return moment


def pupil_by_telegram(db: Session, telegram_id: int) -> User | None:
    return db.scalar(select(User).where(User.telegram_id == telegram_id))


def _new_code(db: Session) -> str:
    for _ in range(8):
        code = "".join(secrets.choice(CODE_ALPHABET) for _ in range(CODE_LENGTH))
        if db.scalar(select(User.id).where(User.parent_link_code == code)) is None:
            return code
    raise RuntimeError("parent code generation failed")


def issue_code(db: Session, user: User) -> tuple[str, datetime]:
    """(Re)issue a one-time code; the previous code becomes invalid."""
    code = _new_code(db)
    expires = datetime.now(timezone.utc) + CODE_TTL
    user.parent_link_code = code
    user.parent_link_expires_at = expires
    db.commit()
    return code, expires


def clear_code(user: User) -> None:
    user.parent_link_code = None
    user.parent_link_expires_at = None


def link_parent(
    db: Session, code: str, parent_telegram_id: int, parent_name: str = ""
) -> User:
    """Attach a parent's Telegram id to the pupil that issued `code`."""
    cleaned = (code or "").strip().upper()
    user = db.scalar(select(User).where(User.parent_link_code == cleaned))
    if user is None:
        raise ParentLinkError("code_invalid")
    expires = _aware(user.parent_link_expires_at)
    if expires is None or expires <= datetime.now(timezone.utc):
        clear_code(user)
        db.commit()
        raise ParentLinkError("code_expired")
    if user.telegram_id == parent_telegram_id:
        raise ParentLinkError("self_link")
    user.parent_telegram_id = parent_telegram_id
    user.parent_name = (parent_name or "").strip()[:128] or None
    clear_code(user)
    db.commit()
    return user


def unlink_parent(db: Session, user: User) -> None:
    user.parent_telegram_id = None
    user.parent_name = None
    clear_code(user)
    db.commit()


def _window(week_start: date | None) -> tuple[date, date, datetime, datetime]:
    if week_start is None:
        return week_bounds()
    if week_start.weekday() != 0:
        raise ValueError("week_start must be a Monday")
    start_local = datetime.combine(week_start, time.min, tzinfo=LEAGUE_TZ)
    end_local = start_local + timedelta(days=7)
    return (
        week_start,
        (end_local).date(),
        start_local.astimezone(timezone.utc),
        end_local.astimezone(timezone.utc),
    )


def weekly_digests(db: Session, week_start: date | None = None) -> dict:
    """Progress of every linked pupil, grouped per parent Telegram id.

    Pupils with no activity are still included (zeros) so the weekly message
    can gently encourage them instead of silently skipping a child.
    """
    start_day, end_day, start, end = _window(week_start)
    pupils = db.scalars(
        select(User)
        .where(User.parent_telegram_id.is_not(None))
        .options(selectinload(User.grade))
        .order_by(User.parent_telegram_id.asc(), User.first_name.asc())
    ).all()
    if not pupils:
        return {"week_start": start_day, "week_end": end_day, "parents": []}

    ids = [p.id for p in pupils]
    week_passes = {
        row.user_id: row.count
        for row in db.execute(
            select(
                QuizAttempt.user_id,
                func.count(func.distinct(QuizAttempt.lesson_id)).label("count"),
            )
            .where(
                QuizAttempt.user_id.in_(ids),
                QuizAttempt.passed.is_(True),
                QuizAttempt.created_at >= start,
                QuizAttempt.created_at < end,
            )
            .group_by(QuizAttempt.user_id)
        )
    }
    week_stars = {
        row.user_id: int(row.total or 0)
        for row in db.execute(
            select(StarLedger.user_id, func.sum(StarLedger.amount).label("total"))
            .where(
                StarLedger.user_id.in_(ids),
                StarLedger.created_at >= start,
                StarLedger.created_at < end,
            )
            .group_by(StarLedger.user_id)
        )
    }
    total_stars = {
        row.user_id: int(row.total or 0)
        for row in db.execute(
            select(StarLedger.user_id, func.sum(StarLedger.amount).label("total"))
            .where(StarLedger.user_id.in_(ids))
            .group_by(StarLedger.user_id)
        )
    }
    total_passes = {
        row.user_id: int(row.total or 0)
        for row in db.execute(
            select(
                LessonProgress.user_id,
                func.count(LessonProgress.id).label("total"),
            )
            .where(LessonProgress.user_id.in_(ids), LessonProgress.passed.is_(True))
            .group_by(LessonProgress.user_id)
        )
    }

    grouped: dict[int, dict] = {}
    for pupil in pupils:
        parent_id = int(pupil.parent_telegram_id or 0)
        entry = grouped.setdefault(
            parent_id,
            {
                "parent_telegram_id": parent_id,
                "parent_name": pupil.parent_name or "",
                "pupils": [],
            },
        )
        lessons_week = int(week_passes.get(pupil.id, 0))
        stars_week = int(week_stars.get(pupil.id, 0))
        entry["pupils"].append(
            {
                "user_id": pupil.id,
                "first_name": pupil.first_name or "O‘quvchi",
                "grade_name": pupil.grade.name if pupil.grade else None,
                "lessons_passed_week": lessons_week,
                "stars_week": stars_week,
                "current_streak": int(pupil.current_streak or 0),
                "lessons_passed_total": int(total_passes.get(pupil.id, 0)),
                "stars_total": int(total_stars.get(pupil.id, 0)),
                "active_week": lessons_week > 0 or stars_week > 0,
            }
        )
    return {
        "week_start": start_day,
        "week_end": end_day,
        "parents": list(grouped.values()),
    }
