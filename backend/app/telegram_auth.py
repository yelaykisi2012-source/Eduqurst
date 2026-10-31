"""
app/telegram_auth.py — verify Telegram Mini App initData (HMAC-SHA256).

Security rule: the frontend can send ANYTHING it wants. We only trust data
whose `hash` was produced by Telegram itself, i.e. HMAC with a key derived
from OUR bot token. Official algorithm:
  secret_key = HMAC_SHA256(key="WebAppData", data=BOT_TOKEN)
  data_check_string = sorted "key=value" fields, EXCLUDING hash + signature
  hash = HMAC_SHA256(key=secret_key, data=data_check_string)

Telegram's own published sample (query_id=...&user=%7B%22id%22... with its
public bot token, see tests/test_telegram_auth.py) reproduces the published
hash ONLY when values are DECODED before building the check-string. That is
the primary variant.

Real clients/validators have been observed using different constructions
(raw vs decoded values; signature included or excluded), so we accept any
construction whose HMAC matches. Every variant is keyed by the same bot
token — accepting more than one does not weaken security (an attacker still
cannot forge any of them without the token). The decoded parse is always
what we use to READ the user.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import time
from urllib.parse import parse_qsl

logger = logging.getLogger(__name__)


class TelegramAuthError(Exception):
    """Raised when initData is missing, tampered with or too old."""


def _check_string(fields: dict[str, str]) -> str:
    return "\n".join(f"{k}={v}" for k, v in sorted(fields.items()))


def _hmac_hex(secret_key: bytes, data: str) -> str:
    return hmac.new(secret_key, data.encode("utf-8"), hashlib.sha256).hexdigest()


def verify_init_data(init_data: str, bot_token: str, max_age_seconds: int = 86_400) -> dict:
    """Return parsed user dict from a VALID initData string, else raise."""
    if not init_data or not bot_token:
        raise TelegramAuthError("init_data yoki bot token yo'q")

    # Decoded view: the official check-string is built from decoded values
    # (%7B%22... -> {"...). It is also the view we read user/auth_date from.
    decoded: dict[str, str] = dict(parse_qsl(init_data, keep_blank_values=True))
    # Raw view (values still percent-encoded): older validators signed this.
    raw: dict[str, str] = {}
    for pair in init_data.split("&"):
        if "=" in pair:
            key, _, value = pair.partition("=")
            raw[key] = value

    received_hash = decoded.pop("hash", None)
    if not received_hash:
        raise TelegramAuthError("initData'da hash yo'q")
    raw.pop("hash", None)

    signature_present = "signature" in decoded

    try:
        auth_date = int(decoded.get("auth_date", "0"))
    except ValueError as exc:  # pragma: no cover
        raise TelegramAuthError("auth_date buzuq") from exc
    if auth_date <= 0:
        raise TelegramAuthError("initData'da auth_date yo'q")
    now = time.time()
    if auth_date > now + 300:  # allow small clock skew, reject far-future dates
        raise TelegramAuthError("auth_date noto'g'ri (kelajakdan)")
    if now - auth_date > max_age_seconds:
        raise TelegramAuthError("initData muddati o'tgan (24 soat+)")

    def variant(fields: dict[str, str], *, drop_signature: bool) -> dict[str, str]:
        excluded = {"signature"} if drop_signature else set()
        return {k: v for k, v in fields.items() if k not in excluded}

    candidates = {
        # Primary / official: decoded values, hash + signature excluded.
        "decoded_no_sig": _check_string(variant(decoded, drop_signature=True)),
        # Compatibility fallbacks seen in the wild (different clients/libs).
        "raw_no_sig": _check_string(variant(raw, drop_signature=True)),
        "decoded_with_sig": _check_string(variant(decoded, drop_signature=False)),
        "raw_with_sig": _check_string(variant(raw, drop_signature=False)),
    }

    secret_key = hmac.new(b"WebAppData", bot_token.encode("utf-8"), hashlib.sha256).digest()
    matched = [name for name, data in candidates.items()
               if hmac.compare_digest(_hmac_hex(secret_key, data), received_hash)]

    if not matched:
        # Diagnose without leaking values: field names, presence flags and
        # short hash fingerprints are enough to tell algorithm vs token issues.
        logger.warning(
            "initData HMAC mismatch: fields=%s signature=%s auth_date=%s "
            "received=%s computed=%s",
            sorted(decoded.keys()), signature_present, auth_date,
            received_hash[:12],
            {name: _hmac_hex(secret_key, data)[:12] for name, data in candidates.items()},
        )
        raise TelegramAuthError("initData imzosi noto'g'ri (tamlangan?)")

    if matched[0] != "decoded_no_sig":
        # Not an error — just tells us which client/validator format was used.
        logger.info("initData accepted via compatibility variant: %s", matched[0])

    user: dict = {}
    try:
        user = json.loads(decoded.get("user", "{}"))
    except json.JSONDecodeError as exc:  # pragma: no cover
        raise TelegramAuthError("user maydoni JSON emas") from exc
    if not user.get("id"):
        raise TelegramAuthError("user.id yo'q")
    return user


def verify_web_login(data: dict, bot_token: str, max_age_seconds: int = 86_400) -> dict:
    """Verify a Telegram Login Widget payload (browser login, outside Telegram).

    Algorithm (official Login Widget docs):
      secret_key = SHA256(bot_token)
      data_check_string = sorted "key=value" of all fields except hash, "\\n"
      hash = HMAC_SHA256(key=secret_key, data=data_check_string)
    Values are the plain strings/numbers the widget hands to the page; the
    widget signs exactly what it sends, so we sign exactly what we received.
    """
    if not data or not bot_token:
        raise TelegramAuthError("login ma'lumoti yoki bot token yo'q")

    # Drop None so a forwarder that maps missing optional fields to null does
    # not add fields Telegram never signed.
    payload = {k: str(v) for k, v in data.items() if v is not None}
    received_hash = payload.pop("hash", None)
    if not received_hash:
        raise TelegramAuthError("login ma'lumotida hash yo'q")

    try:
        telegram_id = int(payload.get("id", ""))
    except ValueError as exc:
        raise TelegramAuthError("login ma'lumotida id yo'q") from exc
    if telegram_id <= 0:
        raise TelegramAuthError("login ma'lumotida id noto'g'ri")

    try:
        auth_date = int(payload.get("auth_date", "0"))
    except ValueError as exc:
        raise TelegramAuthError("login auth_date buzuq") from exc
    if auth_date <= 0:
        raise TelegramAuthError("login ma'lumotida auth_date yo'q")
    now = time.time()
    if auth_date > now + 300:
        raise TelegramAuthError("login auth_date kelajakdan")
    if now - auth_date > max_age_seconds:
        raise TelegramAuthError("login ma'lumoti eskirgan (24 soat+)")

    check_string = _check_string(payload)
    secret_key = hashlib.sha256(bot_token.encode("utf-8")).digest()
    computed = hmac.new(secret_key, check_string.encode("utf-8"), hashlib.sha256).hexdigest()

    if not hmac.compare_digest(computed, received_hash):
        logger.warning(
            "web login HMAC mismatch: fields=%s received=%s computed=%s",
            sorted(payload.keys()), received_hash[:12], computed[:12],
        )
        raise TelegramAuthError("Telegram login imzosi noto'g'ri")

    return {
        "id": telegram_id,
        "first_name": payload.get("first_name", ""),
        "last_name": payload.get("last_name"),
        "username": payload.get("username"),
        "photo_url": payload.get("photo_url"),
    }

