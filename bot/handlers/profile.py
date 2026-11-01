"""
handlers/profile.py — ⭐ Profilim, 🏆 Yutuqlar va 🖼 profil rasmi (bot ichida).

Both read the SAME progress endpoint the Mini App uses, so stars,
counts and medals never diverge between the two screens.

The avatar button copies the pupil's OWN Telegram profile photo onto their
EduQuest profile: Telegram hands the file over (getUserProfilePhotos), the bot
downloads it into memory (no temp files) and the backend normalises + stores it
through exactly the same path as a Mini App upload.
"""
from __future__ import annotations

import html
import logging

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

import backend_client
from keyboards.inline import menu_only_keyboard, profile_keyboard

logger = logging.getLogger(__name__)
router = Router(name="profile")


def esc(value: object) -> str:
    return html.escape(str(value), quote=False)


async def _load(target: Message, tg_id: int) -> dict | None:
    # tg_id is the pupil's id; when `target` is the bot's own message (inline
    # button press) target.from_user is the BOT and must not be queried.
    try:
        return await backend_client.progress(tg_id)
    except backend_client.BackendOffline:
        await target.answer(
            "🔌 Server hozir javob bermayapti — birozdan so‘ng qayta urinib ko‘ring.",
            reply_markup=menu_only_keyboard(),
        )
    except backend_client.BackendBusiness as e:
        if e.code == "pupil_not_found":
            await target.answer("👋 Avval /start yuboring — shundan keyin profilingiz bo‘ladi.")
        else:
            await target.answer(f"⚠️ {esc(e.message)}", reply_markup=menu_only_keyboard())
    return None


def _bar(done: int, total: int) -> str:
    if total == 0:
        return "🚧"
    filled = round(10 * done / total)
    return "█" * filled + "░" * (10 - filled)


async def show_profile(target: Message, tg_id: int) -> None:
    prog = await _load(target, tg_id)
    if prog is None:
        return
    lines = [
        f"👤 <b>{esc(prog['first_name'])}</b>",
        f"🎓 Sinf: <b>{esc(prog['grade_name'] or 'tanlanmagan')}</b>",
        "",
        f"⭐ Yulduzchalar: <b>{prog['stars_total']}</b>",
        f"📖 O‘qilgan darslar: <b>{prog['lessons_viewed']}</b>",
        f"✅ Tugatilgan bosqichlar: <b>{prog['lessons_passed']}</b>",
    ]
    if prog["subjects"]:
        lines.append("\n📚 Fanlar bo‘yicha progress:")
        for s in prog["subjects"]:
            lines.append(
                f"{s['emoji']} {esc(s['subject_name'])}: {_bar(s['passed_lessons'], s['total_lessons'])} "
                f"{s['passed_lessons']}/{s['total_lessons']}"
            )
    lines.append("\n💡 Sinfni o‘zgartirish Mini App’dagi Profil bo‘limida (progress o‘chmaydi).")
    await target.answer("\n".join(lines), reply_markup=profile_keyboard())


async def show_achievements(target: Message, tg_id: int) -> None:
    prog = await _load(target, tg_id)
    if prog is None:
        return
    lines = ["🏆 <b>Yutuqlar</b>\n"]
    for a in prog["achievements"]:
        mark = "✅" if a["earned"] else "🔒"
        lines.append(f"{mark} {a['icon']} <b>{esc(a['title'])}</b> — {esc(a['description'])}")
    earned = sum(1 for a in prog["achievements"] if a["earned"])
    lines.append(f"\nYig‘ilgan: {earned}/{len(prog['achievements'])}. Davom eting! 💪")
    await target.answer("\n".join(lines), reply_markup=menu_only_keyboard())


@router.callback_query(F.data == "nav:profile")
async def cb_profile(cb: CallbackQuery) -> None:
    await cb.answer()  # stop the spinner immediately
    await show_profile(cb.message, cb.from_user.id)


