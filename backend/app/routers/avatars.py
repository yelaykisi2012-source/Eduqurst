"""
app/routers/avatars.py — profile picture upload (pupil) + public serving.

Two very different routes live here on purpose:

  * /api/me/avatar           — needs the Mini App JWT: the pupil editing THEIR
    OWN picture (upload / remove).
  * /api/avatars/{id}/{slug} — NO Authorization header, because an <img> tag
    cannot send one. The unguessable `slug` is the credential (app/avatars.py
    explains why); it rotates on every re-upload, so "I removed my picture" also
    kills every link that was already shared.

The bot pushes Telegram profile photos through
/api/internal/pupils/{telegram_id}/avatar (app/routers/bot_internal.py), which
reuses `read_upload`/`store_avatar`/`avatar_out` from this file — one code path,
so a Telegram photo and an uploaded file cannot end up shaped differently.
"""
from __future__ import annotations

from fastapi import (
    APIRouter,
    Depends,
    File,
    Header,
    HTTPException,
    Response,
    UploadFile,
    status,
)
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import avatars as avatar_store
from app.db import get_db
from app.models import User, UserAvatar
from app.schemas import AvatarOut
from app.security import get_current_user

router = APIRouter(prefix="/api", tags=["avatar"])

MAX_READ = avatar_store.MAX_INPUT_BYTES + 1  # one extra byte proves "too big"


def avatar_out(row: UserAvatar) -> AvatarOut:
    return AvatarOut(
        avatar_url=avatar_store.public_path(row.user_id, row.slug),
        mime=row.mime,
        width=row.width,
        size_bytes=row.size_bytes,
        source=row.source,
        updated_at=row.updated_at,
    )


def rejected_http(exc: Exception) -> HTTPException:
    """422 with the pupil-readable Uzbek reason straight from app/avatars.py."""
    return HTTPException(
        422,  # HTTP_422_UNPROCESSABLE_ENTITY is deprecated in this Starlette
        detail={"error": "avatar_rejected", "message_uz": str(exc)},
    )


async def read_upload(file: UploadFile) -> bytes:
    """Read the body with a hard cap (a 5 MB ceiling, never an unbounded read)."""
    raw = await file.read(MAX_READ)
    if len(raw) > avatar_store.MAX_INPUT_BYTES:
        raise rejected_http(
            avatar_store.AvatarRejected(
                "Rasm juda katta — 5 MB dan kichikroq fayl tanlang."
            )
        )
    return raw


def store_upload(db: Session, user_id: int, raw: bytes, *, source: str) -> AvatarOut:
    """Shared by the Mini App and the bot: normalise, store, describe."""
    try:
        row = avatar_store.store(db, user_id, raw, source=source)
    except avatar_store.AvatarRejected as exc:
        raise rejected_http(exc)
    return avatar_out(row)


@router.post("/me/avatar", response_model=AvatarOut)
async def upload_avatar(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> AvatarOut:
    """Put a picture on the caller's own profile (replaces any previous one)."""
    raw = await read_upload(file)
    return store_upload(db, user.id, raw, source="upload")


@router.delete("/me/avatar")
def remove_avatar(
    db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> dict:
    """Delete the picture (the profile then shows initials again)."""
    return {"ok": True, "removed": avatar_store.remove(db, user.id)}


@router.get("/avatars/{user_id}/{slug}")
def get_avatar(
    user_id: int,
    slug: str,
    if_none_match: str = Header(default="", alias="If-None-Match"),
    db: Session = Depends(get_db),
) -> Response:
    """Serve the (downscaled, EXIF-free) picture behind its capability URL.

    The URL is unique per upload, so the bytes can be cached forever; a re-upload
    hands the Mini App a NEW url and the browser refetches. `If-None-Match` keeps
    a busy chat from re-downloading every face on each poll.
    """
    row = db.scalar(
        select(UserAvatar).where(
            UserAvatar.user_id == user_id, UserAvatar.slug == slug
        )
    )
    if row is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail={"error": "avatar_not_found", "message_uz": "Rasm topilmadi."},
        )
    etag = f'"{slug}"'
    if if_none_match.strip() == etag:
        return Response(status_code=status.HTTP_304_NOT_MODIFIED, headers={"ETag": etag})
    return Response(
        content=row.data,
        media_type=row.mime,
        headers={
            "Cache-Control": "public, max-age=31536000, immutable",
            "ETag": etag,
        },
    )
