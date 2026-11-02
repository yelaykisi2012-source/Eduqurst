"""
app/routers/chat.py — the community chat (rooms, members, files, moderation).

Who may do what lives in app/chat.py; this file only wires HTTP. Short version:
  * a pupil reads/writes THEIR OWN class room, reads the e'lonxona, never writes
    it, and may read + write any group chat the "+" button created;
  * the teachers' room (kind="staff") is closed to pupils — it is where adults
    talk about the class;
  * staff (a teacher by code, or an admin by id) may write anywhere and the admin
    alone runs the moderation queue;
  * nobody sees another pupil's unapproved message — the queue is admin-only.

Why polling and not WebSocket: the Mini App asks for "messages newer than the
last id I show" every few seconds. One worker, one stateless query, no dropped
connections when Render sleeps — a steady feed was worth more than instant
delivery (the teacher chose "Polling — barqaror").

Why two ways to address a room: `room_id` is the real key now, but (kind,
grade_id) still resolves — a Mini App build already cached on a pupil's phone
keeps working the day the server changes.
"""
from __future__ import annotations

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    Query,
    Response,
    UploadFile,
    status,
)
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import chat as chat_rules
from app import chat_media
from app.db import get_db
from app.models import (
    ChatMember,
    ChatMedia,
    ChatMessage,
    ChatRoom,
    ChatRoomAvatar,
    User,
)
from app.routers.admin import get_admin
from app.routers.content import _telegram_file_stream, _telegram_get_file
from app.schemas import (
    ChatFeedOut,
    ChatMediaOut,
    ChatMemberAddRequest,
    ChatMemberOut,
    ChatMessageOut,
    ChatPendingItem,
    ChatPendingOut,
    ChatPeopleOut,
    ChatPersonOut,
    ChatReviewRequest,
    ChatRoomCreateRequest,
    ChatRoomOut,
    ChatRoomOutResult,
    ChatRoomUpdateRequest,
    ChatSendOut,
    ChatSendRequest,
)
from app.security import get_current_user, is_admin_user

router = APIRouter(prefix="/api/chat", tags=["chat"])

MEDIA_URL = "/api/chat/media/"
# A room picture follows the profile-picture rules (app/avatars.py caps the
# decoded input at 5 MB); this guard is one step higher so an absurd upload is
# refused before Pillow is asked to decode it.
MAX_ROOM_PICTURE_BYTES = 6 * 1024 * 1024


# ----------------------------------------------------------------------
# Shaping
# ----------------------------------------------------------------------

def _media_out(media: ChatMedia | None) -> ChatMediaOut | None:
    """A file the bubble can render. Video points at the proxy, not at Telegram."""
    if media is None:
        return None
    return ChatMediaOut(
        kind=media.kind,
        url=f"{MEDIA_URL}{media.slug}",
        mime=media.mime,
        width=media.width,
        height=media.height,
        size_bytes=media.size_bytes,
    )


def _message_out(msg: ChatMessage, me_id: int, avatars: dict[int, str]) -> ChatMessageOut:
    return ChatMessageOut(
        id=msg.id,
        room_id=msg.room_id,
        kind=msg.kind,
        grade_id=msg.grade_id,
        grade_name=msg.grade.name if msg.grade else None,
        author_id=msg.user_id,
        author_name=msg.user.first_name or "O‘quvchi",
        avatar_url=avatars.get(msg.user_id),
        text=msg.text,
        media=_media_out(msg.media),
        status=msg.status,
        reject_reason=msg.reject_reason if msg.user_id == me_id else None,
        is_me=msg.user_id == me_id,
        created_at=msg.created_at,
    )


async def _aread_limited(file: UploadFile, max_bytes: int) -> bytes:
    data = await file.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise chat_rules.ChatProblem(
            413,
            "file_too_big",
            f"Fayl juda katta — {chat_media.human_size(max_bytes)} dan kichikroqini tanlang.",
        )
    return data


def _kind_of_upload(file: UploadFile) -> str:
    """Which cap applies, from what the browser claims + the file name."""
    try:
        return chat_media.kind_for(file.content_type or "", file.filename or "")
    except chat_media.MediaRejected as exc:
        raise chat_rules.ChatProblem(422, "bad_file_type", str(exc))


