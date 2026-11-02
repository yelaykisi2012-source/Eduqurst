"""
app/chat.py — the community chat rules (rooms, members, files, moderation).

ROOMS (a room is a ROW since the "+" button exists)
---------------------------------------------------
  * kind="grade" — one room per class (1-sinf .. 11-sinf). A pupil reads and
    writes ONLY their own class room, so an 11-sinf conversation never lands in
    front of a first-grader. Staff read them all.
  * kind="news"  — the school-wide e'lonxona. Everybody reads it, only staff
    (a teacher or the admin) writes it.
  * kind="staff" — the teachers' own room. NOT readable and NOT writable for a
    pupil, even though every other room here is open: this is where adults
    discuss the class. A teacher is someone who typed the school's code
    (Settings.TEACHER_CODE) once; the admin is staff automatically.
  * kind="group" — created by anyone with the "+" button: name, bio, picture,
    people. The school chose "all open", so every pupil may read and write any
    group room — which is precisely why staff can always delete a message and
    why the rate limit is global.

MEMBERSHIP
----------
Class/news/staff rooms have no member rows: a class room's people ARE that
grade's pupils, and copying 11 × N rows would go stale the day a pupil moves up.
Group rooms keep real rows — the creator is `owner` (may rename, add people,
set the picture), everyone else who joins or is added is a `member`.

MODERATION — two modes, one env flag
------------------------------------
Switched WITHOUT a code change through CHAT_PREMODERATION in Render:

  * off (the default): a message appears at once, staff delete what is wrong;
  * on: a pupil's message is stored as `pending` and only becomes visible after
    an admin approves it; a rejection carries a reason back to the author.

Either way the author always sees their own pending/rejected messages, so
nothing ever looks silently lost. There is no automatic word filter
(deliberately: keyword filters punish honest mistakes while looking like they
protect, and the pupils are real children known to their teachers).

FILES
-----
A message may carry ONE file (picture, GIF or video) — see app/chat_media.py
for what is accepted and where the bytes live.

`status` values: pending | approved | rejected | deleted.
"""
from __future__ import annotations

import hmac
import re
import time
import unicodedata
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import httpx
from fastapi import HTTPException
from sqlalchemy import case, func, or_, select, update
from sqlalchemy.orm import Session, selectinload

from app import chat_media
from app.avatars import new_slug as new_capability_slug
from app.avatars import normalise as normalise_picture
from app.avatars import public_path
from app.config import TEACHER_CODE_MIN_LENGTH, get_settings
from app.grades import user_grade
from app.models import (
    ChatMedia,
    ChatMember,
    ChatMessage,
    ChatRoom,
    ChatRoomAvatar,
    Grade,
    User,
    UserAvatar,
)

GRADE_ROOM = "grade"
NEWS_ROOM = "news"
STAFF_ROOM = "staff"
GROUP_ROOM = "group"

NEWS_NAME = "E'lonxona"
STAFF_NAME = "O‘qituvchilar xonasi"
ROOM_EMOJI = {GRADE_ROOM: "💬", NEWS_ROOM: "📣", STAFF_ROOM: "🧑‍🏫", GROUP_ROOM: "💬"}

TEXT_MIN = 2
TEXT_MAX = 500            # matches models.ChatMessage.text
MAX_LINES = 4             # a wall of text is not a chat message
PAGE_DEFAULT = 40
PAGE_MAX = 100
ROOM_PAGE_MAX = 100

# Emoji are not one code point each. These three are what makes "one emoji" and
# "one code point" different numbers, and they are why _seen_characters exists.
ZWJ = "\u200d"                                    # welds 👨 + 👩 + 👧 into one picture
SKIN_TONES = re.compile("[\U0001F3FB-\U0001F3FF]")  # the modifier on 👍🏽
COMBINING_CATEGORIES = {"Mn", "Me", "Mc"}          # variation selectors, skin-tone marks

NAME_MIN = 3
NAME_MAX = 48             # matches models.ChatRoom.name
BIO_MAX = 200             # matches models.ChatRoom.bio
MEMBER_PAGE_MAX = 50
PEOPLE_PAGE_MAX = 20

PENDING = "pending"
APPROVED = "approved"
REJECTED = "rejected"
DELETED = "deleted"

ROLE_OWNER = "owner"
ROLE_MEMBER = "member"


class ChatProblem(HTTPException):
    """Structured 4xx with an Uzbek message the Mini App shows as-is."""

    def __init__(self, code: int, error: str, message_uz: str, retry_after: int | None = None):
        detail = {"error": error, "message_uz": message_uz}
        headers = {"Retry-After": str(retry_after)} if retry_after else None
        super().__init__(status_code=code, detail=detail, headers=headers)


