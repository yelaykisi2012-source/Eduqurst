"""
app/chat_media.py — the picture, GIF or video a pupil throws into a chat.

WHAT ENDS UP IN THE DATABASE (and why)
--------------------------------------
Pupils send a lot of pictures, and the free Postgres they run on has a size
limit. So a chat picture never reaches the database as the phone sent it:

  * image  — decoded, EXIF stripped (a phone photo carries GPS position),
    downscaled to at most MAX_IMAGE_EDGE on the long side, re-encoded as
    JPEG/WEBP/PNG. A typical result is 60-250 KB, and anything that still comes
    out over CHAT_IMAGE_MAX_BYTES is refused with a message the pupil can act on.
  * gif    — kept as the original bytes, because re-encoding an animation with
    Pillow would drop its frames (a "GIF" that stops moving is not a GIF). It is
    instead *checked*: real GIF header, frame count and edge capped, size capped.
    GIFs carry no EXIF/GPS, so the privacy reason for re-encoding does not apply.
  * video  — never stored in Postgres. It is handed to the Telegram bot (the
    same path lesson videos already use) and only the file_id is kept; the Mini
    App plays it through the backend proxy so the bot token never reaches a URL.

THE SLUG IS THE GUARD
---------------------
An <img>/<video> tag cannot send an Authorization header, so media is served
from /api/chat/media/{slug} — 32 random hex characters, unguessable, exactly
like a profile picture or a certificate code. A deleted message takes its media
row with it (FK CASCADE), which makes the link dead.
"""
from __future__ import annotations

import io

from PIL import Image, ImageOps, UnidentifiedImageError

from app.config import get_settings

IMAGE = "image"
GIF = "gif"
VIDEO = "video"

MAX_IMAGE_EDGE = 1024      # a chat bubble never shows more than this
GIF_MAX_EDGE = 480         # animations are heavier: deliberately smaller
MIN_EDGE = 24              # below this it is only mush
MAX_GIF_FRAMES = 120       # a wallpaper-length animation is not a chat reply
MAX_SOURCE_PIXELS = 40_000_000
JPEG_QUALITY = 78

# What a phone browser puts in Content-Type when a pupil picks a video.
VIDEO_TYPES = {
    "video/mp4",
    "video/quicktime",
    "video/webm",
    "video/x-m4v",
    "video/3gpp",
    "video/3gpp2",
    "video/ogg",
}
# Formats we are willing to decode into a still picture.
IMAGE_TYPES = {"image/jpeg", "image/pjpeg", "image/png", "image/webp", "image/bmp"}


class MediaRejected(ValueError):
    """Raised with an Uzbek message the Mini App shows as-is (router -> 422)."""


def human_size(n: int) -> str:
    """2 MB or 500 KB — a pupil can act on either; "0 MB" cannot be acted on."""
    return f"{n // 1024} KB" if n < 1024 * 1024 else f"{round(n / (1024 * 1024))} MB"


def media_max_bytes(kind: str) -> int:
    settings = get_settings()
    if kind == VIDEO:
        return settings.CHAT_VIDEO_MAX_BYTES
    return settings.CHAT_IMAGE_MAX_BYTES


def kind_for(content_type: str, filename: str) -> str:
    """Decide image / gif / video from what the browser claims + the name.

    The extension is a fallback, not the rule: a file is only accepted once the
    bytes themselves are identified below (a renamed .exe stays a rejected blob).
    """
    ctype = (content_type or "").split(";")[0].strip().lower()
    name = (filename or "").lower()
    if ctype == "image/gif" or name.endswith(".gif"):
        return GIF
    if ctype in VIDEO_TYPES or name.endswith((".mp4", ".mov", ".webm", ".m4v", ".3gp", ".ogv")):
        return VIDEO
    if ctype in IMAGE_TYPES or name.endswith((".jpg", ".jpeg", ".png", ".webp", ".bmp")):
        return IMAGE
    raise MediaRejected(
        "Bu faylni chatga yuborib bo‘lmaydi — rasm, GIF yoki video tanlang."
    )


def _probe(raw: bytes) -> tuple[Image.Image, str]:
    """Identify the bytes for real (verify() checks structure without pixels)."""
    if not raw:
        raise MediaRejected("Fayl bo‘sh — yuklanmagan.")
    try:
        probe = Image.open(io.BytesIO(raw))
        fmt = (probe.format or "").upper()
        probe.verify()
    except UnidentifiedImageError:
        raise MediaRejected("Bu rasm fayli emas — JPG, PNG, WEBP yoki GIF tanlang.")
    except Exception:
        raise MediaRejected("Faylni o‘qib bo‘lmadi — boshqa fayl tanlang.")
    return probe, fmt