# ----------------------------------------------------------------------
# Rooms
# ----------------------------------------------------------------------

@router.get("/rooms", response_model=list[ChatRoomOut])
def list_rooms(
    db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> list[ChatRoomOut]:
    """Every room this person may open: e'lonxona, their class, the teachers'
    room (staff only) and all group chats created with the "+" button."""
    is_admin = is_admin_user(user)
    chat_rules.ensure_system_rooms(db)
    chat_rules.backfill_room_ids(db)
    rooms = chat_rules.visible_rooms(db, user, is_admin)
    newest = chat_rules.latest_ids_by_room(db)
    counts = chat_rules.member_counts(db, [r.id for r in rooms])
    pictures: dict[int, str] = {}
    if rooms:
        slugs = db.execute(
            select(ChatRoomAvatar.room_id, ChatRoomAvatar.slug).where(
                ChatRoomAvatar.room_id.in_({r.id for r in rooms})
            )
        ).all()
        pictures = {
            room_id: chat_rules.room_avatar_path(room_id, slug) for room_id, slug in slugs
        }
    return [
        ChatRoomOut(
            id=room.id,
            kind=room.kind,
            grade_id=room.grade_id,
            name=room.name,
            bio=room.bio,
            emoji=room.emoji,
            avatar_url=pictures.get(room.id),
            can_post=chat_rules.can_post(db, user, room, is_admin),
            can_read=chat_rules.can_read(db, user, room, is_admin),
            is_current_grade=(
                room.kind == chat_rules.GRADE_ROOM and room.grade_id == user.grade_id
            ),
            member_count=counts.get(room.id, 0),
            is_mine=room.created_by == user.id,
            owner_name=(room.creator.first_name or "O‘quvchi") if room.creator else None,
            is_closed=room.is_closed,
            latest_id=newest.get(room.id),
        )
        for room in rooms
    ]


@router.post("/rooms", response_model=ChatRoomOutResult, status_code=status.HTTP_201_CREATED)
def create_room(
    body: ChatRoomCreateRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ChatRoomOutResult:
    """The "+" button: anyone may open a chat and becomes its owner."""
    room = chat_rules.create_room(
        db, user, name=body.name, bio=body.bio, emoji=body.emoji
    )
    return ChatRoomOutResult(
        room=_single_room_out(db, user, room),
        message_uz=f"«{room.name}» ochildi ✅",
    )


@router.patch("/rooms/{room_id}", response_model=ChatRoomOutResult)
def update_room(
    room_id: int,
    body: ChatRoomUpdateRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ChatRoomOutResult:
    """Rename, describe, change the icon or close the room (owner or staff)."""
    room = chat_rules.resolve_room(db, room_id=room_id)
    chat_rules.assert_can_manage(room, user, is_admin_user(user))
    if body.name is not None:
        room.name = chat_rules.clean_room_name(body.name)
    if body.bio is not None:
        room.bio = chat_rules.clean_room_bio(body.bio)
    if body.emoji is not None:
        room.emoji = chat_rules.clean_room_emoji(body.emoji)
    if body.is_closed is not None:
        # Only an adult may silence a room nobody owns any more (a pupil who
        # leaves cannot lock their classmates out of a school-wide chat).
        if not chat_rules.is_staff(user, is_admin_user(user)) and room.created_by != user.id:
            raise chat_rules.ChatProblem(
                403, "not_owner", "Xonani faqat ochgan odam yoki o‘qituvchi yopadi."
            )
        room.is_closed = bool(body.is_closed)
    db.commit()
    db.refresh(room)
    return ChatRoomOutResult(
        room=_single_room_out(db, user, room), message_uz="Saqlandi ✅"
    )


@router.post("/rooms/{room_id}/picture", response_model=ChatRoomOutResult)
async def upload_room_picture(
    room_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ChatRoomOutResult:
    """The chat's picture — square, 256px, EXIF-free (rules in app/avatars.py)."""
    room = chat_rules.resolve_room(db, room_id=room_id)
    chat_rules.assert_can_manage(room, user, is_admin_user(user))
    raw = await _aread_limited(file, MAX_ROOM_PICTURE_BYTES)
    try:
        chat_rules.store_room_avatar(db, room.id, raw)
    except ValueError as exc:  # avatars.AvatarRejected is a ValueError
        raise chat_rules.ChatProblem(422, "picture_rejected", str(exc))
    return ChatRoomOutResult(
        room=_single_room_out(db, user, room), message_uz="Rasm qo‘yildi ✅"
    )


@router.delete("/rooms/{room_id}/picture", response_model=ChatRoomOutResult)
def delete_room_picture(
    room_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ChatRoomOutResult:
    room = chat_rules.resolve_room(db, room_id=room_id)
    chat_rules.assert_can_manage(room, user, is_admin_user(user))
    chat_rules.remove_room_avatar(db, room.id)
    return ChatRoomOutResult(room=_single_room_out(db, user, room), message_uz="Rasm o‘chirildi")


@router.get("/rooms/{room_id}/picture/{slug}")
def get_room_picture(room_id: int, slug: str, db: Session = Depends(get_db)) -> Response:
    """Public capability URL (an <img> tag cannot send a JWT), like a profile
    picture: the slug is random, rotates on every re-upload and is not enumerable.
    """
    row = db.scalar(
        select(ChatRoomAvatar).where(
            ChatRoomAvatar.room_id == room_id, ChatRoomAvatar.slug == slug
        )
    )
    if row is None:
        raise chat_rules.ChatProblem(404, "picture_not_found", "Rasm topilmadi.")
    return Response(content=row.data, media_type=row.mime, headers={"Cache-Control": "private, max-age=300"})


# ----------------------------------------------------------------------
# People and members
# ----------------------------------------------------------------------

@router.get("/people", response_model=ChatPeopleOut)
def search_people(
    q: str = Query(default="", max_length=64),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ChatPeopleOut:
    """The "add people" list: first name / surname only, class + picture.

    No telegram id, no progress, no contact details — the minimum a pupil needs
    to recognise a classmate, and nothing else.
    """
    people = chat_rules.search_people(db, q)
    avatars = chat_rules.avatar_paths(db, [p.id for p in people])
    return ChatPeopleOut(
        people=[
            ChatPersonOut(
                id=person.id,
                name=(f"{person.first_name} {person.last_name or ''}".strip() or "O‘quvchi"),
                grade_name=person.grade.name if person.grade else None,
                avatar_url=avatars.get(person.id),
                is_teacher=person.is_teacher,
                is_me=person.id == user.id,
            )
            for person in people
        ]
    )


@router.get("/rooms/{room_id}/members", response_model=list[ChatMemberOut])
def list_members(
    room_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[ChatMemberOut]:
    room = chat_rules.resolve_room(db, room_id=room_id)
    chat_rules.assert_can_read(db, user, room, is_admin_user(user))
    return _members_after_change(db, room, user)


@router.post("/rooms/{room_id}/join", response_model=list[ChatMemberOut])
def join_room(
    room_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[ChatMemberOut]:
    """Put yourself in a group chat's people list. Reading is already open; this
    is what makes the room show up as "mine" and lets the owner see who is in."""
    room = chat_rules.resolve_room(db, room_id=room_id)
    chat_rules.assert_can_read(db, user, room, is_admin_user(user))
    if room.kind != chat_rules.GROUP_ROOM:
        raise chat_rules.ChatProblem(
            403, "not_group_room", "Sinf va e'lonxona xonalariga a'zo bo‘lish shart emas."
        )
    chat_rules.add_member(db, room, user)
    return _members_after_change(db, room, user)


@router.post("/rooms/{room_id}/members", response_model=list[ChatMemberOut])
def add_member(
    room_id: int,
    body: ChatMemberAddRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[ChatMemberOut]:
    """Owner or staff adds a person to a group chat."""
    room = chat_rules.resolve_room(db, room_id=room_id)
    chat_rules.assert_can_manage(room, user, is_admin_user(user))
    if room.kind != chat_rules.GROUP_ROOM:
        raise chat_rules.ChatProblem(403, "not_group_room", "Bu xonaga odam qo‘shib bo‘lmaydi.")
    person = db.get(User, body.user_id)
    if person is None:
        raise chat_rules.ChatProblem(404, "person_not_found", "Bunday odam topilmadi.")
    chat_rules.add_member(db, room, person)
    return _members_after_change(db, room, user)


@router.delete("/rooms/{room_id}/members/{person_id}", response_model=dict)
def remove_person(
    room_id: int,
    person_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    """A person leaves, or the owner/staff takes them out. The owner cannot be
    removed by anyone but staff — a room with no owner would stop being managed.
    """
    room = chat_rules.resolve_room(db, room_id=room_id)
    is_admin = is_admin_user(user)
    adult = chat_rules.is_staff(user, is_admin)
    if person_id != user.id and not adult and room.created_by != user.id:
        raise chat_rules.ChatProblem(403, "not_owner", "Odamsizni chiqara olmaysiz.")
    target = db.scalar(
        select(ChatMember).where(
            ChatMember.room_id == room.id,
            ChatMember.user_id == person_id,
        )
    )
    if target is None:
        raise chat_rules.ChatProblem(404, "not_member", "Bu odam allaqachon ro‘yxatda yo‘q.")
    if target.role == chat_rules.ROLE_OWNER and not adult:
        raise chat_rules.ChatProblem(
            403, "owner_stays", "Xonani ochgan odamni faqat o‘qituvchi chiqara oladi."
        )
    chat_rules.remove_member(db, room, person_id)
    return {"ok": True}


# ----------------------------------------------------------------------
# Feed
# ----------------------------------------------------------------------

@router.get("/messages", response_model=ChatFeedOut)
def list_messages(
    # No pattern here on purpose: app/chat.py validates the room and answers with
    # the same {"error", "message_uz"} shape the whole API uses.
    room_id: int | None = Query(default=None, ge=1),
    kind: str = Query(default="grade"),
    grade_id: int | None = Query(default=None, ge=1),
    after_id: int | None = Query(default=None, ge=0),
    limit: int = Query(default=chat_rules.PAGE_DEFAULT, ge=1, le=chat_rules.PAGE_MAX),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ChatFeedOut:
    """Oldest-first page of one room.

    First open: no after_id -> the newest `limit` messages. Next polls: send the
    `latest_id` you last rendered and you get only what is newer (empty most of
    the time, which is exactly how cheap polling should look).
    """
    room = chat_rules.resolve_room(db, room_id=room_id, kind=kind, grade_id=grade_id, user=user)
    is_admin = is_admin_user(user)
    chat_rules.assert_can_read(db, user, room, is_admin)
    rows = chat_rules.feed(
        db,
        user_id=user.id,
        is_admin=is_admin,
        room=room,
        after_id=after_id,
        limit=limit,
    )
    avatars = chat_rules.avatar_paths(db, [m.user_id for m in rows])
    return ChatFeedOut(
        room_id=room.id,
        kind=room.kind,
        grade_id=room.grade_id,
        messages=[_message_out(m, user.id, avatars) for m in rows],
        latest_id=rows[-1].id if rows else after_id,
        premoderation=chat_rules.premoderation_enabled(),
    )


@router.post(
    "/messages",
    response_model=ChatSendOut,
    status_code=status.HTTP_201_CREATED,
)
def post_message(
    body: ChatSendRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ChatSendOut:
    """Write one text message into the room (rules + rate limit in app/chat.py)."""
    room = chat_rules.resolve_room(
        db, room_id=body.room_id, kind=body.kind, grade_id=body.grade_id, user=user
    )
    is_admin = is_admin_user(user)
    msg = chat_rules.send(db, user, room=room, text=body.text, is_admin=is_admin)
    return _sent_out(db, user, msg, room)


@router.post(
    "/messages/attach",
    response_model=ChatSendOut,
    status_code=status.HTTP_201_CREATED,
)
async def post_message_with_file(
    room_id: int | None = Form(default=None, ge=1),
    kind: str = Form(default="grade"),
    grade_id: int | None = Form(default=None, ge=1),
    text: str = Form(default=""),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ChatSendOut:
    """One message WITH a file: a picture, a GIF or a video.

    The file is prepared before the message row exists, so a failed Telegram
    upload never leaves a pupil staring at an empty bubble.
    """
    room = chat_rules.resolve_room(db, room_id=room_id, kind=kind, grade_id=grade_id, user=user)
    is_admin = is_admin_user(user)
    # Permission BEFORE reading the upload: a pupil who may not write here should
    # not be able to make the server pull 10 MB out of a request first.
    chat_rules.assert_can_post(db, user, room, is_admin)
    # Which cap applies is decided from the upload's own claim, then the body is
    # read with that cap — a 10 MB "video" cannot be smuggled past a 2 MB image.
    raw = await _aread_limited(file, chat_media.media_max_bytes(_kind_of_upload(file)))
    try:
        payload = await chat_rules.prepare_media(
            db,
            user,
            raw=raw,
            content_type=file.content_type or "",
            filename=file.filename or "",
        )
    except chat_media.MediaRejected as exc:
        # The bytes are only identified here (a .jpg that is really a .exe), so
        # this is where a pupil gets the "not a picture" line — 422, never a 500.
        raise chat_rules.ChatProblem(422, "file_rejected", str(exc))
    msg = chat_rules.send(
        db, user, room=room, text=text, is_admin=is_admin, media=payload
    )
    db.refresh(msg)
    return _sent_out(db, user, msg, room)


@router.get("/media/{slug}")
async def get_media(slug: str, db: Session = Depends(get_db)) -> Response:
    """Serve one attached file. Public capability URL, exactly like a picture:
    an <img>/<video> tag cannot send a JWT, and the slug is random per file.

    A picture/GIF comes out of Postgres; a video is streamed through here from
    Telegram, which is what keeps the bot token out of every client.
    """
    row = chat_rules.get_media_by_slug(db, slug)
    if row is None:
        raise chat_rules.ChatProblem(404, "media_not_found", "Fayl topilmadi yoki o‘chirilgan.")
    if row.data:
        return Response(
            content=row.data,
            media_type=row.mime,
            headers={"Cache-Control": "private, max-age=600"},
        )
    if not row.file_id:
        raise chat_rules.ChatProblem(404, "media_not_found", "Fayl topilmadi.")
    try:
        info = _telegram_get_file(row.file_id)
    except Exception:
        raise chat_rules.ChatProblem(502, "media_fetch_failed", "Faylni olishda xatolik.")
    if not info.get("ok"):
        description = str(info.get("description", "")).lower()
        if "too big" in description:
            raise chat_rules.ChatProblem(
                413, "media_too_big", "Fayl juda katta — uni Telegram bot orqali oling."
            )
        raise chat_rules.ChatProblem(502, "media_fetch_failed", "Faylni olishda xatolik.")
    path = info["result"]["file_path"]
    name = (row.file_name or path.rsplit("/", 1)[-1]).replace('"', "").replace("\n", "")
    return StreamingResponse(
        _telegram_file_stream(path),
        media_type=row.mime,
        headers={"Content-Disposition": f'inline; filename="{name}"'},
    )


# ----------------------------------------------------------------------
# Admin side (moderation)
# ----------------------------------------------------------------------

def _pending_item(
    msg: ChatMessage, avatars: dict[int, str], media: dict[int, ChatMediaOut]
) -> ChatPendingItem:
    return ChatPendingItem(
        id=msg.id,
        kind=msg.kind,
        grade_id=msg.grade_id,
        grade_name=msg.grade.name if msg.grade else None,
        author_id=msg.user_id,
        author_name=msg.user.first_name or "O‘quvchi",
        avatar_url=avatars.get(msg.user_id),
        text=msg.text,
        media=media.get(msg.id),
        created_at=msg.created_at,
    )


@router.get("/admin/pending", response_model=ChatPendingOut)
def admin_pending(
    grade_id: int | None = Query(default=None, ge=1),
    db: Session = Depends(get_db),
    admin: User = Depends(get_admin),
) -> ChatPendingOut:
    """The approval queue (oldest first) + the count for the admin badge.

    When CHAT_PREMODERATION is off the queue is normally empty — the admin's real
    tool in that mode is DELETE on a message that already went out.
    """
    rows = chat_rules.pending(db, grade_id=grade_id)
    avatars = chat_rules.avatar_paths(db, [m.user_id for m in rows])
    # Read the files into a map instead of assigning msg.media: these objects are
    # still attached to the session, and setting a relationship would mark them
    # dirty on a GET.
    media = {
        row.message_id: _media_out(row)
        for row in chat_rules.media_for(db, [m.id for m in rows]).values()
    }
    return ChatPendingOut(
        # count is global (badge), items can be filtered to one grade.
        count=chat_rules.pending_count(db),
        premoderation=chat_rules.premoderation_enabled(),
        items=[_pending_item(m, avatars, media) for m in rows],
    )


def _review(
    decision: str, msg_id: int, admin: User, db: Session, reason: str | None = None
) -> dict:
    """One shape for all three admin decisions (app/chat.py validates them)."""
    msg = chat_rules.review(db, admin, msg_id, decision=decision, reason=reason)
    return {"ok": True, "id": msg.id, "status": msg.status}


@router.post("/admin/{message_id}/approve")
def admin_approve(
    message_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(get_admin),
) -> dict:
    """Show a queued message in its room."""
    return _review("approve", message_id, admin, db)


@router.post("/admin/{message_id}/reject")
def admin_reject(
    message_id: int,
    body: ChatReviewRequest,
    db: Session = Depends(get_db),
    admin: User = Depends(get_admin),
) -> dict:
    """Refuse a queued message; the author sees the reason on their own copy."""
    return _review("reject", message_id, admin, db, reason=body.reason)


@router.delete("/admin/{message_id}")
def admin_delete(
    message_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(get_admin),
) -> dict:
    """Remove a message that is already visible (the no-filter mode's control)."""
    return _review("delete", message_id, admin, db)


# ----------------------------------------------------------------------
# Small internal helpers (kept at the bottom so the routes read top-down)
# ----------------------------------------------------------------------

def _single_room_out(db: Session, user: User, room: ChatRoom) -> ChatRoomOut:
    """One room, echoed after a change (create/rename/picture)."""
    is_admin = is_admin_user(user)
    picture = chat_rules.get_room_avatar(db, room.id)
    counts = chat_rules.member_counts(db, [room.id])
    # Targeted max(id) for THIS room: the whole-table group-by in
    # latest_ids_by_room() is right for the room list, wasteful for one echo.
    latest_id = db.scalar(
        select(func.max(ChatMessage.id)).where(ChatMessage.room_id == room.id)
    )
    return ChatRoomOut(
        id=room.id,
        kind=room.kind,
        grade_id=room.grade_id,
        name=room.name,
        bio=room.bio,
        emoji=room.emoji,
        avatar_url=(
            chat_rules.room_avatar_path(room.id, picture.slug) if picture else None
        ),
        can_post=chat_rules.can_post(db, user, room, is_admin),
        can_read=chat_rules.can_read(db, user, room, is_admin),
        is_current_grade=room.kind == chat_rules.GRADE_ROOM and room.grade_id == user.grade_id,
        member_count=counts.get(room.id, 0),
        is_mine=room.created_by == user.id,
        owner_name=(room.creator.first_name or "O‘quvchi") if room.creator else None,
        is_closed=room.is_closed,
        latest_id=latest_id,
    )


def _members_after_change(db: Session, room: ChatRoom, user: User) -> list[ChatMemberOut]:
    """The room's people list, as one shape shared by GET and every change.

    `is_me` is on it so the panel can offer "leave" to the right person: a first
    name is not proof of identity (two pupils can be called Aziz).
    """
    pairs = chat_rules.members_of(db, room.id)
    avatars = chat_rules.avatar_paths(db, [person.id for person, _role in pairs])
    return [
        ChatMemberOut(
            id=person.id,
            name=person.first_name or "O‘quvchi",
            grade_name=person.grade.name if person.grade else None,
            avatar_url=avatars.get(person.id),
            role=role,
            is_teacher=person.is_teacher,
            is_me=person.id == user.id,
        )
        for person, role in pairs
    ]


def _sent_out(db: Session, user: User, msg: ChatMessage, room: ChatRoom) -> ChatSendOut:
    premod = msg.status == chat_rules.PENDING
    avatars = chat_rules.avatar_paths(db, [user.id])
    return ChatSendOut(
        message=_message_out(msg, user.id, avatars),
        premoderation=premod,
        message_uz=(
            "Xabaring o‘qituvchi tekshiruviga yuborildi ⏳"
            if premod
            else "Yuborildi ✅"
        ),
    )
