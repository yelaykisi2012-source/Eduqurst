"""Parent weekly digest: one-time linking codes + grouped Sunday data."""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, update

from app.db import SessionLocal
from app.models import Lesson, QuizAttempt, StarLedger, User
from tests.conftest import TEST_BOT_TOKEN

BOT = {"X-Bot-Token": TEST_BOT_TOKEN}
PUPIL_TG = 555001
PARENT_TG = 555999


@pytest.fixture(autouse=True)
def _clean_parent_links():
    """Tests share one DB: start every test with no parent links at all."""
    with SessionLocal() as db:
        db.execute(
            update(User).values(
                parent_telegram_id=None,
                parent_name=None,
                parent_link_code=None,
                parent_link_expires_at=None,
            )
        )
        db.commit()
    yield


def _bot_post(client: TestClient, path: str, body: dict):
    return client.post(f"/api/internal{path}", headers=BOT, json=body)


def _register(client: TestClient, telegram_id: int, name: str) -> User:
    resp = _bot_post(
        client, "/pupils", {"telegram_id": telegram_id, "first_name": name}
    )
    assert resp.status_code == 200, resp.text
    with SessionLocal() as db:
        return db.scalar(select(User).where(User.telegram_id == telegram_id))


def _pick_grade(client: TestClient, telegram_id: int, grade_name: str = "1-sinf") -> None:
    grades = client.get(
        "/api/internal/grades", headers=BOT, params={"telegram_id": telegram_id}
    ).json()
    grade_id = next(g["id"] for g in grades if g["name"] == grade_name)
    resp = _bot_post(
        client, "/pupil/grade", {"telegram_id": telegram_id, "grade_id": grade_id}
    )
    assert resp.status_code == 200, resp.text


def _issue_and_link(client: TestClient, pupil_tg: int, parent_tg: int, name: str = "Ona"):
    code = client.post(
        "/api/internal/parent/code", headers=BOT, params={"telegram_id": pupil_tg}
    )
    assert code.status_code == 200, code.text
    payload = code.json()
    assert payload["linked"] is False
    assert len(payload["code"]) == 6
    linked = _bot_post(
        client,
        "/parent/link",
        {
            "code": payload["code"],
            "parent_telegram_id": parent_tg,
            "parent_name": name,
        },
    )
    assert linked.status_code == 200, linked.text
    return payload, linked


def _add_week_activity(user_id: int, *, stars: int = 5, lessons: int = 1) -> None:
    """Insert real rows in the current (Tashkent) week for the digest maths."""
    with SessionLocal() as db:
        chosen = db.scalars(
            select(Lesson).order_by(Lesson.id.asc()).limit(lessons)
        ).all()
        assert len(chosen) == lessons
        for lesson in chosen:
            db.add(
                QuizAttempt(
                    user_id=user_id,
                    lesson_id=lesson.id,
                    idempotency_key=uuid.uuid4().hex,
                    total_count=1,
                    correct_count=1,
                    score_percent=100,
                    passed=True,
                    created_at=datetime.now(timezone.utc),
                )
            )
        db.add(
            StarLedger(
                user_id=user_id,
                amount=stars,
                reason="quiz_pass",
                reference_id=1,
                created_at=datetime.now(timezone.utc),
            )
        )
        db.commit()


