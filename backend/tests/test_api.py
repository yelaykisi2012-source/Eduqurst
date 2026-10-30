"""
End-to-end API tests for the EduQuest backend.

Covers: Telegram initData auth (valid + tampered), content visibility,
level locking, quiz grading, stars, idempotent double-submit, achievements,
progress endpoint. Run:  python -m pytest tests/ -v
"""
from __future__ import annotations

import uuid

from fastapi.testclient import TestClient

from tests.conftest import login_as, make_init_data, pick_grade


# ---------- auth ----------
def test_login_with_valid_init_data(client: TestClient):
    data = make_init_data({"id": 555001, "first_name": "Dilnoza"})
    resp = client.post("/api/auth/telegram", json={"init_data": data})
    assert resp.status_code == 200
    body = resp.json()
    assert body["first_name"] == "Dilnoza"
    assert body["access_token"].count(".") == 2  # JWT shape


def test_login_rejects_tampered_hash(client: TestClient):
    data = make_init_data({"id": 555002, "first_name": "Xakim"}, tamper=True)
    resp = client.post("/api/auth/telegram", json={"init_data": data})
    assert resp.status_code == 401


def test_protected_endpoint_requires_token(client: TestClient):
    assert client.get("/api/subjects").status_code in (401, 403)


# ---------- content ----------
def test_subjects_listed_with_lock_state(client: TestClient, auth: dict):
    resp = client.get("/api/subjects", headers=auth)
    assert resp.status_code == 200
    subjects = resp.json()
    assert {s["name"] for s in subjects} == {"Matematika", "Ingliz tili", "Ona tili"}
    math = next(s for s in subjects if s["slug"] == "matematika")
    assert [l["level_order"] for l in math["lessons"]] == [1, 2, 3, 4]
    assert math["lessons"][0]["unlocked"] is True
    assert math["lessons"][1]["unlocked"] is False  # level 2 locked at start


def test_locked_lesson_not_readable(client: TestClient, auth: dict):
    subjects = client.get("/api/subjects", headers=auth).json()
    math = next(s for s in subjects if s["slug"] == "matematika")
    l2_id = math["lessons"][1]["id"]
    resp = client.get(f"/api/lessons/{l2_id}", headers=auth)
    assert resp.status_code == 403


def test_quiz_never_leaks_correct_answers(client: TestClient, auth: dict):
    subjects = client.get("/api/subjects", headers=auth).json()
    l1_id = next(s for s in subjects if s["slug"] == "matematika")["lessons"][0]["id"]
    quiz = client.get(f"/api/lessons/{l1_id}/quiz", headers=auth).json()
    assert len(quiz["questions"]) == 5
    raw = str(quiz)
    assert "is_correct" not in raw  # server-side grading only


# ---------- full journey ----------
def _quiz_ids(client: TestClient, auth: dict, lesson_id: int):
    """Return (lesson, [(question_id, correct_option_id_guess_via_seed)])"""
    # Correct answers known from seed data (test-side knowledge, not API leak):
    quiz = client.get(f"/api/lessons/{lesson_id}/quiz", headers=auth).json()
    return quiz


