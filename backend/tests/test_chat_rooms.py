"""
Chat rooms the pupils themselves create — the "+" button.

The teacher's words were: "hammasi chat ochish tugmasi bilan amalga oshadi, rasm
nomi bio qoyadi odam qoshadi, o'qituvchilar uchun alohida chat". So the promises
proven here are exactly those, plus the two that keep children safe:

  * a group chat has a name, a bio, a picture and people, and ANY pupil may
    open, read, write and join one (the school chose "barcha ochiq");
  * the teachers' room exists, but a pupil cannot see it, read it or write it —
    a teacher is a person who typed the school's secret code once;
  * a message may carry one file: a picture or a GIF (stored, cleaned) or a
    video (relayed to Telegram, only its file_id stored).

Class rooms keep the old rule: a pupil never reads another class's room.
"""
from __future__ import annotations

import io
import os

import pytest
from fastapi.testclient import TestClient
from PIL import Image, ImageDraw
from sqlalchemy import select

from app import chat as chat_rules
from app.config import get_settings
from app.db import SessionLocal
from app.models import ChatMedia, ChatMessage, User
from tests.test_chat import admin, pupil, texts

ATTACH_URL = "/api/chat/messages/attach"
GROUP = "group"
TEACHER_CODE = "MALAKA2026"


# ------------------------------------------------------------------
# fixtures + helpers
# ------------------------------------------------------------------
@pytest.fixture(autouse=True)
def _clean_trial_guard():
    """The teacher-code throttle is process state: never leak it between tests."""
    chat_rules.reset_teacher_trial_guards()
    yield
    chat_rules.reset_teacher_trial_guards()


def jpeg_photo(size: tuple[int, int] = (900, 600)) -> bytes:
    """A phone-sized photo carrying EXIF make/model + a GPS tag."""
    img = Image.new("RGB", size, (40, 110, 190))
    exif = Image.Exif()
    exif[271] = "NOKIA"
    exif[272] = "XpressMusic"
    exif.get_ifd(0x8825)[1] = "N"
    buf = io.BytesIO()
    img.save(buf, format="JPEG", exif=exif.tobytes())
    return buf.getvalue()


def animated_gif() -> bytes:
    """Three real frames — the test below checks they are not flattened.

    The frames are drawn in RGB and saved straight to GIF: three flat palette
    indexes collapse into one frame, and a "GIF" with one frame would prove
    nothing about keeping animation alive.
    """
    frames = []
    for colour in ((240, 40, 40), (40, 200, 90), (40, 90, 240)):
        img = Image.new("RGB", (140, 100), (250, 250, 250))
        ImageDraw.Draw(img).rectangle([15, 15, 70, 70], fill=colour)
        frames.append(img)
    buf = io.BytesIO()
    frames[0].save(
        buf, format="GIF", save_all=True, append_images=frames[1:], duration=120, loop=0
    )
    return buf.getvalue()


def open_room(client: TestClient, headers: dict, **body) -> dict:
    resp = client.post("/api/chat/rooms", json=body, headers=headers)
    assert resp.status_code == 201, resp.text
    return resp.json()["room"]


def say(client: TestClient, headers: dict, text: str, room_id: int | None = None, **legacy):
    body: dict = {"text": text}
    if room_id is not None:
        body["room_id"] = room_id
    body.update(legacy)
    return client.post("/api/chat/messages", json=body, headers=headers)


def post_file(client: TestClient, headers: dict, *, name: str, mime: str,
              data: dict | None = None, raw: bytes | None = None):
    return client.post(
        ATTACH_URL,
        data={k: str(v) for k, v in (data or {}).items()},
        files={"file": (name, raw if raw is not None else file_for(name), mime)},
        headers=headers,
    )


def file_for(name: str) -> bytes:
    if name.endswith(".gif"):
        return animated_gif()
    if name.endswith((".mp4", ".mov", ".webm")):
        return b"\x00\x00\x00\x18ftypmp42" * 300
    return jpeg_photo()


def page(client: TestClient, headers: dict, room_id: int) -> dict:
    resp = client.get("/api/chat/messages", params={"room_id": room_id}, headers=headers)
    assert resp.status_code == 200, resp.text
    return resp.json()


def find_person(client: TestClient, headers: dict, name: str) -> dict:
    """One exact row of the "add people" list (the search is a substring match)."""
    rows = client.get("/api/chat/people", params={"q": name}, headers=headers).json()["people"]
    return next(p for p in rows if p["name"] == name)