def check_size(raw: bytes, kind: str) -> None:
    limit = media_max_bytes(kind)
    if len(raw) > limit:
        label = "video" if kind == VIDEO else "rasm"
        raise MediaRejected(
            f"{label.capitalize()} juda katta — {human_size(limit)} dan kichikroq fayl tanlang."
        )


def normalise_image(raw: bytes) -> tuple[bytes, str, int, int]:
    """Return (bytes, mime, width, height) for a clean, downscaled still picture."""
    probe, fmt = _probe(raw)
    if fmt == "GIF":
        # Someone can send a GIF through the "photo" picker (a renamed file, or a
        # browser that says image/gif). Route it to the GIF rules so the
        # animation survives instead of being flattened into a still.
        data, width, height = accept_gif(raw)
        return data, "image/gif", width, height
    if fmt not in {"JPEG", "PNG", "WEBP", "BMP"}:
        raise MediaRejected("Bunday rasm turi qabul qilmaydi — JPG, PNG yoki WEBP tanlang.")

    img = Image.open(io.BytesIO(raw))
    if img.width * img.height > MAX_SOURCE_PIXELS:
        raise MediaRejected("Rasm juda katta o‘lchamda — boshqa fayl tanlang.")

    # Rotation flag first: a photo taken sideways must not be cropped through
    # the middle of the frame.
    img = ImageOps.exif_transpose(img)
    has_alpha = img.mode in ("RGBA", "LA", "PA") or (
        img.mode == "P" and "transparency" in img.info
    )
    img = img.convert("RGBA" if has_alpha else "RGB")

    if min(img.width, img.height) < MIN_EDGE:
        raise MediaRejected(f"Rasm juda kichik — kamida {MIN_EDGE}x{MIN_EDGE} px kerak.")

    if max(img.width, img.height) > MAX_IMAGE_EDGE:
        img = ImageOps.contain(img, (MAX_IMAGE_EDGE, MAX_IMAGE_EDGE), Image.LANCZOS)

    # A brand-new container is what actually drops EXIF (gps / camera / the
    # phone's serial) — `info` is never copied over.
    clean = Image.new(img.mode, img.size)
    clean.paste(img, (0, 0))

    buf = io.BytesIO()
    if has_alpha:
        clean.save(buf, format="WEBP", quality=JPEG_QUALITY, method=4)
        mime = "image/webp"
    else:
        clean.save(buf, format="JPEG", quality=JPEG_QUALITY, optimize=True)
        mime = "image/jpeg"
    data = buf.getvalue()
    if not data:
        raise MediaRejected("Rasmni saqlab bo‘lmadi — boshqa fayl tanlang.")
    if len(data) > get_settings().CHAT_IMAGE_MAX_BYTES:
        raise MediaRejected(
            "Rasm juda og‘ir — uni qisqartirib yoki yengilroq fayl bilan urinib ko‘ring."
        )
    return data, mime, clean.width, clean.height


def accept_gif(raw: bytes) -> tuple[bytes, int, int]:
    """Validate a GIF and keep its bytes as-is (so the animation survives).

    Returns (bytes, width, height).
    """
    probe, fmt = _probe(raw)
    if fmt != "GIF":
        raise MediaRejected("Bu GIF emas — faylni o‘zgartirmasdan yuboring.")
    check_size(raw, GIF)

    img = Image.open(io.BytesIO(raw))
    if max(img.width, img.height) > GIF_MAX_EDGE:
        raise MediaRejected(
            f"GIF juda katta — {GIF_MAX_EDGE}px dan kichikroqini tanlang."
        )
    if img.n_frames > MAX_GIF_FRAMES:
        raise MediaRejected("GIF juda uzun — qisqaroq animatsiya tanlang.")
    return raw, img.width, img.height


def check_video(raw: bytes, content_type: str, filename: str) -> None:
    """Only size/type checks: the bytes themselves go to Telegram, not Postgres.

    A video cannot be pixel-checked here (Pillow does not read video), so the
    rules are the ones that matter on a free server: a real video type and a
    size the Bot API will still accept.
    """
    kind = kind_for(content_type, filename)
    if kind != VIDEO:
        raise MediaRejected("Video tanlanmagan — rasm, GIF yoki video fayl yuboring.")
    check_size(raw, VIDEO)
