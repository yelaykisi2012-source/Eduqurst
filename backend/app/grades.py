"""
app/grades.py — shared helpers for the per-pupil grade system.

Rule: a pupil's grade is ONLY ever set explicitly by the pupil (via
POST /api/me/grade). We NEVER infer it from name/username/telegram_id.
Content is always filtered by the pupil's chosen grade, and accessing a
lesson that belongs to a different grade is blocked (prevents mixing).
"""
from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models import Grade, Lesson, User


def user_grade(db: Session, user: User) -> Grade | None:
    """Return the pupil's chosen Grade, or None if they haven't picked yet."""
    if user.grade_id is None:
        return None
    return db.get(Grade, user.grade_id)


def require_grade(db: Session, user: User) -> Grade:
    """Return the pupil's grade or raise 409 to trigger grade onboarding."""
    grade = user_grade(db, user)
    if grade is None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail={
                "error": "grade_not_selected",
                "message_uz": "Davom etish uchun avval sinfinizni tanlang (1–11).",
            },
        )
    return grade


def assert_lesson_in_grade(db: Session, user: User, lesson: Lesson) -> None:
    """Block reading/quizzing a lesson that is not in the pupil's grade.

    If the pupil has no grade yet this also raises 409 (onboarding first).
    """
    grade = require_grade(db, user)
    if lesson.subject.grade_id != grade.id:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            detail={
                "error": "wrong_grade",
                "message_uz": "Bu dars sizning sinfgizga tegishli emas.",
            },
        )