def test_fail_then_pass_unlocks_and_awards_stars(client: TestClient, auth: dict):
    subjects = client.get("/api/subjects", headers=auth).json()
    math = next(s for s in subjects if s["slug"] == "matematika")
    l1 = math["lessons"][0]

    # 1) view lesson -> +2 stars (once) + first_lesson achievement right away
    r = client.post(f"/api/lessons/{l1['id']}/viewed", headers=auth)
    assert r.status_code == 200 and r.json()["stars_granted"] is True
    assert "first_lesson" in r.json()["new_achievements"]
    r = client.post(f"/api/lessons/{l1['id']}/viewed", headers=auth)
    assert r.json()["stars_granted"] is False  # no double grant

    quiz = client.get(f"/api/lessons/{l1['id']}/quiz", headers=auth).json()
    q1 = quiz["questions"][0]

    # 2) wrong answer to everything -> fail, no pass, retry allowed
    wrong_key = uuid.uuid4().hex
    answers = [{"question_id": q["id"], "option_id": q["options"][-1]["id"]} for q in quiz["questions"]]
    # make at least one wrong: first question's last option is wrong (its correct is index 1 "6")
    resp = client.post(
        f"/api/lessons/{l1['id']}/quiz/submit",
        headers=auth,
        json={"idempotency_key": wrong_key, "answers": answers},
    )
    assert resp.status_code == 200
    result = resp.json()
    assert result["passed"] is False
    assert "urinib" in result["message_uz"]  # supportive, not punishing

    # 3) correct answers (from seed: option texts) -> pass
    correct_texts = ["4", "6", "7", "5", "9"]
    answers = []
    for q, text in zip(quiz["questions"], correct_texts):
        option = next(o for o in q["options"] if o["text"] == text)
        answers.append({"question_id": q["id"], "option_id": option["id"]})
    ok_key = uuid.uuid4().hex
    resp = client.post(
        f"/api/lessons/{l1['id']}/quiz/submit",
        headers=auth,
        json={"idempotency_key": ok_key, "answers": answers},
    )
    result = resp.json()
    assert result["passed"] is True and result["score_percent"] == 100
    assert result["stars_earned"] == 5
    assert result["next_level_unlocked"] is True
    assert "first_quiz" in result["new_achievements"]
    assert "first_lesson" not in result["new_achievements"]  # already earned at /viewed

    # 4) replay the SAME idempotency key -> duplicate, stars must NOT grow
    stars_before = result["stars_total"]
    resp2 = client.post(
        f"/api/lessons/{l1['id']}/quiz/submit",
        headers=auth,
        json={"idempotency_key": ok_key, "answers": answers},
    )
    dup = resp2.json()
    assert dup["duplicate"] is True
    assert dup["stars_total"] == stars_before

    # 5) level 2 now unlocked; total stars = 2 (viewed) + 5 (quiz) + 3+3 (2 achievements)
    subjects = client.get("/api/subjects", headers=auth).json()
    math = next(s for s in subjects if s["slug"] == "matematika")
    assert math["lessons"][1]["unlocked"] is True
    assert math["lessons"][2]["unlocked"] is False

    prog = client.get("/api/me/progress", headers=auth).json()
    # 2 viewed + 3 first_lesson + 5 quiz + 3 first_quiz + 3 star_10 (reached 10 at quiz time)
    assert prog["stars_total"] == 16
    assert prog["lessons_passed"] == 1
    earned = {a["code"]: a["earned"] for a in prog["achievements"]}
    assert earned["first_lesson"] and earned["first_quiz"] and earned["star_10"]
    assert not earned["star_50"]


def test_foreign_question_id_ignored(client: TestClient, auth: dict):
    subjects = client.get("/api/subjects", headers=auth).json()
    l1 = next(s for s in subjects if s["slug"] == "ingliz-tili")["lessons"][0]
    quiz = client.get(f"/api/lessons/{l1['id']}/quiz", headers=auth).json()
    answers = [{"question_id": q["id"], "option_id": q["options"][0]["id"]} for q in quiz["questions"]]
    answers.append({"question_id": 999999, "option_id": 999999})  # bogus
    resp = client.post(
        f"/api/lessons/{l1['id']}/quiz/submit",
        headers=auth,
        json={"idempotency_key": uuid.uuid4().hex, "answers": answers},
    )
    assert resp.status_code == 200
    assert resp.json()["total_count"] == 5  # bogus id did not inflate totals


# ---------- grade system (1..11) ----------
def test_grades_are_listed_1_to_11(client: TestClient, grade1_auth: dict):
    grades = client.get("/api/grades", headers=grade1_auth).json()
    assert len(grades) == 11
    assert [g["name"] for g in grades] == [f"{n}-sinf" for n in range(1, 12)]
    assert [g["order_index"] for g in grades] == list(range(1, 12))


