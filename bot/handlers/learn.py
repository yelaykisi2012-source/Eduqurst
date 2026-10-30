"""
handlers/learn.py — the FULL learning loop inside the bot:
sinf tanlash → fanlar → dars basqichi → dars matni → test → natija.

Same rules as the Mini App because the SAME backend endpoints run
(through /api/internal/*, X-Bot-Token protected): server-side grading,
grade scoping, sequential unlocking, idempotent star grants.
"""
from __future__ import annotations

import html
import logging
import uuid
from typing import Any

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

import backend_client
import config
from keyboards.inline import (
    grades_keyboard,
    lesson_actions_keyboard,
    lessons_keyboard,
    main_menu_keyboard,
    menu_only_keyboard,
    quiz_question_keyboard,
    quiz_result_keyboard,
    subjects_keyboard,
)

logger = logging.getLogger(__name__)
router = Router(name="learn")

TELEGRAM_LIMIT = 4000  # safe margin below 4096


def esc(value: Any) -> str:
    """HTML-escape anything that came from user/admin input."""
    return html.escape(str(value), quote=False)


def _split(text: str) -> list[str]:
    """Chunk long messages on newline boundaries when possible."""
    if len(text) <= TELEGRAM_LIMIT:
        return [text]
    parts, buf = [], ""
    for line in text.split("\n"):
        if len(buf) + len(line) + 1 > TELEGRAM_LIMIT:
            parts.append(buf)
            buf = line
        else:
            buf = f"{buf}\n{line}" if buf else line
    if buf:
        parts.append(buf)
    return parts


async def send_long(target: Message, text: str, reply_markup=None) -> None:
    chunks = _split(text)
    for i, chunk in enumerate(chunks):
        await target.answer(chunk, reply_markup=reply_markup if i == len(chunks) - 1 else None)


async def _offline(target: Message) -> None:
    await target.answer(
        "🔌 Server hozir javob bermayapti (Internet yoki backend muammosi).\n"
        "Birozdan so‘ng qayta urinib ko‘ring.",
        reply_markup=menu_only_keyboard(),
    )


async def _business(target: Message, e: backend_client.BackendBusiness) -> None:
    await target.answer(f"⚠️ {esc(e.message)}", reply_markup=menu_only_keyboard())


# ------------------------------------------------------------------ menu

@router.callback_query(F.data == "nav:menu")
async def cb_menu(cb: CallbackQuery) -> None:
    await cb.message.answer(
        "🤖 <b>EduQuest menyusi</b>\n\n📚 Darslar — o‘qish va test\n"
        "⭐ Profilim — yulduzchalar va progress\n🏆 Yutuqlar — medallar",
        reply_markup=main_menu_keyboard(
            config.MINI_APP_URL, cb.from_user.id in config.ADMIN_USER_IDS
        ),
    )
    await cb.answer()


# ------------------------------------------------------------------ grade onboarding

async def show_grade_picker(target: Message, prefix: str = "gr") -> None:
    tg_id = target.from_user.id
    try:
        grades = await backend_client.grades(tg_id)
    except backend_client.BackendOffline:
        await _offline(target)
        return
    except backend_client.BackendBusiness as e:
        await _business(target, e)
        return
    await target.answer("🎓 Qaysi sinfdasiz? O‘zingiz tanlang:", reply_markup=grades_keyboard(grades, prefix))


@router.callback_query(F.data.startswith("gr:"))
async def cb_pick_grade(cb: CallbackQuery, state: FSMContext) -> None:
    grade_id = int(cb.data.split(":")[1])
    try:
        profile = await backend_client.set_grade(cb.from_user.id, grade_id)
    except backend_client.BackendOffline:
        await _offline(cb.message)
        return
    except backend_client.BackendBusiness as e:
        await _business(cb.message, e)
        return
    await cb.answer(f"Sinf: {profile['grade_name']} ✅", show_alert=False)
    await cb.message.answer(
        f"🎉 Ajoyib! Siz endi <b>{esc(profile['grade_name'])}</b> o‘quchisisiz.\n"
        "Keling, darslarni ochamiz!",
    )
    await show_subjects(cb.message)


# ------------------------------------------------------------------ subjects / ladder

@router.message(Command("lessons"))
async def cmd_lessons(message: Message) -> None:
    await show_subjects(message)


