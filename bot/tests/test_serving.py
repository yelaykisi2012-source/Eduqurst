"""
tests/test_serving.py — the bot living inside the API container (serve.py).

The bot now runs in the same process as the FastAPI app, and the only way to
know it is alive from the outside is the heartbeat its keep-alive loop stamps
on app/bot_status. If that loop stops pinging, Render spins the free service
down after 15 idle minutes and every pupil silently loses the bot — so the
ping interval and the heartbeat call are worth testing, not hoping.
"""
from __future__ import annotations

import asyncio
import logging
import os
import sys
import unittest
from unittest.mock import AsyncMock, patch

os.environ.setdefault("BOT_TOKEN", "012345:TEST_TOKEN_NOT_REAL")
os.environ.setdefault("API_URL", "http://127.0.0.1:9")
os.environ.setdefault("MINI_APP_URL", "https://example.com/app")
os.environ.setdefault("ADMIN_USER_IDS", "999000111")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config  # noqa: E402
import main as bot_main  # noqa: E402  (the bot entry point serve.py starts)


class Stop(Exception):
    """Raises itself out of the endless loop so a test can observe one cycle."""


class Recorder:
    def __init__(self):
        self.beats = []

    def heartbeat(self, ok):
        self.beats.append(ok)


class KeepAliveTests(unittest.TestCase):
    def _one_cycle(self, health_result):
        slept = []
        recorder = Recorder()

        async def fake_sleep(seconds):
            slept.append(seconds)
            raise Stop

        with patch.object(bot_main, "bot_status", recorder), patch.object(
            bot_main.backend_client, "health", new=AsyncMock(return_value=health_result)
        ), patch.object(bot_main.asyncio, "sleep", new=fake_sleep):
            logger = logging.getLogger("test")
            with self.assertRaises(Stop):
                asyncio.run(bot_main.keepalive_loop(logger))
        return recorder.beats, slept

    def test_each_ping_stamps_a_heartbeat_the_api_can_publish(self):
        beats, slept = self._one_cycle(True)
        self.assertEqual(beats, [True])
        self.assertEqual(slept, [bot_main.KEEPALIVE_SECONDS])

    def test_a_failed_ping_is_reported_as_failed_not_hidden(self):
        beats, _ = self._one_cycle(False)
        self.assertEqual(beats, [False])

    def test_ping_interval_stays_under_the_spin_down_window(self):
        """Render spins a free service down after 15 min without inbound traffic."""
        self.assertGreater(bot_main.KEEPALIVE_SECONDS, 0)
        self.assertLessEqual(bot_main.KEEPALIVE_SECONDS, 600)


class ContainerConfigTests(unittest.TestCase):
    def test_keepalive_comes_from_the_environment_not_a_hardcoded_number(self):
        self.assertEqual(bot_main.KEEPALIVE_SECONDS, config.KEEPALIVE_SECONDS)

    def test_bool_env_only_accepts_explicit_words(self):
        cases = {
            "1": True, "true": True, "YES": True, "on": True,
            "0": False, "false": False, "no": False, "off": False,
        }
        for raw, expected in cases.items():
            with patch.dict(os.environ, {"SOME_FLAG": raw}):
                self.assertEqual(config._bool_env("SOME_FLAG", not expected), expected, raw)
        with patch.dict(os.environ, {}, clear=True):
            self.assertTrue(config._bool_env("SOME_FLAG", True))
        with patch.dict(os.environ, {"SOME_FLAG": "perhaps"}):
            self.assertTrue(config._bool_env("SOME_FLAG", True), "junk keeps the default")

    def test_the_server_catches_up_on_queued_messages_by_default(self):
        """Dropping pending updates is right on a laptop, wrong on a server:
        a deploy would delete questions pupils already sent."""
        with patch.dict(os.environ, {}, clear=True):
            self.assertFalse(config._bool_env("DROP_PENDING_UPDATES", False))

    def test_int_env_falls_back_on_junk(self):
        with patch.dict(os.environ, {"KEEPALIVE_SECONDS": "abc"}):
            self.assertEqual(config._int_env("KEEPALIVE_SECONDS", 300), 300)
        with patch.dict(os.environ, {"KEEPALIVE_SECONDS": "45"}):
            self.assertEqual(config._int_env("KEEPALIVE_SECONDS", 300), 45)