def test_new_pupil_has_no_grade_and_is_sent_to_onboarding(client: TestClient):
    headers = login_as(client, {"id": 777001, "first_name": "Nilufar"})
    me = client.get("/api/me", headers=headers).json()
    assert me["grade_id"] is None
    assert me["grade_name"] is None
    assert me["needs_grade_selection"] is True
    # Content endpoints must NOT guess a grade — they return 409 instead.
    subj = client.get("/api/subjects", headers=headers)
    assert subj.status_code == 409
    assert subj.json()["detail"]["error"] == "grade_not_selected"


def test_selected_grade_persists_across_visits(client: TestClient):
    headers = login_as(client, {"id": 777002, "first_name": "Sardor"})
    r = client.post("/api/me/grade", json={"grade_id": 5}, headers=headers)
    assert r.status_code == 200
    assert r.json()["grade_name"] == "5-sinf"
    assert r.json()["needs_grade_selection"] is False
    # Re-login (same telegram id) → saved grade auto-loads, no re-prompt.
    again = login_as(client, {"id": 777002, "first_name": "Sardor"})
    me = client.get("/api/me", headers=again).json()
    assert me["grade_name"] == "5-sinf"


def test_invalid_grade_rejected(client: TestClient):
    headers = login_as(client, {"id": 777003, "first_name": "Kamola"})
    # 0 fails the ge=1 schema validation.
    assert client.post("/api/me/grade", json={"grade_id": 0}, headers=headers).status_code == 422
    # a number that is not an existing grade row (grades are 1..11) → 404.
    resp = client.post("/api/me/grade", json={"grade_id": 999}, headers=headers)
    assert resp.status_code == 404
    assert resp.json()["detail"]["error"] == "grade_not_found"


def test_content_is_scoped_to_the_chosen_grade(client: TestClient):
    g5 = login_as(client, {"id": 777004, "first_name": "Jasur"})
    pick_grade(client, g5, "5-sinf")
    # Grade 5 has no published content yet → empty, but NOT grade-1 content.
    assert client.get("/api/subjects", headers=g5).json() == []
    prog = client.get("/api/me/progress", headers=g5).json()
    assert prog["grade_name"] == "5-sinf"
    assert prog["subjects"] == []


def test_cross_grade_lesson_is_blocked(client: TestClient, grade1_auth: dict):
    # Grab a grade-1 lesson id using the grade-1 pupil.
    subjects = client.get("/api/subjects", headers=grade1_auth).json()
    math = next(s for s in subjects if s["slug"] == "matematika")
    l1_id = math["lessons"][0]["id"]
    # A grade-5 pupil must not be able to open that grade-1 lesson.
    g5 = login_as(client, {"id": 777005, "first_name": "Dilnoza"})
    pick_grade(client, g5, "5-sinf")
    resp = client.get(f"/api/lessons/{l1_id}", headers=g5)
    assert resp.status_code == 403
    assert resp.json()["detail"]["error"] == "wrong_grade"


def test_changing_grade_keeps_previous_progress(client: TestClient):
    headers = login_as(client, {"id": 777006, "first_name": "Aziz"})
    pick_grade(client, headers, "1-sinf")
    subjects = client.get("/api/subjects", headers=headers).json()
    l1_id = next(s for s in subjects if s["slug"] == "matematika")["lessons"][0]["id"]
    # view the lesson → global progress records it
    client.post(f"/api/lessons/{l1_id}/viewed", headers=headers)
    assert client.get("/api/me/progress", headers=headers).json()["lessons_viewed"] == 1
    # switch to grade 5 → the grade-1 viewed lesson is NOT deleted
    client.post("/api/me/grade", json={"grade_id": 5}, headers=headers)
    prog5 = client.get("/api/me/progress", headers=headers).json()
    assert prog5["grade_name"] == "5-sinf"
    assert prog5["lessons_viewed"] == 1   # progress preserved
    assert prog5["subjects"] == []        # grade-5 shows no grade-1 subjects
    # switch back to grade 1 → progress still tied to its original grade
    client.post("/api/me/grade", json={"grade_id": 1}, headers=headers)
    back = client.get("/api/me/progress", headers=headers).json()
    assert back["grade_name"] == "1-sinf"
    assert back["lessons_viewed"] == 1
    math = next(s for s in back["subjects"] if s["subject_name"] == "Matematika")
    assert math["total_lessons"] == 4


