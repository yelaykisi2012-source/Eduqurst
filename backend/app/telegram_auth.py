"""
app/telegram_auth.py — verify Telegram Mini App initData (HMAC-SHA256).

Security rule: the frontend can send ANYTHING it wants. We only trust data
whose `hash` was produced by Telegram itself, i.e. HMAC with a key derived
from OUR bot token. Algorithm (official docs):
  secret_key = HMAC_SHA256(key="WebAppData", data=BOT_TOKEN)
  data_check_string = sorted urlencoded fields except "hash"
  hash = HMAC_SHA256(key=secret_key, data=data_check_string)
"""
from __future__ import annotations

import hashlib
import hmac
import json
import time
from urllib.parse import parse_qsl, urlencode


class TelegramAuthError(Exception):
    """Raised when initData is missing, tampered with or too old."""


def verify_init_data(init_data: str, bot_token: str, max_age_seconds: int = 86_400) -> dict:
    """Return parsed user dict from a VALID initData string, else raise."""
    if not init_data or not bot_token:
        raise TelegramAuthError("init_data yoki bot token yo'q")

    parsed = dict(parse_qsl(init_data, keep_blank_values=True))
    received_hash = parsed.pop("hash", None)
    if not received_hash:
        raise TelegramAuthError("initData'da hash yo'q")

    try:
        auth_date = int(parsed.get("auth_date", "0"))
    except ValueError as exc:  # pragma: no cover
        raise TelegramAuthError("auth_date buzuq") from exc
    if auth_date <= 0:
        raise TelegramAuthError("initData'da auth_date yo'q")
    now = time.time()
    if auth_date > now + 300:  # allow small clock skew, reject far-future dates
        raise TelegramAuthError("auth_date noto'g'ri (kelajakdan)")
    if now - auth_date > max_age_seconds:
        raise TelegramAuthError("initData muddati o'tgan (24 soat+)")

    check_string = urlencode(sorted(parsed.items(), key=lambda kv: kv[0]))
    secret_key = hmac.new(b"WebAppData", bot_token.encode("utf-8"), hashlib.sha256).digest()
    computed = hmac.new(secret_key, check_string.encode("utf-8"), hashlib.sha256).hexdigest()

    if not hmac.compare_digest(computed, received_hash):
        raise TelegramAuthError("initData imzosi noto'g'ri (tamlangan?)")

    user: dict = {}
    try:
        user = json.loads(parsed.get("user", "{}"))
    except json.JSONDecodeError as exc:  # pragma: no cover
        raise TelegramAuthError("user maydoni JSON emas") from exc
    if not user.get("id"):
        raise TelegramAuthError("user.id yo'q")
    return user