@router.callback_query(F.data == "nav:subjects")
async def cb_subjects(cb: CallbackQuery) -> None:
    await show_subjects(cb.message)
    await cb.answer()


async def show_subjects(target: Message) -> None:
    tg_id = target.from_user.id
    try:
        subjects = await backend_client.subjects(tg_id)
    except backend_client.BackendOffline:
        await _offline(target)
        return
    except backend_client.BackendBusiness as e:
        if e.code == "grade_not_selected":
            await target.answer("📚 Darslardan oldin sinfinizni tanlang!")
            await show_grade_picker(target)
        else:
            await _business(target, e)
        return
    if not subjects:
        await target.answer(
            "🚧 Bu sinf uchun darslar hozircha tayyorlanmoqda.\n"
            "1–4-sinflarda namuna darslar bor; qolganlarini admin to‘ldiradi.",
            reply_markup=menu_only_keyboard(),
        )
        return
    await target.answer("📚 Fanlaringiz (sinf: tanlangan):", reply_markup=subjects_keyboard(subjects))


@router.callback_query(F.data.startswith("su:"))
async def cb_subject(cb: CallbackQuery) -> None:
    subject_id = int(cb.data.split(":")[1])
    try:
        subjects = await backend_client.subjects(cb.from_user.id)
    except backend_client.BackendOffline:
        await _offline(cb.message)
        return
    except backend_client.BackendBusiness as e:
        await _business(cb.message, e)
        return
    subject = next((s for s in subjects if s["id"] == subject_id), None)
    if subject is None:
        await cb.message.answer("Bu fan topilmadi (sinf o‘zgargan bo‘lishi mumkin).")
        await show_subjects(cb.message)
        return
    await cb.message.answer(
        f"{subject['emoji']} <b>{esc(subject['name'])}</b> — bosqichlar:\n\n"
        "✅ tugatilgan · 📖 o‘qilgan · ▶️ ochiq · 🔒 qulflangan",
        reply_markup=lessons_keyboard(subject),
    )
    await cb.answer()


# ------------------------------------------------------------------ lesson

@router.callback_query(F.data.startswith("le:"))
async def cb_lesson(cb: CallbackQuery) -> None:
    lesson_id = int(cb.data.split(":")[1])
    try:
        lesson = await backend_client.lesson(cb.from_user.id, lesson_id)
    except backend_client.BackendOffline:
        await _offline(cb.message)
        return
    except backend_client.BackendBusiness as e:
        await _business(cb.message, e)
        return
    text = (
        f"📘 <b>{esc(lesson['subject_name'])} · {lesson['level_order']}-bosqich</b>\n"
        f"<b>{esc(lesson['title'])}</b>\n\n"
        f"{esc(lesson['explanation'])}\n\n"
        f"⭐ Sovrin: <b>{lesson['stars_reward']}</b> · o‘tish chegarasi: <b>{lesson['pass_threshold_percent']}%</b>"
    )
    await send_long(cb.message, text, reply_markup=lesson_actions_keyboard(lesson))
    await cb.answer()


@router.callback_query(F.data.startswith("vw:"))
async def cb_viewed(cb: CallbackQuery) -> None:
    lesson_id = int(cb.data.split(":")[1])
    try:
        result = await backend_client.mark_viewed(cb.from_user.id, lesson_id)
    except backend_client.BackendOffline:
        await _offline(cb.message)
        return
    except backend_client.BackendBusiness as e:
        await _business(cb.message, e)
        return
    if result["stars_granted"]:
        note = "✅ Barakalla, dars o‘qildi! ⭐ <b>+2 yulduzcha</b> qo‘shildi."
    else:
        note = "✅ Bu darsni allaqachon o‘qigansiz."
    for code in result.get("new_achievements", []):
        note += f"\n🏆 Yangi yutuq: <b>{esc(code)}</b>!"
    note += "\n\n🧩 Endi testni boshlashingiz mumkin (yuqoridagi tugma)."
    await cb.message.answer(note)
    await cb.answer()


# ------------------------------------------------------------------ quiz

class QuizStates(StatesGroup):
    running = State()  # lesson_id, questions, index, answers