# ---------- bot internal endpoint ----------
from tests.conftest import TEST_BOT_TOKEN

_BOT_HDRS = {"X-Bot-Token": TEST_BOT_TOKEN}


def test_pupil_summary_rejects_missing_or_wrong_token(client: TestClient):
    assert client.get("/api/internal/pupil-summary", params={"telegram_id": 1}).status_code == 401
    assert client.get(
        "/api/internal/pupil-summary",
        params={"telegram_id": 1},
        headers={"X-Bot-Token": "wrong"},
    ).status_code == 401


def test_pupil_summary_unknown_user(client: TestClient):
    resp = client.get(
        "/api/internal/pupil-summary", params={"telegram_id": 999999999}, headers=_BOT_HDRS
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["known_user"] is False
    assert body["needs_onboarding"] is True


def test_pupil_summary_reflects_real_grade_and_stars(client: TestClient):
    tg_id = 777001
    headers = login_as(client, {"id": tg_id, "first_name": "BotTest"})
    pick_grade(client, headers, "1-sinf")
    # earn one star by viewing a lesson
    subjects = client.get("/api/subjects", headers=headers).json()
    math = next(s for s in subjects if s["slug"] == "matematika")
    client.post(f"/api/lessons/{math['lessons'][0]['id']}/viewed", headers=headers)

    body = client.get(
        "/api/internal/pupil-summary", params={"telegram_id": tg_id}, headers=_BOT_HDRS
    ).json()
    assert body["known_user"] is True
    assert body["needs_onboarding"] is False
    assert body["first_name"] == "BotTest"
    assert body["grade_name"] == "1-sinf"
    assert body["stars_total"] >= 1
    assert body["lessons_viewed"] == 1


# ---------- admin panel ----------
def test_admin_endpoints_forbid_non_admin(client: TestClient, grade1_auth):
    assert client.get("/api/admin/overview", headers=grade1_auth).status_code == 403
    assert client.post(
        "/api/admin/subjects",
        json={"grade_id": 5, "name": "Fizika", "emoji": "⚛️"},
        headers=grade1_auth,
    ).status_code == 403
    me = client.get("/api/me", headers=grade1_auth).json()
    assert me["is_admin"] is False


def test_admin_can_create_full_lesson_flow(client: TestClient):
    admin = login_as(client, {"id": 999000111, "first_name": "Admin"})
    assert client.get("/api/me", headers=admin).json()["is_admin"] is True

    # 1) subject for 5-sinf
    subj = client.post(
        "/api/admin/subjects",
        json={"grade_id": 5, "name": "Fizika", "emoji": "⚛️"},
        headers=admin,
    )
    assert subj.status_code == 201, subj.text
    subject = subj.json()
    assert subject["slug"].startswith("fizika")

    # 2) lesson inside it
    lesson = client.post(
        f"/api/admin/subjects/{subject['id']}/lessons",
        json={
            "title": "Kuch va harakat",
            "explanation": "Kuch — jismni harakatga keltiradi yoki to'xtatadi.",
            "stars_reward": 5,
            "pass_threshold_percent": 60,
        },
        headers=admin,
    )
    assert lesson.status_code == 201, lesson.text
    lesson_id = lesson.json()["id"]

    # 3) a question with options
    q = client.post(
        f"/api/admin/lessons/{lesson_id}/questions",
        json={
            "text": "Kuch birligi nima?",
            "kind": "single",
            "options": [
                {"text": "Nyuton", "is_correct": True},
                {"text": "Metrr", "is_correct": False},
                {"text": "Sekund", "is_correct": False},
            ],
        },
        headers=admin,
    )
    assert q.status_code == 201, q.text

    # 4) single-choice validation: two correct answers rejected
    bad = client.post(
        f"/api/admin/lessons/{lesson_id}/questions",
        json={
            "text": "Ikki to'g'ri javobli savol",
            "kind": "single",
            "options": [
                {"text": "a", "is_correct": True},
                {"text": "b", "is_correct": True},
            ],
        },
        headers=admin,
    )
    assert bad.status_code == 422

    # 5) overview shows the new content
    ov = client.get("/api/admin/overview", headers=admin).json()
    g5 = next(g for g in ov if g["grade_name"] == "5-sinf")
    fiz = next(s for s in g5["subjects"] if s["name"] == "Fizika")
    assert fiz["lesson_count"] == 1

    # 6) a real 5-sinf pupil now sees Fizika with the lesson
    pupil = login_as(client, {"id": 888000222, "first_name": "Sardor"})
    pick_grade(client, pupil, "5-sinf")
    subjects = client.get("/api/subjects", headers=pupil).json()
    fiz_p = next(s for s in subjects if s["name"] == "Fizika")
    assert fiz_p["lessons"][0]["title"] == "Kuch va harakat"
    # quiz is fetchable and gradeable
    quiz = client.get(f"/api/lessons/{lesson_id}/quiz", headers=pupil).json()
    client.post(f"/api/lessons/{lesson_id}/viewed", headers=pupil)
    result = client.post(
        f"/api/lessons/{lesson_id}/quiz/submit",
        json={
            "idempotency_key": str(uuid.uuid4()),
            "answers": [{"question_id": quiz["questions"][0]["id"],
                         "option_id": quiz["questions"][0]["options"][0]["id"]}],
        },
        headers=pupil,
    ).json()
    assert result["passed"] is True  # first option was the correct one


# ---------- bot FULL experience (internal endpoints) ----------
def _h(tok: str | None = None) -> dict:
    return {"X-Bot-Token": tok if tok is not None else TEST_BOT_TOKEN}


def test_internal_pupil_flow_requires_bot_token(client: TestClient):
    assert client.get("/api/internal/pupil/subjects", params={"telegram_id": 1}).status_code == 401
    assert client.post(
        "/api/internal/pupils",
        json={"telegram_id": 1, "first_name": "X"},
        headers=_h("wrong-token"),
    ).status_code == 401


def test_internal_unknown_pupil_is_404(client: TestClient):
    resp = client.get(
        "/api/internal/pupil/subjects", params={"telegram_id": 42424242}, headers=_h()
    )
    assert resp.status_code == 404
    assert resp.json()["detail"]["error"] == "pupil_not_found"


def test_bot_full_pupil_journey(client: TestClient):
    """The whole learning loop works through bot-token endpoints alone."""
    tg = 777501
    # /start in the bot registers the pupil
    up = client.post(
        "/api/internal/pupils",
        json={"telegram_id": tg, "first_name": "Botzoda", "username": "botzoda"},
        headers=_h(),
    )
    assert up.status_code == 200
    assert up.json()["known_user"] is True and up.json()["needs_onboarding"] is True

    # No grade yet → same 409 rule as the Mini App (never guess)
    subj = client.get("/api/internal/pupil/subjects", params={"telegram_id": tg}, headers=_h())
    assert subj.status_code == 409
    assert subj.json()["detail"]["error"] == "grade_not_selected"

    # Grade picked via bot button
    g = client.post(
        "/api/internal/pupil/grade",
        json={"telegram_id": tg, "grade_id": 1},
        headers=_h(),
    )
    assert g.status_code == 200 and g.json()["grade_name"] == "1-sinf"

    subjects = client.get(
        "/api/internal/pupil/subjects", params={"telegram_id": tg}, headers=_h()
    ).json()
    math = next(s for s in subjects if s["slug"] == "matematika")
    l1 = math["lessons"][0]

    lesson = client.get(f"/api/internal/pupil/lesson/{l1['id']}", params={"telegram_id": tg}, headers=_h())
    assert lesson.status_code == 200 and lesson.json()["explanation"]

    v = client.post(f"/api/internal/pupil/lesson/{l1['id']}/viewed", params={"telegram_id": tg}, headers=_h())
    assert v.json()["stars_granted"] is True

    quiz = client.get(f"/api/internal/pupil/lesson/{l1['id']}/quiz", params={"telegram_id": tg}, headers=_h()).json()
    assert "is_correct" not in str(quiz)  # answers never leak to the bot either
    correct_texts = ["4", "6", "7", "5", "9"]
    answers = []
    for q, text in zip(quiz["questions"], correct_texts):
        option = next(o for o in q["options"] if o["text"] == text)
        answers.append({"question_id": q["id"], "option_id": option["id"]})
    res = client.post(
        f"/api/internal/pupil/lesson/{l1['id']}/quiz/submit",
        json={"telegram_id": tg, "idempotency_key": str(uuid.uuid4()), "answers": answers},
        headers=_h(),
    ).json()
    assert res["passed"] is True and res["stars_earned"] == 5

    prog = client.get("/api/internal/pupil/progress", params={"telegram_id": tg}, headers=_h()).json()
    assert prog["grade_name"] == "1-sinf"
    assert prog["lessons_passed"] == 1 and prog["stars_total"] >= 7


def test_internal_admin_guard_and_creation_flow(client: TestClient):
    # a normal pupil registered via bot → internal admin is 403
    client.post(
        "/api/internal/pupils", json={"telegram_id": 777502, "first_name": "Odam"}, headers=_h()
    )
    ov = client.get("/api/internal/admin/overview", params={"telegram_id": 777502}, headers=_h())
    assert ov.status_code == 403
    assert ov.json()["detail"]["error"] == "not_admin"

    # the allowlisted admin (ADMIN_TELEGRAM_IDS in conftest) works
    client.post(
        "/api/internal/pupils", json={"telegram_id": 999000111, "first_name": "Admin"}, headers=_h()
    )
    ov = client.get("/api/internal/admin/overview", params={"telegram_id": 999000111}, headers=_h())
    assert ov.status_code == 200 and len(ov.json()) == 11

    subj = client.post(
        "/api/internal/admin/subjects",
        json={"telegram_id": 999000111, "data": {"grade_id": 6, "name": "Botqurilish", "emoji": "🏗️"}},
        headers=_h(),
    )
    assert subj.status_code == 201, subj.text
    sid = subj.json()["id"]

    les = client.post(
        f"/api/internal/admin/subjects/{sid}/lessons",
        json={
            "telegram_id": 999000111,
            "data": {
                "title": "Poydevor",
                "explanation": "Poydevor binoning eng asosiy qismi — u og'irlikni yerga beradi.",
                "stars_reward": 4,
                "pass_threshold_percent": 50,
            },
        },
        headers=_h(),
    )
    assert les.status_code == 201, les.text
    lid = les.json()["id"]

    q = client.post(
        f"/api/internal/admin/lessons/{lid}/questions",
        json={
            "telegram_id": 999000111,
            "data": {
                "text": "Poydevor nimaga xizmat qiladi?",
                "kind": "single",
                "options": [
                    {"text": "Og'irlikni yerga beradi", "is_correct": True},
                    {"text": "Bezak uchun", "is_correct": False},
                ],
            },
        },
        headers=_h(),
    )
    assert q.status_code == 201, q.text

    # a 6-sinf pupil sees the new lesson through the bot endpoints
    client.post(
        "/api/internal/pupils", json={"telegram_id": 777503, "first_name": "Usta"}, headers=_h()
    )
    client.post("/api/internal/pupil/grade", json={"telegram_id": 777503, "grade_id": 6}, headers=_h())
    subjects = client.get(
        "/api/internal/pupil/subjects", params={"telegram_id": 777503}, headers=_h()
    ).json()
    botq = next(s for s in subjects if s["name"] == "Botqurilish")
    assert botq["lessons"][0]["title"] == "Poydevor"
    assert botq["lessons"][0]["unlocked"] is True
