"""
Community chat: one room per grade + the school-wide e'lonxona.

The rules being proven here are the ones a teacher will actually be judged on:
  * a first-grader never sees an eleventh-grader's conversation (and cannot post
    into that room);
  * the e'lonxona is write-restricted to the admin but readable by everyone;
  * nothing is silently swallowed — with the approval queue on, the author sees
    their own message marked "tekshiruvda", and a rejection carries the reason;
  * an admin can delete a message that is already out (the no-filter mode).
"""
from __future__ import annotations

from fastapi.testclient import TestClient

from app.config import get_settings
from tests.conftest import login_as, pick_grade

ADMIN_ID = 999000111  # conftest's ADMIN_TELEGRAM_IDS


def pupil(client: TestClient, tg_id: int, name: str, grade: str) -> dict:
    """A logged-in pupil of a chosen grade (grade names are '1-sinf' .. '11-sinf')."""
    headers = login_as(client, {"id": tg_id, "first_name": name})
    pick_grade(client, headers, grade)
    return headers


def admin(client: TestClient) -> dict:
    return login_as(client, {"id": ADMIN_ID, "first_name": "Malaka oqituvchi"})


def post(client: TestClient, headers: dict, text: str, **params):
    return client.post("/api/chat/messages", json={"text": text, **params}, headers=headers)


def feed(client: TestClient, headers: dict, **params) -> list[dict]:
    resp = client.get("/api/chat/messages", params=params, headers=headers)
    assert resp.status_code == 200, resp.text
    return resp.json()["messages"]


def texts(rows: list[dict]) -> list[str]:
    return [r["text"] for r in rows]


# ------------------------------------------------------------------
# rooms
# ------------------------------------------------------------------
def test_pupil_gets_own_grade_room_plus_the_news_channel(client: TestClient):
    auth = pupil(client, 772000101, "Gulnora", "3-sinf")
    rooms = client.get("/api/chat/rooms", headers=auth).json()
    assert [(r["kind"], r["grade_id"]) for r in rooms] and len(rooms) == 2
    news, grade_room = rooms[0], rooms[1]
    assert news["kind"] == "news" and news["name"] == "E'lonxona"
    assert news["can_post"] is False, "pupils read the announcement channel, they do not write it"
    assert grade_room["kind"] == "grade" and grade_room["is_current_grade"] is True
    assert grade_room["name"] == "3-sinf"


def test_admin_rooms_cover_every_grade(client: TestClient):
    rooms = client.get("/api/chat/rooms", headers=admin(client)).json()
    grades = [r for r in rooms if r["kind"] == "grade"]
    assert len(grades) == 11, "the admin must be able to reach every class"
    assert rooms[0]["kind"] == "news" and rooms[0]["can_post"] is True


def test_pupil_without_a_grade_sees_only_the_announcements(client: TestClient):
    auth = login_as(client, {"id": 772000102, "first_name": "Sinfansiz"})
    rooms = client.get("/api/chat/rooms", headers=auth).json()
    assert [r["kind"] for r in rooms] == ["news"]


# ------------------------------------------------------------------
# reading / writing a grade room
# ------------------------------------------------------------------
def test_own_room_writes_and_reads_back(client: TestClient):
    a = pupil(client, 772000103, "Aziza", "6-sinf")
    b = pupil(client, 772000104, "Bekzod", "6-sinf")

    resp = post(client, a, "Assalomu alaykum, 6-sinf!")
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["message_uz"] == "Yuborildi ✅" and body["premoderation"] is False
    assert body["message"]["status"] == "approved"
    assert body["message"]["is_me"] is True
    assert body["message"]["author_name"] == "Aziza"

    rows = feed(client, b, kind="grade")
    assert "Assalomu alaykum, 6-sinf!" in texts(rows)
    mine = next(r for r in rows if r["text"].startswith("Assalomu"))
    assert mine["is_me"] is False and mine["author_name"] == "Aziza"
    assert "telegram_id" not in mine, "a chat message never leaks another pupil's id"


def test_other_grade_room_is_closed_to_a_pupil(client: TestClient):
    fifth = pupil(client, 772000105, "Feruza", "5-sinf")
    fifth_room = next(
        r["grade_id"]
        for r in client.get("/api/chat/rooms", headers=fifth).json()
        if r["kind"] == "grade"
    )
    post(client, fifth, "5-sinf uchun maxfiy xabar")

    eighth = pupil(client, 772000106, "Elyor", "8-sinf")
    denied = client.get(
        "/api/chat/messages", params={"kind": "grade", "grade_id": fifth_room}, headers=eighth
    )
    assert denied.status_code == 403 and denied.json()["detail"]["error"] == "wrong_grade"
    # and their own room simply does not contain the other class's message
    assert "5-sinf uchun maxfiy xabar" not in texts(feed(client, eighth, kind="grade"))

    nope = post(client, eighth, "5-sinfga sizqirib kiraman", grade_id=fifth_room)
    assert nope.status_code == 403 and nope.json()["detail"]["error"] == "wrong_grade"


