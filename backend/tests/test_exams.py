"""
Mandatory subject exam (majburiy sertifikat).

Covers the rules the teacher asked for:
  * the paper is 20 admin-flagged questions of the subject; a shortfall is
    filled from other subjects of the SAME grade;
  * 90%+ passes and issues a certificate carrying the 5-point mark;
  * below 90% does not pass and locks the exam for 30 days;
  * an exam result is authoritative over an earlier course certificate.

Each test works inside its own grade, because the flagged-question pool (and so
the fillers) is shared per grade — that keeps the tests independent of each
other no matter what order they run in.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient
from sqlalchemy import select

from app import exams
from app.db import SessionLocal
from app.models import ExamAttempt, LessonProgress, Subject, User
from tests.conftest import login_as, pick_grade

ADMIN_ID = 999000111  # the id conftest puts in ADMIN_TELEGRAM_IDS


# ------------------------------------------------------------------ helpers --
def _pupil(client: TestClient, login: str, first_name: str, grade: str) -> dict:
    """A web account (no Telegram needed) that has already chosen its grade."""
    resp = client.post(
        "/api/auth/register",
        json={"login": login, "password": "Probe12345", "first_name": first_name},
    )
    assert resp.status_code == 201, resp.text
    headers = {"Authorization": f"Bearer {resp.json()['access_token']}"}
    pick_grade(client, headers, grade)
    return headers


def _stars(client: TestClient, headers: dict) -> int:
    return client.get("/api/me/progress", headers=headers).json()["stars_total"]


def _admin(client: TestClient) -> dict:
    return login_as(client, {"id": ADMIN_ID, "first_name": "Admin"})


def _grade_id(client: TestClient, headers: dict, name: str) -> int:
    grades = client.get("/api/grades", headers=headers).json()
    return next(g["id"] for g in grades if g["name"] == name)


def _new_subject(client: TestClient, admin: dict, grade_id: int, name: str) -> int:
    resp = client.post(
        "/api/admin/subjects",
        json={"grade_id": grade_id, "name": name, "emoji": "📐"},
        headers=admin,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def _new_lesson(client: TestClient, admin: dict, subject_id: int, title: str) -> int:
    resp = client.post(
        f"/api/admin/subjects/{subject_id}/lessons",
        json={"title": title, "explanation": "Test darsi.", "stars_reward": 5},
        headers=admin,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def _add_question(
    client: TestClient, admin: dict, lesson_id: int, label: str, *, flagged: bool = True
) -> dict:
    """Create one single-choice question, flag it, return {id, right, wrong}.

    The flag response carries the options with their ids, which is what lets a
    test answer "correctly" without reading the database.
    """
    resp = client.post(
        f"/api/admin/lessons/{lesson_id}/questions",
        json={
            "text": f"{label} savoli?",
            "kind": "single",
            "options": [
                {"text": f"{label} — to‘g‘ri", "is_correct": True},
                {"text": f"{label} — noto‘g‘ri", "is_correct": False},
            ],
        },
        headers=admin,
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["is_exam"] is False  # a new question is never auto-flagged
    question_id = resp.json()["id"]

    if flagged:
        flag = client.patch(
            f"/api/admin/questions/{question_id}/exam",
            json={"is_exam": True},
            headers=admin,
        )
        assert flag.status_code == 200, flag.text
        detail = flag.json()
        assert detail["is_exam"] is True
    else:
        rows = client.get(
            f"/api/admin/lessons/{lesson_id}/questions", headers=admin
        ).json()
        detail = next(row for row in rows if row["id"] == question_id)

    by_text = {o["text"]: o["id"] for o in detail["options"]}
    return {
        "id": question_id,
        "right": by_text[f"{label} — to‘g‘ri"],
        "wrong": by_text[f"{label} — noto‘g‘ri"],
    }


def _subject_with_questions(
    client: TestClient, admin: dict, grade_id: int, name: str, count: int
) -> tuple[int, list[dict]]:
    """A fresh subject carrying `count` flagged exam questions in one lesson."""
    subject_id = _new_subject(client, admin, grade_id, name)
    lesson_id = _new_lesson(client, admin, subject_id, f"{name} darsi")
    questions = [
        _add_question(client, admin, lesson_id, f"{name}-{index + 1}")
        for index in range(count)
    ]
    return subject_id, questions


def _answers(questions: list[dict], *, correct: int, total: int | None = None) -> list[dict]:
    """Answer the first `correct` right, the rest wrong; stop after `total`."""
    rows = questions if total is None else questions[:total]
    return [
        {
            "question_id": question["id"],
            "option_id": question["right"]
            if index < correct
            else question["wrong"],
        }
        for index, question in enumerate(rows)
    ]


def _submit(client: TestClient, headers: dict, subject_id: int, answers: list[dict]) -> dict:
    paper = client.get(f"/api/exams/{subject_id}/paper", headers=headers)
    assert paper.status_code == 200, paper.text
    resp = client.post(
        f"/api/exams/{subject_id}/submit",
        json={"attempt_id": paper.json()["attempt_id"], "answers": answers},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


def _card(client: TestClient, headers: dict, subject_id: int) -> dict:
    return next(c for c in client.get("/api/exams", headers=headers).json() if c["subject_id"] == subject_id)


def _unlock(login: str, subject_name: str) -> None:
    """Move the pupil's last submitted attempt's lock into the past."""
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.login == login))
        subject = db.scalar(select(Subject).where(Subject.name == subject_name))
        attempt = db.scalar(
            select(ExamAttempt)
            .where(
                ExamAttempt.user_id == user.id,
                ExamAttempt.subject_id == subject.id,
                ExamAttempt.submitted.is_(True),
            )
            .order_by(ExamAttempt.id.desc())
        )
        assert attempt is not None
        attempt.locked_until = datetime.now(timezone.utc) - timedelta(minutes=1)
        db.commit()


# ------------------------------------------------------------------- units --
def test_mark_bands_follow_the_five_point_scale():
    """1–4 -> 2.5, 5–16 -> 4, 17–20 -> 5 (the scale the teacher described)."""
    assert exams.mark_for(0) == "2.5"
    assert exams.mark_for(4) == "2.5"
    assert exams.mark_for(5) == "4"
    assert exams.mark_for(16) == "4"
    assert exams.mark_for(17) == "5"
    assert exams.mark_for(20) == "5"


# ------------------------------------------------------------------ happy --
def test_exam_pass_issues_certificate_with_mark(client: TestClient):
    admin = _admin(client)
    grade_id = _grade_id(client, admin, "3-sinf")
    pupil = _pupil(client, "exam_pass", "Dilnoza", "3-sinf")
    subject_id, questions = _subject_with_questions(
        client, admin, grade_id, "Imtihon 9 fani", exams.EXAM_SIZE
    )

    card = _card(client, pupil, subject_id)
    assert card["total"] == exams.EXAM_SIZE
    assert card["available"] is True
    assert card["locked_until"] is None
    assert card["passed"] is False
    assert card["certificate_code"] is None

    paper = client.get(f"/api/exams/{subject_id}/paper", headers=pupil)
    assert paper.status_code == 200, paper.text
    body = paper.json()
    assert body["subject_id"] == subject_id
    assert body["total"] == exams.EXAM_SIZE
    assert body["pass_percent"] == 90
    assert body["lock_days"] == 30
    assert len(body["questions"]) == exams.EXAM_SIZE
    # A paper must never reveal which option is right.
    for question in body["questions"]:
        assert "is_correct" not in question["options"][0]

    # Reopening before submitting resumes the SAME frozen paper.
    resumed = client.get(f"/api/exams/{subject_id}/paper", headers=pupil).json()
    assert resumed["attempt_id"] == body["attempt_id"]
    assert [q["id"] for q in resumed["questions"]] == [q["id"] for q in body["questions"]]

    before = _stars(client, pupil)
    out = _submit(client, pupil, subject_id, _answers(questions, correct=exams.EXAM_SIZE))
    assert out["correct_count"] == exams.EXAM_SIZE
    assert out["score_percent"] == 100
    assert out["mark"] == "5"
    assert out["passed"] is True
    assert out["locked_until"] is None
    assert out["mistakes"] == []
    assert out["stars_earned"] == exams.EXAM_PASS_STARS
    # A pass can also unlock star-based achievements, so the ledger may grow by
    # more than the exam reward — it must never grow by less.
    assert out["stars_total"] >= before + exams.EXAM_PASS_STARS

    cert = out["certificate"]
    assert cert is not None
    assert cert["issued_via"] == "exam"
    assert cert["mark"] == "5"
    assert cert["score_percent"] == 100
    assert cert["stars"] == out["stars_total"]

    issued = client.get("/api/certificates", headers=pupil).json()
    assert len(issued) == 1
    assert issued[0]["code"] == cert["code"]
    assert issued[0]["issued_via"] == "exam"
    assert _stars(client, pupil) >= before + exams.EXAM_PASS_STARS

    pdf = client.get(f"/api/certificates/{subject_id}/pdf", headers=pupil)
    assert pdf.status_code == 200
    assert pdf.content.startswith(b"%PDF")

    verified = client.get(f"/api/certificates/verify/{cert['code']}").json()
    assert verified["issued_via"] == "exam"
    assert verified["mark"] == "5"
    page = client.get(
        f"/api/certificates/verify/{cert['code']}", headers={"Accept": "text/html"}
    )
    assert "Majburiy imtihon" in page.text

    card = _card(client, pupil, subject_id)
    assert card["passed"] is True
    assert card["best_score_percent"] == 100
    assert card["best_mark"] == "5"
    assert card["certificate_code"] == cert["code"]


def test_exam_boundary_18_of_20_passes(client: TestClient):
    admin = _admin(client)
    grade_id = _grade_id(client, admin, "4-sinf")
    pupil = _pupil(client, "exam_edge", "Jasur", "4-sinf")
    subject_id, questions = _subject_with_questions(
        client, admin, grade_id, "Imtihon chegarasi", exams.EXAM_SIZE
    )

    out = _submit(client, pupil, subject_id, _answers(questions, correct=18))
    assert out["correct_count"] == 18
    assert out["score_percent"] == 90
    assert out["passed"] is True
    assert out["locked_until"] is None
    assert len(out["mistakes"]) == 2


# ------------------------------------------------------------------- fail --
def test_below_90_percent_locks_the_exam_for_30_days(client: TestClient):
    admin = _admin(client)
    grade_id = _grade_id(client, admin, "10-sinf")
    pupil = _pupil(client, "exam_fail", "Kamola", "10-sinf")
    subject_id, questions = _subject_with_questions(
        client, admin, grade_id, "Imtihon 10 fani", exams.EXAM_SIZE
    )

    paper = client.get(f"/api/exams/{subject_id}/paper", headers=pupil).json()
    before = _stars(client, pupil)
    resp = client.post(
        f"/api/exams/{subject_id}/submit",
        json={"attempt_id": paper["attempt_id"], "answers": _answers(questions, correct=17)},
        headers=pupil,
    )
    assert resp.status_code == 200, resp.text
    out = resp.json()
    assert out["passed"] is False
    assert out["score_percent"] == 85
    assert out["certificate"] is None
    assert out["stars_earned"] == 0
    deadline = datetime.fromisoformat(out["locked_until"])
    assert deadline.tzinfo is not None, "deadline must be unambiguous (UTC)"
    days = (deadline - datetime.now(timezone.utc)).total_seconds() / 86400
    assert 29 < days <= 30.5
    assert _stars(client, pupil) == before

    # Double-tap of the same attempt returns the recorded result — no re-marking.
    repeat = client.post(
        f"/api/exams/{subject_id}/submit",
        json={"attempt_id": paper["attempt_id"], "answers": _answers(questions, correct=20)},
        headers=pupil,
    )
    assert repeat.status_code == 200
    assert repeat.json()["score_percent"] == 85
    assert repeat.json()["locked_until"] == out["locked_until"]

    # While locked the paper cannot be opened, and the card says until when.
    blocked = client.get(f"/api/exams/{subject_id}/paper", headers=pupil)
    assert blocked.status_code == 409
    assert blocked.json()["detail"]["error"] == "exam_locked"
    assert (
        datetime.fromisoformat(blocked.json()["detail"]["locked_until"])
        == deadline
    )
    card = _card(client, pupil, subject_id)
    assert datetime.fromisoformat(card["locked_until"]) == deadline
    assert card["passed"] is False

    # A month later the retake opens, and passing issues the certificate.
    _unlock("exam_fail", "Imtihon 10 fani")
    fresh = client.get(f"/api/exams/{subject_id}/paper", headers=pupil)
    assert fresh.status_code == 200, fresh.text
    second = fresh.json()
    assert second["attempt_id"] != paper["attempt_id"]
    result = client.post(
        f"/api/exams/{subject_id}/submit",
        json={"attempt_id": second["attempt_id"], "answers": _answers(questions, correct=20)},
        headers=pupil,
    ).json()
    assert result["passed"] is True
    assert result["locked_until"] is None
    assert result["certificate"]["issued_via"] == "exam"
    assert _stars(client, pupil) >= before + exams.EXAM_PASS_STARS
    assert _card(client, pupil, subject_id)["locked_until"] is None


def test_unanswered_questions_count_as_wrong(client: TestClient):
    admin = _admin(client)
    grade_id = _grade_id(client, admin, "10-sinf")
    pupil = _pupil(client, "exam_blank", "Sardor", "10-sinf")
    subject_id, questions = _subject_with_questions(
        client, admin, grade_id, "Imtihon 10 bo‘sh", exams.EXAM_SIZE
    )

    # 19 answered (all right), one left blank -> 95%: still a pass, still reviewed.
    out = _submit(client, pupil, subject_id, _answers(questions, correct=19, total=19))
    assert out["total_count"] == exams.EXAM_SIZE
    assert out["correct_count"] == 19
    assert out["score_percent"] == 95
    assert out["passed"] is True
    assert len(out["mistakes"]) == 1
    mistake = out["mistakes"][0]
    assert mistake["question_id"] == questions[19]["id"]
    assert mistake["your_answer"] == ""
    assert mistake["correct_answer"].endswith("to‘g‘ri")


# ------------------------------------------------------------- paper build --
def test_paper_is_filled_from_the_same_grade(client: TestClient):
    """A subject with fewer than 20 flagged questions borrows from its grade."""
    admin = _admin(client)
    grade_id = _grade_id(client, admin, "11-sinf")
    pupil = _pupil(client, "exam_fill", "Nilufar", "11-sinf")

    _big_subject, big_questions = _subject_with_questions(
        client, admin, grade_id, "Katta fan", 18
    )
    small_subject, small_questions = _subject_with_questions(
        client, admin, grade_id, "Kichik fan", 5
    )

    card = _card(client, pupil, small_subject)
    assert card["total"] == exams.EXAM_SIZE
    assert card["available"] is True

    paper = client.get(f"/api/exams/{small_subject}/paper", headers=pupil).json()
    ids = [q["id"] for q in paper["questions"]]
    own = [q["id"] for q in small_questions]
    borrowed = {q["id"] for q in big_questions}
    assert ids[: len(own)] == own, "the subject's own questions come first"
    assert len(set(ids) & borrowed) == exams.EXAM_SIZE - len(own)


def test_unflagged_questions_never_reach_the_paper(client: TestClient):
    admin = _admin(client)
    grade_id = _grade_id(client, admin, "8-sinf")
    pupil = _pupil(client, "exam_unflag", "Aziz", "8-sinf")
    subject_id, flagged = _subject_with_questions(
        client, admin, grade_id, "Imtihon aralash", 2
    )
    lesson_id = _new_lesson(client, admin, subject_id, "Belgilanmagan dars")
    extra = _add_question(client, admin, lesson_id, "Belgilanmagan", flagged=False)

    card = _card(client, pupil, subject_id)
    # 3 questions exist in the subject, but only the 2 flagged ones count.
    assert card["total"] == 2
    assert card["available"] is False

    resp = client.get(f"/api/exams/{subject_id}/paper", headers=pupil)
    assert resp.status_code == 409
    detail = resp.json()["detail"]
    assert detail["error"] == "exam_not_configured"
    assert detail["available"] == 2
    assert detail["required"] == exams.EXAM_SIZE
    assert extra["id"] not in {question["id"] for question in flagged}


# ------------------------------------------------------------------ access --
def test_exam_requires_grade_and_own_grade_subject(client: TestClient):
    admin = _admin(client)
    grade_id = _grade_id(client, admin, "3-sinf")
    pupil = _pupil(client, "exam_scope", "Farhod", "3-sinf")
    subject_id, _ = _subject_with_questions(
        client, admin, grade_id, "Imtihon 9 scope", exams.EXAM_SIZE
    )

    outsider = _pupil(client, "exam_outsider", "Malika", "10-sinf")
    resp = client.get(f"/api/exams/{subject_id}/paper", headers=outsider)
    assert resp.status_code == 404
    assert resp.json()["detail"]["error"] == "subject_not_found"

    ungraded = client.post(
        "/api/auth/register",
        json={"login": "exam_nograde", "password": "Probe12345", "first_name": "Bekzod"},
    ).json()
    ungraded_headers = {"Authorization": f"Bearer {ungraded['access_token']}"}
    listing = client.get("/api/exams", headers=ungraded_headers)
    assert listing.status_code == 409
    assert listing.json()["detail"]["error"] == "grade_not_selected"

    # Another pupil of the same grade cannot submit someone else's paper.
    classmate = _pupil(client, "exam_classmate", "Donier", "3-sinf")
    paper = client.get(f"/api/exams/{subject_id}/paper", headers=pupil).json()
    stolen = client.post(
        f"/api/exams/{subject_id}/submit",
        json={"attempt_id": paper["attempt_id"], "answers": []},
        headers=classmate,
    )
    assert stolen.status_code == 404
    assert stolen.json()["detail"]["error"] == "attempt_not_found"

    # An unknown subject is a 404, not a 500.
    assert client.get("/api/exams/999999/paper", headers=pupil).status_code == 404


# ------------------------------------------------------------------- admin --
def test_admin_exam_flag_is_admin_only_and_visible(client: TestClient):
    admin = _admin(client)
    pupil = _pupil(client, "exam_admin_probe", "Gulnoza", "6-sinf")
    grade_id = _grade_id(client, pupil, "6-sinf")
    subject_id = _new_subject(client, admin, grade_id, "Imtihon admin fani")
    lesson_id = _new_lesson(client, admin, subject_id, "Savollar")
    question = _add_question(client, admin, lesson_id, "Ko‘rinadimi", flagged=False)

    denied = client.patch(
        f"/api/admin/questions/{question['id']}/exam",
        json={"is_exam": True},
        headers=pupil,
    )
    assert denied.status_code == 403

    rows = client.get(f"/api/admin/lessons/{lesson_id}/questions", headers=admin).json()
    assert rows[0]["is_exam"] is False

    flagged = client.patch(
        f"/api/admin/questions/{question['id']}/exam",
        json={"is_exam": True},
        headers=admin,
    ).json()
    assert flagged["is_exam"] is True
    rows = client.get(f"/api/admin/lessons/{lesson_id}/questions", headers=admin).json()
    assert rows[0]["is_exam"] is True

    # Unflagging works too (a teacher can change their mind).
    off = client.patch(
        f"/api/admin/questions/{question['id']}/exam",
        json={"is_exam": False},
        headers=admin,
    ).json()
    assert off["is_exam"] is False

    coverage = client.get("/api/admin/exams", params={"grade_id": grade_id}, headers=admin)
    assert coverage.status_code == 200, coverage.text
    row = next(r for r in coverage.json() if r["subject_id"] == subject_id)
    assert row["flagged"] == 0
    assert row["ready"] is False, "an empty grade pool cannot build a paper"
    assert row["grade_name"] == "6-sinf"

    missing = client.patch(
        "/api/admin/questions/999999/exam", json={"is_exam": True}, headers=admin
    )
    assert missing.status_code == 404


def test_exam_upgrades_an_earlier_course_certificate(client: TestClient):
    """Passing the exam replaces the course result but keeps the certificate code."""
    admin = _admin(client)
    grade_id = _grade_id(client, admin, "7-sinf")
    pupil = _pupil(client, "exam_upgrade", "Rustam", "7-sinf")
    subject_id, questions = _subject_with_questions(
        client, admin, grade_id, "Imtihon yangilash", exams.EXAM_SIZE
    )

    # Finish the course the normal way, then download its certificate.
    with SessionLocal() as db:
        subject = db.scalar(select(Subject).where(Subject.id == subject_id))
        user = db.scalar(select(User).where(User.login == "exam_upgrade"))
        for lesson in subject.lessons:
            db.add(
                LessonProgress(
                    user_id=user.id,
                    lesson_id=lesson.id,
                    lesson_viewed=True,
                    passed=True,
                    best_score_percent=70,
                )
            )
        db.commit()

    course_pdf = client.get(f"/api/certificates/{subject_id}/pdf", headers=pupil)
    assert course_pdf.status_code == 200
    assert course_pdf.content.startswith(b"%PDF")
    issued = client.get("/api/certificates", headers=pupil).json()
    assert issued[0]["issued_via"] == "course"
    assert issued[0]["mark"] is None
    code = issued[0]["code"]

    out = _submit(client, pupil, subject_id, _answers(questions, correct=18))
    assert out["certificate"]["code"] == code, "same document, not a second one"
    assert out["certificate"]["issued_via"] == "exam"
    assert out["certificate"]["mark"] == "5"
    assert out["certificate"]["score_percent"] == 90

    issued = client.get("/api/certificates", headers=pupil).json()
    assert len(issued) == 1
    assert issued[0]["issued_via"] == "exam"
    assert issued[0]["mark"] == "5"
    page = client.get(f"/api/certificates/verify/{code}", headers={"Accept": "text/html"})
    assert "Majburiy imtihon" in page.text