def class_room(client: TestClient, headers: dict) -> dict:
    return next(r for r in client.get("/api/chat/rooms", headers=headers).json()
                if r["kind"] == "grade")


def grade_id_of(client: TestClient, headers: dict, name: str) -> int:
    return next(g["id"] for g in client.get("/api/grades", headers=headers).json()
                if g["name"] == name)


# ------------------------------------------------------------------
# the "+" button: name, bio, icon, picture, people
# ------------------------------------------------------------------
def test_the_plus_button_opens_a_chat_with_name_bio_and_icon(client: TestClient):
    owner = pupil(client, 772100001, "Gulbahor", "5-sinf")
    room = open_room(
        client, owner, name="  Matematika   to‘garagi  ", bio="Chorshanba, 15:00", emoji="🧮"
    )
    assert room["kind"] == GROUP and room["grade_id"] is None
    assert room["name"] == "Matematika to‘garagi", "blank runs are squashed"
    assert room["bio"] == "Chorshanba, 15:00" and room["emoji"] == "🧮"
    assert room["is_mine"] is True and room["owner_name"] == "Gulbahor"
    assert room["can_post"] is True and room["can_read"] is True
    assert room["member_count"] == 1, "whoever opened it is already in it"
    assert room["is_closed"] is False and room["avatar_url"] is None

    listed = client.get("/api/chat/rooms", headers=owner).json()
    assert [r["id"] for r in listed if r["kind"] == GROUP] == [room["id"]]
    assert listed[0]["kind"] == "news", "the e'lonxona stays on top for a pupil"


def test_a_group_chat_is_open_to_the_whole_school(client: TestClient):
    owner = pupil(client, 772100002, "Sarvar", "8-sinf")
    visitor = pupil(client, 772100003, "Madina", "3-sinf")
    room = open_room(client, owner, name="Futbol klubi")

    assert say(client, owner, "Kimda qo‘l to‘p bor?", room["id"]).status_code == 201
    body = page(client, visitor, room["id"])
    assert texts(body["messages"]) == ["Kimda qo‘l to‘p bor?"]
    assert body["room_id"] == room["id"] and body["kind"] == GROUP
    # the school chose "barcha ochiq": a 3-sinf pupil writes into an 8-sinf chat…
    assert say(client, visitor, "Menda bor!", room["id"]).status_code == 201
    # …but still cannot open another class's OWN room
    blocked = client.get(
        "/api/chat/messages",
        params={"kind": "grade", "grade_id": grade_id_of(client, owner, "8-sinf")},
        headers=visitor,
    )
    assert blocked.status_code == 403 and blocked.json()["detail"]["error"] == "wrong_grade"


def test_a_room_name_is_validated_with_an_uzbek_line(client: TestClient):
    owner = pupil(client, 772100004, "NomSinovchi", "6-sinf")
    short = client.post("/api/chat/rooms", json={"name": "ab"}, headers=owner)
    assert short.status_code == 422 and short.json()["detail"]["error"] == "name_too_short"
    long = client.post("/api/chat/rooms", json={"name": "n" * 60}, headers=owner)
    assert long.json()["detail"]["error"] == "name_too_long"
    # A tab/newline is ordinary whitespace and gets squashed into one space;
    # \x01 is invisible and never is, so it is the character that must be refused.
    control = client.post("/api/chat/rooms", json={"name": "Sinf\x01chat"}, headers=owner)
    assert control.json()["detail"]["error"] == "name_bad_chars"
    bio = client.post("/api/chat/rooms", json={"name": "To‘g‘ri nom", "bio": "b" * 300}, headers=owner)
    assert bio.json()["detail"]["error"] == "bio_too_long"
    icon = client.post("/api/chat/rooms", json={"name": "Yana bir", "emoji": "🧮" * 9}, headers=owner)
    assert icon.json()["detail"]["error"] == "emoji_too_long"


