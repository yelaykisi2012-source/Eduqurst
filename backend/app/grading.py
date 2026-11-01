"""
app/grading.py — the single place where one answer is marked correct.

Both the lesson quiz (app/routers/quiz.py) and the mandatory exam
(app/routers/exams.py) call grade_answer(), so a question can never be scored
one way in a quiz and another way in an exam. `is_correct` is never sent to the
client: marking always happens here, on the server.
"""
from __future__ import annotations

import json
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AnswerOption, Question
from app.schemas import AnswerIn, MistakeOut


@dataclass
class Graded:
    """The outcome of marking one answer, ready to be persisted."""

    question_id: int
    is_correct: bool
    option_id: int | None = None
    text_answer: str | None = None


def grade_answer(question: Question, answer: AnswerIn | None, db: Session) -> Graded:
    """Mark one answer against one question of any supported kind."""
    if question.kind == "text":
        expected = next((o.text for o in question.options if o.is_correct), "")
        given = (answer.text or "").strip() if answer else ""
        return Graded(
            question_id=question.id,
            text_answer=given,
            is_correct=bool(expected) and given.lower() == expected.strip().lower(),
        )

    if question.kind == "matching":
        prompts = {p.id: p for p in question.prompts}
        options_by_id = {o.id: o for o in question.options}
        picked: dict[int, int] = {}
        for pair in answer.pairs if answer else []:
            if (
                pair.prompt_id in prompts
                and pair.option_id in options_by_id
                and pair.prompt_id not in picked
            ):
                picked[pair.prompt_id] = pair.option_id
        is_correct = (
            bool(prompts)
            and len(picked) == len(prompts)
            # one right-hand choice can only serve a single prompt
            and len(set(picked.values())) == len(picked)
            and all(
                options_by_id[option_id].pair_key == prompts[prompt_id].pair_key
                for prompt_id, option_id in picked.items()
            )
        )
        return Graded(
            question_id=question.id,
            text_answer=json.dumps(picked) if picked else "",
            is_correct=is_correct,
        )

    # single / image: one chosen option
    option = (
        db.get(AnswerOption, answer.option_id)
        if answer and answer.option_id
        else None
    )
    if option is not None and option.question_id == question.id:
        return Graded(
            question_id=question.id,
            option_id=option.id,
            is_correct=bool(option.is_correct),
        )
    return Graded(question_id=question.id, is_correct=False)


def grade_questions(
    questions: dict[int, Question], answers: list[AnswerIn], db: Session
) -> list[Graded]:
    """Mark every question once (a repeated question id keeps the LAST answer,
    exactly like the quiz did before this helper existed).

    Iterating the paper — not the submitted answers — means an unanswered
    question is recorded as wrong instead of silently disappearing.
    """
    by_question: dict[int, AnswerIn] = {}
    for answer in answers:
        if answer.question_id in questions:
            by_question[answer.question_id] = answer
    return [
        grade_answer(question, by_question.get(qid), db)
        for qid, question in questions.items()
    ]


# ---------------------------------------------------------------- review ----
def build_mistakes(db: Session, graded: list[Graded]) -> list[MistakeOut]:
    """Wrong answers with the correct option + supportive hint, in paper order.

    Only ever called after submission, so the right answers stay hidden while
    the pupil is still answering.
    """
    wrong = [item for item in graded if not item.is_correct]
    if not wrong:
        return []
    questions = {
        q.id: q
        for q in db.scalars(
            select(Question).where(Question.id.in_([item.question_id for item in wrong]))
        ).all()
    }
    chosen: dict[int, AnswerOption] = {}
    option_ids = [item.option_id for item in wrong if item.option_id]
    if option_ids:
        chosen = {
            o.id: o
            for o in db.scalars(
                select(AnswerOption).where(AnswerOption.id.in_(option_ids))
            ).all()
        }

    items: list[tuple[int, MistakeOut]] = []
    for item in wrong:
        question = questions.get(item.question_id)
        if question is None:  # pragma: no cover - defensive
            continue
        if question.kind == "matching":
            your_answer, correct_answer, explanation = _matching_review(question, item)
        else:
            correct_options = [o.text for o in question.options if o.is_correct]
            explanation = next(
                (o.feedback for o in question.options if o.is_correct and o.feedback), ""
            )
            your_answer = ""
            if item.option_id and item.option_id in chosen:
                your_answer = chosen[item.option_id].text
            elif item.text_answer:
                your_answer = item.text_answer
            correct_answer = " / ".join(correct_options)
        items.append(
            (
                question.order_index,
                MistakeOut(
                    question_id=question.id,
                    question_text=question.text,
                    kind=question.kind,
                    your_answer=your_answer,
                    correct_answer=correct_answer,
                    explanation=explanation,
                ),
            )
        )
    items.sort(key=lambda pair: pair[0])
    return [mistake for _, mistake in items]


def _matching_review(question: Question, item: Graded) -> tuple[str, str, str]:
    """Readable left→right review for a wrong matching answer."""
    option_text = {o.id: o.text for o in question.options}
    try:
        picked = {
            int(prompt_id): int(option_id)
            for prompt_id, option_id in json.loads(item.text_answer or "{}").items()
        }
    except (TypeError, ValueError, json.JSONDecodeError):
        picked = {}
    your_parts = [
        f"{prompt.text} → {option_text.get(picked[prompt.id], '?')}"
        for prompt in question.prompts
        if prompt.id in picked
    ]
    right_by_key = {o.pair_key: o.text for o in question.options if o.pair_key}
    correct_parts = [
        f"{prompt.text} → {right_by_key.get(prompt.pair_key, '?')}"
        for prompt in question.prompts
    ]
    return (
        "; ".join(your_parts) or "javob berilmagan",
        "; ".join(correct_parts),
        "Har bir chap elementni o‘z jufti bilan bog‘lang.",
    )
