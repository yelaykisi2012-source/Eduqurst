"""
tests/test_bot_status.py — the status board the bot thread writes to.

/api/bot-status answers one question: is the Telegram bot alive inside this
container? Two promises are tested here:
  1. it answers usefully (phase, restarts, heartbeat age);
  2. it leaks nothing — no token, no telegram id, no pupil name. The field set
     is asserted exactly, so a future "helpful" addition cannot sneak a secret
     onto a public endpoint by accident.
"""
import json

import pytest

from app import bot_status

FIELDS = {
    "phase",
    "restarts",
    "last_error",
    "last_error_detail",
    "uptime_seconds",
    "last_heartbeat_ok",
    "heartbeat_age_seconds",
    "server_time",
}


@pytest.fixture(autouse=True)
def clean_board():
    bot_status.reset()
    yield
    bot_status.reset()


class TestBoard:
    def test_a_board_nobody_wrote_on_is_not_claiming_the_bot_runs(self):
        state = bot_status.snapshot()
        assert state["phase"] == "not_started"
        assert state["last_heartbeat_ok"] is None
        assert state["heartbeat_age_seconds"] is None
        assert state["uptime_seconds"] is None

    def test_heartbeat_proves_the_loop_is_turning(self):
        bot_status.update(phase="starting", started_at=1_000.0)
        bot_status.heartbeat(True)
        state = bot_status.snapshot()
        assert state["phase"] == "running"
        assert state["last_heartbeat_ok"] is True
        assert state["heartbeat_age_seconds"] < 5
        assert state["uptime_seconds"] > 0

    def test_a_failed_ping_is_not_reported_as_healthy(self):
        bot_status.heartbeat(True)
        bot_status.heartbeat(False)
        state = bot_status.snapshot()
        assert state["last_heartbeat_ok"] is False
        assert state["phase"] == "unreachable"

    def test_restarts_are_counted_and_the_error_is_a_class_name(self):
        bot_status.update(phase="crashed", last_error="SystemExit")
        bot_status.note_restart()
        bot_status.note_restart()
        state = bot_status.snapshot()
        assert state["restarts"] == 2
        assert state["last_error"] == "SystemExit"

    def test_the_one_line_detail_reaches_the_board(self):
        """Without it a crash-loop on Render is unfixable from the outside."""
        bot_status.update(
            phase="crashed", last_error="RuntimeError", last_error_detail="Polling is not started"
        )
        state = bot_status.snapshot()
        assert state["last_error_detail"] == "Polling is not started"

    def test_snapshot_is_json_safe(self):
        bot_status.heartbeat(True)
        json.dumps(bot_status.snapshot())  # must not raise


class TestEndpoint:
    def test_reports_the_board(self, client):
        bot_status.update(phase="running", started_at=1, restarts=1, last_error="X")
        body = client.get("/api/bot-status").json()
        assert body["phase"] == "running"
        assert body["restarts"] == 1
        assert body["last_error"] == "X"

    def test_field_set_is_exactly_the_public_one(self, client):
        assert set(client.get("/api/bot-status").json()) == FIELDS

    def test_nothing_secret_can_ride_along(self, client):
        from app.config import get_settings

        settings = get_settings()
        # What the board is allowed to hold: names, counters, one scrubbed line.
        bot_status.update(
            phase="crashed",
            last_error="TelegramUnauthorizedError",
            last_error_detail="Telegram server says - Unauthorized",
        )
        text = client.get("/api/bot-status").text
        for secret in (
            settings.BOT_TOKEN,
            settings.JWT_SECRET,
            str(settings.DATABASE_URL),
        ):
            assert secret and secret not in text
        assert "999000111" not in text  # the admin id used across this suite