def test_only_the_owner_or_staff_can_change_a_chat(client: TestClient):
    owner = pupil(client, 772100005, "Egasi", "9-sinf")
    member = pupil(client, 772100006, "A'zos", "9-sinf")
    room = open_room(client, owner, name="Kimyo halqasi")

    added = client.post(
        f"/api/chat/rooms/{room['id']}/members",
        json={"user_id": find_person(client, owner, "A'zos")["id"]},
        headers=owner,
    )
    assert added.status_code == 200, added.text
    assert [m["role"] for m in added.json()] == ["owner", "member"], "the owner leads the list"

    hijack = client.patch(f"/api/chat/rooms/{room['id']}", json={"name": "Meningkim"}, headers=member)
    assert hijack.status_code == 403 and hijack.json()["detail"]["error"] == "not_owner"

    renamed = client.patch(
        f"/api/chat/rooms/{room['id']}", json={"name": "Kimyo to‘garagi", "bio": "Yangi"}, headers=owner
    )
    assert renamed.status_code == 200, renamed.text
    assert renamed.json()["room"]["name"] == "Kimyo to‘garagi"
    assert renamed.json()["room"]["bio"] == "Yangi"

    closed = client.patch(f"/api/chat/rooms/{room['id']}", json={"is_closed": True}, headers=owner)
    assert closed.json()["room"]["is_closed"] is True
    after = say(client, member, "Yopiq xonaga yozaman", room["id"])
    assert after.status_code == 403 and after.json()["detail"]["error"] == "room_closed"

    # closing is a grown-up decision too: a member may not do it
    assert client.patch(
        f"/api/chat/rooms/{room['id']}", json={"is_closed": False}, headers=member
    ).status_code == 403
    boss = admin(client)
    assert client.patch(
        f"/api/chat/rooms/{room['id']}", json={"is_closed": False}, headers=boss
    ).json()["room"]["is_closed"] is False


def test_the_owner_sets_a_picture_and_it_loads_without_a_token(client: TestClient):
    owner = pupil(client, 772100007, "Rasmqoy", "2-sinf")
    room = open_room(client, owner, name="Kitobxonalar")

    resp = client.post(
        f"/api/chat/rooms/{room['id']}/picture",
        headers=owner,
        files={"file": ("group.jpg", jpeg_photo(), "image/jpeg")},
    )
    assert resp.status_code == 200, resp.text
    picture = resp.json()["room"]["avatar_url"]
    assert picture.startswith(f"/api/chat/rooms/{room['id']}/picture/")

    got = client.get(picture)  # no Authorization: an <img> tag cannot send one
    assert got.status_code == 200 and got.headers["content-type"].startswith("image/")
    stored = Image.open(io.BytesIO(got.content))
    assert stored.size == (256, 256), "a room picture follows the profile rules"
    assert stored.getexif().get(271) is None, "no camera make and no GPS in it"

    listed = next(r for r in client.get("/api/chat/rooms", headers=owner).json()
                  if r["id"] == room["id"])
    assert listed["avatar_url"] == picture

    second = client.post(
        f"/api/chat/rooms/{room['id']}/picture",
        headers=owner,
        files={"file": ("again.jpg", jpeg_photo((500, 500)), "image/jpeg")},
    ).json()["room"]["avatar_url"]
    assert second != picture
    assert client.get(picture).status_code == 404, "the old link must die"

    removed = client.delete(f"/api/chat/rooms/{room['id']}/picture", headers=owner)
    assert removed.json()["room"]["avatar_url"] is None
    assert client.get(second).status_code == 404

    # a stranger may not paint over somebody else's chat
    other = pupil(client, 772100008, "Begma", "2-sinf")
    refuse = client.post(
        f"/api/chat/rooms/{room['id']}/picture",
        headers=other,
        files={"file": ("x.jpg", jpeg_photo(), "image/jpeg")},
    )
    assert refuse.status_code == 403
    # and a "photo" that is not a photo is refused with a usable line
    bad = client.post(
        f"/api/chat/rooms/{room['id']}/picture",
        headers=owner,
        files={"file": ("hat.pdf", b"%PDF-1.4", "application/pdf")},
    )
    assert bad.status_code == 422 and bad.json()["detail"]["error"] == "picture_rejected"


def test_the_people_list_shows_a_name_a_class_and_nothing_else(client: TestClient):
    owner = pupil(client, 772100009, "Qidiruvchi", "10-sinf")
    pupil(client, 772100010, "Doniyor", "10-sinf")
    row = find_person(client, owner, "Doniyor")
    assert row["grade_name"] == "10-sinf" and row["is_me"] is False
    assert row["avatar_url"] is None and row["is_teacher"] is False
    assert "telegram_id" not in row and "username" not in row, "a pupil's number is never listed"
    assert find_person(client, owner, "Qidiruvchi")["is_me"] is True


