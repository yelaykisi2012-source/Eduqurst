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
