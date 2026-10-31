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

from app import gamification, streaks
from app.db import get_db
from app.grades import assert_lesson_in_grade
from app.models import (
    Achievement,
    AnswerOption,
    Lesson,
    Question,
    QuizAnswer,
    QuizAttempt,
    User,
)
from app.schemas import MistakeOut, QuizSubmitRequest, QuizSubmitResult
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
    streak_changed = streaks.touch(db, user)

    # --- duplicate protection: same idempotency key => original result ---
    existing = db.scalar(
        select(QuizAttempt).where(QuizAttempt.idempotency_key == body.idempotency_key)
    )
    if existing is not None:
        if streak_changed:
            db.commit()
        return _result(db, user, existing, lesson, duplicate=True, new_achievements=[])

    qmap = {
        q.id: q
        for q in db.scalars(
            select(Question).where(Question.lesson_id == lesson.id)
        ).all()
    }
    # One answer per question id (a repeated id keeps the last answer).
    answers_by_question = {
        ans.question_id: ans for ans in body.answers if ans.question_id in qmap
    }
    correct = 0
    answer_rows: list[QuizAnswer] = []
    for qid, question in qmap.items():
        ans = answers_by_question.get(qid)
        is_correct = False
        option_id: int | None = None
        text_answer: str | None = None
        if question.kind == "text":
            expected = next((o.text for o in question.options if o.is_correct), "")
            text_answer = (ans.text or "").strip() if ans else ""
            is_correct = bool(expected) and text_answer.lower() == expected.strip().lower()
        else:
            option = db.get(AnswerOption, ans.option_id) if ans and ans.option_id else None
            if option is not None and option.question_id == question.id:
                option_id = option.id
                is_correct = bool(option.is_correct)
        if is_correct:
            correct += 1
        answer_rows.append(
            QuizAnswer(
                question_id=qid,
                option_id=option_id,
                text_answer=text_answer[:255] if text_answer else None,
                is_correct=is_correct,
            )
        )

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
    for row in answer_rows:
        row.attempt_id = attempt.id
        db.add(row)

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
        # Same rule as gamification.is_lesson_unlocked: skip hidden lessons,
        # so archiving a middle lesson does not produce a false "no unlock".
        nxt = db.scalar(
            select(Lesson)
            .where(
                Lesson.subject_id == lesson.subject_id,
                Lesson.level_order > lesson.level_order,
                Lesson.is_published.is_(True),
            )
            .order_by(Lesson.level_order.asc())
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
        new_achievement_titles=[a.title for a in new_achievements],
        duplicate=duplicate,
        mistakes=_mistakes(db, attempt),
    )


def _mistakes(db: Session, attempt: QuizAttempt) -> list[MistakeOut]:
    """Wrong answers of this attempt, with the correct option + feedback.

    Empty for attempts recorded before answers were persisted — nothing is
    invented. Correct answers are only exposed here, after submission.
    """
    rows = db.scalars(
        select(QuizAnswer).where(QuizAnswer.attempt_id == attempt.id)
    ).all()
    if not rows:
        return []

    questions = {
        q.id: q
        for q in db.scalars(
            select(Question).where(
                Question.id.in_([row.question_id for row in rows])
            )
        ).all()
    }
    chosen: dict[int, AnswerOption] = {}
    option_ids = [row.option_id for row in rows if row.option_id]
    if option_ids:
        chosen = {
            o.id: o
            for o in db.scalars(
                select(AnswerOption).where(AnswerOption.id.in_(option_ids))
            ).all()
        }

    items: list[tuple[int, MistakeOut]] = []
    for row in rows:
        if row.is_correct:
            continue
        question = questions.get(row.question_id)
        if question is None:
            continue
        correct_options = [o.text for o in question.options if o.is_correct]
        explanation = next(
            (o.feedback for o in question.options if o.is_correct and o.feedback), ""
        )
        your_answer = ""
        if row.option_id and row.option_id in chosen:
            your_answer = chosen[row.option_id].text
        elif row.text_answer:
            your_answer = row.text_answer
        items.append(
            (
                question.order_index,
                MistakeOut(
                    question_id=question.id,
                    question_text=question.text,
                    kind=question.kind,
                    your_answer=your_answer,
                    correct_answer=" / ".join(correct_options),
                    explanation=explanation,
                ),
            )
        )
    items.sort(key=lambda pair: pair[0])
    return [mistake for _, mistake in items]