def test_the_owner_adds_people_a_member_leaves_and_the_owner_is_protected(client: TestClient):
    owner = pupil(client, 772100011, "Mehmondo‘st", "4-sinf")
    guest = pupil(client, 772100012, "Mehmon", "4-sinf")
    stranger = pupil(client, 772100013, "Yovvoyi", "4-sinf")
    room = open_room(client, owner, name="Suzana")
    guest_id = find_person(client, owner, "Mehmon")["id"]

    added = client.post(
        f"/api/chat/rooms/{room['id']}/members", json={"user_id": guest_id}, headers=owner
    )
    assert added.status_code == 200 and [m["role"] for m in added.json()] == ["owner", "member"]

    # a member may not invite others, but may put themselves in with "join"
    invite = client.post(
        f"/api/chat/rooms/{room['id']}/members",
        json={"user_id": find_person(client, owner, "Yovvoyi")["id"]},
        headers=guest,
    )
    assert invite.status_code == 403
    assert client.post(f"/api/chat/rooms/{room['id']}/join", headers=guest).status_code == 200
    assert client.post(f"/api/chat/rooms/{room['id']}/join", headers=guest).status_code == 200, \
        "joining twice is not an error"
    names = [m["name"] for m in client.get(f"/api/chat/rooms/{room['id']}/members", headers=owner).json()]
    assert names[0] == "Mehmondo‘st" and "Mehmon" in names
    # is_me is the app's only honest way to label a row "siz": two pupils can be
    # called Aziz, and a name is not proof of identity.
    members = lambda auth: client.get(f"/api/chat/rooms/{room['id']}/members", headers=auth).json()
    assert [m["name"] for m in members(owner) if m["is_me"]] == ["Mehmondo‘st"]
    assert [m["name"] for m in members(guest) if m["is_me"]] == ["Mehmon"]

    # leaving is allowed, taking the owner out is not
    leave = client.request("DELETE", f"/api/chat/rooms/{room['id']}/members/{guest_id}", headers=guest)
    assert leave.json() == {"ok": True}
    gone = client.request(
        "DELETE", f"/api/chat/rooms/{room['id']}/members/{guest_id}", headers=owner
    )
    assert gone.status_code == 404 and gone.json()["detail"]["error"] == "not_member"
    # …and a stranger is refused before the room is even looked at: they may not
    # manage anybody but themselves.
    nosy = client.request(
        "DELETE", f"/api/chat/rooms/{room['id']}/members/{guest_id}", headers=stranger
    )
    assert nosy.status_code == 403 and nosy.json()["detail"]["error"] == "not_owner"

    owner_id = find_person(client, owner, "Mehmondo‘st")["id"]
    stuck = client.request(
        "DELETE", f"/api/chat/rooms/{room['id']}/members/{owner_id}", headers=stranger
    )
    assert stuck.status_code == 403
    assert stuck.json()["detail"]["error"] == "not_owner"
    let_go = client.request(
        "DELETE", f"/api/chat/rooms/{room['id']}/members/{owner_id}", headers=admin(client)
    )
    assert let_go.json() == {"ok": True}, "only a teacher can let the owner out"


def test_joining_or_adding_people_in_a_system_room_is_not_a_thing(client: TestClient):
    owner = pupil(client, 772100014, "Sinfxon", "1-sinf")
    classmate = pupil(client, 772100016, "Sinfdo‘sim", "1-sinf")
    room_id = class_room(client, owner)["id"]
    join = client.post(f"/api/chat/rooms/{room_id}/join", headers=owner)
    assert join.status_code == 403 and join.json()["detail"]["error"] == "not_group_room"
    add = client.post(
        f"/api/chat/rooms/{room_id}/members",
        json={"user_id": find_person(client, owner, "Sinfdo‘sim")["id"]},
        headers=admin(client),
    )
    assert add.status_code == 403, "an admin still cannot put people into a class room"
    # and a class room's "people" list is the whole grade, not a member table
    assert class_room(client, classmate)["member_count"] == 0


def test_an_unknown_room_id_is_a_404_with_the_usual_shape(client: TestClient):
    owner = pupil(client, 772100015, "Yo‘qol", "1-sinf")
    for resp in (
        client.get("/api/chat/messages", params={"room_id": 987654}, headers=owner),
        client.get("/api/chat/rooms/987654/members", headers=owner),
        say(client, owner, "Salom", 987654),
    ):
        assert resp.status_code == 404
        assert resp.json()["detail"]["error"] == "room_not_found"
        assert resp.json()["detail"]["message_uz"]


