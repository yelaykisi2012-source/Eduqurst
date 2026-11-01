"""
app/chat.py — the community chat rules (rooms, limits, moderation states).

ROOMS (what the teacher asked for: "har sinf + e'lonxona")
----------------------------------------------------------
  * kind="grade" — one room per grade (1-sinf .. 11-sinf). A pupil reads and
    writes ONLY their own grade's room, so an 11-sinf conversation never lands in
    front of a first-grader.
  * kind="news"  — one school-wide announcement channel (e'lonxona). Everybody
    reads it, only admins may write.

MODERATION — two modes, one env flag
------------------------------------
The teacher first asked for "every message goes through approval", then chose
"no filter, admin deletes manually". Both are implemented and switched WITHOUT a
code change, through CHAT_PREMODERATION in Render:

  * off (the current default): a message appears at once, the admin can delete
    it afterwards;
  * on: a message is stored as `pending` and only becomes visible after an admin
    approves it; a rejection carries a reason back to the author.

Either way the author always sees their own pending/rejected messages, so
nothing ever looks silently lost — and rejected/deleted rows never appear in
anyone else's feed. There is no automatic word filter (deliberately: the pupils
are real children known to their teachers, and a keyword filter would punish
honest mistakes while looking like it protects).

`status` values: pending | approved | rejected | deleted.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.avatars import public_path
from app.config import get_settings
from app.grades import user_grade
from app.models import ChatMessage, Grade, User, UserAvatar

GRADE_ROOM = "grade"
NEWS_ROOM = "news"
NEWS_NAME = "E'lonxona"

TEXT_MIN = 2
TEXT_MAX = 500            # matches models.ChatMessage.text
MAX_LINES = 4             # a wall of text is not a chat message
PAGE_DEFAULT = 40
PAGE_MAX = 100

PENDING = "pending"
APPROVED = "approved"
REJECTED = "rejected"
DELETED = "deleted"


class ChatProblem(HTTPException):
    """Structured 4xx with an Uzbek message the Mini App shows as-is."""

    def __init__(self, code: int, error: str, message_uz: str, retry_after: int | None = None):
        detail = {"error": error, "message_uz": message_uz}
        headers = {"Retry-After": str(retry_after)} if retry_after else None
        super().__init__(status_code=code, detail=detail, headers=headers)


def premoderation_enabled() -> bool:
    """True = every new message waits for an admin (CHAT_PREMODERATION=1)."""
    return get_settings().CHAT_PREMODERATION


def clean_text(raw: str) -> str:
    """Trim, squash blank lines, enforce length — or raise with a clear reason."""
    text = (raw or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    text = re.sub(r"\n{3,}", "\n\n", text)
    if len(text) < TEXT_MIN:
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
        raise ChatProblem(
            422, "too_many_lines", f"Xabarda ko‘pi bilan {MAX_LINES} qator bo‘lsin."
        )
    return text


def room_or_404(db: Session, kind: str, grade_id: int | None) -> Grade | None:
    """Validate a room address; returns the Grade for grade rooms (None for news)."""
    if kind == NEWS_ROOM:
        return None
    if kind != GRADE_ROOM:
        raise ChatProblem(422, "bad_room", "Bunday chat xonasi yo‘q.")
    grade = db.get(Grade, grade_id) if grade_id else None
    if grade is None:
        raise ChatProblem(404, "room_not_found", "Bunday sinf xonasi topilmadi.")
    return grade


def assert_can_read(db: Session, user: User, kind: str, grade: Grade | None, is_admin: bool) -> None:
    """Grade rooms are only readable by that grade's pupils (admins: all rooms)."""
    if is_admin or kind == NEWS_ROOM:
        return
    mine = user_grade(db, user)
    if mine is None:
        raise ChatProblem(
            409, "grade_not_selected", "Chatni ochish uchun avval sinfini tanla."
        )
    if grade is None or mine.id != grade.id:
        raise ChatProblem(403, "wrong_grade", "Bu sinf xonasi sizga tegishli emas.")


def assert_can_post(db: Session, user: User, kind: str, grade: Grade | None, is_admin: bool) -> None:
    """Posting rules: news = admin only; a grade room = that grade or an admin."""
    if kind == NEWS_ROOM:
        if not is_admin:
            raise ChatProblem(
                403, "news_admin_only", "E'lonxonaga faqat o‘qituvchi yozadi."
            )
        return
    if is_admin:
        return
    mine = user_grade(db, user)
    if mine is None:
        raise ChatProblem(409, "grade_not_selected", "Yozishdan oldin sinfini tanla.")
    if grade is None or mine.id != grade.id:
        raise ChatProblem(403, "wrong_grade", "Siz faqat o‘z sinfingiz xonasiga yozasiz.")


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


def send(
    db: Session, user: User, *, kind: str, grade_id: int | None, text: str, is_admin: bool
) -> ChatMessage:
    """Validate + store one message. The status is decided by CHAT_PREMODERATION."""
    grade = room_or_404(db, kind, grade_id)
    assert_can_post(db, user, kind, grade, is_admin)
    body = clean_text(text)
    assert_not_flooding(db, user.id)
    msg = ChatMessage(
        kind=kind,
        grade_id=grade.id if grade else None,
        user_id=user.id,
        text=body,
        status=PENDING if premoderation_enabled() and not is_admin else APPROVED,
    )
    db.add(msg)
    db.commit()
    db.refresh(msg)
    return msg


def feed(
    db: Session,
    *,
    user_id: int,
    is_admin: bool,
    kind: str,
    grade_id: int | None,
    after_id: int | None = None,
    limit: int = PAGE_DEFAULT,
) -> list[ChatMessage]:
    """Oldest-first page of a room: approved messages + the caller's own ones.

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
        .where(
            ChatMessage.kind == kind,
            ChatMessage.grade_id == grade_id,
            or_(*visible),
        )
        .options(selectinload(ChatMessage.user), selectinload(ChatMessage.grade))
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
