"""app/leaderboard.py — weekly star league ("haftalik reyting").

The league week is the Asia/Tashkent (UTC+5) calendar week: Monday 00:00
through the next Monday 00:00 (exclusive). Only StarLedger rows created in
that window count, so the board resets by itself every Monday morning and no
scheduled job is needed. Pupils with zero weekly stars are not ranked.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import StarLedger, User

LEAGUE_TZ = timezone(timedelta(hours=5))
TOP_LIMIT = 10


def week_bounds(now: datetime | None = None) -> tuple[date, date, datetime, datetime]:
    """Return (local_monday, local_next_monday, utc_start, utc_end)."""
    moment = (now or datetime.now(timezone.utc)).astimezone(LEAGUE_TZ)
    start_local = moment.replace(
        hour=0, minute=0, second=0, microsecond=0
    ) - timedelta(days=moment.weekday())
    end_local = start_local + timedelta(days=7)
    return (
        start_local.date(),
        end_local.date(),
        start_local.astimezone(timezone.utc),
        end_local.astimezone(timezone.utc),
    )


def _week_totals(start: datetime, end: datetime):
    """Per-user star sums for [start, end), as a subquery."""
    return (
        select(
            StarLedger.user_id.label("user_id"),
            func.sum(StarLedger.amount).label("stars"),
        )
        .where(StarLedger.created_at >= start, StarLedger.created_at < end)
        .group_by(StarLedger.user_id)
        .subquery()
    )


@dataclass
class LeagueRow:
    user_id: int
    first_name: str
    stars: int
    rank: int


def weekly_board(
    db: Session, grade_id: int, me_id: int | None
) -> tuple[date, date, list[LeagueRow], int, int, int]:
    """Build the weekly board for one grade.

    Returns (week_start, week_end, top_rows, participants, my_rank, my_stars).
    my_rank/my_stars are 0 when the pupil has no stars this week or is not in
    the requested grade (me_id=None).
    """
    start_day, end_day, start, end = week_bounds()
    totals = _week_totals(start, end)

    base = (
        select(
            User.id,
            User.first_name,
            totals.c.stars,
        )
        .join(totals, totals.c.user_id == User.id)
        .join(StarLedger, StarLedger.user_id == User.id)
        .where(
            User.grade_id == grade_id,
            StarLedger.created_at >= start,
            StarLedger.created_at < end,
        )
        .group_by(User.id, User.first_name, totals.c.stars)
        .having(totals.c.stars > 0)
    )

    ordered = db.execute(
        base.order_by(
            totals.c.stars.desc(), func.min(StarLedger.created_at).asc(), User.id.asc()
        ).limit(TOP_LIMIT)
    ).all()

    rows: list[LeagueRow] = []
    previous_stars: int | None = None
    previous_rank = 0
    for index, (user_id, first_name, stars) in enumerate(ordered, start=1):
        # Ties share a position (1, 1, 3, ...) — friendlier for a kids' league.
        rank = previous_rank if stars == previous_stars else index
        rows.append(
            LeagueRow(
                user_id=user_id,
                first_name=first_name or "",
                stars=int(stars or 0),
                rank=rank,
            )
        )
        previous_stars = stars
        previous_rank = rank

    participants = int(
        db.scalar(
            select(func.count()).select_from(base.order_by(None).subquery())
        )
        or 0
    )

    participants_totals = select(totals).subquery()
    if me_id is None:
        return start_day, end_day, rows, participants, 0, 0
    my_stars = int(
        db.scalar(
            select(func.coalesce(func.sum(StarLedger.amount), 0)).where(
                StarLedger.user_id == me_id,
                StarLedger.created_at >= start,
                StarLedger.created_at < end,
            )
        )
        or 0
    )
    if my_stars <= 0:
        return start_day, end_day, rows, participants, 0, 0

    ahead = int(
        db.scalar(
            select(func.count())
            .select_from(participants_totals)
            .join(User, User.id == participants_totals.c.user_id)
            .where(
                User.grade_id == grade_id,
                participants_totals.c.stars > my_stars,
            )
        )
        or 0
    )
    return start_day, end_day, rows, participants, ahead + 1, my_stars
