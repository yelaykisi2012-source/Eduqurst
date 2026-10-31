"""Daily streak rules + profile exposure.

Streak days are Asia/Tashkent calendar dates; the helper takes an explicit
`today` in tests so nothing depends on when the suite runs.
"""
from __future__ import annotations

from datetime import date

from fastapi.testclient import TestClient

from app.models import User
from app.streaks import local_today, touch


class _FakeSession:
    """touch() only stages the user; tests don't need a real session."""

    def __init__(self) -> None:
        self.added: list[User] = []

    def add(self, obj: User) -> None:
        self.added.append(obj)


def _user() -> User:
    return User(first_name="Ali", current_streak=0, max_streak=0)


def test_first_action_starts_the_streak():
    db, user = _FakeSession(), _user()
    assert touch(db, user, date(2026, 10, 31)) is True
    assert user.current_streak == 1
    assert user.max_streak == 1
    assert user.last_active_date == date(2026, 10, 31)


def test_same_day_is_idempotent():
    db, user = _FakeSession(), _user()
    touch(db, user, date(2026, 10, 31))
    assert touch(db, user, date(2026, 10, 31)) is False
    assert user.current_streak == 1


def test_consecutive_days_grow_and_remember_max():
    db, user = _FakeSession(), _user()
    for day in (1, 2, 3):
        touch(db, user, date(2026, 10, day))
    assert user.current_streak == 3
    assert user.max_streak == 3

    # Missed 4-Oct → restart at 1, max stays 3.
    touch(db, user, date(2026, 10, 5))
    assert user.current_streak == 1
    assert user.max_streak == 3


def test_clock_skew_restarts_instead_of_going_negative():
    db, user = _FakeSession(), _user()
    touch(db, user, date(2026, 10, 31))
    touch(db, user, date(2026, 10, 1))
    assert user.current_streak == 1
    assert user.last_active_date == date(2026, 10, 1)


def test_local_today_uses_tashkent_midnight():
    from datetime import datetime, timezone

    # 2026-10-31 19:30 UTC == 2026-11-01 00:30 in Tashkent (UTC+5).
    assert local_today(datetime(2026, 10, 31, 19, 30, tzinfo=timezone.utc)) == date(
        2026, 11, 1
    )


def test_profile_reports_the_streak(client: TestClient):
    reg = client.post(
        "/api/auth/register",
        json={"login": "streak_pupil", "password": "maxfiy123", "first_name": "Ali"},
    )
    assert reg.status_code == 201, reg.text
    headers = {"Authorization": f"Bearer {reg.json()['access_token']}"}

    me = client.get("/api/me", headers=headers)
    assert me.status_code == 200, me.text
    assert me.json()["current_streak"] == 1
    assert me.json()["max_streak"] == 1

    # Opening the app again on the same day does not double count.
    again = client.get("/api/me", headers=headers)
    assert again.json()["current_streak"] == 1
