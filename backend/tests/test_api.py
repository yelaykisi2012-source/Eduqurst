"""
End-to-end API tests for the EduQuest backend.

Covers: Telegram initData auth (valid + tampered), content visibility,
level locking, quiz grading, stars, idempotent double-submit, achievements,
progress endpoint. Run:  python -m pytest tests/ -v
"""
from __future__ import annotations

import time
import uuid

from fastapi.testclient import TestClient

from tests.conftest import login_as, make_init_data, make_web_login, pick_grade


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


def test_login_accepts_names_with_spaces(client: TestClient):
    # Telegram percent-encodes a space in initData values (%20) and signs the
    # DECODED check-string, i.e. with a real space. Signing the raw %20 text
    # rejects every real login — this regression test catches exactly that.
    data = make_init_data(
        {"id": 555003, "first_name": "Ali Karim", "last_name": "Said o'g'li",
         "username": "ali_test"}
    )
    resp = client.post("/api/auth/telegram", json={"init_data": data})
    assert resp.status_code == 200, resp.text
    assert resp.json()["first_name"] == "Ali Karim"


def test_login_ignores_ed25519_signature_field(client: TestClient):
    # Telegram 2024+ adds an Ed25519 `signature` field to initData. The HMAC
    # check-string must EXCLUDE it; folding it in breaks every real login
    # (forged test data without the field would still pass — false green).
    data = make_init_data({"id": 555004, "first_name": "Imzoli"})
    assert "signature=" in data
    resp = client.post("/api/auth/telegram", json={"init_data": data})
    assert resp.status_code == 200, resp.text


def test_login_rejects_missing_stale_or_future_auth_date(client: TestClient):
    user = {"id": 555010, "first_name": "Vaqt"}
    # missing auth_date (auth_date=0 means "omit the field")
    missing = make_init_data(user, auth_date=0)
    assert client.post("/api/auth/telegram", json={"init_data": missing}).status_code == 401
    # older than 24 hours
    stale = make_init_data(user, auth_date=int(time.time()) - 90_000)
    assert client.post("/api/auth/telegram", json={"init_data": stale}).status_code == 401
    # far in the future (replay/clock abuse)
    future = make_init_data(user, auth_date=int(time.time()) + 3_600)
    assert client.post("/api/auth/telegram", json={"init_data": future}).status_code == 401
    # a fresh date still works
    fresh = make_init_data(user, auth_date=int(time.time()) - 60)
    assert client.post("/api/auth/telegram", json={"init_data": fresh}).status_code == 200


# ---------- web login (Telegram Login Widget, browser outside Telegram) ----------
def test_web_login_with_valid_widget_payload(client: TestClient):
    payload = make_web_login({
        "id": 556001,
        "first_name": "Veb",
        "last_name": "Foydalanuvchi",
        "username": "veb_user",
        "photo_url": "https://t.me/i/userpic/320/veb.jpg",
    })
    resp = client.post("/api/auth/telegram-web", json=payload)
    assert resp.status_code == 200, resp.text
    assert resp.json()["first_name"] == "Veb"
    me = client.get(
        "/api/me", headers={"Authorization": f"Bearer {resp.json()['access_token']}"}
    )
    assert me.status_code == 200
    assert me.json()["first_name"] == "Veb"


def test_web_login_rejects_tampered_hash(client: TestClient):
    payload = make_web_login({"id": 556002, "first_name": "Fake"}, tamper=True)
    assert client.post("/api/auth/telegram-web", json=payload).status_code == 401


def test_web_login_rejects_stale_payload(client: TestClient):
    payload = make_web_login(
        {"id": 556003, "first_name": "Eski"}, auth_date=int(time.time()) - 90_000
    )
    assert client.post("/api/auth/telegram-web", json=payload).status_code == 401


def test_web_login_rejects_missing_hash(client: TestClient):
    payload = make_web_login({"id": 556004, "first_name": "Hashsiz"})
    payload.pop("hash")
    assert client.post("/api/auth/telegram-web", json=payload).status_code == 401


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
    assert "Birinchi dars" in r.json()["new_achievement_titles"]
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
    assert "Birinchi test" in result["new_achievement_titles"]

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
    assert client.patch(
        "/api/admin/lessons/1", json={"is_published": False}, headers=grade1_auth
    ).status_code == 403
    assert client.delete("/api/admin/questions/1", headers=grade1_auth).status_code == 403
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


