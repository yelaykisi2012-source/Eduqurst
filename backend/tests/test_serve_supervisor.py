"""
tests/test_serve_supervisor.py — the bot supervisor inside serve.py.

One promise, tested from every side: the Telegram bot may crash, exit or hang
up — the API must stay up, and the board must say what happened. These tests
never start uvicorn or Telegram; they drive bot_loop() with fake jobs and a
fake stop event, so no test waits a real second.
"""
import sys
import threading
from pathlib import Path

import pytest

# serve.py lives at the repository root, next to bot/ and backend/.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import serve  # noqa: E402
from app import bot_status  # noqa: E402


class FakeStop:
    """A threading.Event that records the backoff instead of really sleeping."""

    def __init__(self, stops_after=None):
        self.waited = []
        self.calls = 0
        self.stops_after = stops_after
        self._set = False

    def is_set(self):
        return self._set

    def wait(self, timeout):
        self.calls += 1
        self.waited.append(timeout)
        if self.stops_after is not None and self.calls >= self.stops_after:
            self._set = True
        return self._set


class FailingJob:
    """Raises `times` failures, then behaves like a bot that stopped cleanly."""

    def __init__(self, times, error_factory=lambda: RuntimeError("polling died")):
        self.times = times
        self.error_factory = error_factory
        self.calls = 0

    def __call__(self):
        self.calls += 1
        if self.calls <= self.times:
            raise self.error_factory()


@pytest.fixture(autouse=True)
def clean_board():
    bot_status.reset()
    yield
    bot_status.reset()


class TestSupervisor:
    def test_a_crashing_bot_is_restarted_not_mourned(self):
        job = FailingJob(times=2)
        stop = FakeStop(stops_after=2)
        serve.bot_loop(stop, job=job, delays=(1, 2, 3))
        assert job.calls == 2  # the supervisor stopped waiting, it did not retry
        assert bot_status.snapshot()["restarts"] == 2

    def test_backoff_grows_and_caps_at_the_last_step(self):
        job = FailingJob(times=99)
        stop = FakeStop(stops_after=5)
        serve.bot_loop(stop, job=job, delays=(5, 15, 30))
        assert stop.waited == [5, 15, 30, 30, 30]

    def test_a_long_healthy_run_resets_the_ladder(self):
        job = FailingJob(times=99)
        stop = FakeStop(stops_after=3)
        # healthy_seconds=0 → every crash "ran long enough", so backoff restarts
        serve.bot_loop(stop, job=job, delays=(5, 300), healthy_seconds=0)
        assert stop.waited == [5, 5, 5]

    def test_system_exit_does_not_swallow_the_supervisor(self):
        """bot/main.py sys.exit(0)s when another poller holds the lock.

        SystemExit is a BaseException, not an Exception: catching only
        Exception would let the bot thread disappear while the API cheerfully
        reported no crash at all.
        """
        job = FailingJob(times=2, error_factory=lambda: SystemExit(0))
        stop = FakeStop(stops_after=2)
        serve.bot_loop(stop, job=job, delays=(1,))
        state = bot_status.snapshot()
        assert state["restarts"] == 2
        assert state["last_error"] == "SystemExit"

    def test_a_clean_stop_is_not_counted_as_a_crash(self):
        job = FailingJob(times=0)
        stop = FakeStop()
        serve.bot_loop(stop, job=job)
        state = bot_status.snapshot()
        assert state["phase"] == "stopped"
        assert state["restarts"] == 0
        assert stop.waited == []

    def test_keyboard_interrupt_is_never_eaten(self):
        with pytest.raises(KeyboardInterrupt):
            serve.bot_loop(FakeStop(), job=_raise_keyerror)


def _raise_keyerror():
    raise KeyboardInterrupt


class TestErrorDetail:
    """The public board may carry ONE line about the crash — never a secret.

    Without it a crash-loop on Render cannot be diagnosed from outside, because
    nobody is sitting at a terminal with the logs open.
    """

    def test_a_bot_token_inside_the_message_is_scrubbed(self, monkeypatch):
        monkeypatch.setenv("BOT_TOKEN", "123456:SECRETVALUE")
        detail = serve.safe_error_detail(
            RuntimeError("token 123456:SECRETVALUE was rejected")
        )
        assert "SECRETVALUE" not in detail
        assert "rejected" in detail

    def test_a_database_url_inside_the_message_is_scrubbed(self, monkeypatch):
        monkeypatch.setenv("DATABASE_URL", "postgresql://user:pw@ep-x.neon.tech/db")
        detail = serve.safe_error_detail(
            RuntimeError("could not connect to postgresql://user:pw@ep-x.neon.tech/db")
        )
        assert "pw@ep-x" not in detail

    def test_a_long_traceback_line_is_cut_short(self):
        assert len(serve.safe_error_detail(RuntimeError("x" * 5000))) <= 240

    def test_multiline_becomes_one_line(self):
        assert serve.safe_error_detail(RuntimeError("a\n   b")) == "a b"

    def test_an_empty_message_still_says_what_died(self):
        assert serve.safe_error_detail(ValueError()) == "ValueError"

    def test_the_board_learns_the_reason_after_a_crash(self):
        job = FailingJob(times=1, error_factory=lambda: RuntimeError("Polling is not started"))
        serve.bot_loop(FakeStop(stops_after=1), job=job, delays=(1,))
        state = bot_status.snapshot()
        assert state["last_error"] == "RuntimeError"
        assert state["last_error_detail"] == "Polling is not started"

    def test_a_fresh_attempt_clears_the_previous_reason(self):
        job = FailingJob(times=1, error_factory=lambda: RuntimeError("birinchi xato"))
        serve.bot_loop(FakeStop(stops_after=2), job=job, delays=(1, 1))
        state = bot_status.snapshot()
        assert state["last_error_detail"] is None, "yangi urinish — eski xato o'chsin"


class TestMissingBot:
    def test_no_bot_folder_means_disabled_not_an_endless_retry_loop(self, tmp_path, monkeypatch):
        monkeypatch.setattr(serve, "BOT_DIR", tmp_path / "absent")
        stop = FakeStop()
        serve.bot_loop(stop)  # default job: run_bot_once
        assert bot_status.snapshot()["phase"] == "disabled"
        assert stop.calls == 0


class TestWiring:
    def test_status_board_endpoint_is_registered(self):
        from app.main import app

        # FastAPI keeps lazily-included routers as _IncludedRouter placeholders,
        # so the OpenAPI map — not app.routes — is the honest list of paths.
        assert "/api/bot-status" in app.openapi()["paths"]

    def test_the_container_entry_is_serve_not_bare_uvicorn(self):
        """If the Dockerfile stops calling serve.py the bot silently never runs."""
        dockerfile = (serve.ROOT / "Dockerfile").read_text(encoding="utf-8")
        assert "CMD python serve.py" in dockerfile
        assert "COPY bot ./bot" in dockerfile
        assert "bot-requirements.txt" in dockerfile

