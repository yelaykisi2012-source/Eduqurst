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
import sys

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import BotCommand

import backend_client
import config
from handlers import admin as admin_handlers
from handlers import learn as learn_handlers
from handlers import profile as profile_handlers
from handlers import start as start_handlers

# Render free tier sleeps after ~15 min without traffic. A light ping every
# 10 min keeps the API warm so pupils never stare at a cold start.
KEEPALIVE_SECONDS = 600


def setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )


async def keepalive_loop(logger: logging.Logger) -> None:
    """Ping the backend forever; health() never raises and logs failures."""
    while True:
        try:
            await backend_client.health()
        except Exception:  # pragma: no cover — health() already swallows errors
            logger.warning("Keep-alive ping xato bo'ldi", exc_info=True)
        await asyncio.sleep(KEEPALIVE_SECONDS)


async def main() -> None:
    setup_logging()
    logger = logging.getLogger("eduquest")

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

    dp = Dispatcher()
    # Order matters: flow routers (with FSM states) run BEFORE the start
    # router, whose catch-all only fires outside any state. The admin router
    # comes first so its "leave menu" state handlers win over learn's.
    dp.include_router(admin_handlers.router)
    dp.include_router(learn_handlers.router)
    dp.include_router(profile_handlers.router)
    dp.include_router(start_handlers.router)

    # Show the command list in Telegram's menu (the "/" button).
    await bot.set_my_commands(
        [
            BotCommand(command="start", description="EduQuest’ni boshlash"),
            BotCommand(command="lessons", description="📚 Darslar (bot ichida)"),
            BotCommand(command="profile", description="⭐ Profilim"),
            BotCommand(command="medallar", description="🏆 Yutuqlar"),
            BotCommand(command="app", description="Mini App’ni ochish"),
            BotCommand(command="help", description="Qanday ishlaydi?"),
        ]
    )

    # Ignore updates that piled up while the bot was offline.
    await bot.delete_webhook(drop_pending_updates=True)

    logger.info("EduQuest bot ishga tushdi. To'xtatish: Ctrl+C")
    keepalive = asyncio.create_task(keepalive_loop(logger))
    try:
        await dp.start_polling(bot)
    finally:
        keepalive.cancel()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        # Ctrl+C during polling = normal developer stop, exit code 0.
        print("Bot to'xtatildi.")
    # A SystemExit (e.g. missing BOT_TOKEN) keeps its non-zero exit code
    # so process managers can detect the failure.
