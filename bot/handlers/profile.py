"""
handlers/profile.py — ⭐ Profilim and 🏆 Yutuqlar inside the bot.

Both read the SAME progress endpoint the Mini App uses, so stars,
counts and medals never diverge between the two screens.
"""
from __future__ import annotations

import html
import logging

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

import backend_client
from keyboards.inline import menu_only_keyboard

logger = logging.getLogger(__name__)
router = Router(name="profile")


def esc(value: object) -> str:
    return html.escape(str(value), quote=False)


async def _load(target: Message) -> dict | None:
    try:
        return await backend_client.progress(target.from_user.id)
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


async def show_profile(target: Message) -> None:
    prog = await _load(target)
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
    await target.answer("\n".join(lines), reply_markup=menu_only_keyboard())


async def show_achievements(target: Message) -> None:
    prog = await _load(target)
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
    await show_profile(cb.message)
    await cb.answer()


@router.callback_query(F.data == "nav:ach")
async def cb_achievements(cb: CallbackQuery) -> None:
    await show_achievements(cb.message)
    await cb.answer()


@router.message(Command("profile"))
async def cmd_profile(message: Message) -> None:
    await show_profile(message)


@router.message(Command("medallar"))
async def cmd_medals(message: Message) -> None:
    await show_achievements(message)