class RestartSafetyTests(unittest.TestCase):
    """serve.py restarts main() inside ONE process — nothing may be one-shot."""

    def tearDown(self):
        bot_main._instance_lock = None

    def test_a_restart_does_not_bind_the_instance_lock_twice(self):
        """The lock lives in a module global, so attempt #2 must skip binding.

        When it was a local variable the socket stayed alive through the crash
        traceback and the restart died with "port is already in use".
        """
        with patch.object(bot_main, "socket") as fake_socket:
            bot_main.acquire_single_instance()
            bot_main.acquire_single_instance()
            bot_main.acquire_single_instance()
        self.assertEqual(fake_socket.socket.call_count, 1)

    def test_the_four_routers_attach_again_after_a_crash(self):
        """aiogram refuses a second parent, and the routers are module singletons."""
        expected = [module.router for module in bot_main.ROUTER_ORDER]
        first = bot_main.build_dispatcher()
        self.assertEqual(list(first.sub_routers), expected)
        try:
            second = bot_main.build_dispatcher()
        except RuntimeError as exc:  # pragma: no cover — the bug this test guards
            self.fail(f"Qayta boshlashda router birikmadi: {exc}")
        self.assertEqual(list(second.sub_routers), expected)
        self.assertIsNot(first, second)
        self.assertEqual(first.sub_routers, [], "eski Dispatcher ushlab qolmasin")

    def test_handlers_are_reachable_through_the_rebuilt_dispatcher(self):
        dp = bot_main.build_dispatcher()
        # A Dispatcher with no observers would poll Telegram and answer nothing.
        answered = set()
        for router in dp.sub_routers:
            for name, observer in router.observers.items():
                if observer.handlers:
                    answered.add(name)
        self.assertIn("callback_query", answered)
        self.assertIn("message", answered)


class PollingSetupTests(unittest.TestCase):
    """main() must hand the bot over to Telegram the way a container needs."""

    def _run_main(self):
        seen: dict = {}

        class FakeSession:
            def __init__(self):
                self.closed = False

            async def close(self):
                self.closed = True

        class FakeBot:
            def __init__(self, **kwargs):
                seen["bot_kwargs"] = kwargs
                self.session = FakeSession()

            async def set_my_commands(self, commands):
                seen["commands"] = commands

            async def delete_webhook(self, **kwargs):
                seen["delete_webhook"] = kwargs

        class RecordingDispatcher(bot_main.Dispatcher):
            async def start_polling(self, *bots, **kwargs):
                seen["start_polling"] = kwargs
                seen["polling_bots"] = bots
                raise Stop

        async def never_digest(bot):
            await asyncio.sleep(3600)

        with patch.object(bot_main, "Bot", FakeBot), patch.object(
            bot_main, "Dispatcher", RecordingDispatcher
        ), patch.object(bot_main, "acquire_single_instance") as lock, patch.object(
            bot_main.weekly_digest, "digest_loop", never_digest
        ):
            with self.assertRaises(Stop):
                asyncio.run(bot_main.main())
        seen["lock_called"] = lock.called
        return seen

    def test_polling_never_installs_signal_handlers_from_a_thread(self):
        """The bug that killed the bot on Render on its very first attempt.

        Linux asyncio refuses signal handlers outside the main thread and raises
        "RuntimeError: set_wakeup_fd only works in main thread of the main
        interpreter". Windows suppresses it, so only the server ever saw it.
        """
        seen = self._run_main()
        self.assertIs(seen["start_polling"]["handle_signals"], False)

    def test_the_queued_messages_setting_is_actually_sent_to_telegram(self):
        seen = self._run_main()
        self.assertEqual(
            seen["delete_webhook"], {"drop_pending_updates": config.DROP_PENDING_UPDATES}
        )

    def test_the_bot_really_starts_polling_and_cleans_up_afterwards(self):
        seen = self._run_main()
        self.assertTrue(seen["lock_called"], "ikki nusxa bir Telegram'ni oldi olmasin")
        self.assertEqual(len(seen["polling_bots"]), 1)
        self.assertTrue(seen["polling_bots"][0].session.closed, "restart sesh leak qilmasin")


if __name__ == "__main__":
    unittest.main()
