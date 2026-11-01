"""
app/routers/exams.py — the mandatory subject exam (majburiy sertifikat).

WHY THIS EXISTS
---------------
Some pupils already know the material but never sit through every lesson, so the
course-completion certificate stays out of their reach. The exam is the second
route to the same certificate:

  * 20 questions, all of them marked "imtihon savoli" by an admin;
  * 90%+ (18/20) = passed -> certificate with the 5-point mark;
  * below 90%  = not passed -> this subject's exam is locked for 30 days;
  * no lesson prerequisite: any pupil of the grade may sit it.

The rules themselves live in app/exams.py, the marking in app/grading.py (shared
with the lesson quiz, so a question can never be scored two different ways).
"""
from __future__ import annotations

import random

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import certificates as certs
from app import exams, gamification, grading, streaks
from app.db import get_db
from app.grades import require_grade
from app.models import Certificate, ExamAttempt, Question, Subject, User
from app.routers.certificates import to_out
from app.schemas import (
    ExamCardOut,
    ExamPaperOut,
    ExamResultOut,
    ExamSubmitRequest,
    MatchPromptOut,
    QuizOptionOut,
    QuizQuestionOut,
)
from app.security import get_current_user

router = APIRouter(prefix="/api/exams", tags=["exams"])

MSG_PASS = "Tabriklaymiz! Majburiy imtihondan muvaffaqiyatli o‘tdingiz 🎉"
MSG_NOT_READY = (
    "Bu fan uchun imtihon hali tayyor emas — admin yetarli savol belgilamagan."
)
MSG_FAIL = "90% ga yetmadingiz. Yana urinib ko‘ring!"


def _retry_uz(locked_until) -> str:
    """Supportive (never punishing) failure message with the local retry date."""
    day = exams.as_utc(locked_until).astimezone(streaks.STREAK_TZ).strftime("%d.%m.%Y")
    return f"90% ga yetmadi — qayta urinish {day} sanasidan mumkin."


def _subject_or_404(db: Session, grade_id: int, subject_id: int) -> Subject:
    subject = db.get(Subject, subject_id)
    if subject is None or not subject.is_published or subject.grade_id != grade_id:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail={
                "error": "subject_not_found",
                "message_uz": "Bu sinfda bunday fan imtihoni yo‘q.",
            },
        )
    return subject


def _paper_questions(db: Session, question_ids: list[int]) -> list[QuizQuestionOut]:
    """The frozen paper, shaped exactly like a lesson quiz (no correct flags).

    ids are kept in paper order; a question an admin deleted meanwhile simply
    drops out of both the paper and the grading (they are derived from the same
    list, so the count can never disagree).
    """
    if not question_ids:
        return []
    rows = db.scalars(
        select(Question).where(Question.id.in_(question_ids))
    ).all()
    by_id = {q.id: q for q in rows}
    out: list[QuizQuestionOut] = []
    for qid in question_ids:
        q = by_id.get(qid)
        if q is None:
            continue
        options = list(q.options)
        prompts: list[MatchPromptOut] = []
        if q.kind == "matching":
            # Same stable-per-question shuffle as the lesson quiz, so the admin
            # order never reveals the right pair.
            random.Random(q.id).shuffle(options)
            prompts = [MatchPromptOut(id=p.id, text=p.text) for p in q.prompts]
        out.append(
            QuizQuestionOut(
                id=q.id,
                text=q.text,
                kind=q.kind,
                image_url=q.image_url,
                options=[QuizOptionOut(id=o.id, text=o.text) for o in options],
                prompts=prompts,
            )
        )
    return out


def _question_map(db: Session, question_ids: list[int]) -> dict[int, Question]:
    if not question_ids:
        return {}
    rows = db.scalars(select(Question).where(Question.id.in_(question_ids))).all()
    by_id = {q.id: q for q in rows}
    # Ordered by the paper, so grading (and the review) follow the printed order.
    return {qid: by_id[qid] for qid in question_ids if qid in by_id}


def _graded_from_rows(rows: list[dict]) -> list[grading.Graded]:
    """Rebuild marked answers stored on a submitted attempt (double-tap safe)."""
    items: list[grading.Graded] = []
    for row in rows:
        try:
            items.append(
                grading.Graded(
                    question_id=int(row["question_id"]),
                    is_correct=bool(row["is_correct"]),
                    option_id=row.get("option_id"),
                    text_answer=row.get("text_answer"),
                )
            )
        except (KeyError, TypeError, ValueError):
            continue
    return items


def _result(
    db: Session,
    user: User,
    subject: Subject,
    attempt: ExamAttempt,
    graded: list[grading.Graded],
) -> ExamResultOut:
    mistakes = grading.build_mistakes(db, graded)
    order = {qid: index for index, qid in enumerate(attempt.question_ids or [])}
    mistakes.sort(key=lambda m: order.get(m.question_id, 10_000))

    cert = db.scalar(
        select(Certificate).where(
            Certificate.user_id == user.id, Certificate.subject_id == subject.id
        )
    )
    # SQLite hands naive timestamps back; an unmarked ISO string would be read
    # as local time by the app, so the deadline is always normalised to UTC.
    locked = exams.as_utc(attempt.locked_until) if attempt.locked_until else None

    if attempt.passed:
        message = MSG_PASS
    elif locked is not None:
        message = _retry_uz(locked)
    else:  # pragma: no cover - defensive (a failed sitting always carries a lock)
        message = MSG_FAIL

    return ExamResultOut(
        attempt_id=attempt.id,
        total_count=attempt.total_count,
        correct_count=attempt.correct_count,
        score_percent=attempt.score_percent,
        mark=attempt.mark or exams.mark_for(attempt.correct_count),
        passed=attempt.passed,
        stars_earned=exams.EXAM_PASS_STARS if attempt.passed else 0,
        stars_total=gamification.stars_total(db, user.id),
        locked_until=locked,
        certificate=to_out(cert) if cert else None,
        message_uz=message,
        mistakes=mistakes,
    )


