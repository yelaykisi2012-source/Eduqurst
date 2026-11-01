"""
app/routers/chat.py — the community chat (har sinf xonasi + e'lonxona).

Who may do what (all of it lives in app/chat.py; this file only wires HTTP):
  * a pupil reads/writes THEIR OWN grade's room, reads the e'lonxona, and never
    writes it;
  * an admin reads every room, writes anywhere, and runs the moderation queue;
  * nobody sees another pupil's unapproved message — the queue is admin-only.

Why polling and not WebSocket: the Mini App asks for "messages newer than the
last id I show" every few seconds. One worker, one stateless query, no dropped
connections when Render sleeps — a steady feed was worth more than instant
delivery (the teacher chose "Polling — barqaror").
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import chat as chat_rules
from app.db import get_db
from app.grades import require_grade
from app.models import ChatMessage, Grade, User
from app.routers.admin import get_admin
from app.schemas import (
    ChatFeedOut,
    ChatMessageOut,
    ChatPendingItem,
    ChatPendingOut,
    ChatReviewRequest,
    ChatRoomOut,
    ChatSendOut,
    ChatSendRequest,
)
from app.security import get_current_user, is_admin_user

router = APIRouter(prefix="/api/chat", tags=["chat"])

NEWS_EMOJI = "📣"
GRADE_EMOJI = "💬"


def _room(db: Session, kind: str, grade_id: int | None, user: User) -> Grade | None:
    """Resolve the room address; a grade room without grade_id means MY grade.

    Returning the Grade (None for news) lets every rule downstream work off the
    real row instead of trusting an id the client sent.
    """
    if kind == chat_rules.GRADE_ROOM and grade_id is None:
        return require_grade(db, user)
    return chat_rules.room_or_404(db, kind, grade_id)


def _latest_ids(db: Session) -> dict[tuple[str, int | None], int]:
    """Newest message id per room, in ONE grouped query (poll hint for the UI)."""
    rows = db.execute(
        select(
            ChatMessage.kind, ChatMessage.grade_id, func.max(ChatMessage.id)
        ).group_by(ChatMessage.kind, ChatMessage.grade_id)
    ).all()
    return {(kind, grade_id): newest for kind, grade_id, newest in rows}


def _message_out(
    msg: ChatMessage, me_id: int, avatars: dict[int, str]
) -> ChatMessageOut:
    return ChatMessageOut(
        id=msg.id,
        kind=msg.kind,
        grade_id=msg.grade_id,
        grade_name=msg.grade.name if msg.grade else None,
        author_id=msg.user_id,
        author_name=msg.user.first_name or "O‘quvchi",
        avatar_url=avatars.get(msg.user_id),
        text=msg.text,
        status=msg.status,
        reject_reason=msg.reject_reason if msg.user_id == me_id else None,
        is_me=msg.user_id == me_id,
        created_at=msg.created_at,
    )


# ------------------------------------------------------------------
# Pupil side
# ------------------------------------------------------------------

@router.get("/rooms", response_model=list[ChatRoomOut])
def list_rooms(
    db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> list[ChatRoomOut]:
    """Rooms the caller may open: the e'lonxona always, plus one grade room.

    An admin gets every grade room as well — that is how they reach a class to
    read it. A pupil who has not chosen a grade sees only the e'lonxona (the app
    then nudges them to pick a grade), because a chat without a grade makes no
    sense here.
    """
    is_admin = is_admin_user(user)
    my_grade = user.grade_id
    newest = _latest_ids(db)

    rooms = [
        ChatRoomOut(
            kind=chat_rules.NEWS_ROOM,
            grade_id=None,
            name=chat_rules.NEWS_NAME,
            emoji=NEWS_EMOJI,
            can_post=is_admin,
            is_current_grade=False,
            latest_id=newest.get((chat_rules.NEWS_ROOM, None)),
        )
    ]
    grades = db.scalars(select(Grade).order_by(Grade.order_index)).all()
    for grade in grades:
        if not is_admin and grade.id != my_grade:
            continue
        rooms.append(
            ChatRoomOut(
                kind=chat_rules.GRADE_ROOM,
                grade_id=grade.id,
                name=grade.name,
                emoji=GRADE_EMOJI,
                can_post=True,
                is_current_grade=grade.id == my_grade,
                latest_id=newest.get((chat_rules.GRADE_ROOM, grade.id)),
            )
        )
    return rooms


@router.get("/messages", response_model=ChatFeedOut)
def list_messages(
    # No pattern here on purpose: app/chat.py validates the room and answers with
    # the same {"error", "message_uz"} shape the whole API uses.
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
    grade = _room(db, kind, grade_id, user)
    is_admin = is_admin_user(user)
    chat_rules.assert_can_read(db, user, kind, grade, is_admin)
    rows = chat_rules.feed(
        db,
        user_id=user.id,
        is_admin=is_admin,
        kind=kind,
        grade_id=grade.id if grade else None,
        after_id=after_id,
        limit=limit,
    )
    avatars = chat_rules.avatar_paths(db, [m.user_id for m in rows])
    return ChatFeedOut(
        kind=kind,
        grade_id=grade.id if grade else None,
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
    """Write one message into the room (rules + rate limit in app/chat.py)."""
    grade = _room(db, body.kind, body.grade_id, user)
    is_admin = is_admin_user(user)
    msg = chat_rules.send(
        db,
        user,
        kind=body.kind,
        grade_id=grade.id if grade else None,
        text=body.text,
        is_admin=is_admin,
    )
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


# ------------------------------------------------------------------
# Admin side (moderation)
# ------------------------------------------------------------------

def _pending_item(msg: ChatMessage, avatars: dict[int, str]) -> ChatPendingItem:
    return ChatPendingItem(
        id=msg.id,
        kind=msg.kind,
        grade_id=msg.grade_id,
        grade_name=msg.grade.name if msg.grade else None,
        author_id=msg.user_id,
        author_name=msg.user.first_name or "O‘quvchi",
        avatar_url=avatars.get(msg.user_id),
        text=msg.text,
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
    return ChatPendingOut(
        # count is global (badge), items can be filtered to one grade.
        count=chat_rules.pending_count(db),
        premoderation=chat_rules.premoderation_enabled(),
        items=[_pending_item(m, avatars) for m in rows],
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
