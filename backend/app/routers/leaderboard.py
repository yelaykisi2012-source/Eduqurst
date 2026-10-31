"""app/routers/leaderboard.py — weekly stars league (Top-10 by grade)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app import leaderboard
from app.db import get_db
from app.grades import require_grade
from app.models import Grade, User
from app.schemas import LeaderboardEntry, LeaderboardMe, LeaderboardResponse
from app.security import get_current_user

router = APIRouter(prefix="/api", tags=["leaderboard"])


@router.get("/leaderboard", response_model=LeaderboardResponse)
def get_leaderboard(
    grade_id: int | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> LeaderboardResponse:
    """Top-10 pupils of a grade by stars earned in the current week.

    `grade_id` is optional: without it the pupil's own grade is used. The
    response also carries the pupil's own rank/stars even when outside Top-10.
    """
    if grade_id is None:
        grade = require_grade(db, user)  # 409 → app runs grade onboarding
    else:
        grade = db.get(Grade, grade_id)
        if grade is None:
            raise HTTPException(
                status.HTTP_404_NOT_FOUND,
                detail={"error": "grade_not_found", "message_uz": "Bunday sinf topilmadi."},
            )

    start_day, end_day, rows, participants, my_rank, my_stars = (
        leaderboard.weekly_board(
            db, grade.id, user.id if user.grade_id == grade.id else None
        )
    )

    top = [
        LeaderboardEntry(
            rank=row.rank,
            user_id=row.user_id,
            first_name=row.first_name,
            stars=row.stars,
            is_me=row.user_id == user.id,
        )
        for row in rows
    ]
    me = (
        LeaderboardMe(rank=my_rank, stars=my_stars) if my_rank > 0 else None
    )
    return LeaderboardResponse(
        grade_id=grade.id,
        grade_name=grade.name,
        week_start=start_day,
        week_end=end_day,
        participants=participants,
        top=top,
        me=me,
    )
