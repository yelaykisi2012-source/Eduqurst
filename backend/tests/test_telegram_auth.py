"""
Regression guard for initData validation, using Telegram's OWN published
sample (the exact vector the official init-data-golang library tests with,
including its public bot token).

Why this file exists: forged test data signed with our own (wrong) reading of
the algorithm always "passes" — it cannot catch a wrong reading. This vector
can: signing the RAW percent-encoded values rejects it, signing the DECODED
values reproduces the published hash. It is what proves the real fix.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import time
from urllib.parse import quote

import pytest

from app.telegram_auth import TelegramAuthError, verify_init_data

OFFICIAL_INIT_DATA = (
    "query_id=AAHdF6IQAAAAAN0XohDhrOrc"
    "&user=%7B%22id%22%3A279058397%2C%22first_name%22%3A%22Vladislav%22"
    "%2C%22last_name%22%3A%22Kibenko%22%2C%22username%22%3A%22vdkfrost%22"
    "%2C%22language_code%22%3A%22ru%22%2C%22is_premium%22%3Atrue%7D"
    "&auth_date=1662771648"
    "&hash=c501b71e775f74ce10e377dea85a7ea24ecd640b223ea86dfe453e0eaed2e2b2"
)
OFFICIAL_BOT_TOKEN = "5768337691:AAH5YkoiEuPk8-FZa32hStHTqXiLPtAEhx8"


def test_official_telegram_sample_validates():
    # Old auth_date: real logins still cap at 24h, this test only checks the HMAC.
    user = verify_init_data(
        OFFICIAL_INIT_DATA, OFFICIAL_BOT_TOKEN, max_age_seconds=10**10
    )
    assert user["id"] == 279058397
    assert user["first_name"] == "Vladislav"


def test_tampered_official_sample_is_rejected():
    tampered = OFFICIAL_INIT_DATA.replace("Vladislav", "Vladislaw")
    with pytest.raises(TelegramAuthError):
        verify_init_data(tampered, OFFICIAL_BOT_TOKEN, max_age_seconds=10**10)


def test_official_sample_rejected_with_wrong_bot_token():
    with pytest.raises(TelegramAuthError):
        verify_init_data(
            OFFICIAL_INIT_DATA, "000000:WRONG_TOKEN", max_age_seconds=10**10
        )


# --- compatibility variants -------------------------------------------------
# Real clients/validators have been observed signing different constructions
# (decoded vs raw values; signature field included or excluded). All of them
# are keyed by the bot token, so accepting each one is safe.

def _build_init_data(*, signing: str, drop_signature: bool) -> str:
    token = os.environ["BOT_TOKEN"]  # fake token set by conftest
    fields = {
        "query_id": "compatquery",
        "user": json.dumps(
            {"id": 424242, "first_name": "Kompat", "username": "compat_user"},
            separators=(",", ":"),
        ),
        "auth_date": str(int(time.time())),
        "signature": "ZmFrZS1zaWduYXR1cmU",
    }
    if signing == "decoded":
        check_fields = dict(fields)
    else:
        check_fields = {k: quote(v, safe="") for k, v in fields.items()}
    if drop_signature:
        check_fields.pop("signature", None)
    check_string = "\n".join(f"{k}={v}" for k, v in sorted(check_fields.items()))
    secret = hmac.new(b"WebAppData", token.encode(), hashlib.sha256).digest()
    digest = hmac.new(secret, check_string.encode(), hashlib.sha256).hexdigest()
    parts = [f"{k}={quote(v, safe='')}" for k, v in sorted(fields.items())]
    parts.append("hash=" + digest)
    return "&".join(parts)


@pytest.mark.parametrize(
    "signing,drop_signature",
    [
        ("decoded", True),   # official
        ("raw", True),       # legacy raw signing
        ("decoded", False),  # signature folded in (some validators)
        ("raw", False),
    ],
)
def test_known_initdata_variants_are_accepted(signing: str, drop_signature: bool):
    data = _build_init_data(signing=signing, drop_signature=drop_signature)
    user = verify_init_data(data, os.environ["BOT_TOKEN"])
    assert user["id"] == 424242


def test_variants_still_reject_tampering():
    data = _build_init_data(signing="raw", drop_signature=False)
    tampered = data.replace("Kompat", "KompatX")
    with pytest.raises(TelegramAuthError):
        verify_init_data(tampered, os.environ["BOT_TOKEN"])

