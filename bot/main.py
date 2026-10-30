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

import config
from handlers import start as start_handlers


def setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )


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
    dp.include_router(start_handlers.router)

    # Show the command list in Telegram's menu (the "/" button).
    await bot.set_my_commands(
        [
            BotCommand(command="start", description="EduQuest'ni boshlash"),
            BotCommand(command="app", description="Mini App'ni ochish"),
            BotCommand(command="help", description="Qanday ishlaydi?"),
        ]
    )

    # Ignore updates that piled up while the bot was offline.
    await bot.delete_webhook(drop_pending_updates=True)

    logger.info("EduQuest bot ishga tushdi. To'xtatish: Ctrl+C")
    await dp.start_polling(bot)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        # Ctrl+C during polling = normal developer stop, exit code 0.
        print("Bot to'xtatildi.")
    # A SystemExit (e.g. missing BOT_TOKEN) keeps its non-zero exit code
    # so process managers can detect the failure.