def test_an_admin_writes_the_news_channel_and_pupils_read_it(client: TestClient):
    teacher = admin(client)
    resp = post(client, teacher, "Ertaga dars 8:30 da boshlanadi.", kind="news")
    assert resp.status_code == 201, resp.text
    rows = feed(client, pupil(client, 772000107, "Nodira", "2-sinf"), kind="news")
    assert "Ertaga dars 8:30 da boshlanadi." in texts(rows)
    assert rows[-1]["grade_name"] is None, "news is not tied to a grade"


def test_a_pupil_cannot_write_the_news_channel(client: TestClient):
    resp = post(client, pupil(client, 772000108, "Otabek", "4-sinf"), "Men ham yozaman", kind="news")
    assert resp.status_code == 403
    assert resp.json()["detail"]["error"] == "news_admin_only"


def test_pupils_need_a_grade_before_using_a_room(client: TestClient):
    auth = login_as(client, {"id": 772000109, "first_name": "SinfTanlamagan"})
    read = client.get("/api/chat/messages", params={"kind": "grade"}, headers=auth)
    assert read.status_code == 409 and read.json()["detail"]["error"] == "grade_not_selected"
    write = post(client, auth, "Salom")
    assert write.status_code == 409


# ------------------------------------------------------------------
# message shape + flood guard
# ------------------------------------------------------------------
def test_message_length_and_shape_are_checked(client: TestClient):
    auth = pupil(client, 772000110, "Zilola", "7-sinf")
    short = post(client, auth, " a ")
    assert short.status_code == 422 and short.json()["detail"]["error"] == "text_too_short"

    long = post(client, auth, "a" * 600)
    assert long.status_code == 422 and long.json()["detail"]["error"] == "text_too_long"

    many_lines = post(client, auth, "1\n2\n3\n4\n5")
    assert many_lines.status_code == 422
    assert many_lines.json()["detail"]["error"] == "too_many_lines"


def test_room_address_is_validated(client: TestClient):
    auth = pupil(client, 772000111, "Shahzoda", "9-sinf")
    bad = client.get("/api/chat/messages", params={"kind": "corridor"}, headers=auth)
    assert bad.status_code == 422 and bad.json()["detail"]["error"] == "bad_room"
    ghost = client.get(
        "/api/chat/messages", params={"kind": "grade", "grade_id": 99999}, headers=auth
    )
    assert ghost.status_code == 404 and ghost.json()["detail"]["error"] == "room_not_found"


def test_flooding_is_stopped_without_losing_the_first_messages(client: TestClient, monkeypatch):
    monkeypatch.setattr(get_settings(), "CHAT_RATE_LIMIT", 3)
    monkeypatch.setattr(get_settings(), "CHAT_RATE_WINDOW_SECONDS", 60)
    auth = pupil(client, 772000112, "Tezyozuvchi", "10-sinf")
    for n in range(3):
        assert post(client, auth, f"Salom {n}").status_code == 201
    blocked = post(client, auth, "to‘rtinchi xabar")
    assert blocked.status_code == 429
    assert blocked.json()["detail"]["error"] == "chat_flood"
    assert blocked.headers["retry-after"] == "60"


# ------------------------------------------------------------------
# polling
# ------------------------------------------------------------------
def test_polling_returns_only_newer_messages(client: TestClient):
    a = pupil(client, 772000113, "Dilnoza", "1-sinf")
    b = pupil(client, 772000114, "Sardor", "1-sinf")
    first = post(client, a, "Birinchi xabar").json()["message"]
    page = feed(client, b, kind="grade")
    latest = max(r["id"] for r in page)
    post(client, b, "Ikkinchi xabar")

    newer = client.get(
        "/api/chat/messages", params={"kind": "grade", "after_id": latest}, headers=b
    ).json()
    assert "Ikkinchi xabar" in texts(newer["messages"]), "a poll returns what arrived"
    assert "Birinchi xabar" not in texts(newer["messages"]), "…and nothing the client has already"
    assert newer["latest_id"] == max(r["id"] for r in page + newer["messages"])
    assert first["kind"] == "grade"


# ------------------------------------------------------------------
# moderation: the approval queue (CHAT_PREMODERATION)
# ------------------------------------------------------------------
def test_approval_queue_hides_a_message_until_the_admin_approves(client: TestClient, monkeypatch):
    monkeypatch.setattr(get_settings(), "CHAT_PREMODERATION", True)
    a = pupil(client, 772000115, "Kamola", "11-sinf")
    b = pupil(client, 772000116, "Jasur", "11-sinf")

    sent = post(client, a, "Tekshiruvdan o‘tadigan xabar").json()
    assert sent["premoderation"] is True
    assert "tekshiruviga yuborildi" in sent["message_uz"]
    assert sent["message"]["status"] == "pending"

    # the author sees it (marked), their classmate does not
    own = feed(client, a, kind="grade")
    assert "Tekshiruvdan o‘tadigan xabar" in texts(own)
    assert next(r for r in own if r["text"].startswith("Tekshiruvdan"))["status"] == "pending"
    assert "Tekshiruvdan o‘tadigan xabar" not in texts(feed(client, b, kind="grade"))

    teacher = admin(client)
    queue = client.get("/api/chat/admin/pending", headers=teacher).json()
    assert queue["premoderation"] is True and queue["count"] >= 1
    item = next(i for i in queue["items"] if i["text"].startswith("Tekshiruvdan"))
    assert item["author_name"] == "Kamola" and item["grade_name"] == "11-sinf"

    ok = client.post(f"/api/chat/admin/{item['id']}/approve", headers=teacher)
    assert ok.status_code == 200 and ok.json()["status"] == "approved"
    assert "Tekshiruvdan o‘tadigan xabar" in texts(feed(client, b, kind="grade"))
    after = client.get("/api/chat/admin/pending", headers=teacher).json()
    assert item["id"] not in [i["id"] for i in after["items"]], "approved leaves the queue"
    assert after["count"] == len(after["items"]), "the badge and the list always agree"


