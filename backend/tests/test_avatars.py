"""
Profile pictures (avatars).

Two promises are tested here, because both are about a real child's privacy:

  1. WHAT WE STORE — whatever the pupil uploads becomes a 256px square, and the
     camera metadata (make/model/GPS) that a phone photo carries is gone. A
     school app must not keep where a child's photo was taken.
  2. WHO CAN SEE IT — the picture is served without a JWT (an <img> cannot send
     one) through an unguessable URL that ROTATES on every re-upload, so
     "remove my picture" also breaks the link that was already out there.
"""
from __future__ import annotations

import io
import os

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app import avatars
from tests.conftest import login_as

BOT_HEADERS = {"X-Bot-Token": os.environ["BOT_TOKEN"]}


def jpeg_with_exif(size: tuple[int, int] = (900, 1200)) -> bytes:
    """A real phone-shaped photo: portrait, EXIF make/model + a GPS sub-IFD."""
    img = Image.new("RGB", size, (30, 60, 90))
    exif = Image.Exif()
    exif[271] = "NOKIA"  # Make
    exif[272] = "XpressMusic"  # Model
    exif.get_ifd(0x8825)[1] = "N"  # GPSLatitudeRef — a position, not a label
    buf = io.BytesIO()
    img.save(buf, format="JPEG", exif=exif.tobytes())
    return buf.getvalue()


def png_with_alpha(size: tuple[int, int] = (400, 400)) -> bytes:
    img = Image.new("RGBA", size, (200, 30, 30, 128))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


# ---------- app/avatars.py: what lands in the database ----------
def test_normalise_crops_squares_and_strips_exif():
    data, mime, edge = avatars.normalise(jpeg_with_exif())
    img = Image.open(io.BytesIO(data))

    assert mime == "image/jpeg"
    assert edge == avatars.MAX_OUTPUT_EDGE == img.size[0] == img.size[1]
    assert len(data) < avatars.MAX_INPUT_BYTES

    stored = img.getexif()
    assert stored.get(271) is None, "camera make must not survive re-encoding"
    assert stored.get(272) is None, "camera model must not survive re-encoding"
    assert not stored.get_ifd(0x8825), "GPS data must never be stored"


def test_normalise_keeps_transparency_as_png():
    data, mime, _ = avatars.normalise(png_with_alpha())
    img = Image.open(io.BytesIO(data))
    assert mime == "image/png", "an alpha picture must not be flattened onto black"
    assert img.mode == "RGBA"


@pytest.mark.parametrize(
    "raw,why",
    [
        (b"", "empty"),
        (b"\x00\x01\x02not an image at all", "not an image"),
        (b"%PDF-1.4\n", "a pdf is not a picture"),
    ],
)
def test_normalise_rejects_non_images(raw, why):
    with pytest.raises(avatars.AvatarRejected):
        avatars.normalise(raw)


def test_normalise_rejects_too_small_and_too_big():
    tiny = io.BytesIO()
    Image.new("RGB", (8, 8)).save(tiny, format="PNG")
    with pytest.raises(avatars.AvatarRejected, match="kichik"):
        avatars.normalise(tiny.getvalue())

    with pytest.raises(avatars.AvatarRejected, match="5 MB"):
        avatars.normalise(b"x" * (avatars.MAX_INPUT_BYTES + 1))


def test_store_rotates_the_slug_and_replaces_the_row():
    """One picture per pupil: re-uploading never leaves a second row behind."""
    from app.db import SessionLocal
    from app.models import UserAvatar

    with SessionLocal() as db:
        user = login_user(db)
        # capture the strings, not the ORM objects: one row is updated in place,
        # so the same object would show the NEW slug twice.
        first_slug = avatars.store(db, user.id, jpeg_with_exif(), source="upload").slug
        second = avatars.store(db, user.id, png_with_alpha(), source="telegram")
        assert first_slug != second.slug, "old URL must die when a new picture comes in"
        assert second.source == "telegram"
        assert second.size_bytes == len(second.data) > 0
        rows = db.query(UserAvatar).filter_by(user_id=user.id).all()
        assert len(rows) == 1
        assert avatars.remove(db, user.id) is True
        assert avatars.remove(db, user.id) is False


def login_user(db):
    """A throwaway pupil for the pure-service test above."""
    from app.models import User

    user = User(telegram_id=771000901, first_name="Rasmtest")
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


