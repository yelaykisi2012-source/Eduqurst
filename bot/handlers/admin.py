"""
handlers/admin.py — content management INSIDE the bot (admins only).

Two gates:
  1) config.ADMIN_USER_IDS (bot/.env) — only these Telegram ids see the flow;
  2) the backend re-checks ADMIN_TELEGRAM_IDS on every call — the bot UI
     alone can never grant admin powers.

Flows (each is a small FSM asking one thing at a time):
  🏫 Fan qo'shish      : sinf → nom → emoji
  📖 Dars qo'shish     : sinf → fan → sarlavha → matn → ⭐ → chegara %
  🎞 Material qo'shish : sinf → fan → dars → format → sarlavha → havola/matn
  ❓ Savol qo'shish    : sinf → fan → dars → savol → variantlar (* = to'g'ri)

Material formats: video (havola), pdf (havola), live (havola), text (yozma matn).
"""
from __future__ import annotations

import html
import logging

from aiogram import F, Router
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

import backend_client
import config
from keyboards.inline import (
    admin_menu_keyboard,
    admin_pick_row,
    grades_keyboard,
    main_menu_keyboard,
    material_kind_keyboard,
)

logger = logging.getLogger(__name__)
router = Router(name="admin")


def esc(value: object) -> str:
    return html.escape(str(value), quote=False)


class AdmStates(StatesGroup):
    pick_grade = State()      # waiting for a grade button (per flow type in data)
    subject_name = State()    # text: fan nomi
    subject_emoji = State()   # text: emoji yoki "default"
    lesson_subject = State()  # button: fan
    lesson_title = State()    # text
    lesson_text = State()     # text (may be long)
    lesson_stars = State()    # text: int or "skip"
    lesson_threshold = State()
    material_subject = State()
    material_lesson = State()
    material_kind = State()     # button: video / pdf / live / text
    material_title = State()    # text
    material_content = State()  # text: URL (video/pdf/live) yoki matn (text)
    question_subject = State()
    question_lesson = State()
    question_text = State()
    question_options = State()


def _is_admin(user_id: int) -> bool:
    return user_id in config.ADMIN_USER_IDS


async def _fail(target: Message, e: Exception) -> None:
    if isinstance(e, backend_client.BackendOffline):
        await target.answer("🔌 Serverga bog‘lanib bo‘lmadi — qayta urinib ko‘ring.")
    elif isinstance(e, backend_client.BackendBusiness):
        await target.answer(f"⚠️ {esc(e.message)}")
    else:
        raise e


# Any plain text typed while a grade/subject button is expected → gentle hint.
async def _press_a_button(message: Message) -> None:
    await message.answer("👆 Iltimos, yuqoridagi <b>tugmalardan</b> birini bosing.")


@router.callback_query(F.data == "nav:admin")
async def cb_admin_menu(cb: CallbackQuery, state: FSMContext) -> None:
    if not _is_admin(cb.from_user.id):
        await cb.answer("🔐 Bu bo‘lim faqat adminlar uchun.", show_alert=True)
        return
    await state.clear()
    await cb.message.answer("🛠 <b>Admin panel (bot rejimi)</b>", reply_markup=admin_menu_keyboard())
    await cb.answer()