# ------------------------------------------------------------------
# the teachers' room + the secret code
# ------------------------------------------------------------------
def test_the_teachers_room_is_invisible_and_unopenable_for_a_pupil(client: TestClient):
    a = pupil(client, 772100020, "Dilnoza", "6-sinf")
    kinds = [r["kind"] for r in client.get("/api/chat/rooms", headers=a).json()]
    assert "staff" not in kinds, "a pupil never sees the staff room in their list"

    boss = admin(client)
    staff_room = next(r for r in client.get("/api/chat/rooms", headers=boss).json()
                      if r["kind"] == "staff")
    assert staff_room["name"] == "O‘qituvchilar xonasi"
    assert staff_room["can_post"] is True and staff_room["can_read"] is True

    read = client.get("/api/chat/messages", params={"room_id": staff_room["id"]}, headers=a)
    assert read.status_code == 403 and read.json()["detail"]["error"] == "staff_only"
    write = say(client, a, "Men ham kiraman", staff_room["id"])
    assert write.status_code == 403 and write.json()["detail"]["error"] == "staff_only"
    people = client.get(f"/api/chat/rooms/{staff_room['id']}/members", headers=a)
    assert people.status_code == 403


def test_a_pupil_becomes_a_teacher_with_the_school_code(client: TestClient, monkeypatch):
    monkeypatch.setattr(get_settings(), "TEACHER_CODE", TEACHER_CODE)
    a = pupil(client, 772100021, "Kodli", "6-sinf")
    before = client.get("/api/me", headers=a).json()
    assert before["is_teacher"] is False and before["can_claim_teacher"] is True

    wrong = client.post("/api/me/teacher-code", json={"code": "bilmayman"}, headers=a)
    assert wrong.status_code == 403
    assert wrong.json()["detail"]["error"] == "wrong_teacher_code"
    assert "bilmayman" not in wrong.text, "a guess is never echoed back"

    ok = client.post("/api/me/teacher-code", json={"code": TEACHER_CODE}, headers=a)
    assert ok.status_code == 200 and ok.json()["is_teacher"] is True, ok.text
    again = client.post("/api/me/teacher-code", json={"code": TEACHER_CODE}, headers=a)
    assert again.status_code == 409 and again.json()["detail"]["error"] == "already_teacher"

    kinds = [r["kind"] for r in client.get("/api/chat/rooms", headers=a).json()]
    assert kinds[0] == "staff", "the teachers' room is now on top of their list"
    assert say(client, a, "Yig‘ilish 9:00 da", kind="staff").status_code == 201
    # a teacher writes the e'lonxona too, and may read every class room
    assert say(client, a, "Ertaga imtihon", kind="news").status_code == 201
    fifth = grade_id_of(client, a, "5-sinf")
    assert client.get(
        "/api/chat/messages", params={"kind": "grade", "grade_id": fifth}, headers=a
    ).status_code == 200


def test_the_teacher_form_hides_itself_when_the_school_set_no_code(client: TestClient, monkeypatch):
    monkeypatch.setattr(get_settings(), "TEACHER_CODE", "")
    a = pupil(client, 772100022, "Kodsiz", "6-sinf")
    assert client.get("/api/me", headers=a).json()["can_claim_teacher"] is False
    resp = client.post("/api/me/teacher-code", json={"code": "harqanday" * 2}, headers=a)
    assert resp.status_code == 403 and resp.json()["detail"]["error"] == "wrong_teacher_code"


def test_a_short_code_is_refused_even_when_it_is_the_right_one(client: TestClient, monkeypatch):
    """The door to the teachers' room needs more than three letters."""
    monkeypatch.setattr(get_settings(), "TEACHER_CODE", "abc")
    a = pupil(client, 772100023, "Qisqa", "6-sinf")
    assert client.get("/api/me", headers=a).json()["can_claim_teacher"] is False
    resp = client.post("/api/me/teacher-code", json={"code": "abc"}, headers=a)
    assert resp.status_code == 403
    assert "staff" not in [r["kind"] for r in client.get("/api/chat/rooms", headers=a).json()]


