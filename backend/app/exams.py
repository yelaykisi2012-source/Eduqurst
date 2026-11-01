"""
app/exams.py — the mandatory subject exam (majburiy sertifikat).

WHY
---
Some pupils already know the material but never sit through every lesson, so the
course-completion certificate stays out of reach. The exam is the second route:
20 questions an admin marked as exam questions, and a high bar — 90% or better.

RULES (all of them are constants below, so the teacher can change one line):
  * the paper is 20 questions taken from the subject's admin-flagged exam
    questions; if the subject has fewer, the rest come from other published
    subjects of the SAME grade;
  * 18+ correct (90%) = passed -> certificate with mark "5";
  * below that = not passed -> this subject's exam is locked for 30 days;
  * marks follow the 5-point scale: 17-20 -> "5", 5-16 -> "4", 0-4 -> "2.5".
"""
from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    ExamAttempt,
    Grade,
    Lesson,
    Question,
    Subject,
    User,
)

EXAM_SIZE = 20          # questions in one paper
EXAM_PASS_PERCENT = 90  # 18/20
EXAM_LOCK_DAYS = 30     # cooldown after a failed sitting
EXAM_PASS_STARS = 20    # star reward for passing (one grant per attempt)


def _aware(value: datetime) -> datetime:
    """Treat naive DB timestamps as UTC (SQLite hands them back naive)."""
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


# Public alias: routers compare/format stored deadlines and must never trust the
# driver to have attached a tzinfo (SQLite does not).
as_utc = _aware


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def mark_for(correct: int) -> str:
    """5-point mark of a 20-question paper."""
    if correct >= 17:
        return "5"
    if correct >= 5:
        return "4"
    return "2.5"


def exam_questions(db: Session, subject: Subject) -> list[Question]:
    """Admin-flagged questions of this subject (published lessons only)."""
    return list(
        db.scalars(
            select(Question)
            .join(Lesson, Question.lesson_id == Lesson.id)
            .where(
                Lesson.subject_id == subject.id,
                Lesson.is_published.is_(True),
                Question.is_exam.is_(True),
            )
            .order_by(Lesson.level_order.asc(), Question.order_index.asc(), Question.id.asc())
        ).all()
    )


def grade_questions(db: Session, grade: Grade, subject: Subject) -> list[Question]:
    """Flagged questions of the OTHER published subjects of this grade."""
    rows = db.scalars(
        select(Question)
        .join(Lesson, Question.lesson_id == Lesson.id)
        .join(Subject, Lesson.subject_id == Subject.id)
        .where(
            Subject.grade_id == grade.id,
            Subject.id != subject.id,
            Subject.is_published.is_(True),
            Lesson.is_published.is_(True),
            Question.is_exam.is_(True),
        )
        .order_by(Question.id.asc())
    ).all()
    # Stable per subject, varied between subjects: the same grade never yields
    # the identical filler paper for every course.
    fillers = list(rows)
    random.Random(subject.id).shuffle(fillers)
    return fillers


def build_paper(db: Session, grade: Grade, subject: Subject) -> list[Question]:
    """The frozen exam paper: subject questions first, grade fillers after."""
    picked = exam_questions(db, subject)
    if len(picked) < EXAM_SIZE:
        chosen = {question.id for question in picked}
        for filler in grade_questions(db, grade, subject):
            if len(picked) >= EXAM_SIZE:
                break
            if filler.id not in chosen:
                picked.append(filler)
                chosen.add(filler.id)
    return picked[:EXAM_SIZE]


def paper_is_ready(questions: list[Question]) -> bool:
    return len(questions) >= EXAM_SIZE


def latest_attempt(db: Session, user_id: int, subject_id: int) -> ExamAttempt | None:
    return db.scalar(
        select(ExamAttempt)
        .where(ExamAttempt.user_id == user_id, ExamAttempt.subject_id == subject_id)
        .order_by(ExamAttempt.created_at.desc())
    )


def open_attempt(db: Session, user_id: int, subject_id: int) -> ExamAttempt | None:
    """An attempt that was opened but never submitted (resume the same paper)."""
    return db.scalar(
        select(ExamAttempt)
        .where(
            ExamAttempt.user_id == user_id,
            ExamAttempt.subject_id == subject_id,
            ExamAttempt.submitted.is_(False),
        )
        .order_by(ExamAttempt.created_at.desc())
    )


def lock_until(db: Session, user_id: int, subject_id: int) -> datetime | None:
    """When the pupil may sit this exam again, or None if it is not locked."""
    attempt = latest_attempt(db, user_id, subject_id)
    if attempt is None or attempt.passed or not attempt.submitted:
        return None
    if attempt.locked_until is None:
        return None
    until = _aware(attempt.locked_until)
    return until if until > now_utc() else None


def best_passed(db: Session, user_id: int, subject_id: int) -> ExamAttempt | None:
    """The pupil's best passed sitting of this subject, if any."""
    rows = db.scalars(
        select(ExamAttempt).where(
            ExamAttempt.user_id == user_id,
            ExamAttempt.subject_id == subject_id,
            ExamAttempt.submitted.is_(True),
            ExamAttempt.passed.is_(True),
        )
    ).all()
    if not rows:
        return None
    return max(rows, key=lambda row: (row.score_percent, row.correct_count))


def create_attempt(
    db: Session, user: User, subject: Subject, questions: list[Question]
) -> ExamAttempt:
    attempt = ExamAttempt(
        user_id=user.id,
        subject_id=subject.id,
        question_ids=[question.id for question in questions],
        total_count=len(questions),
    )
    db.add(attempt)
    db.commit()
    db.refresh(attempt)
    return attempt


def lock_deadline() -> datetime:
    return now_utc() + timedelta(days=EXAM_LOCK_DAYS)