def test_rejection_returns_the_reason_to_its_author_only(client: TestClient, monkeypatch):
    monkeypatch.setattr(get_settings(), "CHAT_PREMODERATION", True)
    a = pupil(client, 772000117, "Malika", "1-sinf")
    b = pupil(client, 772000118, "Yusuf", "1-sinf")
    msg_id = post(client, a, "Yomon so‘z bilan yozilgan xabar").json()["message"]["id"]

    teacher = admin(client)
    no_reason = client.post(
        f"/api/chat/admin/{msg_id}/reject", json={}, headers=teacher
    )
    assert no_reason.status_code == 422
    assert no_reason.json()["detail"]["error"] == "reason_required"

    rejected = client.post(
        f"/api/chat/admin/{msg_id}/reject",
        json={"reason":  "  Do‘stona yozing  "},
        headers=teacher,
    )
    assert rejected.json()["status"] == "rejected"

    mine = next(r for r in feed(client, a, kind="grade") if r["id"] == msg_id)
    assert mine["status"] == "rejected"
    assert mine["reject_reason"] == "Do‘stona yozing", "the whitespace is trimmed for the author"
    theirs = [r for r in feed(client, b, kind="grade") if r["id"] == msg_id]
    assert theirs == [], "a rejected message is invisible to everyone but its author"


def test_admin_deletes_a_live_message_in_the_no_filter_mode(client: TestClient):
    a = pupil(client, 772000119, "Zarina", "2-sinf")
    b = pupil(client, 772000120, "Oysha", "2-sinf")
    msg_id = post(client, a, "O‘chiriladigan xabar").json()["message"]["id"]
    assert "O‘chiriladigan xabar" in texts(feed(client, b, kind="grade"))

    teacher = admin(client)
    assert client.delete(f"/api/chat/admin/{msg_id}", headers=teacher).json()["status"] == "deleted"
    assert "O‘chiriladigan xabar" not in texts(feed(client, b, kind="grade"))
    assert "O‘chiriladigan xabar" not in texts(feed(client, a, kind="grade"))


def test_moderation_is_admin_only(client: TestClient):
    auth = pupil(client, 772000121, "Bahodir", "3-sinf")
    queue = client.get("/api/chat/admin/pending", headers=auth)
    assert queue.status_code == 403 and queue.json()["detail"]["error"] == "not_admin"
    msg_id = post(client, auth, "O‘zimni o‘chira olmayman").json()["message"]["id"]
    assert client.delete(f"/api/chat/admin/{msg_id}", headers=auth).status_code == 403
    assert client.post(f"/api/chat/admin/{msg_id}/approve", headers=auth).status_code == 403


def test_unknown_message_and_decision_are_reported(client: TestClient):
    teacher = admin(client)
    gone = client.post("/api/chat/admin/99999999/approve", headers=teacher)
    assert gone.status_code == 404 and gone.json()["detail"]["error"] == "message_not_found"


# ------------------------------------------------------------------
# the two halves of the feature meet: a chat line shows a face
# ------------------------------------------------------------------
def test_chat_shows_the_author_avatar(client: TestClient):
    auth = pupil(client, 772000122, "Rasmli", "4-sinf")
    from tests.test_avatars import jpeg_with_exif

    url = client.post(
        "/api/me/avatar", headers=auth, files={"file": ("r.jpg", jpeg_with_exif(), "image/jpeg")}
    ).json()["avatar_url"]
    post(client, auth, "Rasmim bilan ko‘rinadigan xabar")

    row = next(r for r in feed(client, auth, kind="grade") if r["text"].startswith("Rasmim"))
    assert row["avatar_url"] == url
    assert client.get(url).status_code == 200, "the URL in the chat really loads"

    # a pupil with no picture gets None, and the Mini App draws initials
    plain = pupil(client, 772000123, "Rassiz", "4-sinf")
    post(client, plain, "Menda rasm yo‘q")
    row2 = next(r for r in feed(client, plain, kind="grade") if r["text"] == "Menda rasm yo‘q")
    assert row2["is_me"] is True and row2["avatar_url"] is None