def test_lesson_four_formats_material_flow(client: TestClient):
    """Admin posts all four lesson formats; pupils receive them in lesson detail."""
    admin = login_as(client, {"id": 999000111, "first_name": "Admin"})
    subj = client.post(
        "/api/admin/subjects",
        json={"grade_id": 8, "name": "Media darslar", "emoji": "🎬"},
        headers=admin,
    ).json()
    lesson = client.post(
        f"/api/admin/subjects/{subj['id']}/lessons",
        json={
            "title": "To‘rt format",
            "explanation": "Video, PDF, yozma va jonli dars — hammasi bitta darsda.",
        },
        headers=admin,
    ).json()

    formats = [
        ("video", "Video dars", "https://youtu.be/dQw4w9WgXcQ"),
        ("pdf", "Mashqlar to‘plami", "https://example.com/mashqlar.pdf"),
        ("live", "Dushanba 18:00", "https://meet.example.com/xona-1"),
        ("text", "Qisqa eslatma", "Asosiy qoidalar: ..."),
    ]
    ids = []
    for kind, title, content in formats:
        r = client.post(
            f"/api/admin/lessons/{lesson['id']}/materials",
            json={"kind": kind, "title": title, "content": content},
            headers=admin,
        )
        assert r.status_code == 201, r.text
        ids.append(r.json()["id"])

    # URL-required kinds must reject free text; unknown kinds are rejected too
    assert client.post(
        f"/api/admin/lessons/{lesson['id']}/materials",
        json={"kind": "video", "title": "Buzuq", "content": "havola emas"},
        headers=admin,
    ).status_code == 422
    assert client.post(
        f"/api/admin/lessons/{lesson['id']}/materials",
        json={"kind": "audio", "title": "Buzuq", "content": "https://x.uz/a.mp3"},
        headers=admin,
    ).status_code == 422

    # material_count shows up for admins
    lessons = client.get(f"/api/admin/subjects/{subj['id']}/lessons", headers=admin).json()
    assert lessons[0]["material_count"] == 4

    # a pupil reads all four formats in the lesson payload
    pupil = login_as(client, {"id": 888000444, "first_name": "Media"})
    pick_grade(client, pupil, "8-sinf")
    detail = client.get(f"/api/lessons/{lesson['id']}", headers=pupil).json()
    kinds = [(m["kind"], m["content"]) for m in detail["materials"]]
    assert kinds[0] == ("video", "https://youtu.be/dQw4w9WgXcQ")
    assert kinds[1][0] == "pdf" and kinds[1][1].endswith(".pdf")
    assert kinds[2][0] == "live" and "meet" in kinds[2][1]
    assert kinds[3][0] == "text"

    # ... and through the bot's internal endpoint as well
    client.post("/api/internal/pupils", json={"telegram_id": 777504, "first_name": "Media"}, headers=_h())
    client.post("/api/internal/pupil/grade", json={"telegram_id": 777504, "grade_id": 8}, headers=_h())
    bot_detail = client.get(
        f"/api/internal/pupil/lesson/{lesson['id']}",
        params={"telegram_id": 777504},
        headers=_h(),
    ).json()
    assert {m["kind"] for m in bot_detail["materials"]} == {"video", "pdf", "live", "text"}