@dataclass
class MediaPayload:
    """A validated file, ready to be attached to one message.

    `data` is set for a picture/GIF (bytes live in Postgres); `file_id` is set
    for a video (the bytes live in Telegram, the file_id is all we store).
    """

    kind: str
    mime: str
    size_bytes: int
    width: int | None = None
    height: int | None = None
    data: bytes | None = None
    file_id: str | None = None
    file_name: str | None = None


def premoderation_enabled() -> bool:
    """True = every new pupil message waits for an admin (CHAT_PREMODERATION=1)."""
    return get_settings().CHAT_PREMODERATION


def _seen_characters(text: str) -> list[str]:
    """The characters a pupil actually SEES, one per emoji.

    "❤️" is a heart plus a variation selector, "👍🏽" is a thumb plus a skin tone,
    "👨‍👩‍👧" is three people welded by zero-width joiners. Each is one tap on the
    emoji strip but two or three code points in the database, so raw `len()` is
    the wrong thing to measure a message by.
    """
    seen = []
    for ch in text:
        if ch == ZWJ or SKIN_TONES.match(ch):
            continue
        if unicodedata.combining(ch) or unicodedata.category(ch) in COMBINING_CATEGORIES:
            continue
        seen.append(ch)
    return seen


def is_single_emoji(text: str) -> bool:
    """True for a message that is exactly one emoji and nothing else ("👍")."""
    seen = _seen_characters(text)
    return len(seen) == 1 and unicodedata.category(seen[0]) == "So"