@router.get("", response_model=list[ExamCardOut])
def list_exams(
    db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> list[ExamCardOut]:
    """Every exam of the pupil's grade: readiness, lock, best result, certificate."""
    grade = require_grade(db, user)
    subjects = db.scalars(
        select(Subject)
        .where(Subject.grade_id == grade.id, Subject.is_published.is_(True))
        .order_by(Subject.order_index.asc(), Subject.id.asc())
    ).all()
    issued = {
        cert.subject_id: cert
        for cert in db.scalars(
            select(Certificate).where(Certificate.user_id == user.id)
        ).all()
    }
    cards: list[ExamCardOut] = []
    for subject in subjects:
        paper = exams.build_paper(db, grade, subject)
        best = exams.best_passed(db, user.id, subject.id)
        cert = issued.get(subject.id)
        cards.append(
            ExamCardOut(
                subject_id=subject.id,
                subject_name=subject.name,
                emoji=subject.emoji,
                total=len(paper),
                available=exams.paper_is_ready(paper),
                locked_until=exams.lock_until(db, user.id, subject.id),
                best_score_percent=best.score_percent if best else None,
                best_mark=best.mark if best else None,
                passed=best is not None,
                certificate_code=cert.code if cert else None,
            )
        )
    return cards


@router.get("/{subject_id}/paper", response_model=ExamPaperOut)
def get_paper(
    subject_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ExamPaperOut:
    """Open (or resume) the exam paper for one subject.

    The paper is frozen on first call: the same 20 questions come back until it
    is submitted, so a refresh in the middle of the exam loses nothing.
    """
    grade = require_grade(db, user)
    subject = _subject_or_404(db, grade.id, subject_id)

    locked = exams.lock_until(db, user.id, subject.id)
    if locked is not None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail={
                "error": "exam_locked",
                "message_uz": _retry_uz(locked),
                "locked_until": locked.isoformat(),
            },
        )

    attempt = exams.open_attempt(db, user.id, subject.id)
    if attempt is None:
        paper = exams.build_paper(db, grade, subject)
        if not exams.paper_is_ready(paper):
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                detail={
                    "error": "exam_not_configured",
                    "message_uz": MSG_NOT_READY,
                    "available": len(paper),
                    "required": exams.EXAM_SIZE,
                },
            )
        attempt = exams.create_attempt(db, user, subject, paper)

    questions = _paper_questions(db, list(attempt.question_ids or []))
    return ExamPaperOut(
        attempt_id=attempt.id,
        subject_id=subject.id,
        subject_name=subject.name,
        total=len(questions),
        pass_percent=exams.EXAM_PASS_PERCENT,
        lock_days=exams.EXAM_LOCK_DAYS,
        questions=questions,
    )


@router.post("/{subject_id}/submit", response_model=ExamResultOut)
def submit_exam(
    subject_id: int,
    body: ExamSubmitRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ExamResultOut:
    """Mark the paper, apply pass/lock rules, issue the certificate on a pass.

    Submitting the same attempt twice returns the recorded result — it never
    re-marks and never grants stars twice (StarLedger is unique per attempt).
    """
    grade = require_grade(db, user)
    subject = _subject_or_404(db, grade.id, subject_id)
    attempt = db.get(ExamAttempt, body.attempt_id)
    if attempt is None or attempt.user_id != user.id or attempt.subject_id != subject.id:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail={
                "error": "attempt_not_found",
                "message_uz": "Imtihon varaqasi topilmadi. Imtihonni qaytadan oching.",
            },
        )

    if attempt.submitted:
        return _result(db, user, subject, attempt, _graded_from_rows(attempt.answers or []))

    qmap = _question_map(db, list(attempt.question_ids or []))
    graded = grading.grade_questions(qmap, body.answers, db)
    correct = sum(1 for item in graded if item.is_correct)
    total = len(qmap)
    score = round(correct * 100 / total) if total else 0
    passed = score >= exams.EXAM_PASS_PERCENT

    streaks.touch(db, user)
    attempt.answers = [
        {
            "question_id": item.question_id,
            "is_correct": item.is_correct,
            "option_id": item.option_id,
            "text_answer": item.text_answer,
        }
        for item in graded
    ]
    attempt.total_count = total
    attempt.correct_count = correct
    attempt.score_percent = score
    attempt.mark = exams.mark_for(correct)
    attempt.passed = passed
    attempt.submitted = True
    attempt.submitted_at = exams.now_utc()
    # Below the bar: the certificate waits a month (the teacher's rule).
    attempt.locked_until = None if passed else exams.lock_deadline()
    db.add(attempt)

    if passed:
        gamification.add_stars(
            db, user.id, exams.EXAM_PASS_STARS, gamification.REASON_EXAM_PASS, attempt.id
        )
        db.flush()
        gamification.evaluate_achievements(db, user)
        db.commit()
        # The exam result is authoritative for the certificate of this subject.
        certs.get_or_issue(
            db,
            user,
            grade,
            subject,
            {"score_percent": score, "total_lessons": 0},
            mark=attempt.mark,
            issued_via="exam",
        )
        db.refresh(attempt)
        return _result(db, user, subject, attempt, graded)

    db.commit()
    return _result(db, user, subject, attempt, graded)