def test_internal_admin_can_add_four_formats(client: TestClient):
    """The bot's admin flow must be able to post every format through /api/internal."""
    # the admin must exist as a pupil (the bot upserts on /start) ...
    client.post(
        "/api/internal/pupils",
        json={"telegram_id": 999000111, "first_name": "Admin"},
        headers=_h(),
    )
    subj = client.post(
        "/api/internal/admin/subjects",
        json={
            "telegram_id": 999000111,
            "data": {"grade_id": 9, "name": "Bot media", "emoji": "🎥"},
        },
        headers=_h(),
    )
    assert subj.status_code == 201, subj.text
    lesson = client.post(
        f"/api/internal/admin/subjects/{subj.json()['id']}/lessons",
        json={
            "telegram_id": 999000111,
            "data": {"title": "Bot orqali dars", "explanation": "To‘rt format botdan."},
        },
        headers=_h(),
    )
    assert lesson.status_code == 201, lesson.text
    lid = lesson.json()["id"]

    formats = [
        ("video", "Video", "https://youtu.be/abc123"),
        ("pdf", "PDF", "https://example.com/a.pdf"),
        ("live", "Jonli", "https://meet.example.com/room"),
        ("text", "Yozma", "Qisqa eslatma matni"),
    ]
    for kind, title, content in formats:
        r = client.post(
            f"/api/internal/admin/lessons/{lid}/materials",
            json={"telegram_id": 999000111, "data": {"kind": kind, "title": title, "content": content}},
            headers=_h(),
        )
        assert r.status_code == 201, r.text
        assert r.json()["kind"] == kind

    # same server-side validation as the Mini App admin panel
    bad_url = client.post(
        f"/api/internal/admin/lessons/{lid}/materials",
        json={"telegram_id": 999000111, "data": {"kind": "video", "title": "X", "content": "havola emas"}},
        headers=_h(),
    )
    assert bad_url.status_code == 422
    bad_kind = client.post(
        f"/api/internal/admin/lessons/{lid}/materials",
        json={"telegram_id": 999000111, "data": {"kind": "audio", "title": "X", "content": "https://a.uz/a.mp3"}},
        headers=_h(),
    )
    assert bad_kind.status_code == 422

    lessons = client.get(
        f"/api/internal/admin/subjects/{subj.json()['id']}/lessons",
        params={"telegram_id": 999000111},
        headers=_h(),
    ).json()
    assert lessons[0]["material_count"] == 4

    # a non-admin telegram id is refused even with a valid bot token
    client.post("/api/internal/pupils", json={"telegram_id": 777505, "first_name": "Oddiy"}, headers=_h())
    forbidden = client.post(
        f"/api/internal/admin/lessons/{lid}/materials",
        json={"telegram_id": 777505, "data": {"kind": "text", "title": "XX", "content": "yy"}},
        headers=_h(),
    )
    assert forbidden.status_code == 403
    assert forbidden.json()["detail"]["error"] == "not_admin"


