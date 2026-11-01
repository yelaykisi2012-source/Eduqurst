"""
main.py — entry point. Run the bot with:  python main.py  (inside venv)

Flow:
  1. check that BOT_TOKEN exists (fail fast with a friendly message)
  2. create Bot + Dispatcher
  3. register routers
  4. drop pending updates and start long polling
"""
import asyncio
import logging
import socket
import sys

from aiogram import Bot, Dispatcher, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import BotCommand

import backend_client
import config
import weekly_digest
from handlers import admin as admin_handlers
from handlers import learn as learn_handlers
from handlers import profile as profile_handlers
from handlers import start as start_handlers
from pupil_guard import PupilGuard

# The status board lives in the backend package and only exists when the bot
# runs inside the API container (serve.py). Started with plain `python main.py`
# on a laptop the import fails, and the bot simply keeps a private heartbeat.
try:
    from app import bot_status
except Exception:  # pragma: no cover — local run without the backend on the path
    bot_status = None

# Render free tier sleeps after ~15 min without traffic. A light ping every
# 5 min keeps the API warm so pupils never stare at a cold start — and inside
# the shared container that ping is what stops the whole service (bot included)
# from being spun down. See config.KEEPALIVE_SECONDS.
KEEPALIVE_SECONDS = config.KEEPALIVE_SECONDS

# One bot copy per machine. Two copies of the same token fight over
# Telegram's getUpdates: updates land on one or the other at random, so /start
# may be answered by copy A while a button is answered by copy B — producing
# confusing errors like "Avval /start bosing." for a fully registered pupil.
INSTANCE_PORT = 49221

# Held in a module global, NOT in a local variable. serve.py restarts the bot
# inside the same process, and a lock that lived only as long as main()'s frame
# was not released until the traceback was garbage collected — so every restart
# died with "port is already in use" before reaching Telegram. That turned a
# recoverable crash into a permanently dead bot (found by the local smoke run
# on 2026-11-01, not by a unit test).
_instance_lock: socket.socket | None = None


def acquire_single_instance() -> None:
    """Bind a localhost port once per process as a lock; the OS frees it on exit."""
    global _instance_lock
    if _instance_lock is not None:
        return  # this process already holds the lock — a supervisor restart
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.bind(("127.0.0.1", INSTANCE_PORT))
        sock.listen(1)
    except OSError:
        sock.close()
        print(
            "⛔ EduQuest bot allaqachon ishlab turibdi.\n"
            "Ikkinchi nusxani ishga tushirmang — eski terminalda Ctrl+C bosing."
        )
        sys.exit(0)
    _instance_lock = sock


def setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )


async def keepalive_loop(logger: logging.Logger) -> None:
    """Ping the backend forever; health() never raises and logs failures."""
    while True:
        try:
            ok = await backend_client.health()
        except Exception:  # pragma: no cover — health() already swallows errors
            logger.warning("Keep-alive ping xato bo'ldi", exc_info=True)
            ok = False
        if bot_status is not None:
            # Doubles as proof-of-life for /api/bot-status: this line only runs
            # while the bot's own event loop is actually turning.
            bot_status.heartbeat(ok)
        await asyncio.sleep(KEEPALIVE_SECONDS)


ROUTER_ORDER = (
    # Order matters: flow routers (with FSM states) run BEFORE the start
    # router, whose catch-all only fires outside any state. The admin router
    # comes first so its "leave menu" state handlers win over learn's.
    admin_handlers,
    learn_handlers,
    profile_handlers,
    start_handlers,
)


