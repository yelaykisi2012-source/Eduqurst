"""Matching questions: admin creates pairs, pupil pairs them, server grades."""
from __future__ import annotations

import uuid

from fastapi.testclient import TestClient

from tests.conftest import login_as, pick_grade

PAIRS = [("Olma", "Apple"), ("Banan", "Banana"), ("Uzum", "Grape")]


def _admin_lesson(client: TestClient) -> tuple[dict, int]:
    admin = login_as(client, {"id": 999000111, "first_name": "Admin"})
    grades = client.get("/api/grades", headers=admin).json()
    grade1 = next(g["id"] for g in grades if g["name"] == "1-sinf")
    subject = client.post(
        "/api/admin/subjects",
        headers=admin,
        json={"grade_id": grade1, "name": "Mantiq o‘yini", "emoji": "🧩"},
    )
    assert subject.status_code == 201, subject.text
    lesson = client.post(
        f"/api/admin/subjects/{subject.json()['id']}/lessons",
        headers=admin,
        json={
            "title": "Juftliklarni topish",
            "explanation": "Chapdagi so‘zni o‘ngdagi tarjimasi bilan bog‘lang.",
        },
    )
    assert lesson.status_code == 201, lesson.text
    return admin, lesson.json()["id"]


def _pupil(client: TestClient) -> dict:
    headers = login_as(
        client, {"id": 777000111, "first_name": "Juftlik", "username": "match_probe"}
    )
    pick_grade(client, headers, "1-sinf")
    return headers


def test_matching_question_full_flow(client: TestClient):
    admin, lesson_id = _admin_lesson(client)

    created = client.post(
        f"/api/admin/lessons/{lesson_id}/questions",
        headers=admin,
        json={
            "text": "So‘zlarni tarjimasi bilan bog‘lang",
            "kind": "matching",
            "pairs": [{"left": left, "right": right} for left, right in PAIRS],
        },
    )
    assert created.status_code == 201, created.text
    assert created.json()["option_count"] == 3
    assert created.json()["correct_count"] == 3

    details = client.get(
        f"/api/admin/lessons/{lesson_id}/questions", headers=admin
    ).json()
    assert details[0]["kind"] == "matching"
    assert [(p["left"], p["right"]) for p in details[0]["pairs"]] == PAIRS

    pupil = _pupil(client)
    subjects = client.get("/api/subjects", headers=pupil).json()
    subject = next(s for s in subjects if s["name"] == "Mantiq o‘yini")
    lesson = subject["lessons"][0]
    quiz = client.get(f"/api/lessons/{lesson['id']}/quiz", headers=pupil)
    assert quiz.status_code == 200, quiz.text
    question = quiz.json()["questions"][0]
    assert question["kind"] == "matching"
    assert [p["text"] for p in question["prompts"]] == [left for left, _ in PAIRS]
    assert {o["text"] for o in question["options"]} == {right for _, right in PAIRS}
    # The correct pairing must never leak to the pupil payload.
    assert all("pair_key" not in o for o in question["options"])
    assert "pair_key" not in quiz.text

    prompts = question["prompts"]
    options = question["options"]
    option_by_text = {o["text"]: o["id"] for o in options}

    # Wrong mapping: every prompt gets the NEXT pair's right answer, so the
    # mistake review is deterministic regardless of the shuffled option order.
    wrong = [
        {"prompt_id": prompt["id"], "option_id": option_by_text[PAIRS[(i + 1) % len(PAIRS)][1]]}
        for i, prompt in enumerate(prompts)
    ]
    key = uuid.uuid4().hex
    resp = client.post(
        f"/api/lessons/{lesson['id']}/quiz/submit",
        headers=pupil,
        json={"idempotency_key": key, "answers": [{"question_id": question["id"], "pairs": wrong}]},
    )
    assert resp.status_code == 200, resp.text
    result = resp.json()
    assert result["score_percent"] == 0
    assert result["passed"] is False
    assert len(result["mistakes"]) == 1
    mistake = result["mistakes"][0]
    assert mistake["kind"] == "matching"
    assert "Olma → Banana" in mistake["your_answer"]
    assert "Olma → Apple" in mistake["correct_answer"]
    assert mistake["explanation"]

    # Replaying the same key returns the same persisted review.
    again = client.post(
        f"/api/lessons/{lesson['id']}/quiz/submit",
        headers=pupil,
        json={"idempotency_key": key, "answers": [{"question_id": question["id"], "pairs": wrong}]},
    ).json()
    assert again["duplicate"] is True
    assert again["mistakes"] == result["mistakes"]

    # Correct mapping → 100% and a pass.
    correct = [
        {"prompt_id": prompt["id"], "option_id": option_by_text[right]}
        for prompt, (_, right) in zip(prompts, PAIRS)
    ]
    passed = client.post(
        f"/api/lessons/{lesson['id']}/quiz/submit",
        headers=pupil,
        json={
            "idempotency_key": uuid.uuid4().hex,
            "answers": [{"question_id": question["id"], "pairs": correct}],
        },
    ).json()
    assert passed["score_percent"] == 100
    assert passed["passed"] is True
    assert passed["mistakes"] == []


def test_matching_admin_validation(client: TestClient):
    admin, lesson_id = _admin_lesson(client)
    url = f"/api/admin/lessons/{lesson_id}/questions"

    too_few = client.post(
        url, headers=admin,
        json={"text": "Bitta juftlik", "kind": "matching",
              "pairs": [{"left": "A", "right": "B"}]},
    )
    assert too_few.status_code == 422

    duplicate_right = client.post(
        url, headers=admin,
        json={"text": "Takroriy o‘ng", "kind": "matching",
              "pairs": [{"left": "A", "right": "X"}, {"left": "B", "right": "X"}]},
    )
    assert duplicate_right.status_code == 422

    blank_side = client.post(
        url, headers=admin,
        json={"text": "Bo‘sh tomon", "kind": "matching",
              "pairs": [{"left": "A", "right": "X"}, {"left": " ", "right": "Y"}]},
    )
    assert blank_side.status_code == 422