async def sync_avatar(target: Message, tg_id: int, bot: Bot) -> None:
    """Copy the pupil's own Telegram profile photo onto their EduQuest profile.

    Every branch answers with a real reason — a silently failing button is the
    one thing a 12-year-old cannot recover from.
    """
    try:
        photos = (await bot.get_user_profile_photos(user_id=tg_id, limit=1)).photos
    except TelegramAPIError as e:
        logger.warning("getUserProfilePhotos: %s", e)
        photos = []
    if not photos:
        await target.answer(
            "📷 Telegram’da profil rasmingiz yo‘q.\n\n"
            "Telegram sozlamalarida rasm qo‘ying, keyin shu tugmani qayta bosing. "
            "Yoki Mini App’ning Profil bo‘limidan rasm yuklang.",
            reply_markup=profile_keyboard(),
        )
        return

    sizes = photos[0]  # Telegram kichikdan kattaga beradi — eng tiniqini olamiz
    file = None
    raw = b""
    try:
        file = await bot.get_file(file_id=sizes[-1].file_id)
        if file.file_path:  # None = fayl hali Telegram serverida tayyor emas
            stream = await bot.download_file(file.file_path)
            raw = stream.read() if stream is not None else b""
    except (TelegramAPIError, OSError, ValueError) as e:
        logger.warning("Avatar yuklab bo‘lmadi: %s", e)
        await target.answer(
            "⚠️ Rasmini Telegram’dan yuklab bo‘lmadi — birozdan so‘ng qayta urinib ko‘ring.",
            reply_markup=profile_keyboard(),
        )
        return

    if not raw:
        await target.answer(
            "⚠️ Telegram rasmini berolmadi — qayta urinib ko‘ring.",
            reply_markup=profile_keyboard(),
        )
        return

    name = (file.file_path or "").rsplit("/", 1)[-1] or "telegram_rasmi.jpg"
    try:
        out = await backend_client.set_avatar(tg_id, raw, filename=name)
    except backend_client.BackendOffline:
        await target.answer(
            "🔌 Server hozir javob bermayapti — birozdan so‘ng qayta urinib ko‘ring.",
            reply_markup=profile_keyboard(),
        )
    except backend_client.BackendBusiness as e:
        if e.code == "pupil_not_found":
            await target.answer("👋 Avval /start yuboring — shundan keyin profilingiz bo‘ladi.")
        else:
            # e.message is the backend's own Uzbek reason (e.g. "Rasm juda katta…")
            await target.answer(f"⚠️ {esc(e.message)}", reply_markup=profile_keyboard())
    else:
        width = out.get("width")
        size = f" ({width} px)" if width else ""
        await target.answer(
            f"✅ Profil rasmingiz qo‘yildi{size}!\n\n"
            "📲 Endi u Mini App profilangizda va sinf chatidagi xabarlaringiz yonida ko‘rinadi.\n"
            "🔁 Boshqa rasm xohlasangiz — Telegram rasmingizni almashtiring va tugmani qayta bosing.",
            reply_markup=profile_keyboard(),
        )


@router.callback_query(F.data == "nav:avatar")
async def cb_avatar(cb: CallbackQuery, bot: Bot) -> None:
    await cb.answer()  # stop the spinner immediately
    # cb.from_user = the pupil; cb.message.from_user would be the BOT itself.
    await sync_avatar(cb.message, cb.from_user.id, bot)


@router.callback_query(F.data == "nav:ach")
async def cb_achievements(cb: CallbackQuery) -> None:
    await cb.answer()  # stop the spinner immediately
    await show_achievements(cb.message, cb.from_user.id)


@router.message(Command("profile"))
async def cmd_profile(message: Message) -> None:
    await show_profile(message, message.from_user.id)


@router.message(Command("medallar"))
async def cmd_medals(message: Message) -> None:
    await show_achievements(message, message.from_user.id)