def test_parent_link_and_weekly_digest(client: TestClient):
    _register(client, PUPIL_TG, "Aziz")
    _pick_grade(client, PUPIL_TG)

    payload, linked = _issue_and_link(client, PUPIL_TG, PARENT_TG)
    assert payload["expires_at"]
    assert linked.json()["pupil_first_name"] == "Aziz"
    assert linked.json()["grade_name"] == "1-sinf"

    status_resp = client.get(
        "/api/internal/parent/status", headers=BOT, params={"telegram_id": PUPIL_TG}
    ).json()
    assert status_resp == {"linked": True, "parent_name": "Ona"}

    # A second code request must not hand out a code to an already-linked pupil.
    again = client.post(
        "/api/internal/parent/code", headers=BOT, params={"telegram_id": PUPIL_TG}
    ).json()
    assert again["linked"] is True and again["code"] is None

    user = _register(client, PUPIL_TG, "Aziz")  # same row, fresh read
    _add_week_activity(user.id, stars=7, lessons=2)

    digest = client.get("/api/internal/parents/weekly-digest", headers=BOT)
    assert digest.status_code == 200, digest.text
    data = digest.json()
    assert len(data["parents"]) == 1
    group = data["parents"][0]
    assert group["parent_telegram_id"] == PARENT_TG
    assert group["parent_name"] == "Ona"
    assert len(group["pupils"]) == 1
    pupil = group["pupils"][0]
    assert pupil["first_name"] == "Aziz"
    assert pupil["grade_name"] == "1-sinf"
    assert pupil["lessons_passed_week"] == 2
    assert pupil["stars_week"] == 7
    assert pupil["stars_total"] == 7
    assert pupil["active_week"] is True

    # Unlinking stops the digest immediately.
    unlink = client.post(
        "/api/internal/parent/unlink", headers=BOT, json={"telegram_id": PUPIL_TG}
    )
    assert unlink.status_code == 204
    assert client.get(
        "/api/internal/parents/weekly-digest", headers=BOT
    ).json()["parents"] == []
    # The old code was cleared with the unlink.
    late = _bot_post(
        client,
        "/parent/link",
        {"code": payload["code"], "parent_telegram_id": PARENT_TG},
    )
    assert late.status_code == 400
    assert late.json()["detail"]["error"] == "code_invalid"


def test_expired_code_and_self_link_are_rejected(client: TestClient):
    _register(client, 555003, "Dilnoza")
    code = client.post(
        "/api/internal/parent/code", headers=BOT, params={"telegram_id": 555003}
    ).json()["code"]

    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.telegram_id == 555003))
        user.parent_link_expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
        db.commit()
    expired = _bot_post(
        client, "/parent/link", {"code": code, "parent_telegram_id": PARENT_TG}
    )
    assert expired.status_code == 400
    assert expired.json()["detail"]["error"] == "code_expired"

    fresh = client.post(
        "/api/internal/parent/code", headers=BOT, params={"telegram_id": 555003}
    ).json()["code"]
    self_link = _bot_post(
        client,
        "/parent/link",
        {"code": fresh, "parent_telegram_id": 555003},
    )
    assert self_link.status_code == 400
    assert self_link.json()["detail"]["error"] == "self_link"


def test_digest_groups_siblings_and_requires_bot_token(client: TestClient):
    assert client.get("/api/internal/parents/weekly-digest").status_code == 401

    for tg, name in ((555004, "Ali"), (555005, "Zuhra"), (555006, "Sardor")):
        _register(client, tg, name)
    _issue_and_link(client, 555004, 555998, "Ota")
    _issue_and_link(client, 555005, 555998, "Ota")
    _issue_and_link(client, 555006, 555997, "Ona")

    ali = _register(client, 555004, "Ali")
    _add_week_activity(ali.id, stars=3, lessons=1)

    data = client.get("/api/internal/parents/weekly-digest", headers=BOT).json()
    groups = {g["parent_telegram_id"]: g for g in data["parents"]}
    assert set(groups) == {555998, 555997}
    siblings = groups[555998]["pupils"]
    assert [p["first_name"] for p in siblings] == ["Ali", "Zuhra"]
    by_name = {p["first_name"]: p for p in siblings}
    assert by_name["Ali"]["lessons_passed_week"] == 1
    assert by_name["Ali"]["stars_week"] == 3
    assert by_name["Zuhra"]["active_week"] is False
    assert by_name["Zuhra"]["lessons_passed_week"] == 0

    # A non-Monday week_start is refused instead of silently rounded.
    bad = client.get(
        "/api/internal/parents/weekly-digest",
        headers=BOT,
        params={"week_start": "2026-10-28"},  # Wednesday
    )
    assert bad.status_code == 422
