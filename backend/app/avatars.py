"""
app/avatars.py — pupils' profile pictures, stored safely.

WHY BYTES IN POSTGRES
---------------------
Render's filesystem is ephemeral: every redeploy wipes whatever a process wrote
to disk, so uploaded pictures cannot live in a folder. They are stored as small
re-encoded bytes in the `user_avatars` table instead (same reason the lesson
materials are Telegram-hosted rather than kept locally).

WHY THE URL LOOKS WEIRD
-----------------------
An <img> tag cannot send an Authorization header, so the picture cannot sit
behind the normal JWT check. It is served from an unguessable capability URL:

    /api/avatars/{user_id}/{slug}

`slug` is 32 random hex characters and it ROTATES on every re-upload, so an old
link dies as soon as the pupil changes their picture. Nothing about a pupil is
readable from the URL — it only ever returns the already-public 256px square.

WHAT `normalise()` GUARANTEES
-----------------------------
  * only real image files get in (JPEG / PNG / WEBP / GIF first frame);
  * the stored bytes are a centre-cropped square, at most 256px, ~10-40 KB;
  * EXIF is GONE: re-encoding into a fresh image container drops the GPS position
    and camera details a phone photo carries — that is a privacy requirement for
    a school app, not a tidy-up;
  * oversized / absurdly small / decompression-bomb files are refused with an
    Uzbek message the pupil can act on.
"""
from __future__ import annotations

import io
import secrets

from PIL import Image, ImageOps, UnidentifiedImageError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import UserAvatar

MAX_INPUT_BYTES = 5 * 1024 * 1024  # a phone selfie is well under this
MAX_OUTPUT_EDGE = 256             # stored/displayed size
MIN_SOURCE_EDGE = 32              # below this it is only mush
MAX_SOURCE_PIXELS = 40_000_000    # decompression-bomb guard
JPEG_QUALITY = 82

# Format Pillow detected -> mime we serve. GIF becomes PNG (its first frame,
# so a profile picture can never be a 20-frame animation).
ALLOWED_FORMATS = {
    "JPEG": "image/jpeg",
    "PNG": "image/png",
    "WEBP": "image/webp",
    "GIF": "image/png",
    "BMP": "image/png",
}


class AvatarRejected(ValueError):
    """Raised with a pupil-readable Uzbek message; routers turn it into 422."""


def new_slug() -> str:
    """32 hex chars — the unguessable part of the avatar URL."""
    return secrets.token_hex(16)


def public_path(user_id: int, slug: str) -> str:
    """Relative URL the Mini App prefixes with its API base."""
    return f"/api/avatars/{user_id}/{slug}"


def normalise(raw: bytes) -> tuple[bytes, str, int]:
    """Return (bytes, mime, edge) for a clean square profile picture.

    Raises AvatarRejected for anything we do not want in the database.
    """
    if not raw:
        raise AvatarRejected("Rasm bo‘sh — fayl yuklanmagan.")
    if len(raw) > MAX_INPUT_BYTES:
        raise AvatarRejected(
            "Rasm juda katta — 5 MB dan kichikroq fayl tanlang."
        )

    # 1) Is it an image at all? verify() checks the header/structure without
    #    decoding pixels (cheap + safe against malformed files).
    try:
        probe = Image.open(io.BytesIO(raw))
        fmt = (probe.format or "").upper()
        probe.verify()
    except UnidentifiedImageError:
        raise AvatarRejected("Bu rasm fayli emas — JPG, PNG yoki WEBP tanlang.")
    except Exception:
        raise AvatarRejected("Rasmni o‘qib bo‘lmadi — boshqa fayl tanlang.")
    if fmt not in ALLOWED_FORMATS:
        raise AvatarRejected(
            "Bunday rasm turi qabul qilmaydi — JPG, PNG yoki WEBP tanlang."
        )

    # 2) Reopen for the real work (verify() leaves the object unusable).
    img = Image.open(io.BytesIO(raw))
    if img.width * img.height > MAX_SOURCE_PIXELS:
        raise AvatarRejected("Rasm juda katta o‘lchamda — boshqa fayl tanlang.")

    # 3) Honour the phone's rotation flag BEFORE cropping, otherwise a portrait
    #    shot taken sideways comes out cropped through the middle.
    img = ImageOps.exif_transpose(img)

    has_alpha = img.mode in ("RGBA", "LA", "PA") or (
        img.mode == "P" and "transparency" in img.info
    )
    img = img.convert("RGBA" if has_alpha else "RGB")

    w, h = img.size
    edge = min(w, h)
    if edge < MIN_SOURCE_EDGE:
        raise AvatarRejected(
            f"Rasm juda kichik — kamida {MIN_SOURCE_EDGE}x{MIN_SOURCE_EDGE} px kerak."
        )

    # 4) Centre-crop to a square, then downscale.
    left, top = (w - edge) // 2, (h - edge) // 2
    img = img.crop((left, top, left + edge, top + edge))
    img = img.resize((MAX_OUTPUT_EDGE, MAX_OUTPUT_EDGE), Image.LANCZOS)

    # 5) Paste into a brand-new container: this is what actually drops EXIF,
    #    because `info` (exif / icc / xmp keys) is NOT copied over.
    clean = Image.new(img.mode, img.size)
    clean.paste(img, (0, 0))

    buf = io.BytesIO()
    if has_alpha:
        clean.save(buf, format="PNG", optimize=True)
        mime = "image/png"
    else:
        clean.save(buf, format="JPEG", quality=JPEG_QUALITY, optimize=True)
        mime = "image/jpeg"
    data = buf.getvalue()
    if not data:
        raise AvatarRejected("Rasmni saqlab bo‘lmadi — boshqa fayl tanlang.")
    return data, mime, MAX_OUTPUT_EDGE


def get(db: Session, user_id: int) -> UserAvatar | None:
    return db.scalar(select(UserAvatar).where(UserAvatar.user_id == user_id))


def store(db: Session, user_id: int, raw: bytes, *, source: str) -> UserAvatar:
    """Normalise `raw` and put it on the pupil's account (one row per user).

    The slug is regenerated every time, so the old cached URL stops working —
    that is how "I removed my picture" behaves honestly in the browser.
    """
    data, mime, edge = normalise(raw)
    row = get(db, user_id)
    if row is None:
        row = UserAvatar(user_id=user_id)
        db.add(row)
    row.slug = new_slug()
    row.mime = mime
    row.width = edge
    row.size_bytes = len(data)
    row.source = source
    row.data = data
    db.commit()
    db.refresh(row)
    return row


def remove(db: Session, user_id: int) -> bool:
    """Delete the picture; True if there was one to delete."""
    row = get(db, user_id)
    if row is None:
        return False
    db.delete(row)
    db.commit()
    return True