# ---------- the HTTP surface ----------
def test_upload_then_profile_then_public_url(client: TestClient):
    auth = login_as(client, {"id": 771000902, "first_name": "Surat"})
    assert client.get("/api/me", headers=auth).json()["avatar_url"] is None

    resp = client.post(
        "/api/me/avatar", headers=auth, files={"file": ("rasm.jpg", jpeg_with_exif(), "image/jpeg")}
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["source"] == "upload"
    assert body["width"] == 256 and body["mime"] == "image/jpeg"

    # /api/me now carries the URL the Mini App puts in <img src>
    profile = client.get("/api/me", headers=auth).json()
    assert profile["avatar_url"] == body["avatar_url"]

    # the public route needs NO token (that is the whole point of the slug)
    got = client.get(body["avatar_url"])
    assert got.status_code == 200
    assert got.headers["content-type"].startswith("image/jpeg")
    assert "immutable" in got.headers["cache-control"]
    assert len(got.content) == body["size_bytes"]
    assert Image.open(io.BytesIO(got.content)).getexif().get(271) is None


def test_public_url_is_unguessable_and_rotates(client: TestClient):
    auth = login_as(client, {"id": 771000903, "first_name": "Aylantir"})
    old = client.post(
        "/api/me/avatar", headers=auth, files={"file": ("a.jpg", jpeg_with_exif(), "image/jpeg")}
    ).json()["avatar_url"]

    # a wrong slug for a real user id is a 404, not the picture
    user_id = old.split("/")[3]
    assert client.get(f"/api/avatars/{user_id}/{'0' * 32}").status_code == 404

    new = client.post(
        "/api/me/avatar", headers=auth, files={"file": ("b.jpg", jpeg_with_exif(), "image/jpeg")}
    ).json()["avatar_url"]
    assert new != old
    assert client.get(old).status_code == 404, "the previous URL must stop working"
    assert client.get(new).status_code == 200


def test_delete_avatar_removes_it_everywhere(client: TestClient):
    auth = login_as(client, {"id": 771000904, "first_name": "Ochir"})
    url = client.post(
        "/api/me/avatar", headers=auth, files={"file": ("a.jpg", jpeg_with_exif(), "image/jpeg")}
    ).json()["avatar_url"]

    assert client.delete("/api/me/avatar", headers=auth).json() == {"ok": True, "removed": True}
    assert client.get("/api/me", headers=auth).json()["avatar_url"] is None
    assert client.get(url).status_code == 404
    # deleting twice is honest about there being nothing to delete
    assert client.delete("/api/me/avatar", headers=auth).json()["removed"] is False


def test_etag_makes_a_repeat_fetch_free(client: TestClient):
    auth = login_as(client, {"id": 771000905, "first_name": "Kesh"})
    url = client.post(
        "/api/me/avatar", headers=auth, files={"file": ("a.jpg", jpeg_with_exif(), "image/jpeg")}
    ).json()["avatar_url"]
    etag = client.get(url).headers["etag"]
    again = client.get(url, headers={"If-None-Match": etag})
    assert again.status_code == 304
    assert not again.content


def test_bad_upload_is_rejected_with_an_actionable_message(client: TestClient):
    auth = login_as(client, {"id": 771000906, "first_name": "Yomon"})
    resp = client.post(
        "/api/me/avatar", headers=auth, files={"file": ("hat.txt", b"men rasm emasman", "text/plain")}
    )
    assert resp.status_code == 422
    detail = resp.json()["detail"]
    assert detail["error"] == "avatar_rejected"
    assert "rasm" in detail["message_uz"].lower()


def test_avatar_routes_need_login(client: TestClient):
    assert client.post("/api/me/avatar", files={"file": ("a.jpg", jpeg_with_exif(), "image/jpeg")}).status_code in (401, 403)
    assert client.delete("/api/me/avatar").status_code in (401, 403)


# ---------- the bot half (Telegram profile photo) ----------
def test_bot_can_push_telegram_photo(client: TestClient):
    login_as(client, {"id": 771000907, "first_name": "Botrasm"})
    resp = client.post(
        "/api/internal/pupils/771000907/avatar",
        headers=BOT_HEADERS,
        files={"file": ("photo.jpg", jpeg_with_exif(), "image/jpeg")}
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["source"] == "telegram"
    assert body["width"] == 256
    got = client.get(body["avatar_url"])
    assert got.status_code == 200
    assert got.headers["content-type"].startswith("image/jpeg")


def test_bot_route_rejects_wrong_token_and_unknown_pupil(client: TestClient):
    bad = client.post(
        "/api/internal/pupils/771000908/avatar",
        headers={"X-Bot-Token": "not-the-bot-token"},
        files={"file": ("a.jpg", jpeg_with_exif(), "image/jpeg")},
    )
    assert bad.status_code == 401
    assert bad.json()["detail"]["error"] == "bad_bot_token"

    missing = client.post(
        "/api/internal/pupils/771000999/avatar",
        headers=BOT_HEADERS,
        files={"file": ("a.jpg", jpeg_with_exif(), "image/jpeg")},
    )
    assert missing.status_code == 404
    assert missing.json()["detail"]["error"] == "pupil_not_found"


def test_bot_rejects_a_non_photo(client: TestClient):
    login_as(client, {"id": 771000909, "first_name": "Fayl"})
    resp = client.post(
        "/api/internal/pupils/771000909/avatar",
        headers=BOT_HEADERS,
        files={"file": ("note.pdf", b"%PDF-1.4", "application/pdf")},
    )
    assert resp.status_code == 422
    assert resp.json()["detail"]["error"] == "avatar_rejected"
