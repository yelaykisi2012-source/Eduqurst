"""
app/gamification.py — stars, achievements, level-unlock rules.

All write logic lives here so routers stay thin and rules are testable.
Duplicate protection: StarLedger has UNIQUE(user_id, reason, reference_id),
so the same lesson/attempt can never grant stars twice.
"""
from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import (
    Achievement,
    Lesson,
    LessonProgress,
    StarLedger,
    Subject,
    User,
    UserAchievement,
)

REASON_LESSON_VIEWED = "lesson_viewed"
REASON_QUIZ_PASS = "quiz_pass"
REASON_ACHIEVEMENT = "achievement"
LESSON_VIEWED_STARS = 2


def add_stars(db: Session, user_id: int, amount: int, reason: str, reference_id: int) -> bool:
    """Grant stars once per (reason, reference_id). Returns True if granted now."""
    exists = db.scalar(
        select(StarLedger).where(
            StarLedger.user_id == user_id,
            StarLedger.reason == reason,
            StarLedger.reference_id == reference_id,
        )
    )
    if exists:
        return False
    db.add(StarLedger(user_id=user_id, amount=amount, reason=reason, reference_id=reference_id))
    return True


def stars_total(db: Session, user_id: int) -> int:
    return db.scalar(
        select(func.coalesce(func.sum(StarLedger.amount), 0)).where(StarLedger.user_id == user_id)
    ) or 0


def is_lesson_unlocked(db: Session, user_id: int, lesson: Lesson) -> bool:
    """Level 1 is open; level N opens when level N-1 is passed."""
    if lesson.level_order <= 1:
        return True
    prev = db.scalar(
        select(Lesson).where(
            Lesson.subject_id == lesson.subject_id,
            Lesson.level_order == lesson.level_order - 1,
        )
    )
    if prev is None:
        return True
    prog = db.scalar(
        select(LessonProgress).where(
            LessonProgress.user_id == user_id, LessonProgress.lesson_id == prev.id
        )
    )
    return bool(prog and prog.passed)


def get_progress(db: Session, user_id: int, lesson_id: int) -> LessonProgress:
    prog = db.scalar(
        select(LessonProgress).where(
            LessonProgress.user_id == user_id, LessonProgress.lesson_id == lesson_id
        )
    )
    if prog is None:
        prog = LessonProgress(user_id=user_id, lesson_id=lesson_id)
        db.add(prog)
        db.flush()
    return prog


def evaluate_achievements(db: Session, user: User) -> list[Achievement]:
    """Check all achievement rules; award newly met ones (+bonus stars). Returns new list."""
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
    total_stars = stars_total(db, user.id)

    # subject master: passed every published lesson of at least one subject
    subject_master = False
    for subject in db.scalars(select(Subject)).all():
        total = db.scalar(
            select(func.count(Lesson.id)).where(
                Lesson.subject_id == subject.id, Lesson.is_published.is_(True)
            )
        ) or 0
        done = db.scalar(
            select(func.count(LessonProgress.id))
            .join(Lesson, Lesson.id == LessonProgress.lesson_id)
            .where(
                Lesson.subject_id == subject.id,
                LessonProgress.user_id == user.id,
                LessonProgress.passed.is_(True),
            )
        ) or 0
        if total > 0 and done == total:
            subject_master = True
            break

    earned_codes = set(
        db.scalars(
            select(UserAchievement.achievement_id).where(UserAchievement.user_id == user.id)
        ).all()
    )
    earned_ids = set(
        db.scalars(
            select(Achievement.id).where(
                Achievement.code.in_(
                    [
                        c
                        for c, ok in {
                            "first_lesson": viewed >= 1,
                            "first_quiz": passed >= 1,
                            "star_10": total_stars >= 10,
                            "star_50": total_stars >= 50,
                            "subject_master": subject_master,
                        }.items()
                        if ok
                    ]
                )
            )
        ).all()
    )

    new: list[Achievement] = []
    for ach_id in earned_ids - earned_codes:
        ach = db.get(Achievement, ach_id)
        if ach is None:  # pragma: no cover
            continue
        db.add(UserAchievement(user_id=user.id, achievement_id=ach.id))
        new.append(ach)
        add_stars(db, user.id, 3, REASON_ACHIEVEMENT, ach.id)  # +3 bonus, once per achievement
    db.flush()  # session has autoflush=False; make grants visible to follow-up queries
    return new
