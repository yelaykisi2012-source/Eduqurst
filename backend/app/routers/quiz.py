"""
app/routers/quiz.py — grading a submission.

Rules implemented here:
- grading happens ONLY on the server (options carry no is_correct to client);
- idempotency_key (client-generated UUID) prevents double star grants on
  retry/double-tap: the same key returns the original result with duplicate=true;
- passing unlocks the next level (unlock logic in gamification.is_lesson_unlocked);
- failing never punishes: supportive message + free retry.
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import gamification
from app.db import get_db
from app.grades import assert_lesson_in_grade
from app.models import Achievement, AnswerOption, Lesson, Question, QuizAttempt, User
from app.schemas import QuizSubmitRequest, QuizSubmitResult
from app.security import get_current_user

router = APIRouter(prefix="/api", tags=["quiz"])

MSG_PASS = "Barakalla! Sen uddalading! ⭐"
MSG_FAIL = "Yana bir bor urinib ko'ramiz! 🤖"
MSG_UNLOCK = "Ajoyib! Yangi bosqich ochildi! 🚀"


@router.post("/lessons/{lesson_id}/quiz/submit", response_model=QuizSubmitResult)
def submit_quiz(
    lesson_id: int,
    body: QuizSubmitRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> QuizSubmitResult:
    lesson = db.get(Lesson, lesson_id)
    if lesson is None or not lesson.is_published:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Dars topilmadi")
    # Grade scoping: a pupil may only be quizzed on lessons of their own grade
    # (also raises 409 if they have not selected a grade yet).
    assert_lesson_in_grade(db, user, lesson)
    if not gamification.is_lesson_unlocked(db, user.id, lesson):
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Bosqich ochilmagan")

    # --- duplicate protection: same idempotency key => original result ---
    existing = db.scalar(
        select(QuizAttempt).where(QuizAttempt.idempotency_key == body.idempotency_key)
    )
    if existing is not None:
        return _result(db, user, existing, lesson, duplicate=True, new_achievements=[])

    qmap = {
        q.id: q
        for q in db.scalars(
            select(Question).where(Question.lesson_id == lesson.id)
        ).all()
    }
    correct = 0
    for ans in body.answers:
        question = qmap.get(ans.question_id)
        if question is None:
            continue  # ignore foreign question ids (validation, not error)
        if question.kind == "text":
            expected = next((o.text for o in question.options if o.is_correct), "")
            if (ans.text or "").strip().lower() == expected.strip().lower():
                correct += 1
        else:
            option = db.get(AnswerOption, ans.option_id) if ans.option_id else None
            if option is not None and option.question_id == question.id and option.is_correct:
                correct += 1

    total = len(qmap)
    score = round(correct * 100 / total) if total else 0
    passed = score >= lesson.pass_threshold_percent

    attempt = QuizAttempt(
        user_id=user.id,
        lesson_id=lesson.id,
        idempotency_key=body.idempotency_key,
        total_count=total,
        correct_count=correct,
        score_percent=score,
        passed=passed,
    )
    db.add(attempt)
    db.flush()

    prog = gamification.get_progress(db, user.id, lesson.id)
    prog.best_score_percent = max(prog.best_score_percent, score)
    if passed and not prog.passed:
        prog.passed = True
        gamification.add_stars(
            db, user.id, lesson.stars_reward, gamification.REASON_QUIZ_PASS, attempt.id
        )

    db.flush()  # make pending prog.passed visible to achievement queries (autoflush is off)
    new_achievements = gamification.evaluate_achievements(db, user)
    db.commit()
    return _result(db, user, attempt, lesson, duplicate=False, new_achievements=new_achievements)


def _result(
    db: Session,
    user: User,
    attempt: QuizAttempt,
    lesson: Lesson,
    *,
    duplicate: bool,
    new_achievements: list[Achievement],
) -> QuizSubmitResult:
    next_unlocked = False
    if attempt.passed:
        nxt = db.scalar(
            select(Lesson).where(
                Lesson.subject_id == lesson.subject_id,
                Lesson.level_order == lesson.level_order + 1,
                Lesson.is_published.is_(True),
            )
        )
        next_unlocked = nxt is not None

    message = MSG_FAIL
    if attempt.passed:
        message = MSG_UNLOCK if next_unlocked else MSG_PASS

    return QuizSubmitResult(
        attempt_id=attempt.id,
        total_count=attempt.total_count,
        correct_count=attempt.correct_count,
        score_percent=attempt.score_percent,
        passed=attempt.passed,
        stars_earned=lesson.stars_reward if attempt.passed else 0,
        stars_total=gamification.stars_total(db, user.id),
        next_level_unlocked=next_unlocked,
        message_uz=message,
        new_achievements=[a.code for a in new_achievements],
        duplicate=duplicate,
    )