def detach_router(router: Router) -> None:
    """Un-hook a module-level router from whatever Dispatcher owned it last.

    serve.py restarts main() inside the SAME process. The routers in handlers/*.py
    are module-level singletons, so on the second attempt aiogram refuses to
    attach them again and raises "RuntimeError: Router is already attached to
    <Dispatcher ...>" — the bot would crash-loop forever and never answer pupils
    again after its first real crash (found by the local smoke run, 2026-11-01).
    aiogram 3 has no public detach, so this clears the two links that
    `include_router` created. It is written defensively: if a future aiogram
    renames those internals, the loop simply skips them and the crash stays
    visible in /api/bot-status instead of silently mis-wiring the bot.
    """
    parent = getattr(router, "_parent_router", None)
    if parent is None:
        return
    siblings = getattr(parent, "sub_routers", None)
    if isinstance(siblings, list):
        try:
            siblings.remove(router)
        except ValueError:  # already gone
            pass
    router._parent_router = None


def build_dispatcher() -> Dispatcher:
    """A Dispatcher with all four routers attached, safe to call per bot run."""
    dp = Dispatcher()
    for module in ROUTER_ORDER:
        detach_router(module.router)
        dp.include_router(module.router)
    return dp


async def main() -> None:
    setup_logging()
    logger = logging.getLogger("eduquest")

    # Module global, not a local: serve.py restarts this coroutine inside the
    # same process, and a socket held only by a dead frame is not freed at once.
    acquire_single_instance()

    if not config.BOT_TOKEN:
        logger.error(
            "BOT_TOKEN topilmadi! bot/.env faylga BOT_TOKEN qiymatini kiriting "
            "(BotFather'dan oling). .env.example — namunalar uchun."
        )
        sys.exit(1)

    bot = Bot(
        token=config.BOT_TOKEN,
        # HTML is safe here because all text is written by us.
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )

    dp = build_dispatcher()

    # Every message/button first ensures the pupil exists in the backend, so a
    # missed or stale /start can never break navigation ("Avval /start bosing").
    pupil_guard = PupilGuard()
    dp.message.middleware(pupil_guard)
    dp.callback_query.middleware(pupil_guard)

    # Show the command list in Telegram's menu (the "/" button).
    await bot.set_my_commands(
        [
            BotCommand(command="start", description="EduQuest’ni boshlash"),
            BotCommand(command="lessons", description="📚 Darslar (bot ichida)"),
            BotCommand(command="profile", description="⭐ Profilim"),
            BotCommand(command="medallar", description="🏆 Yutuqlar"),
            BotCommand(command="parent", description="📲 Ota-ona hisoboti"),
            BotCommand(command="app", description="Mini App’ni ochish"),
            BotCommand(command="help", description="Qanday ishlaydi?"),
        ]
    )

    # Updates that piled up while this instance was offline. On the server the
    # default is to CATCH UP (a restart or a 30-second deploy must not throw
    # away the messages pupils already sent). Running locally you usually want
    # the old queue gone — set DROP_PENDING_UPDATES=true in bot/.env for that.
    await bot.delete_webhook(drop_pending_updates=config.DROP_PENDING_UPDATES)

    logger.info("EduQuest bot ishga tushdi — Telegram yangiliklari kutilmoqda.")
    keepalive = asyncio.create_task(keepalive_loop(logger))
    digest = asyncio.create_task(weekly_digest.digest_loop(bot))
    try:
        # handle_signals=False is REQUIRED inside serve.py: the bot runs in a
        # non-main thread, and on Linux asyncio refuses to install signal handlers
        # there ("RuntimeError: set_wakeup_fd only works in main thread"). Windows
        # silently skips it, so a laptop run never shows the problem — the server
        # crash-looped on its very first polling attempt. uvicorn (main thread)
        # owns SIGTERM/SIGINT; when the container stops, this thread stops with it.
        await dp.start_polling(bot, handle_signals=False)
    finally:
        digest.cancel()
        keepalive.cancel()
        # Close the HTTP session. Without this, every supervisor restart leaks a
        # fresh aiohttp session (and its connection pool) until the container
        # runs out of sockets. The instance lock is deliberately NOT released
        # here — see _instance_lock.
        await bot.session.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        # Ctrl+C during polling = normal developer stop, exit code 0.
        print("Bot to'xtatildi.")
    # A SystemExit (e.g. missing BOT_TOKEN) keeps its non-zero exit code
    # so process managers can detect the failure.