def test_guessing_the_code_is_limited_per_account(client: TestClient, monkeypatch):
    monkeypatch.setattr(get_settings(), "TEACHER_CODE", TEACHER_CODE)
    a = pupil(client, 772100024, "Yovvoyi", "6-sinf")
    guesses = [
        client.post("/api/me/teacher-code", json={"code": f"taxmin{i:03d}"}, headers=a)
        for i in range(chat_rules.TEACHER_TRIALS_MAX)
    ]
    assert [r.status_code for r in guesses] == [403] * chat_rules.TEACHER_TRIALS_MAX
    blocked = client.post("/api/me/teacher-code", json={"code": TEACHER_CODE}, headers=a)
    assert blocked.status_code == 429
    assert blocked.json()["detail"]["error"] == "too_many_attempts"
    assert int(blocked.headers["retry-after"]) > 0


# ------------------------------------------------------------------
# files in a chat: picture, GIF, video
# ------------------------------------------------------------------
def test_a_pupil_sends_a_picture_and_it_is_cleaned_and_visible(client: TestClient):
    a = pupil(client, 772100030, "Rasmiy", "7-sinf")
    b = pupil(client, 772100031, "Ko‘ruvchi", "7-sinf")
    room = class_room(client, a)

    resp = post_file(client, a, name="masala.jpg", mime="image/jpeg",
                     data={"room_id": room["id"], "text": "Mana yechim"})
    assert resp.status_code == 201, resp.text
    msg = resp.json()["message"]
    media = msg["media"]
    assert msg["kind"] == "grade" and msg["text"] == "Mana yechim"
    assert media["kind"] == "image" and media["url"].startswith("/api/chat/media/")
    assert media["mime"].startswith("image/") and 0 < media["width"] <= 1024
    assert os.environ["BOT_TOKEN"] not in media["url"], "the URL is ours, not Telegram's"

    got = client.get(media["url"])
    assert got.status_code == 200 and got.headers["content-type"].startswith("image/")
    assert Image.open(io.BytesIO(got.content)).getexif().get(271) is None, \
        "no GPS survives into a chat photo"

    rows = page(client, b, room["id"])["messages"]
    assert next(r for r in rows if r["text"] == "Mana yechim")["media"]["url"] == media["url"]

    # a picture with no words is a normal thing a pupil does
    quiet = post_file(client, a, name="silence.jpg", mime="image/jpeg",
                      data={"room_id": room["id"]})
    assert quiet.status_code == 201 and quiet.json()["message"]["text"] == ""


def test_a_gif_keeps_its_animation(client: TestClient):
    a = pupil(client, 772100032, "Animate", "3-sinf")
    room = open_room(client, a, name="Kulgili lahzalar")
    raw = animated_gif()
    resp = client.post(
        ATTACH_URL,
        data={"room_id": str(room["id"]), "text": "Qarang"},
        files={"file": ("lol.gif", raw, "image/gif")},
        headers=a,
    )
    assert resp.status_code == 201, resp.text
    media = resp.json()["message"]["media"]
    assert media["kind"] == "gif" and media["mime"] == "image/gif"
    got = client.get(media["url"])
    assert got.content == raw, "re-encoding would freeze the animation"
    assert Image.open(io.BytesIO(got.content)).n_frames == 3

    # a GIF sent through the "photo" picker (or renamed) is still a GIF
    sneaky = post_file(client, a, name="meme.jpg", mime="image/jpeg",
                       data={"room_id": str(room["id"])}, raw=raw)
    assert sneaky.status_code == 201, sneaky.text
    sneaky_media = sneaky.json()["message"]["media"]
    assert sneaky_media["mime"] == "image/gif", "the bytes decide, not the extension"
    assert client.get(sneaky_media["url"]).content == raw


def test_a_video_goes_to_telegram_and_plays_through_the_backend(client: TestClient, monkeypatch):
    calls: list[dict] = []

    async def fake_relay(raw, *, file_name: str, mime: str, chat_id: int) -> str:
        calls.append({"size": len(raw), "file_name": file_name, "mime": mime, "chat_id": chat_id})
        return "FAKE_VIDEO_FILE_ID"

    monkeypatch.setattr(chat_rules, "send_video_to_telegram", fake_relay)
    monkeypatch.setattr(
        "app.routers.chat._telegram_get_file",
        lambda file_id: {"ok": True, "result": {"file_path": f"videos/{file_id}.mp4"}},
    )
    monkeypatch.setattr(
        "app.routers.chat._telegram_file_stream", lambda path: iter([b"streamed-bytes"])
    )

    a = pupil(client, 772100033, "Suvchi", "5-sinf")
    room = open_room(client, a, name="Tajribalar")
    resp = post_file(client, a, name="siniq.mp4", mime="video/mp4",
                     data={"room_id": room["id"], "text": "Siniq stakan"})
    assert resp.status_code == 201, resp.text
    media = resp.json()["message"]["media"]
    assert media["kind"] == "video" and media["url"].startswith("/api/chat/media/")

    assert len(calls) == 1, "the bytes went to Telegram exactly once"
    assert calls[0]["file_name"] == "siniq.mp4" and calls[0]["mime"] == "video/mp4"
    assert calls[0]["chat_id"] == 772100033, "into the sender's own Telegram"

    slug = media["url"].rsplit("/", 1)[-1]
    with SessionLocal() as db:
        row = db.scalar(select(ChatMedia).where(ChatMedia.slug == slug))
        assert row is not None and row.file_id == "FAKE_VIDEO_FILE_ID"
        assert not row.data, "a video's bytes never land in Postgres"

    got = client.get(media["url"])
    assert got.status_code == 200 and got.content == b"streamed-bytes"
    assert got.headers["content-type"].startswith("video/")
    assert "inline" in got.headers["content-disposition"]
    assert "api.telegram.org" not in got.text
    assert os.environ["BOT_TOKEN"] not in got.text, "the token is not in anything a pupil sees"