def test_admin_can_edit_publish_and_delete_content(client: TestClient):
    admin = login_as(client, {"id": 999000111, "first_name": "Admin"})
    subj = client.post(
        "/api/admin/subjects",
        json={"grade_id": 10, "name": "Astronomiya", "emoji": "🪐"},
        headers=admin,
    )
    assert subj.status_code == 201, subj.text
    sid = subj.json()["id"]

    lesson = client.post(
        f"/api/admin/subjects/{sid}/lessons",
        json={
            "title": "Quyosh tizimi",
            "explanation": "Quyosh tizimida sakkizta sayyora bor.",
        },
        headers=admin,
    )
    assert lesson.status_code == 201, lesson.text
    lid = lesson.json()["id"]
    assert lesson.json()["is_published"] is True
    assert lesson.json()["question_count"] == 0

    m1 = client.post(
        f"/api/admin/lessons/{lid}/materials",
        json={"kind": "video", "title": "Video dars", "content": "https://youtu.be/x"},
        headers=admin,
    ).json()
    m2 = client.post(
        f"/api/admin/lessons/{lid}/materials",
        json={"kind": "text", "title": "Eslatma", "content": "Sayyoralarni yodda tut!"},
        headers=admin,
    ).json()
    q1 = client.post(
        f"/api/admin/lessons/{lid}/questions",
        json={
            "text": "Nechta sayyora bor?",
            "kind": "single",
            "options": [
                {"text": "8", "is_correct": True},
                {"text": "9", "is_correct": False},
            ],
        },
        headers=admin,
    ).json()
    client.post(
        f"/api/admin/lessons/{lid}/questions",
        json={
            "text": "Quyosh nima?",
            "kind": "single",
            "options": [
                {"text": "Yulduz", "is_correct": True},
                {"text": "Sayyora", "is_correct": False},
            ],
        },
        headers=admin,
    )

    # lists: ordered materials + full question view with correct flags
    mats = client.get(f"/api/admin/lessons/{lid}/materials", headers=admin).json()
    assert [m["id"] for m in mats] == [m1["id"], m2["id"]]
    qs = client.get(f"/api/admin/lessons/{lid}/questions", headers=admin).json()
    assert len(qs) == 2
    assert any(o["is_correct"] for o in qs[0]["options"])
    assert [o["text"] for o in qs[0]["options"] if o["is_correct"]] == ["8"]

    # edit lesson: text, points, threshold, hide
    r = client.patch(
        f"/api/admin/lessons/{lid}",
        json={
            "title": "Quyosh oilasi",
            "stars_reward": 8,
            "pass_threshold_percent": 90,
            "is_published": False,
        },
        headers=admin,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["title"] == "Quyosh oilasi"
    assert body["stars_reward"] == 8
    assert body["pass_threshold_percent"] == 90
    assert body["is_published"] is False
    assert body["material_count"] == 2 and body["question_count"] == 2

    # edit subject: rename + emoji (slug stays stable for old links)
    r = client.patch(
        f"/api/admin/subjects/{sid}",
        json={"name": "Koinot", "emoji": "🌌"},
        headers=admin,
    )
    assert r.status_code == 200, r.text
    assert r.json()["name"] == "Koinot" and r.json()["emoji"] == "🌌"
    assert r.json()["lesson_count"] == 1
    assert r.json()["slug"] == subj.json()["slug"]

    # delete one material and one question (options go with the question)
    assert client.delete(f"/api/admin/materials/{m1['id']}", headers=admin).status_code == 204
    assert client.delete(f"/api/admin/questions/{q1['id']}", headers=admin).status_code == 204
    assert client.delete(f"/api/admin/materials/{m1['id']}", headers=admin).status_code == 404
    lesson_now = client.get(f"/api/admin/lessons/{lid}", headers=admin).json()
    assert lesson_now["material_count"] == 1
    assert lesson_now["question_count"] == 1

    # a pupil of the same grade: hidden lesson is not listed or readable
    pupil = login_as(client, {"id": 888000901, "first_name": "Koinot"})
    pick_grade(client, pupil, "10-sinf")
    subjects = client.get("/api/subjects", headers=pupil).json()
    koinot = next(s for s in subjects if s["id"] == sid)
    assert koinot["name"] == "Koinot" and koinot["lessons"] == []
    assert client.get(f"/api/lessons/{lid}", headers=pupil).status_code == 404

    # publish the lesson again → it reappears with the edited title
    client.patch(f"/api/admin/lessons/{lid}", json={"is_published": True}, headers=admin)
    subjects = client.get("/api/subjects", headers=pupil).json()
    koinot = next(s for s in subjects if s["id"] == sid)
    assert [l["title"] for l in koinot["lessons"]] == ["Quyosh oilasi"]

    # hide the whole subject → disappears from the pupil's home page
    client.patch(f"/api/admin/subjects/{sid}", json={"is_published": False}, headers=admin)
    subjects = client.get("/api/subjects", headers=pupil).json()
    assert sid not in {s["id"] for s in subjects}


def test_hidden_middle_lesson_does_not_block_unlock(client: TestClient):
    admin = login_as(client, {"id": 999000111, "first_name": "Admin"})
    subj = client.post(
        "/api/admin/subjects",
        json={"grade_id": 11, "name": "Zanjir", "emoji": "🔗"},
        headers=admin,
    )
    sid = subj.json()["id"]
    lids = []
    for n in (1, 2, 3):
        lesson = client.post(
            f"/api/admin/subjects/{sid}/lessons",
            json={
                "title": f"Bosqich {n}",
                "explanation": f"Bosqich {n} uchun yetarlicha uzun matn.",
            },
            headers=admin,
        ).json()
        lids.append(lesson["id"])
        client.post(
            f"/api/admin/lessons/{lesson['id']}/questions",
            json={
                "text": f"Savol {n}?",
                "kind": "single",
                "options": [
                    {"text": "To'g'ri", "is_correct": True},
                    {"text": "Xato", "is_correct": False},
                ],
            },
            headers=admin,
        )

    # archive the middle lesson
    client.patch(f"/api/admin/lessons/{lids[1]}", json={"is_published": False}, headers=admin)

    pupil = login_as(client, {"id": 888000902, "first_name": "Zanjir"})
    pick_grade(client, pupil, "11-sinf")
    z = next(
        s for s in client.get("/api/subjects", headers=pupil).json() if s["id"] == sid
    )
    assert [l["level_order"] for l in z["lessons"]] == [1, 3]
    assert z["lessons"][1]["unlocked"] is False  # still needs level 1

    quiz = client.get(f"/api/lessons/{lids[0]}/quiz", headers=pupil).json()
    result = client.post(
        f"/api/lessons/{lids[0]}/quiz/submit",
        json={
            "idempotency_key": uuid.uuid4().hex,
            "answers": [
                {"question_id": q["id"], "option_id": q["options"][0]["id"]}
                for q in quiz["questions"]
            ],
        },
        headers=pupil,
    ).json()
    assert result["passed"] is True
    assert result["next_level_unlocked"] is True  # level 3, not the hidden level 2

    z = next(
        s for s in client.get("/api/subjects", headers=pupil).json() if s["id"] == sid
    )
    assert z["lessons"][1]["level_order"] == 3
    assert z["lessons"][1]["unlocked"] is True


# ---------- fayl materiallar (Telegram orqali yuklangan pdf/video) ----------

def _file_material_setup(client: TestClient) -> tuple[dict, dict, dict, dict, dict]:
    """7-sinfda bitta dars yaratadi: fayl pdf + fayl video + yozma eslatma."""
    admin = login_as(client, {"id": 999000111, "first_name": "Admin"})
    subj = client.post(
        "/api/admin/subjects",
        json={"grade_id": 7, "name": "Fayllar", "emoji": "📁"},
        headers=admin,
    ).json()
    lesson = client.post(
        f"/api/admin/subjects/{subj['id']}/lessons",
        json={"title": "Fayl dars", "explanation": "PDF va video fayl sifatida."},
        headers=admin,
    ).json()
    pdf = client.post(
        f"/api/admin/lessons/{lesson['id']}/materials",
        json={
            "kind": "pdf", "title": "Kitob",
            "file_id": "BQACAgIAAx1pdf", "file_name": "kitob.pdf", "file_size": 1_234_567,
        },
        headers=admin,
    )
    video = client.post(
        f"/api/admin/lessons/{lesson['id']}/materials",
        json={
            "kind": "video", "title": "Rollik",
            "file_id": "BAACAgIAAx2mp4", "file_name": "dars.mp4", "file_size": 5_000_000,
        },
        headers=admin,
    )
    text = client.post(
        f"/api/admin/lessons/{lesson['id']}/materials",
        json={"kind": "text", "title": "Eslatma", "content": "Yozma matn"},
        headers=admin,
    )
    assert pdf.status_code == 201, pdf.text
    assert video.status_code == 201, video.text
    assert text.status_code == 201, text.text
    return admin, lesson, pdf.json(), video.json(), text.json()


def test_material_create_with_file_needs_no_url(client: TestClient):
    admin, lesson, pdf, video, text = _file_material_setup(client)

    # fayl materiallarida content bo'sh bo'ladi, fayl maydonlari saqlanadi
    assert pdf["content"] == "" and pdf["file_id"] == "BQACAgIAAx1pdf"
    assert pdf["file_name"] == "kitob.pdf" and pdf["file_size"] == 1_234_567
    assert video["file_id"] and video["file_name"] == "dars.mp4"

    # video/pdf: havola ham, file_id ham bo'lmasa → 422
    assert client.post(
        f"/api/admin/lessons/{lesson['id']}/materials",
        json={"kind": "pdf", "title": "Buzuq", "content": "havola emas"},
        headers=admin,
    ).status_code == 422
    assert client.post(
        f"/api/admin/lessons/{lesson['id']}/materials",
        json={"kind": "video", "title": "Buzuq", "content": ""},
        headers=admin,
    ).status_code == 422

    # jonli dars faqat havola (Zoom/Meet): file_id bilan ham URL talab qilinadi
    assert client.post(
        f"/api/admin/lessons/{lesson['id']}/materials",
        json={"kind": "live", "title": "Jonli", "file_id": "AAA", "file_name": "a.mp4"},
        headers=admin,
    ).status_code == 422

    # o'quvchi dars tafsilotida fayl maydonlarini ko'radi
    pupil = login_as(client, {"id": 888001001, "first_name": "Faylchi"})
    pick_grade(client, pupil, "7-sinf")
    detail = client.get(f"/api/lessons/{lesson['id']}", headers=pupil).json()
    by_kind = {m["kind"]: m for m in detail["materials"]}
    assert by_kind["pdf"]["file_id"] == "BQACAgIAAx1pdf"
    assert by_kind["pdf"]["content"] == ""
    assert by_kind["video"]["file_name"] == "dars.mp4"
    assert by_kind["text"]["file_id"] is None


def test_material_file_proxy(client: TestClient, monkeypatch):
    from app.routers import content as content_api

    _, _, pdf, video, text = _file_material_setup(client)
    pupil = login_as(client, {"id": 888001002, "first_name": "Proxy"})
    pick_grade(client, pupil, "7-sinf")

    monkeypatch.setattr(
        content_api, "_telegram_get_file",
        lambda fid: {"ok": True, "result": {"file_path": f"documents/{fid}.bin"}},
    )

    # PDF → inline application/pdf, stream body o'tadi, token URLda ko'rinmaydi
    monkeypatch.setattr(
        content_api, "_telegram_file_stream", lambda path: (b for b in [b"%PDF-1.4", b"-fayl"])
    )
    resp = client.get(f"/api/materials/{pdf['id']}/file", headers=pupil)
    assert resp.status_code == 200, resp.text
    assert resp.headers["content-type"].startswith("application/pdf")
    assert 'filename="kitob.pdf"' in resp.headers["content-disposition"]
    assert resp.content == b"%PDF-1.4-fayl"

    # MP4 → video/mp4
    monkeypatch.setattr(
        content_api, "_telegram_file_stream", lambda path: (b for b in [b"video-bytes"])
    )
    resp = client.get(f"/api/materials/{video['id']}/file", headers=pupil)
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("video/mp4")
    assert resp.content == b"video-bytes"

    # fayli yo'q material (yozma eslatma) → 404
    assert client.get(f"/api/materials/{text['id']}/file", headers=pupil).status_code == 404
    # umuman mavjud bo'lmagan material → 404
    assert client.get("/api/materials/999999/file", headers=pupil).status_code == 404

    # Telegram fayl juda katta desa → halol 413
    monkeypatch.setattr(
        content_api, "_telegram_get_file",
        lambda fid: {"ok": False, "description": "file is too big to download"},
    )
    assert client.get(f"/api/materials/{pdf['id']}/file", headers=pupil).status_code == 413

    # boshqa sinf o'quvchisi faylni ko'ra olmaydi → 403
    stranger = login_as(client, {"id": 888001003, "first_name": "Begona"})
    pick_grade(client, stranger, "6-sinf")
    monkeypatch.setattr(
        content_api, "_telegram_get_file",
        lambda fid: {"ok": True, "result": {"file_path": "documents/x.bin"}},
    )
    assert client.get(f"/api/materials/{pdf['id']}/file", headers=stranger).status_code == 403


def test_internal_material_endpoint(client: TestClient):
    _, _, pdf, video, text = _file_material_setup(client)
    client.post(
        "/api/internal/pupils", json={"telegram_id": 777601, "first_name": "Botchi"}, headers=_h()
    )
    client.post("/api/internal/pupil/grade", json={"telegram_id": 777601, "grade_id": 7}, headers=_h())

    resp = client.get(
        f"/api/internal/materials/{pdf['id']}", params={"telegram_id": 777601}, headers=_h()
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["kind"] == "pdf"
    assert body["file_id"] == "BQACAgIAAx1pdf"
    assert body["file_name"] == "kitob.pdf" and body["file_size"] == 1_234_567
    assert client.get(
        f"/api/internal/materials/{video['id']}", params={"telegram_id": 777601}, headers=_h()
    ).json()["file_id"] == "BAACAgIAAx2mp4"

    # faylsiz material → 404; noto'g'ri bot token → 401; boshqa sinf → 403
    assert client.get(
        f"/api/internal/materials/{text['id']}", params={"telegram_id": 777601}, headers=_h()
    ).status_code == 404
    assert client.get(
        f"/api/internal/materials/{pdf['id']}", params={"telegram_id": 777601}, headers=_h("xato")
    ).status_code == 401
    client.post(
        "/api/internal/pupils", json={"telegram_id": 777602, "first_name": "Boshqa"}, headers=_h()
    )
    client.post("/api/internal/pupil/grade", json={"telegram_id": 777602, "grade_id": 6}, headers=_h())
    assert client.get(
        f"/api/internal/materials/{pdf['id']}", params={"telegram_id": 777602}, headers=_h()
    ).status_code == 403
