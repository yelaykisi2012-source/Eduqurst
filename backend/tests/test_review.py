"""Review mistakes: wrong questions return correct answer + hint after submit."""
from __future__ import annotations

import uuid

from fastapi.testclient import TestClient

# Correct option texts for the seeded 1-sinf "matematika" lesson 1.
CORRECT = ["4", "6", "7", "5", "9"]


def _math_lesson(client: TestClient, auth: dict):
    subjects = client.get("/api/subjects", headers=auth).json()
    lesson = next(s for s in subjects if s["slug"] == "matematika")["lessons"][0]
    quiz = client.get(f"/api/lessons/{lesson['id']}/quiz", headers=auth).json()
    return lesson, quiz


def test_wrong_answers_return_review_and_survive_duplicate(
    client: TestClient, auth: dict
):
    lesson, quiz = _math_lesson(client, auth)

    answers = []
    picked: dict[int, str] = {}
    for question, correct_text in zip(quiz["questions"], CORRECT):
        wrong = next(o for o in question["options"] if o["text"] != correct_text)
        answers.append({"question_id": question["id"], "option_id": wrong["id"]})
        picked[question["id"]] = wrong["text"]

    key = uuid.uuid4().hex
    resp = client.post(
        f"/api/lessons/{lesson['id']}/quiz/submit",
        headers=auth,
        json={"idempotency_key": key, "answers": answers},
    )
    assert resp.status_code == 200, resp.text
    result = resp.json()
    assert result["passed"] is False
    assert result["correct_count"] == 0
    assert len(result["mistakes"]) == result["total_count"]

    by_id = {m["question_id"]: m for m in result["mistakes"]}
    for question, correct_text in zip(quiz["questions"], CORRECT):
        mistake = by_id[question["id"]]
        assert mistake["your_answer"] == picked[question["id"]]
        assert mistake["correct_answer"] == correct_text
        assert mistake["explanation"]  # seeded correct option carries a hint
        assert mistake["question_text"]
        assert mistake["kind"] == "single"

    # The review is persisted: replaying the same key returns the same list.
    again = client.post(
        f"/api/lessons/{lesson['id']}/quiz/submit",
        headers=auth,
        json={"idempotency_key": key, "answers": answers},
    ).json()
    assert again["duplicate"] is True
    assert again["mistakes"] == result["mistakes"]


def test_correct_submission_has_no_mistakes(client: TestClient, auth: dict):
    lesson, quiz = _math_lesson(client, auth)
    answers = []
    for question, correct_text in zip(quiz["questions"], CORRECT):
        option = next(o for o in question["options"] if o["text"] == correct_text)
        answers.append({"question_id": question["id"], "option_id": option["id"]})

    result = client.post(
        f"/api/lessons/{lesson['id']}/quiz/submit",
        headers=auth,
        json={"idempotency_key": uuid.uuid4().hex, "answers": answers},
    ).json()
    assert result["score_percent"] == 100
    assert result["mistakes"] == []
