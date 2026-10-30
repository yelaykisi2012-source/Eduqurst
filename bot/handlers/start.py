"""
handlers/start.py — what the bot says when a pupil arrives.

Handlers are grouped in a Router. In later stages we will add
handlers/help.py, handlers/quiz.py and simply register every router
in main.py — that keeps each file small and readable.
"""
import logging

from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.types import Message

import backend_client
import config
from keyboards.inline import main_menu_keyboard

logger = logging.getLogger(__name__)

router = Router(name="start")

GREETING = (
    "🤖 <b>EduQuest'ga xush kelibsiz!</b>\n\n"
    "Quest bilan birga bilimlar olamiga sayohat qiling!\n\n"
    "📚 Qiziqarli darslar\n"
    "🧩 Interaktiv testlar\n"
    "⭐ Yulduzlar va mukofotlar\n"
    "🚀 Yangi bilim bosqichlari"
)


async def personalized_intro(message: Message) -> str:
    """Greeting enriched with the pupil's real stats from the backend.

    Honest by design: if the backend is unreachable or the pupil is new,
    we show the plain welcome — we never invent a grade or star count.
    """
    text = GREETING
    summary = await backend_client.pupil_summary(message.from_user.id)
    if not summary or not summary.get("known_user"):
        return text

    first_name = summary.get("first_name") or message.from_user.first_name or "Qahramon"
    lines = [f"👋 <b>Salom, {first_name}!</b>", ""]
    if summary.get("needs_onboarding"):
        lines.append("📚 Siz hali sinfinizni tanlamadingiz — Mini App'ni ochib tanlang!")
    else:
        stars = summary.get("stars_total", 0)
        passed = summary.get("lessons_passed", 0)
        lines.append(
            f"Sizning sinfiniz: <b>{summary.get('grade_name')}</b>\n"
            f"⭐ Yulduzchalar: <b>{stars}</b> · ✅ Tugatilgan darslar: <b>{passed}</b>"
        )
        if stars == 0:
            lines.append("\nBirinchi yulduzchangizni yutish uchun kiring! 🚀")
        else:
            lines.append("\nShunday davom eting — Quest siz bilan faxrlanadi! 🤖")
    return "\n".join(lines) + "\n\n" + GREETING.split("\n\n", 1)[1]


@router.message(CommandStart())
async def cmd_start(message: Message) -> None:
    """/start — greeting + the button that launches the Mini App."""
    if not config.MINI_APP_URL:
        # Honest behaviour: no fake button that opens nothing.
        logger.warning("MINI_APP_URL is empty — showing greeting without button.")
        await message.answer(
            GREETING
            + "\n\n⚠️ Mini App hozir sozlanmagan (MINI_APP_URL bo'sh)."
        )
        return

    intro = await personalized_intro(message)
    await message.answer(intro, reply_markup=main_menu_keyboard(config.MINI_APP_URL))


@router.message(Command("app"))
async def cmd_app(message: Message) -> None:
    """/app — open the Mini App directly."""
    if not config.MINI_APP_URL:
        await message.answer("⚠️ Mini App hozir sozlanmagan (MINI_APP_URL bo'sh).")
        return

    await message.answer(
        "🚀 Quyidagi tugma orqali EduQuest Mini App'ni oching:",
        reply_markup=main_menu_keyboard(config.MINI_APP_URL),
    )


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    await message.answer(
        "🤖 <b>EduQuest — qanday ishlaydi?</b>\n\n"
        "1️⃣ /start yuboring\n"
        "2️⃣ «Mini App'ni ochish» tugmasini bosing\n"
        "3️⃣ Darslarni tugating, viktorinalarga javob bering ⭐ yutib oling\n\n"
        "Savol bo'lsa: admin bilan bog'laning."
    )


@router.message(F.text)
async def unknown_text(message: Message) -> None:
    """Catch-all so the bot never silently ignores a child."""
    await message.answer("🤔 Tushunmadim. Boshlash uchun /start yuboring!")