def clean_text(raw: str, *, allow_empty: bool = False) -> str:
    """Trim, squash blank lines, enforce length — or raise with a clear reason.

    `allow_empty` is only ever set by a message that carries a file: "a picture
    with no words" is a normal thing a pupil does, while a room full of empty
    text messages is not.

    The floor is TEXT_MIN *seen* characters, with one exception: a lone emoji.
    " a " is a slip of a finger, "👍" is a reaction — and the Mini App puts
    twenty-four of them one tap away from the send button, so refusing them
    would ship a button that always fails.
    """
    text = (raw or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    text = re.sub(r"\n{3,}", "\n\n", text)
    if not text:
        if allow_empty:
            return ""
        raise ChatProblem(
            422, "text_too_short", f"Xabarni kamida {TEXT_MIN} belgi qilib yozing."
        )
    if len(_seen_characters(text)) < TEXT_MIN and not is_single_emoji(text):
        raise ChatProblem(
            422, "text_too_short", f"Xabarni kamida {TEXT_MIN} belgi qilib yozing."
        )
    if len(text) > TEXT_MAX:
        raise ChatProblem(
            422,
            "text_too_long",
            f"Xabar juda uzun — {TEXT_MAX} belgidan oshmasin ({len(text)}).",
        )
    if text.count("\n") + 1 > MAX_LINES:
        raise ChatProblem(422, "too_many_lines", f"Xabarda ko‘pi bilan {MAX_LINES} qator bo‘lsin.")
    return text


def clean_room_name(raw: str) -> str:
    name = re.sub(r"\s+", " ", (raw or "").strip())
    if len(name) < NAME_MIN:
        raise ChatProblem(422, "name_too_short", f"Chat nomini kamida {NAME_MIN} belgi qiling.")
    if len(name) > NAME_MAX:
        raise ChatProblem(422, "name_too_long", f"Chat nomi {NAME_MAX} belgidan oshmasin.")
    # Control characters would let a room look like another one ("Sinf  chat").
    if any(ord(ch) < 32 for ch in name):
        raise ChatProblem(422, "name_bad_chars", "Chat nomida maxsus belgilar bo‘lmasin.")
    return name


def clean_room_bio(raw: str | None) -> str | None:
    bio = re.sub(r"\s+", " ", (raw or "").strip())
    if not bio:
        return None
    if len(bio) > BIO_MAX:
        raise ChatProblem(422, "bio_too_long", f"Tavsif {BIO_MAX} belgidan oshmasin.")
    return bio


def clean_room_emoji(raw: str | None) -> str:
    emoji = (raw or "").strip() or "💬"
    if len(emoji) > 8:
        raise ChatProblem(422, "emoji_too_long", "Bitta belgi tanlang (ikonka).")
    return emoji


# ----------------------------------------------------------------------
# Rooms
# ----------------------------------------------------------------------

def _insert_room(db: Session, kind: str, grade_id: int | None, name: str) -> ChatRoom:
    """Create one system room (grade/news/staff). Never a group room."""
    room = ChatRoom(kind=kind, grade_id=grade_id, name=name, emoji=ROOM_EMOJI.get(kind, "💬"))
    db.add(room)
    db.commit()
    db.refresh(room)
    return room


def room_for_pair(db: Session, kind: str, grade_id: int | None) -> ChatRoom | None:
    if grade_id is None:
        return db.scalar(
            select(ChatRoom).where(ChatRoom.kind == kind, ChatRoom.grade_id.is_(None))
        )
    return db.scalar(
        select(ChatRoom).where(ChatRoom.kind == kind, ChatRoom.grade_id == grade_id)
    )


def ensure_system_rooms(db: Session) -> None:
    """Create the rooms the school always has, if the migration did not.

    Needed because the test suite (and any fresh install) builds tables with
    `create_all`, which runs no data step. Cheap and idempotent: it compares the
    pairs that already exist and only inserts what is missing.
    """
    existing = {
        (kind, grade_id)
        for kind, grade_id in db.execute(select(ChatRoom.kind, ChatRoom.grade_id)).all()
    }
    if (NEWS_ROOM, None) not in existing:
        _insert_room(db, NEWS_ROOM, None, NEWS_NAME)
    if (STAFF_ROOM, None) not in existing:
        _insert_room(db, STAFF_ROOM, None, STAFF_NAME)
    for grade in db.scalars(select(Grade).order_by(Grade.order_index)).all():
        if (GRADE_ROOM, grade.id) not in existing:
            _insert_room(db, GRADE_ROOM, grade.id, grade.name)


def backfill_room_ids(db: Session) -> int:
    """Give a room to the messages that were posted without one.

    The migration assigned a room to every row that existed the day it ran. But
    a server still running the OLD build keeps inserting messages addressed only
    by (kind, grade_id), and those land with room_id = NULL — invisible to the
    new feeds, which read by room. Runs after ensure_system_rooms, so the room a
    row needs is normally already there. Returns how many rows were repaired
    (always 0 in the steady state, so this is not work done on every request).
    """
    pairs = db.execute(
        select(ChatMessage.kind, ChatMessage.grade_id)
        .where(ChatMessage.room_id.is_(None))
        .distinct()
    ).all()
    fixed = 0
    for kind, grade_id in pairs:
        room = room_for_pair(db, kind, grade_id)
        if room is None:
            # A class deleted since then: leave the row alone rather than invent
            # a room name nobody asked for. It stays out of the feeds, as before.
            continue
        clause = (
            ChatMessage.grade_id.is_(None)
            if grade_id is None
            else ChatMessage.grade_id == grade_id
        )
        fixed += (
            db.execute(
                update(ChatMessage)
                .where(ChatMessage.room_id.is_(None), ChatMessage.kind == kind, clause)
                .values(room_id=room.id)
            )
            .rowcount
        )
    if fixed:
        db.commit()
    return fixed


def resolve_room(
    db: Session,
    *,
    room_id: int | None = None,
    kind: str | None = None,
    grade_id: int | None = None,
    user: User | None = None,
) -> ChatRoom:
    """Find the room a request means, from the new id or the old address.

    The old (kind, grade_id) address still works — a Mini App build already open
    on a pupil's phone must not break on the day the server changes. `kind="grade"`
    without a grade_id means MY class room, which is what the app always sent.
    """
    if room_id is not None:
        room = db.get(ChatRoom, room_id)
        if room is None:
            raise ChatProblem(404, "room_not_found", "Bunday chat xonasi topilmadi.")
        return room

    kind = (kind or GRADE_ROOM).strip().lower()
    if kind not in {GRADE_ROOM, NEWS_ROOM, STAFF_ROOM}:
        raise ChatProblem(422, "bad_room", "Bunday chat xonasi yo‘q.")

    if kind == GRADE_ROOM and grade_id is None:
        grade = user_grade(db, user) if user is not None else None
        if grade is None:
            raise ChatProblem(
                409, "grade_not_selected", "Chatni ochish uchun avval sinfini tanla."
            )
        grade_id = grade.id

    if kind == GRADE_ROOM:
        grade = db.get(Grade, grade_id) if grade_id else None
        if grade is None:
            raise ChatProblem(404, "room_not_found", "Bunday sinf xonasi topilmadi.")
        room = room_for_pair(db, GRADE_ROOM, grade.id)
        if room is None:
            room = _insert_room(db, GRADE_ROOM, grade.id, grade.name)
        return room

    if kind == NEWS_ROOM:
        room = room_for_pair(db, NEWS_ROOM, None)
        if room is None:
            room = _insert_room(db, NEWS_ROOM, None, NEWS_NAME)
        return room

    room = room_for_pair(db, STAFF_ROOM, None)
    if room is None:
        room = _insert_room(db, STAFF_ROOM, None, STAFF_NAME)
    return room


# Legacy address helper, kept so callers (and the tests written against the old
# shape) can still say "the Grade this room belongs to, if any".
def room_grade(db: Session, room: ChatRoom) -> Grade | None:
    return db.get(Grade, room.grade_id) if room.grade_id else None


def is_staff(user: User, is_admin: bool) -> bool:
    """Teacher by code, or admin by id — the one adult check the rules use."""
    return bool(user.is_teacher) or is_admin


def assert_can_read(db: Session, user: User, room: ChatRoom, is_admin: bool) -> None:
    """Who may open a room. Everything is open EXCEPT the teachers' room and
    another class's room (a pupil is never shown a conversation of older kids)."""
    if room.kind == STAFF_ROOM:
        if not is_staff(user, is_admin):
            raise ChatProblem(
                403, "staff_only", "Bu xona faqat o‘qituvchilar uchun."
            )
        return
    if room.kind == GRADE_ROOM and not is_staff(user, is_admin):
        mine = user_grade(db, user)
        if mine is None:
            raise ChatProblem(409, "grade_not_selected", "Chatni ochish uchun avval sinfini tanla.")
        if room.grade_id != mine.id:
            raise ChatProblem(403, "wrong_grade", "Bu sinf xonasi sizga tegishli emas.")


def can_read(db: Session, user: User, room: ChatRoom, is_admin: bool) -> bool:
    try:
        assert_can_read(db, user, room, is_admin)
        return True
    except ChatProblem:
        return False


def assert_can_post(db: Session, user: User, room: ChatRoom, is_admin: bool) -> None:
    """Who may write. A group room is open (the school chose that); the other
    three keep their old, tighter rules."""
    adult = is_staff(user, is_admin)
    if room.is_closed:
        raise ChatProblem(403, "room_closed", "Bu chat yopilgan — yozib bo‘lmaydi.")
    if room.kind in (NEWS_ROOM, STAFF_ROOM):
        if not adult:
            raise ChatProblem(
                403,
                "staff_only",
                "Ushbu xonaga faqat o‘qituvchi yozadi."
                if room.kind == STAFF_ROOM
                else "E'lonxonaga faqat o‘qituvchi yozadi.",
            )
        return
    if room.kind == GRADE_ROOM:
        if adult:
            return
        mine = user_grade(db, user)
        if mine is None:
            raise ChatProblem(409, "grade_not_selected", "Yozishdan oldin sinfini tanla.")
        if room.grade_id != mine.id:
            raise ChatProblem(403, "wrong_grade", "Siz faqat o‘z sinfingiz xonasiga yozasiz.")
        return
    # A group room: any pupil may write — the teacher asked for open chats. The
    # flood guard below and the delete power stay with staff.
    return


def can_post(db: Session, user: User, room: ChatRoom, is_admin: bool) -> bool:
    try:
        assert_can_post(db, user, room, is_admin)
        return True
    except ChatProblem:
        return False


def assert_can_manage(room: ChatRoom, user: User, is_admin: bool) -> None:
    """Rename / picture / people: the owner of a group room, or any adult."""
    if is_staff(user, is_admin):
        return
    if room.kind != GROUP_ROOM:
        raise ChatProblem(403, "staff_only", "Bu xonani faqat o‘qituvchi o‘zgartiradi.")
    if room.created_by != user.id:
        raise ChatProblem(403, "not_owner", "Xonani faqat ochgan odam o‘zgartiraadi.")


def create_room(db: Session, user: User, *, name: str, bio: str | None, emoji: str | None) -> ChatRoom:
    """The "+" button. Anyone may open a chat; the creator becomes its owner."""
    room = ChatRoom(
        kind=GROUP_ROOM,
        name=clean_room_name(name),
        bio=clean_room_bio(bio),
        emoji=clean_room_emoji(emoji),
        created_by=user.id,
    )
    db.add(room)
    db.flush()
    db.add(ChatMember(room_id=room.id, user_id=user.id, role=ROLE_OWNER))
    db.commit()
    db.refresh(room)
    return room


def visible_rooms(db: Session, user: User, is_admin: bool, *, limit: int = 60) -> list[ChatRoom]:
    """Rooms this person may open, in the order the app should show them.

    staff room first (only for adults), then the e'lonxona, then class rooms,
    then group chats newest-active first. Group rooms are capped: an open
    school-wide chat list must not grow without bound.
    """
    adult = is_staff(user, is_admin)
    mine = user_grade(db, user)
    rooms = db.scalars(select(ChatRoom)).all()
    out: list[ChatRoom] = []
    for room in rooms:
        if room.kind == STAFF_ROOM and not adult:
            continue
        if room.kind == GRADE_ROOM and not adult and (mine is None or room.grade_id != mine.id):
            continue
        out.append(room)
    order = {STAFF_ROOM: 0, NEWS_ROOM: 1, GRADE_ROOM: 2, GROUP_ROOM: 3}
    # Newest first inside each section: a pupil looks for the chat that is live.
    newest = latest_ids_by_room(db)
    out.sort(key=lambda r: (order.get(r.kind, 9), -(newest.get(r.id, 0)), r.id))
    return out[:limit]


def latest_ids_by_room(db: Session) -> dict[int, int]:
    """Newest message id per room in ONE grouped query (the poll's cache hint)."""
    rows = db.execute(
        select(ChatMessage.room_id, func.max(ChatMessage.id)).group_by(ChatMessage.room_id)
    ).all()
    return {room_id: newest for room_id, newest in rows if room_id is not None}


# ----------------------------------------------------------------------
# Members and the people directory
# ----------------------------------------------------------------------

def add_member(db: Session, room: ChatRoom, person: User, *, role: str = ROLE_MEMBER) -> ChatMember:
    """Idempotent: adding twice does not create two rows (there is a UNIQUE for it)."""
    row = db.scalar(
        select(ChatMember).where(ChatMember.room_id == room.id, ChatMember.user_id == person.id)
    )
    if row is not None:
        return row
    row = ChatMember(room_id=room.id, user_id=person.id, role=role)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def remove_member(db: Session, room: ChatRoom, person_id: int) -> bool:
    row = db.scalar(
        select(ChatMember).where(ChatMember.room_id == room.id, ChatMember.user_id == person_id)
    )
    if row is None:
        return False
    db.delete(row)
    db.commit()
    return True


def members_of(db: Session, room_id: int, *, limit: int = MEMBER_PAGE_MAX) -> list[tuple[User, str]]:
    """(person, role) pairs, owner first then by name — the room's people panel.

    The role is ranked on purpose: "member" sorts before "owner" alphabetically,
    so a plain ORDER BY role would put whoever opened the chat at the bottom.
    """
    rows = db.execute(
        select(ChatMember, User)
        .join(User, User.id == ChatMember.user_id)
        .where(ChatMember.room_id == room_id)
        .order_by(
            case((ChatMember.role == ROLE_OWNER, 0), else_=1),
            User.first_name.asc(),
        )
        .limit(max(1, min(limit, MEMBER_PAGE_MAX)))
    ).all()
    return [(person, member.role) for member, person in rows]


def member_counts(db: Session, room_ids: list[int]) -> dict[int, int]:
    if not room_ids:
        return {}
    rows = db.execute(
        select(ChatMember.room_id, func.count(ChatMember.id))
        .where(ChatMember.room_id.in_(set(room_ids)))
        .group_by(ChatMember.room_id)
    ).all()
    return {room_id: count for room_id, count in rows}


def search_people(db: Session, query: str, *, limit: int = PEOPLE_PAGE_MAX) -> list[User]:
    """The directory the "add people" list reads.

    Minimal data about children on purpose: name, class and picture only — no
    telegram id, no progress, no contact details.
    """
    text = re.sub(r"\s+", " ", (query or "").strip())
    limit = max(1, min(limit, PEOPLE_PAGE_MAX))
    stmt = select(User).order_by(User.first_name.asc()).limit(limit)
    if text:
        like = f"%{text}%"
        stmt = stmt.where(or_(User.first_name.ilike(like), User.last_name.ilike(like)))
    return list(db.scalars(stmt).all())


# ----------------------------------------------------------------------
# Room pictures
# ----------------------------------------------------------------------

def room_avatar_path(room_id: int, slug: str) -> str:
    return f"/api/chat/rooms/{room_id}/picture/{slug}"


def get_room_avatar(db: Session, room_id: int) -> ChatRoomAvatar | None:
    return db.scalar(select(ChatRoomAvatar).where(ChatRoomAvatar.room_id == room_id))


def store_room_avatar(db: Session, room_id: int, raw: bytes) -> ChatRoomAvatar:
    """Square, 256px, EXIF-free — the exact rules of a pupil's profile picture
    (app/avatars.py owns them, so a room photo cannot quietly be bigger than one).
    """
    data, mime, edge = normalise_picture(raw)
    row = get_room_avatar(db, room_id)
    if row is None:
        row = ChatRoomAvatar(room_id=room_id, slug=new_capability_slug())
        db.add(row)
    row.slug = new_capability_slug()
    row.mime = mime
    row.width = edge
    row.size_bytes = len(data)
    row.data = data
    db.commit()
    db.refresh(row)
    return row


def remove_room_avatar(db: Session, room_id: int) -> bool:
    row = get_room_avatar(db, room_id)
    if row is None:
        return False
    db.delete(row)
    db.commit()
    return True


def room_avatar_by_slug(db: Session, slug: str) -> ChatRoomAvatar | None:
    return db.scalar(select(ChatRoomAvatar).where(ChatRoomAvatar.slug == slug))


# ----------------------------------------------------------------------
# Flood guard and file quota
# ----------------------------------------------------------------------

def assert_not_flooding(db: Session, user_id: int) -> None:
    """Simple DB-backed rate limit that survives a restart (no in-process state).

    The bound is a tz-aware UTC datetime, exactly like app/leaderboard.py binds its
    week bounds — that is the shape proven to work on both SQLite and Postgres.
    """
    window = get_settings().CHAT_RATE_WINDOW_SECONDS
    limit = get_settings().CHAT_RATE_LIMIT
    since = datetime.now(timezone.utc) - timedelta(seconds=window)
    recent = db.scalar(
        select(func.count(ChatMessage.id)).where(
            ChatMessage.user_id == user_id,
            ChatMessage.created_at >= since,
            ChatMessage.status != DELETED,
        )
    ) or 0
    if recent >= limit:
        raise ChatProblem(
            429,
            "chat_flood",
            "Juda tez yozdyingiz — biroz dam oling va qayta urinib ko'ring.",
            retry_after=window,
        )


def assert_media_quota(db: Session, user_id: int) -> None:
    """How many files one person may send per day (protects a free database)."""
    limit = get_settings().CHAT_MEDIA_PER_DAY
    since = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    today = db.scalar(
        select(func.count(ChatMedia.id))
        .join(ChatMessage, ChatMessage.id == ChatMedia.message_id)
        .where(ChatMessage.user_id == user_id, ChatMedia.created_at >= since)
    ) or 0
    if today >= limit:
        raise ChatProblem(
            429,
            "media_quota",
            f"Bugun {limit} ta fayl yubordingiz — ertaga davom eting.",
            retry_after=3600,
        )


async def prepare_media(
    db: Session, user: User, *, raw: bytes, content_type: str, filename: str
) -> MediaPayload:
    """Turn an uploaded file into a MediaPayload (nothing written yet).

    A video goes to Telegram HERE, before the message exists: if that upload
    fails the message is never created, so a pupil cannot see a bubble with a
    broken file inside it.
    """
    assert_media_quota(db, user.id)
    kind = chat_media.kind_for(content_type, filename)

    if kind == chat_media.VIDEO:
        settings = get_settings()
        if not settings.BOT_TOKEN:
            raise ChatProblem(503, "bot_not_configured", "Video yuborish sozlanmagan.")
        chat_id = user.telegram_id or (
            next(iter(settings.admin_id_set)) if settings.admin_id_set else None
        )
        if not chat_id:
            raise ChatProblem(409, "no_telegram", "Video uchun Telegram ID kerak.")
        chat_media.check_video(raw, content_type, filename)
        file_id = await send_video_to_telegram(
            raw,
            file_name=(filename or "video.mp4"),
            mime=content_type or "video/mp4",
            chat_id=chat_id,
        )
        return MediaPayload(
            kind=kind,
            mime=content_type or "video/mp4",
            size_bytes=len(raw),
            file_id=file_id,
            file_name=(filename or "video.mp4")[:255],
        )

    chat_media.check_size(raw, kind)
    if kind == chat_media.GIF:
        data, width, height = chat_media.accept_gif(raw)
        return MediaPayload(
            kind=kind, mime="image/gif", size_bytes=len(data), width=width, height=height, data=data
        )

    data, mime, width, height = chat_media.normalise_image(raw)
    return MediaPayload(
        kind=chat_media.IMAGE, mime=mime, size_bytes=len(data), width=width, height=height, data=data
    )


async def send_video_to_telegram(
    raw: bytes, *, file_name: str, mime: str, chat_id: int
) -> str:
    """Relay one chat video to the Telegram bot for permanent free hosting.

    Returns the file_id. Async because the free server runs one worker: a
    blocking 10 MB upload would freeze every other pupil's request meanwhile.
    Same path lesson videos already take (app/routers/admin.py).
    """
    settings = get_settings()
    url = f"https://api.telegram.org/bot{settings.BOT_TOKEN}/sendVideo"
    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(
                url,
                data={"chat_id": chat_id, "caption": "💬 EduQuest chat"},
                files={"video": (file_name, raw, mime)},
            )
            data = resp.json()
    except Exception as exc:
        raise ChatProblem(502, "telegram_connection", f"Telegram bilan aloqa xatosi: {exc}")
    if not data.get("ok"):
        description = str(data.get("description", ""))[:180]
        raise ChatProblem(502, "telegram_upload_failed", f"Video yuborilmadi: {description}")
    video = (data.get("result") or {}).get("video") or {}
    file_id = video.get("file_id")
    if not file_id:
        raise ChatProblem(502, "telegram_upload_failed", "Video ID olinmadi.")
    return str(file_id)


def get_media_by_slug(db: Session, slug: str) -> ChatMedia | None:
    return db.scalar(select(ChatMedia).where(ChatMedia.slug == slug))


def media_for(db: Session, message_ids: list[int]) -> dict[int, ChatMedia]:
    """message_id -> media, for one page of the feed (a single IN query)."""
    if not message_ids:
        return {}
    rows = db.scalars(select(ChatMedia).where(ChatMedia.message_id.in_(set(message_ids)))).all()
    return {row.message_id: row for row in rows}


# ----------------------------------------------------------------------
# Writing and reading messages
# ----------------------------------------------------------------------

def send(
    db: Session,
    user: User,
    *,
    room: ChatRoom,
    text: str,
    is_admin: bool,
    media: MediaPayload | None = None,
) -> ChatMessage:
    """Validate + store one message (and its file) in `room`.

    `kind`/`grade_id` on the row are COPIED from the room, never taken from the
    client: they exist so an older Mini App build and the old index keep working.
    """
    assert_can_post(db, user, room, is_admin)
    body = clean_text(text, allow_empty=media is not None)
    if not body and media is None:
        raise ChatProblem(422, "empty_message", "Bo‘sh xabar yuborib bo‘lmadi.")
    assert_not_flooding(db, user.id)
    msg = ChatMessage(
        room_id=room.id,
        kind=room.kind,
        grade_id=room.grade_id,
        user_id=user.id,
        text=body,
        status=PENDING if premoderation_enabled() and not is_staff(user, is_admin) else APPROVED,
    )
    db.add(msg)
    db.flush()
    if media is not None:
        db.add(
            ChatMedia(
                message_id=msg.id,
                kind=media.kind,
                slug=new_capability_slug(),
                mime=media.mime,
                width=media.width,
                height=media.height,
                size_bytes=media.size_bytes,
                data=media.data,
                file_id=media.file_id,
                file_name=media.file_name,
            )
        )
    db.commit()
    db.refresh(msg)
    return msg


def feed(
    db: Session,
    *,
    user_id: int,
    is_admin: bool,
    room: ChatRoom,
    after_id: int | None = None,
    limit: int = PAGE_DEFAULT,
) -> list[ChatMessage]:
    """Oldest-first page of one room: approved messages + the caller's own ones.

    `after_id` is how the Mini App polls: ask for everything newer than the last
    id you already rendered. Without it you get the newest `limit` rows (already
    sorted oldest-first, so the UI can append them as-is).
    """
    limit = max(1, min(limit, PAGE_MAX))
    visible = [ChatMessage.status == APPROVED]
    visible.append(
        (ChatMessage.user_id == user_id)
        & ChatMessage.status.in_([PENDING, REJECTED])
    )
    if is_admin:
        # An admin browsing a room also sees what is still waiting there.
        visible.append(ChatMessage.status == PENDING)
    stmt = (
        select(ChatMessage)
        .where(ChatMessage.room_id == room.id, or_(*visible))
        .options(selectinload(ChatMessage.user), selectinload(ChatMessage.media))
        .order_by(ChatMessage.id.desc() if after_id is None else ChatMessage.id.asc())
        .limit(limit)
    )
    if after_id is not None:
        stmt = stmt.where(ChatMessage.id > after_id)
    rows = db.scalars(stmt).all()
    return list(reversed(rows)) if after_id is None else list(rows)


def avatar_paths(db: Session, user_ids: list[int]) -> dict[int, str]:
    """user_id -> relative avatar URL, for the authors on one page of chat."""
    if not user_ids:
        return {}
    rows = db.scalars(
        select(UserAvatar).where(UserAvatar.user_id.in_(set(user_ids)))
    ).all()
    return {row.user_id: public_path(row.user_id, row.slug) for row in rows}


def get_message(db: Session, message_id: int) -> ChatMessage:
    msg = db.get(ChatMessage, message_id)
    if msg is None:
        raise ChatProblem(404, "message_not_found", "Xabar topilmadi.")
    return msg


def review(
    db: Session, admin: User, message_id: int, *, decision: str, reason: str | None = None
) -> ChatMessage:
    """Admin action: approve | reject | delete (the author keeps their own copy)."""
    target = {
        "approve": APPROVED,
        "reject": REJECTED,
        "delete": DELETED,
    }.get(decision)
    if target is None:
        raise ChatProblem(400, "bad_decision", "Bunday tasdiq amali yo‘q.")
    msg = get_message(db, message_id)
    # `decision` names the ACTION ("reject"); REJECTED is the STATUS it produces.
    # Confusing the two would silently accept a rejection without a reason.
    if decision == "reject" and not (reason or "").strip():
        raise ChatProblem(422, "reason_required", "Red javob uchun qisqa sabab yozing.")
    msg.status = target
    if decision == "reject":
        msg.reject_reason = (reason or "").strip()[:160]
    if decision in ("approve", "reject"):
        msg.reviewed_by = admin.id
        msg.reviewed_at = datetime.now(timezone.utc)
    if decision == "delete" and msg.media is not None:
        # "delete" is what a teacher does to a picture of a child that should
        # never have been posted. The message row stays (a soft delete keeps the
        # audit trail), the FILE goes — otherwise the unguessable URL someone
        # already saved would keep serving the picture forever.
        db.delete(msg.media)
    db.commit()
    db.refresh(msg)
    return msg


def pending(db: Session, *, limit: int = PAGE_MAX, grade_id: int | None = None) -> list[ChatMessage]:
    """The moderation queue, oldest first (nothing gets approved by accident)."""
    stmt = (
        select(ChatMessage)
        .where(ChatMessage.status == PENDING)
        .options(selectinload(ChatMessage.user), selectinload(ChatMessage.grade))
        .order_by(ChatMessage.id.asc())
        .limit(max(1, min(limit, PAGE_MAX)))
    )
    if grade_id is not None:
        stmt = stmt.where(ChatMessage.grade_id == grade_id)
    return list(db.scalars(stmt).all())


def pending_count(db: Session) -> int:
    return db.scalar(
        select(func.count(ChatMessage.id)).where(ChatMessage.status == PENDING)
    ) or 0


# ----------------------------------------------------------------------
# Becoming a teacher
# ----------------------------------------------------------------------

def teacher_code_ok(code: str | None) -> bool:
    """Constant-time compare against Settings.TEACHER_CODE.

    Empty/short codes are refused on purpose: this endpoint is the door to the
    teachers' room, and a 3-letter code on a public URL is not a door. The
    minimum is the same number the app uses to decide whether to show the form
    at all (Settings.teacher_code_set), so the two can never disagree.
    """
    settings = get_settings()
    expected = settings.TEACHER_CODE.strip()
    if len(expected) < TEACHER_CODE_MIN_LENGTH:
        return False
    supplied = (code or "").strip()
    return hmac.compare_digest(expected, supplied)


def teacher_claim(db: Session, user: User, code: str) -> bool:
    """Try the school's code once; True when this person is now staff.

    Gated per account, because the only people who can reach this are logged-in
    pupils — a pupil with unlimited guesses is a password attack with a login.
    The counter is in-process on purpose: Render runs one worker, and a restart
    resetting a 15-minute lockout costs nothing next to an 8+ character code.
    """
    take_teacher_trial(user.id)
    if not teacher_code_ok(code):
        return False
    clear_teacher_trials(user.id)
    user.is_teacher = True
    db.commit()
    return True


# ----------------------------------------------------------------------
# Guess-limit for the teacher code (in-process, per user id)
# ----------------------------------------------------------------------

TEACHER_TRIALS_MAX = 8
TEACHER_TRIAL_WINDOW_SECONDS = 900

_teacher_trials: dict[int, deque[float]] = {}


def take_teacher_trial(user_id: int) -> None:
    """429 when this account spent its guesses inside the window."""
    now = time.monotonic()
    tries = _teacher_trials.setdefault(user_id, deque())
    while tries and now - tries[0] > TEACHER_TRIAL_WINDOW_SECONDS:
        tries.popleft()
    if len(tries) >= TEACHER_TRIALS_MAX:
        wait = int(TEACHER_TRIAL_WINDOW_SECONDS - (now - tries[0])) + 1
        raise ChatProblem(
            429,
            "too_many_attempts",
            "Kodni juda ko‘p marta sinab ko‘rdingiz. "
            f"{wait} soniyadan so‘ng yana urinib ko‘ring.",
            retry_after=wait,
        )
    tries.append(now)


def clear_teacher_trials(user_id: int) -> None:
    """A correct code resets the counter (a later re-claim stays cheap)."""
    _teacher_trials.pop(user_id, None)


def reset_teacher_trial_guards() -> None:
    """Tests only: the counter is process state, so it must not leak between cases."""
    _teacher_trials.clear()
