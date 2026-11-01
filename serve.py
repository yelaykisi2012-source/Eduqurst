"""
serve.py — ONE process running both jobs: the API and the Telegram bot.

Why this exists. Render has no free Background Worker instance type, so a bot
that runs 24/7 would cost $7/month on its own service. The bot is a plain
asyncio program and the API is a plain asyncio server; 512 MB is enough for
both, so the Docker image starts them together from this file.

Rules this file obeys:
  * The bot runs in its own thread with its own event loop. A crash there can
    never break uvicorn's loop — pupils keep getting lessons and profiles even
    if Telegram answering is briefly down.
  * A supervisor restarts the bot with backoff (5s → 5min) instead of letting
    the container exit, because an exit would take the Mini App with it.
  * Everything the supervisor knows is published at /api/bot-status, so
    "is the bot alive?" is one curl, not a guess.
  * The free service sleeps after 15 min without INBOUND traffic; Telegram
    polling is outbound and would not count. The bot's keep-alive loop
    (config.KEEPALIVE_SECONDS, default 300) therefore requests this service's
    own public /api/health, which does count — and stamps a heartbeat.

Local development is unchanged: `uvicorn app.main:app` in backend/, and
`python main.py` in bot/ — each with its own venv.
"""
from __future__ import annotations

import asyncio
import logging
import os
import sys
import threading
import time
from pathlib import Path
from typing import Callable

ROOT = Path(__file__).resolve().parent
BOT_DIR = ROOT / "bot"

RESTART_DELAYS = (5, 15, 30, 60, 120, 300)
HEALTHY_SECONDS = 600  # a run longer than this resets the backoff ladder

logger = logging.getLogger("serve")


def import_bot_main():
    """Import bot/main.py the way the bot's own folder expects (flat imports)."""
    if str(BOT_DIR) not in sys.path:
        sys.path.insert(0, str(BOT_DIR))
    import main as bot_main  # noqa: E402 — bot/main.py

    return bot_main


_board = None
_board_tried = False


def status_board():
    """The backend's bot_status module, or None if this image has no backend.

    Cached after the first lookup, and every failure is swallowed on purpose:
    /api/bot-status is a nice-to-have. A supervisor thread that dies while
    reporting would take the bot down with it and leave the API looking fine.
    """
    global _board, _board_tried
    if not _board_tried:
        _board_tried = True
        try:
            from app import bot_status as board

            _board = board
        except Exception:  # pragma: no cover — backend-only or bot-only image
            logger.warning("Bot holati jadvali mavjud emas — /api/bot-status yo‘q.")
    return _board


def _report(**changes) -> None:
    board = status_board()
    if board is not None:
        board.update(**changes)


def _note_restart() -> None:
    board = status_board()
    if board is not None:
        board.note_restart()


def run_bot_once() -> None:
    """Start polling and block until the bot stops (it normally never returns)."""
    asyncio.run(import_bot_main().main())


def bot_loop(
    stop: threading.Event,
    job: Callable[[], None] = run_bot_once,
    delays: tuple[int, ...] = RESTART_DELAYS,
    healthy_seconds: float = HEALTHY_SECONDS,
) -> None:
    """Keep the bot running; never let a failure escape into the API process."""
    if not BOT_DIR.is_dir() and job is run_bot_once:
        # backend-only checkout (or a stripped image): say so instead of looping.
        _report(phase="disabled")
        logger.warning("Bot papkasi topilmadi — faqat API ishlaydi: %s", BOT_DIR)
        return

    attempt = 0
    while not stop.is_set():
        _report(phase="starting", started_at=time.time(), last_error=None)
        started = time.time()
        try:
            job()
            _report(phase="stopped")
            logger.info("Bot o‘z ixtiyori bilan to‘xtadi.")
            return
        except BaseException as exc:  # noqa: BLE001 — SystemExit is the real reason
            # bot/main.py calls sys.exit(0) when another instance already holds
            # the poll lock. SystemExit is NOT an Exception, so catching only
            # Exception here would let the bot thread vanish silently and leave
            # the API reporting a healthy-looking "crash never happened".
            if isinstance(exc, KeyboardInterrupt):
                raise
            if stop.is_set():
                _report(phase="stopped")
                return
            if time.time() - started >= healthy_seconds:
                attempt = 0  # it ran fine for a while; start the ladder again
            attempt += 1
            delay = delays[min(attempt - 1, len(delays) - 1)]
            _note_restart()
            _report(phase="crashed", last_error=type(exc).__name__)
            logger.exception(
                "Bot ishdan chiqdi (%s) — %d soniyadan qayta boshlanadi (urinish %d)",
                type(exc).__name__, delay, attempt,
            )
            if stop.wait(delay):
                _report(phase="stopped")
                return


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )
    port = int(os.environ.get("PORT", "8000"))

    if BOT_DIR.is_dir():
        stop = threading.Event()
        threading.Thread(
            target=bot_loop, args=(stop,), name="eduquest-bot", daemon=True
        ).start()
        logger.info("Bot oqimi thread’da boshlandi (API porti %d bilan birga).", port)
    else:
        logger.warning("bot/ papkasi yo‘q — bu image faqat API’ni beradi.")

    import uvicorn

    uvicorn.run("app.main:app", host="0.0.0.0", port=port, log_level="info")


if __name__ == "__main__":
    main()