def test_a_file_that_is_not_really_a_file_is_refused(client: TestClient):
    a = pupil(client, 772100034, "Aldovchi", "5-sinf")
    room = open_room(client, a, name="Xavfsiz")

    renamed = post_file(client, a, name="rasm.jpg", mime="image/jpeg",
                        data={"room_id": room["id"], "text": "Och bu rasm emas"},
                        raw=b"men rasm emasman - .exe man")
    assert renamed.status_code == 422
    assert renamed.json()["detail"]["error"] == "file_rejected"
    assert renamed.json()["detail"]["message_uz"]

    wrong_type = post_file(client, a, name="hisob.txt", mime="text/plain",
                           data={"room_id": room["id"]})
    assert wrong_type.status_code == 422
    assert wrong_type.json()["detail"]["error"] == "bad_file_type"


def test_an_oversized_picture_is_refused_while_it_is_read(client: TestClient, monkeypatch):
    monkeypatch.setattr(get_settings(), "CHAT_IMAGE_MAX_BYTES", 2000)
    a = pupil(client, 772100035, "Og‘ir", "5-sinf")
    room = open_room(client, a, name="Katta fayllar")
    resp = post_file(client, a, name="katta.jpg", mime="image/jpeg",
                     data={"room_id": room["id"]})
    assert resp.status_code == 413
    detail = resp.json()["detail"]
    assert detail["error"] == "file_too_big"
    assert "KB" in detail["message_uz"], "the cap is named in a size a child understands"


def test_one_day_of_files_is_enough(client: TestClient, monkeypatch):
    monkeypatch.setattr(get_settings(), "CHAT_MEDIA_PER_DAY", 2)
    a = pupil(client, 772100036, "Ko‘pYuboruvchi", "5-sinf")
    room = open_room(client, a, name="Fayl bozori")
    for n in range(2):
        assert post_file(client, a, name=f"r{n}.jpg", mime="image/jpeg",
                         data={"room_id": room["id"]}).status_code == 201
    third = post_file(client, a, name="r3.jpg", mime="image/jpeg", data={"room_id": room["id"]})
    assert third.status_code == 429
    assert third.json()["detail"]["error"] == "media_quota"
    assert int(third.headers["retry-after"]) > 0


# ------------------------------------------------------------------
# the old address keeps working (a cached Mini App build must not break)
# ------------------------------------------------------------------
def test_the_legacy_kind_address_resolves_to_the_same_room(client: TestClient):
    a = pupil(client, 772100040, "EskiBin", "9-sinf")
    room = class_room(client, a)

    legacy = client.get("/api/chat/messages", params={"kind": "grade"}, headers=a).json()
    by_id = page(client, a, room["id"])
    assert legacy["room_id"] == by_id["room_id"] == room["id"]
    assert legacy["kind"] == "grade" and legacy["grade_id"] == room["grade_id"]

    body = say(client, a, "Aloqa", room["id"]).json()["message"]
    assert body["room_id"] == room["id"]
    assert body["kind"] == "grade" and body["grade_id"] == room["grade_id"], \
        "kind/grade are copied from the room, never taken from the client"

    # a client cannot aim a message at a different room by lying about `kind`
    forged = client.post(
        "/api/chat/messages",
        json={"text": "Soxta", "room_id": room["id"], "kind": "news"},
        headers=a,
    )
    assert forged.status_code == 201
    assert forged.json()["message"]["kind"] == "grade"


