"""
app/telegram_auth.py — verify Telegram Mini App initData (HMAC-SHA256).

Security rule: the frontend can send ANYTHING it wants. We only trust data
whose `hash` was produced by Telegram itself, i.e. HMAC with a key derived
from OUR bot token. Algorithm (official docs):
  secret_key = HMAC_SHA256(key="WebAppData", data=BOT_TOKEN)
  data_check_string = sorted "key=value" fields, joined with "\n"
  hash = HMAC_SHA256(key=secret_key, data=data_check_string)

Two details that are easy to get wrong — both proven against Telegram's own
published sample (query_id=...&user=%7B%22id%22... with its public bot
token): the published hash is reproduced ONLY when
  1. values are DECODED before building the check-string, and
  2. the Ed25519 `signature` field (sent by Telegram since 2024) and `hash`
     are BOTH excluded.
`user` always arrives percent-encoded, so signing the raw `%7B%22...` text
rejects every real login, while forged test data signed the same wrong way
still passes — a convincing false green.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import time
from urllib.parse import parse_qsl


class TelegramAuthError(Exception):
    """Raised when initData is missing, tampered with or too old."""


def verify_init_data(init_data: str, bot_token: str, max_age_seconds: int = 86_400) -> dict:
    """Return parsed user dict from a VALID initData string, else raise."""
    if not init_data or not bot_token:
        raise TelegramAuthError("init_data yoki bot token yo'q")

    # Telegram signs the DECODED values. parse_qsl turns %7B%22... into
    # {"id":..., which is exactly what ends up in the check-string (verified
    # against the official sample in tests/test_telegram_auth.py).
    fields: dict[str, str] = dict(parse_qsl(init_data, keep_blank_values=True))

    received_hash = fields.pop("hash", None)
    if not received_hash:
        raise TelegramAuthError("initData'da hash yo'q")

    # Telegram 2024+ adds an Ed25519 `signature` field. The HMAC check-string
    # EXCLUDES it (official docs: "except hash and signature"); folding it in
    # breaks every real login.
    fields.pop("signature", None)

    try:
        auth_date = int(fields.get("auth_date", "0"))
    except ValueError as exc:  # pragma: no cover
        raise TelegramAuthError("auth_date buzuq") from exc
    if auth_date <= 0:
        raise TelegramAuthError("initData'da auth_date yo'q")
    now = time.time()
    if auth_date > now + 300:  # allow small clock skew, reject far-future dates
        raise TelegramAuthError("auth_date noto'g'ri (kelajakdan)")
    if now - auth_date > max_age_seconds:
        raise TelegramAuthError("initData muddati o'tgan (24 soat+)")

    check_string = "\n".join(f"{k}={v}" for k, v in sorted(fields.items()))
    secret_key = hmac.new(b"WebAppData", bot_token.encode("utf-8"), hashlib.sha256).digest()
    computed = hmac.new(secret_key, check_string.encode("utf-8"), hashlib.sha256).hexdigest()

    if not hmac.compare_digest(computed, received_hash):
        raise TelegramAuthError("initData imzosi noto'g'ri (tamlangan?)")

    user: dict = {}
    try:
        user = json.loads(fields.get("user", "{}"))
    except json.JSONDecodeError as exc:  # pragma: no cover
        raise TelegramAuthError("user maydoni JSON emas") from exc
    if not user.get("id"):
        raise TelegramAuthError("user.id yo'q")
    return user
