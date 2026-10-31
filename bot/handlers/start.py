"""
handlers/start.py — what the bot says when a pupil arrives.

/start now also REGISTERS the pupil in the backend (via the bot-token
internal endpoint), so the whole learning loop works inside the bot even
for children who never opened the Mini App. Honest fallback everywhere:
if the backend is unreachable we show the plain welcome and never invent
stars, grades or names.
"""
import html
import logging

from aiogram import F, Router
from aiogram.filters import CommandStart, Command, StateFilter
from aiogram.types import CallbackQuery, Message

import backend_client
import config
from keyboards.inline import main_menu_keyboard, parent_panel_keyboard

logger = logging.getLogger(__name__)

router = Router(name="start")


def esc(value: object) -> str:
    return html.escape(str(value), quote=False)

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


async def _offline(message: Message) -> None:
    await message.answer(
        "🔌 Server hozir javob bermayapti. Birozdan so‘ng qayta urinib ko‘ring."
    )


# ------------------------------------------------------------------ parent digest

@router.message(CommandStart(deep_link=True))
async def cmd_start_parent_code(message: Message) -> None:
    """`/start ABC123` from a parent links them to one pupil's weekly digest."""
    parts = (message.text or "").split(maxsplit=1)
    code = parts[1].strip() if len(parts) > 1 else ""
    if not code:
        await cmd_start(message)
        return
    try:
        result = await backend_client.link_parent(
            code, message.from_user.id, message.from_user.first_name or ""
        )
    except backend_client.BackendOffline:
        await _offline(message)
        return
    except backend_client.BackendBusiness as e:
        await message.answer(
            f"❌ {esc(e.message)}\n\nFarzandingizdan yangi kod so‘rang "
            "(u botda /parent buyrug‘ini yuboradi)."
        )
        return
    grade = f" · {esc(result['grade_name'])}" if result.get("grade_name") else ""
    await message.answer(
        "✅ <b>Bog‘landi!</b>\n\n"
        f"Endi <b>{esc(result['pupil_first_name'])}</b>{grade}ning haftalik "
        "hisobotini har yakshanba shu yerda olasiz.\n\n"
        "Hisobotni to‘xtatish uchun farzandingiz botda /parent → "
        "«Hisobotni uzish» tugmasini bosadi."
    )


async def show_parent_panel(target: Message, tg_id: int) -> None:
    """Pupil side: show the linking code (or the current link + unlink)."""
    try:
        status = await backend_client.parent_status(tg_id)
    except backend_client.BackendOffline:
        await _offline(target)
        return
    except backend_client.BackendBusiness as e:
        await target.answer(f"⚠️ {esc(e.message)}")
        return

    linked = bool(status.get("linked"))
    parent_name = status.get("parent_name")
    if linked:
        await target.answer(
            "📲 <b>Ota-ona hisoboti ulangan</b>\n\n"
            f"Hisobot har yakshanba kuni <b>{esc(parent_name or 'ota-onangiz')}</b>"
            "ning Telegramiga yuboriladi.\n\n"
            "Uzish uchun quyidagi tugmani bosing.",
            reply_markup=parent_panel_keyboard(True),
        )
        return

    try:
        data = await backend_client.parent_code(tg_id)
    except backend_client.BackendOffline:
        await _offline(target)
        return
    except backend_client.BackendBusiness as e:
        await target.answer(f"⚠️ {esc(e.message)}")
        return
    if data.get("linked"):
        await target.answer(
            f"📲 Hisobot allaqachon <b>{esc(data.get('parent_name') or 'ota-onangiz')}</b>"
            "ning Telegramiga ulanagan.",
            reply_markup=parent_panel_keyboard(True),
        )
        return
    code = data.get("code") or "—"
    await target.answer(
        "📲 <b>Ota-ona uchun haftalik hisobot</b>\n\n"
        "1️⃣ Quyidagi havolani ota-onangizga yuboring — ular bir bosishda ulanadi:\n"
        f'<a href="https://t.me/{esc(config.BOT_USERNAME)}?start={esc(code)}">'
        "👉 Ota-onaga havola</a>\n\n"
        "2️⃣ Yoki ular botga kirib shunday yozishsin:\n"
        f"<code>/start {esc(code)}</code>\n\n"
        "⏳ Kod <b>15 daqiqa</b> amal qiladi. Har yakshanba ular hisobot oladi.",
        reply_markup=parent_panel_keyboard(False),
    )


@router.message(Command("parent"))
async def cmd_parent(message: Message) -> None:
    await show_parent_panel(message, message.from_user.id)


@router.callback_query(F.data == "nav:parent")
async def cb_parent(cb: CallbackQuery) -> None:
    await cb.answer()
    await show_parent_panel(cb.message, cb.from_user.id)


@router.callback_query(F.data == "pr:off")
async def cb_parent_off(cb: CallbackQuery) -> None:
    await cb.answer()
    try:
        await backend_client.unlink_parent(cb.from_user.id)
    except backend_client.BackendOffline:
        await _offline(cb.message)
        return
    except backend_client.BackendBusiness as e:
        await cb.message.answer(f"⚠️ {esc(e.message)}")
        return
    await cb.message.answer(
        "✅ Ota-ona hisoboti uzildi. Qayta ulash uchun /parent buyrug‘ini yuboring."
    )


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