def test_a_pupils_own_chat_room_is_the_one_their_grade_room_is_not(client: TestClient):
    """A group chat is not a class room: it has no grade, so its messages carry
    none — and the class rooms keep working exactly as before."""
    a = pupil(client, 772100041, "IkkiXona", "9-sinf")
    group = open_room(client, a, name="Musqa")
    sent = say(client, a, "Guruhda yozdim", group["id"]).json()["message"]
    assert sent["grade_id"] is None and sent["kind"] == GROUP
    klass = say(client, a, "Sinfda yozdim").json()["message"]
    assert klass["kind"] == "grade" and klass["grade_id"] == class_room(client, a)["grade_id"]
    assert texts(page(client, a, group["id"])["messages"]) == ["Guruhda yozdim"]
    assert "Guruhda yozdim" not in texts(page(client, a, klass["room_id"])["messages"])


# ------------------------------------------------------------------
# moderation still covers the new rooms
# ------------------------------------------------------------------
def test_the_queue_shows_a_pending_picture_to_the_admin(client: TestClient, monkeypatch):
    monkeypatch.setattr(get_settings(), "CHAT_PREMODERATION", True)
    a = pupil(client, 772100050, "Navbatda", "11-sinf")
    room = open_room(client, a, name="Navbatchilar")
    sent = post_file(client, a, name="kul.jpg", mime="image/jpeg",
                      data={"room_id": room["id"], "text": "Rasm tekshirilsin"})
    assert sent.status_code == 201
    assert sent.json()["message"]["status"] == "pending"
    # the author's classmate sees nothing of it
    other = pupil(client, 772100051, "Sinfdo‘sh", "11-sinf")
    assert "Rasm tekshirilsin" not in texts(page(client, other, room["id"])["messages"])

    boss = admin(client)
    queue = client.get("/api/chat/admin/pending", headers=boss).json()
    item = next(i for i in queue["items"] if i["text"] == "Rasm tekshirilsin")
    assert item["media"] and item["media"]["kind"] == "image"
    assert item["author_name"] == "Navbatda"

    ok = client.post(f"/api/chat/admin/{item['id']}/approve", headers=boss)
    assert ok.json()["status"] == "approved"
    rows = page(client, other, room["id"])["messages"]
    assert next(r for r in rows if r["id"] == item["id"])["media"]["url"] == item["media"]["url"]

    # deleting the message takes its file with it — the link goes dead
    gone = client.delete(f"/api/chat/admin/{item['id']}", headers=boss)
    assert gone.json()["status"] == "deleted"
    assert client.get(item["media"]["url"]).status_code == 404


# ------------------------------------------------------------------
# the deploy window: rows the migration could not have seen
# ------------------------------------------------------------------
def test_a_roomless_message_is_repaired_and_stays_repaired(client: TestClient):
    """A message posted by the OLD build must not disappear from the class chat.

    The migration assigns a room to every row that exists the day it runs — but
    between that moment and the server actually being replaced, the old code is
    still writing messages keyed only by (kind, grade_id), and those land with
    room_id = NULL. The feed reads strictly by room, so such a row is invisible.
    GET /api/chat/rooms is the first call any chat screen makes, so it is where
    the repair belongs; the second call proves it is not doing the work twice.
    """
    a = pupil(client, 772100060, "Migratsiyadan", "6-sinf")
    room = class_room(client, a)
    gid = grade_id_of(client, a, "6-sinf")
    legacy = "E'lon qilingan eski xabar"

    with SessionLocal() as db:
        author = db.scalar(select(User).where(User.first_name == "Migratsiyadan"))
        db.add(
            ChatMessage(
                room_id=None, kind="grade", grade_id=gid,
                user_id=author.id, text=legacy, status="approved",
            )
        )
        db.commit()

    assert legacy not in texts(page(client, a, room["id"])["messages"])

    assert client.get("/api/chat/rooms", headers=a).status_code == 200
    rows = page(client, a, room["id"])["messages"]
    assert legacy in texts(rows), "the roomless message never came back"
    assert next(r for r in rows if r["text"] == legacy)["room_id"] == room["id"]

    with SessionLocal() as db:
        moved = db.scalar(select(ChatMessage).where(ChatMessage.text == legacy))
        assert moved.room_id == room["id"]
        # nothing left to fix: cheap on every later request
        assert chat_rules.backfill_room_ids(db) == 0