# leaving admin via the generic menu — cancel the FSM cleanly, then show menu
@router.callback_query(F.data.in_({"nav:menu", "adm:cancel"}), StateFilter(AdmStates))
async def cb_leave_admin(cb: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    if cb.data == "adm:cancel":
        await cb.message.answer("⬅️ Bekor qilindi.", reply_markup=admin_menu_keyboard())
    else:
        await cb.message.answer(
            "🤖 <b>EduQuest menyusi</b>",
            reply_markup=main_menu_keyboard(config.MINI_APP_URL, _is_admin(cb.from_user.id)),
        )
    await cb.answer()


@router.callback_query(F.data == "adm:stat")
async def cb_stats(cb: CallbackQuery) -> None:
    if not _is_admin(cb.from_user.id):
        await cb.answer("🔐 Faqat adminlar.", show_alert=True)
        return
    await cb.answer()
    try:
        overview = await backend_client.admin_overview(cb.from_user.id)
    except Exception as e:
        await _fail(cb.message, e)
        return
    lines = ["📊 <b>Kontent holati</b>\n"]
    total_lessons = 0
    for g in overview:
        if not g["subjects"]:
            lines.append(f"{g['grade_name']}: 🚧 (fanlar yo‘q)")
            continue
        parts = [f"{s['emoji']} {esc(s['name'])} ({s['lesson_count']})" for s in g["subjects"]]
        total_lessons += sum(s["lesson_count"] for s in g["subjects"])
        lines.append(f"{g['grade_name']}: " + ", ".join(parts))
    lines.append(f"\nJami darslar: <b>{total_lessons}</b>")
    await cb.message.answer("\n".join(lines))


# ------------------------------------------------------------------ common: grade picker

async def _ask_grade(cb: CallbackQuery, state: FSMContext, flow: str, question: str) -> None:
    if not _is_admin(cb.from_user.id):
        await cb.answer("🔐 Faqat adminlar.", show_alert=True)
        return
    await cb.answer()  # stop the spinner before the API call
    try:
        grades = await backend_client.grades(cb.from_user.id)
    except Exception as e:
        await _fail(cb.message, e)
        return
    await state.set_state(AdmStates.pick_grade)
    await state.update_data(flow=flow)
    await cb.message.answer(question, reply_markup=grades_keyboard(grades, "ag"))


@router.callback_query(AdmStates.pick_grade, F.data.startswith("ag:"))
async def adm_grade_chosen(cb: CallbackQuery, state: FSMContext) -> None:
    await cb.answer()  # stop the spinner immediately — API calls follow
    data = await state.get_data()
    flow = data.get("flow")
    if not flow:
        await state.clear()
        await cb.message.answer(
            "⌛ Sessiya eskirgan. Admin menyudan qaytadan boshlang.",
            reply_markup=admin_menu_keyboard(),
        )
        return
    grade_id = int(cb.data.split(":")[1])
    await state.update_data(grade_id=grade_id)
    tg = cb.from_user.id
    if flow == "subject":
        await state.set_state(AdmStates.subject_name)
        await cb.message.answer("✏️ Fan nomini yuboring (masalan: <b>Tarix</b>):")
    elif flow == "lesson":
        try:
            overview = await backend_client.admin_overview(tg)
            grade = next(g for g in overview if g["grade_id"] == grade_id)
            buttons = [(f"{s['emoji']} {s['name']}", f"ls:{s['id']}") for s in grade["subjects"]]
        except Exception as e:
            await _fail(cb.message, e)
            return
        if not buttons:
            await cb.message.answer("Bu sinfda fan yo‘q — avval «🏫 Fan qo‘shish».")
            await state.clear()
        else:
            await state.set_state(AdmStates.lesson_subject)
            await cb.message.answer("Qaysi fanga dars qo‘shamiz?", reply_markup=admin_pick_row(buttons, "adm:cancel"))
    elif flow == "material":
        try:
            overview = await backend_client.admin_overview(tg)
            grade = next(g for g in overview if g["grade_id"] == grade_id)
            buttons = [(f"{s['emoji']} {s['name']}", f"ms:{s['id']}") for s in grade["subjects"]]
        except Exception as e:
            await _fail(cb.message, e)
            return
        if not buttons:
            await cb.message.answer("Bu sinfda fan yo‘q — avval «🏫 Fan qo‘shish».")
            await state.clear()
        else:
            await state.set_state(AdmStates.material_subject)
            await cb.message.answer("Qaysi fandagi darsga material qo‘shamiz?",
                                    reply_markup=admin_pick_row(buttons, "adm:cancel"))
    else:  # question
        try:
            overview = await backend_client.admin_overview(tg)
            grade = next(g for g in overview if g["grade_id"] == grade_id)
            buttons = [(f"{s['emoji']} {s['name']}", f"qs:{s['id']}") for s in grade["subjects"]]
        except Exception as e:
            await _fail(cb.message, e)
            return
        if not buttons:
            await cb.message.answer("Bu sinfda fan yo‘q.")
            await state.clear()
        else:
            await state.set_state(AdmStates.question_subject)
            await cb.message.answer("Qaysi fanga savol qo‘shamiz?", reply_markup=admin_pick_row(buttons, "adm:cancel"))


@router.message(AdmStates.pick_grade, F.text)
async def adm_grade_text(message: Message) -> None:
    await _press_a_button(message)


# ------------------------------------------------------------------ 🏫 fan qo'shish

@router.callback_query(F.data == "adm:addsubject")
async def adm_add_subject(cb: CallbackQuery, state: FSMContext) -> None:
    await _ask_grade(cb, state, "subject", "🏫 Fanni qaysi sinfga qo‘shamiz? Sinfni tanlang:")


@router.message(AdmStates.subject_name, F.text)
async def adm_subject_name(message: Message, state: FSMContext) -> None:
    await state.update_data(name=message.text.strip()[:64])
    await state.set_state(AdmStates.subject_emoji)
    await message.answer("Endi emoji yuboring (masalan 📐) yoki <b>default</b> deb yozing:")


@router.message(AdmStates.subject_emoji, F.text)
async def adm_subject_emoji(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    if not data.get("name") or not data.get("grade_id"):
        await state.clear()
        await message.answer(
            "⌛ Sessiya eskirgan. Admin menyudan qaytadan boshlang.",
            reply_markup=admin_menu_keyboard(),
        )
        return
    emoji = "📘" if message.text.strip().lower() == "default" else message.text.strip()[:8]
    try:
        subject = await backend_client.admin_create_subject(
            message.from_user.id, data["grade_id"], data["name"], emoji
        )
    except Exception as e:
        await _fail(message, e)
        return
    await state.clear()
    await message.answer(
        f"✅ Fan qo‘shildi: <b>{esc(subject['emoji'])} {esc(subject['name'])}</b> (id={subject['id']}).",
        reply_markup=admin_menu_keyboard(),
    )


# ------------------------------------------------------------------ 📖 dars qo'shish

@router.callback_query(F.data == "adm:addlesson")
async def adm_add_lesson(cb: CallbackQuery, state: FSMContext) -> None:
    await _ask_grade(cb, state, "lesson", "📖 Darsni qaysi sinfga qo‘shamiz? Sinfni tanlang:")


@router.callback_query(AdmStates.lesson_subject, F.data.startswith("ls:"))
async def adm_lesson_subject(cb: CallbackQuery, state: FSMContext) -> None:
    await state.update_data(subject_id=int(cb.data.split(":")[1]))
    await state.set_state(AdmStates.lesson_title)
    await cb.message.answer("✏️ Dars nomini yuboring (masalan: <b>Ozarlar va ularning belgilari</b>):")
    await cb.answer()


@router.message(AdmStates.lesson_subject, F.text)
async def adm_lesson_subject_text(message: Message) -> None:
    await _press_a_button(message)


@router.message(AdmStates.lesson_title, F.text)
async def adm_lesson_title(message: Message, state: FSMContext) -> None:
    await state.update_data(title=message.text.strip()[:160])
    await state.set_state(AdmStates.lesson_text)
    await message.answer("📄 Dars matnini yuboring (o‘quvchi shu matnni o‘qiydi, kamida 10 belgi):")


@router.message(AdmStates.lesson_text, F.text)
async def adm_lesson_text(message: Message, state: FSMContext) -> None:
    text = message.text.strip()
    if len(text) < 10:
        await message.answer("⚠️ Matn juda qisqa (kamida 10 belgi). Qayta yuboring.")
        return
    await state.update_data(explanation=text)
    await state.set_state(AdmStates.lesson_stars)
    await message.answer("⭐ Bu dars uchun nechta yulduzcha? (1–50, yoki <b>skip</b> = 5)")


@router.message(AdmStates.lesson_stars, F.text)
async def adm_lesson_stars(message: Message, state: FSMContext) -> None:
    raw = message.text.strip().lower()
    if raw in {"skip", "default", "-"}:
        stars = 5
    elif raw.isdigit() and 1 <= int(raw) <= 50:
        stars = int(raw)
    else:
        await message.answer("1–50 orasida son yuboring (yoki <b>skip</b>).")
        return
    await state.update_data(stars=stars)
    await state.set_state(AdmStates.lesson_threshold)
    await message.answer("O‘tish chegarasi %? (10–100, yoki <b>skip</b> = 60)")


@router.message(AdmStates.lesson_threshold, F.text)
async def adm_lesson_threshold(message: Message, state: FSMContext) -> None:
    raw = message.text.strip().lower()
    if raw in {"skip", "default", "-"}:
        threshold = 60
    elif raw.isdigit() and 10 <= int(raw) <= 100:
        threshold = int(raw)
    else:
        await message.answer("10–100 orasida son yuboring (yoki <b>skip</b>).")
        return
    data = await state.get_data()
    try:
        lesson = await backend_client.admin_create_lesson(
            message.from_user.id, data["subject_id"], data["title"],
            data["explanation"], data["stars"], threshold,
        )
    except Exception as e:
        await _fail(message, e)
        return
    await state.clear()
    await message.answer(
        f"✅ Dars qo‘shildi: <b>{esc(lesson['title'])}</b> "
        f"({lesson['level_order']}-bosqich, {data['stars']} ⭐). Testdan o‘tish: {threshold}%.\n"
        "Endi unga savol qo‘shing — «❓ Savol qo‘shish».",
        reply_markup=admin_menu_keyboard(),
    )


# ------------------------------------------------------------------ 🎞 material qo'shish

@router.callback_query(F.data == "adm:addmaterial")
async def adm_add_material(cb: CallbackQuery, state: FSMContext) -> None:
    await _ask_grade(cb, state, "material", "🎞 Materialni qaysi sinfga qo‘shamiz? Sinfni tanlang:")


@router.callback_query(AdmStates.material_subject, F.data.startswith("ms:"))
async def adm_material_subject(cb: CallbackQuery, state: FSMContext) -> None:
    await cb.answer()
    subject_id = int(cb.data.split(":")[1])
    try:
        lessons = await backend_client.admin_lessons(cb.from_user.id, subject_id)
    except Exception as e:
        await _fail(cb.message, e)
        return
    if not lessons:
        await cb.message.answer("Bu fanda dars yo‘q — avval «📖 Dars qo‘shish».")
        await state.clear()
        return
    buttons = [(f"{l['level_order']}. {l['title'][:40]}", f"ml:{l['id']}") for l in lessons]
    await state.set_state(AdmStates.material_lesson)
    await cb.message.answer("Qaysi darsga material qo‘shamiz?",
                            reply_markup=admin_pick_row(buttons, "adm:cancel"))


@router.message(AdmStates.material_subject, F.text)
async def adm_material_subject_text(message: Message) -> None:
    await _press_a_button(message)


@router.callback_query(AdmStates.material_lesson, F.data.startswith("ml:"))
async def adm_material_lesson(cb: CallbackQuery, state: FSMContext) -> None:
    await cb.answer()
    await state.update_data(material_lesson_id=int(cb.data.split(":")[1]))
    await state.set_state(AdmStates.material_kind)
    await cb.message.answer(
        "Formatni tanlang:\n"
        "▶️ Video — YouTube/MP4 havola\n"
        "📄 PDF — hujjat havolasi\n"
        "🔴 Jonli dars — Zoom/YouTube Live havola\n"
        "📝 Yozma matn — oddiy matn",
        reply_markup=material_kind_keyboard(),
    )


@router.message(AdmStates.material_lesson, F.text)
async def adm_material_lesson_text(message: Message) -> None:
    await _press_a_button(message)


@router.callback_query(AdmStates.material_kind, F.data.startswith("mk:"))
async def adm_material_kind(cb: CallbackQuery, state: FSMContext) -> None:
    await cb.answer()
    kind = cb.data.split(":")[1]
    await state.update_data(material_kind=kind)
    await state.set_state(AdmStates.material_title)
    labels = {"video": "video", "pdf": "PDF", "live": "jonli dars", "text": "yozma matn"}
    await cb.message.answer(f"🏷 {labels.get(kind, 'material').capitalize()} uchun sarlavha yuboring:")


@router.message(AdmStates.material_kind, F.text)
async def adm_material_kind_text(message: Message) -> None:
    await _press_a_button(message)


@router.message(AdmStates.material_title, F.text)
async def adm_material_title(message: Message, state: FSMContext) -> None:
    title = message.text.strip()[:160]
    if len(title) < 2:
        await message.answer("Sarlavha kamida 2 belgi bo‘lsin. Qayta yuboring.")
        return
    await state.update_data(material_title=title)
    data = await state.get_data()
    kind = data.get("material_kind", "text")
    await state.set_state(AdmStates.material_content)
    if kind == "text":
        await message.answer("📝 Yozma matnni yuboring (o‘quvchi dars ichida o‘qiydi):")
    else:
        await message.answer(
            "🔗 Havolani yuboring. <b>https://</b> yoki <b>http://</b> bilan boshlansin.\n"
            "Masalan: <code>https://youtu.be/…</code>"
        )


@router.message(AdmStates.material_content, F.text)
async def adm_material_content(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    kind = data.get("material_kind", "text")
    content = message.text.strip()
    if not data.get("material_lesson_id") or not data.get("material_title"):
        await state.clear()
        await message.answer(
            "⌛ Sessiya eskirgan. Admin menyudan qaytadan boshlang.",
            reply_markup=admin_menu_keyboard(),
        )
        return
    if kind in {"video", "pdf", "live"} and not content.lower().startswith(("http://", "https://")):
        await message.answer("⚠️ Bu format uchun havola kerak (http:// yoki https://). Qayta yuboring.")
        return
    if not content:
        await message.answer("Bo‘sh bo‘lmasin. Qayta yuboring.")
        return
    try:
        material = await backend_client.admin_create_material(
            message.from_user.id, data["material_lesson_id"], kind,
            data["material_title"], content[:5000],
        )
    except Exception as e:
        await _fail(message, e)
        return
    await state.clear()
    labels = {"video": "▶️ Video", "pdf": "📄 PDF", "live": "🔴 Jonli dars", "text": "📝 Yozma matn"}
    await message.answer(
        f"✅ Material qo‘shildi: <b>{labels.get(kind, kind)}</b> — {esc(material['title'])}.",
        reply_markup=admin_menu_keyboard(),
    )


# ------------------------------------------------------------------ ❓ savol qo'shish

@router.callback_query(F.data == "adm:addquestion")
async def adm_add_question(cb: CallbackQuery, state: FSMContext) -> None:
    await _ask_grade(cb, state, "question", "❓ Savolni qaysi sinfga qo‘shamiz? Sinfni tanlang:")


@router.callback_query(AdmStates.question_subject, F.data.startswith("qs:"))
async def adm_question_subject(cb: CallbackQuery, state: FSMContext) -> None:
    await cb.answer()
    subject_id = int(cb.data.split(":")[1])
    try:
        lessons = await backend_client.admin_lessons(cb.from_user.id, subject_id)
    except Exception as e:
        await _fail(cb.message, e)
        return
    if not lessons:
        await cb.message.answer("Bu fanda dars yo‘q — avval «📖 Dars qo‘shish».")
        await state.clear()
    else:
        buttons = [(f"{l['level_order']}. {l['title'][:40]}", f"ql:{l['id']}") for l in lessons]
        await state.set_state(AdmStates.question_lesson)
        await cb.message.answer("Qaysi darsga savol qo‘shamiz?", reply_markup=admin_pick_row(buttons, "adm:cancel"))


@router.message(AdmStates.question_subject, F.text)
async def adm_question_subject_text(message: Message) -> None:
    await _press_a_button(message)


@router.callback_query(AdmStates.question_lesson, F.data.startswith("ql:"))
async def adm_question_lesson(cb: CallbackQuery, state: FSMContext) -> None:
    await state.update_data(lesson_id=int(cb.data.split(":")[1]))
    await state.set_state(AdmStates.question_text)
    await cb.message.answer("✍️ Savol matnini yuboring (masalan: <b>7 − 3 nechaga teng?</b>):")
    await cb.answer()


@router.message(AdmStates.question_lesson, F.text)
async def adm_question_lesson_text(message: Message) -> None:
    await _press_a_button(message)


@router.message(AdmStates.question_text, F.text)
async def adm_question_text(message: Message, state: FSMContext) -> None:
    text = message.text.strip()
    if len(text) < 3:
        await message.answer("Savol kamida 3 belgi bo‘lsin. Qayta yuboring.")
        return
    await state.update_data(q_text=text)
    await state.set_state(AdmStates.question_options)
    await message.answer(
        "Javob variantlarini yuboring — <b>har biri alohida qatorda</b>.\n"
        "To‘g‘ri javobning oldiga <b>*</b> qo‘ying.\n\n"
        "Masalan:\n<code>4\n*5\n6</code>\n\n"
        "(2–6 variant bo‘lishi kerak)"
    )


@router.message(AdmStates.question_options, F.text)
async def adm_question_options(message: Message, state: FSMContext) -> None:
    lines = [ln.strip() for ln in message.text.splitlines() if ln.strip()]
    options = [{"text": ln.lstrip("*").strip()[:255], "is_correct": ln.startswith("*")} for ln in lines]
    options = [o for o in options if o["text"]]
    correct = [o for o in options if o["is_correct"]]
    if len(options) < 2 or len(options) > 6:
        await message.answer("Kamida 2, ko‘pi bilan 6 variant kerak. Qayta yuboring.")
        return
    if len(correct) != 1:
        await message.answer("Aynan <b>bitta</b> variantning oldiga * qo‘ying (to‘g‘ri javob). Qayta yuboring.")
        return
    data = await state.get_data()
    if not data.get("lesson_id") or not data.get("q_text"):
        await state.clear()
        await message.answer(
            "⌛ Sessiya eskirgan. Admin menyudan qaytadan boshlang.",
            reply_markup=admin_menu_keyboard(),
        )
        return
    try:
        q = await backend_client.admin_create_question(
            message.from_user.id, data["lesson_id"], data["q_text"], "single", options
        )
    except Exception as e:
        await _fail(message, e)
        return
    await state.clear()
    await message.answer(
        f"✅ Savol qo‘shildi ({q['option_count']} variant, to‘g‘risi: {q['correct_count']}).",
        reply_markup=admin_menu_keyboard(),
    )