async def _render_question(
    target: Message, questions: list[dict], lesson_id: int, index: int, answers: dict,
    *, state: FSMContext, quiz_title: str = "",
) -> None:
    """Shows questions[index] and keeps the whole quiz in FSM state."""
    await state.set_state(QuizStates.running)
    await state.update_data(
        lesson_id=lesson_id, questions=questions, index=index, answers=answers, quiz_title=quiz_title
    )
    q = questions[index]
    header = f"🧪 <b>{esc(quiz_title)}</b>\nSavol {index + 1}/{len(questions)}:"
    if q["kind"] == "text":
        await target.answer(f"{header}\n{esc(q['text'])}\n\n✍️ Javobingizni matn bilan yuboring:")
    else:
        await target.answer(
            f"{header}\n{esc(q['text'])}",
            reply_markup=quiz_question_keyboard(q, index, len(questions) - index),
        )


@router.callback_query(F.data.startswith("qz:"))
async def cb_quiz(cb: CallbackQuery, state: FSMContext) -> None:
    lesson_id = int(cb.data.split(":")[1])
    try:
        quiz = await backend_client.quiz(cb.from_user.id, lesson_id)
    except backend_client.BackendOffline:
        await _offline(cb.message)
        return
    except backend_client.BackendBusiness as e:
        await _business(cb.message, e)
        return
    await _render_question(
        cb.message, quiz["questions"], lesson_id, 0, {},
        state=state, quiz_title=quiz.get("lesson_title", "Test"),
    )
    await cb.answer()


def _answers_payload(answers: dict[str, Any]) -> list[dict[str, Any]]:
    return [{"question_id": int(qid), **val} for qid, val in answers.items()]


async def _finish_quiz(target: Message, state: FSMContext, lesson_id: int, answers: dict) -> None:
    await state.clear()
    try:
        result = await backend_client.submit_quiz(
            target.from_user.id, lesson_id, uuid.uuid4().hex, _answers_payload(answers)
        )
    except backend_client.BackendOffline:
        await _offline(target)
        return
    except backend_client.BackendBusiness as e:
        await _business(target, e)
        return
    lines = [
        f"🧪 <b>Test natijasi</b>",
        f"{esc(result['message_uz'])}",
        "",
        f"✅ To‘g‘ri javoblar: <b>{result['correct_count']}/{result['total_count']}</b> · {result['score_percent']}%",
        f"⭐ Sovrin: <b>+{result['stars_earned']}</b> (jami: {result['stars_total']})",
    ]
    if result["next_level_unlocked"]:
        lines.append("🚀 Keyingi bosqich ochildi!")
    for code in result["new_achievements"]:
        lines.append(f"🏆 Yangi yutuq: <b>{esc(code)}</b>!")
    await target.answer(
        "\n".join(lines),
        reply_markup=quiz_result_keyboard(result["passed"], lesson_id),
    )


@router.callback_query(QuizStates.running, F.data.startswith("qa:"))
async def cb_answer(cb: CallbackQuery, state: FSMContext) -> None:
    _, idx, opt = cb.data.split(":")
    data = await state.get_data()
    questions = data["questions"]
    i = int(idx)
    if not (0 <= i < len(questions)) or i != data["index"]:
        await cb.answer("Bu javob endigiga tegishli emas — joriy savolga javob bering 🙂", show_alert=True)
        return
    q = questions[i]
    try:
        option = q["options"][int(opt)]
    except (ValueError, IndexError):
        await cb.answer("Variant topilmadi — qayta urinib ko‘ring.", show_alert=True)
        return
    answers = data["answers"]
    answers[str(q["id"])] = {"option_id": option["id"]}
    nxt = data["index"] + 1
    if nxt >= len(questions):
        await _finish_quiz(cb.message, state, data["lesson_id"], answers)
    else:
        await _render_question(
            cb.message, questions, data["lesson_id"], nxt, answers,
            state=state, quiz_title=data.get("quiz_title", "Test"),
        )
    await cb.answer()


@router.message(QuizStates.running, F.text)
async def msg_text_answer(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    questions = data["questions"]
    q = questions[data["index"]]
    if q["kind"] != "text":
        await message.answer("👆 Bu savolga quyidagi variant tugmalaridan birini bosib javob bering.")
        return
    answers = data["answers"]
    answers[str(q["id"])] = {"text": message.text.strip()[:255]}
    nxt = data["index"] + 1
    if nxt >= len(questions):
        await _finish_quiz(message, state, data["lesson_id"], answers)
    else:
        await _render_question(
            message, questions, data["lesson_id"], nxt, answers,
            state=state, quiz_title=data.get("quiz_title", "Test"),
        )
