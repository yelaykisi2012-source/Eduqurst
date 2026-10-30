"""
handlers/start.py — what the bot says when a pupil arrives.

/start now also REGISTERS the pupil in the backend (via the bot-token
internal endpoint), so the whole learning loop works inside the bot even
for children who never opened the Mini App. Honest fallback everywhere:
if the backend is unreachable we show the plain welcome and never invent
stars, grades or names.
"""
import logging

from aiogram import F, Router
from aiogram.filters import CommandStart, Command, StateFilter
from aiogram.types import Message

import backend_client
import config
from keyboards.inline import main_menu_keyboard

logger = logging.getLogger(__name__)

router = Router(name="start")

GREETING = (
    "🤖 <b>EduQuest’ga xush kelibsiz!</b>\n\n"
    "Quest bilan birga bilimlar olamiga sayohat qiling!\n\n"
    "📚 Qiziqarli darslar\n"
    "🧩 Interaktiv testlar\n"
    "⭐ Yulduzlar va mukofotlar\n"
    "🚀 Yangi bilim bosqichlari"
)

MENU_HINT = "\n\n👇 Quyidagi tugmalar orqali davom eting: 📚 Darslar, ⭐ Profilim, 🏆 Yutuqlar."


async def _intro_from_summary(message: Message, summary: dict | None) -> str:
    """Greeting enriched with the pupil's real stats. Never invents data."""
    if not summary or not summary.get("known_user"):
        return GREETING

    first_name = summary.get("first_name") or message.from_user.first_name or "Qahramon"
    lines = [f"👋 <b>Salom, {first_name}!</b>", ""]
    if summary.get("needs_onboarding"):
        lines.append("🎓 Siz hali sinfinizni tanlamadingiz — <b>📚 Darslar</b> tugmasini bosing!")
    else:
        stars = summary.get("stars_total", 0)
        passed = summary.get("lessons_passed", 0)
        lines.append(
            f"Sizning sinfiniz: <b>{summary.get('grade_name')}</b>\n"
            f"⭐ Yulduzchalar: <b>{stars}</b> · ✅ Tugatilgan darslar: <b>{passed}</b>"
        )
        lines.append(
            "\nBirinchi yulduzchangizni yutish uchun kiring! 🚀"
            if stars == 0
            else "\nShunday davom eting — Quest siz bilan faxrlanadi! 🤖"
        )
    return "\n".join(lines) + MENU_HINT


@router.message(CommandStart())
async def cmd_start(message: Message) -> None:
    """/start — register the pupil, greet personally, show the full menu."""
    if not config.MINI_APP_URL:
        logger.warning("MINI_APP_URL is empty — Mini App button will be disabled.")

    summary: dict | None = None
    try:
        fu = message.from_user
        summary = await backend_client.upsert_pupil(
            fu.id, first_name=fu.first_name or "", username=fu.username
        )
    except (backend_client.BackendOffline, backend_client.BackendBusiness) as e:
        logger.warning("pupil upsert failed: %s", e)
        summary = await backend_client.pupil_summary(message.from_user.id)

    intro = await _intro_from_summary(message, summary)
    is_admin = message.from_user.id in config.ADMIN_USER_IDS
    await message.answer(intro, reply_markup=main_menu_keyboard(config.MINI_APP_URL, is_admin))


@router.message(Command("menu"))
async def cmd_menu(message: Message) -> None:
    """Shortest way back to the buttons."""
    await message.answer(
        "🤖 <b>EduQuest menyusi</b>",
        reply_markup=main_menu_keyboard(
            config.MINI_APP_URL, message.from_user.id in config.ADMIN_USER_IDS
        ),
    )


@router.message(Command("app"))
async def cmd_app(message: Message) -> None:
    """/app — open the Mini App directly."""
    if not config.MINI_APP_URL:
        await message.answer("⚠️ Mini App hozir sozlanmagan (MINI_APP_URL bo'sh).")
        return
    await message.answer(
        "🚀 Quyidagi tugma orqali EduQuest Mini App’ni oching:",
        reply_markup=main_menu_keyboard(
            config.MINI_APP_URL, message.from_user.id in config.ADMIN_USER_IDS
        ),
    )


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    await message.answer(
        "🤖 <b>EduQuest — qanday ishlaydi?</b>\n\n"
        "1️⃣ /start yuboring\n"
        "2️⃣ <b>📚 Darslar</b> — sinfini tanlang, dars o‘qing, test yeching ⭐\n"
        "3️⃣ <b>⭐ Profilim</b> — yulduzchalar va progress\n"
        "4️⃣ <b>🏆 Yutuqlar</b> — medallar\n"
        "5️⃣ <b>🚀 Mini App</b> — hammasi chiroyli interfeysda\n\n"
        "Darslar bilan testlar bot ichida ham, Mini App’da ham bir xil ishlaydi."
    )


@router.message(F.text, StateFilter(None))
async def unknown_text(message: Message) -> None:
    """Catch-all for random text OUTSIDE any flow (quiz/admin text steps
    are handled by their own routers first)."""
    await message.answer("🤔 Tushunmadim. Boshlash uchun /start yuboring!")
