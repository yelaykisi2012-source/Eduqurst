"""
keyboards/inline.py — all inline (above-the-message) keyboards in one place.

A Mini App launch button is an InlineKeyboardButton with a `web_app`
payload (WebAppInfo) instead of `callback_data`/`url`. When the pupil
taps it, Telegram opens your HTTPS-hosted React app inside Telegram.

Callback data conventions (keep short, Telegram limit is 64 bytes):
  nav:<page>          — menu navigation (subjects / profile / ach / admin)
  gr:<grade_id>       — pupil picks a grade
  su:<subject_id>     — open a subject's lesson ladder
  le:<lesson_id>      — open a lesson
  vw:<lesson_id>      — mark lesson as read
  qz:<lesson_id>      — start / restart the quiz
  qa:<q_index>:<opt_index> — answer for question q_index with option opt_index
  adm:*               — admin flows (see admin.py)
"""
from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    WebAppInfo,
)


def _btn(text: str, cb: str, enabled: bool = True) -> InlineKeyboardButton:
    """A real button when we have a callback; a grey, harmless button otherwise."""
    if enabled and cb:
        return InlineKeyboardButton(text=text, callback_data=cb)
    return InlineKeyboardButton(text=text, enabled=False)


def main_menu_keyboard(mini_app_url: str, is_admin: bool = False) -> InlineKeyboardMarkup:
    """The home menu shown after /start: bot learning + the Mini App button."""
    rows = [
        [
            _btn("📚 Darslar", "nav:subjects"),
            _btn("⭐ Profilim", "nav:profile"),
            _btn("🏆 Yutuqlar", "nav:ach"),
        ]
    ]
    app_row = [_btn("🚀 Mini App", "") if not mini_app_url else
               InlineKeyboardButton(text="🚀 Mini App’ni ochish", web_app=WebAppInfo(url=mini_app_url))]
    if is_admin:
        app_row.append(_btn("🛠 Admin", "nav:admin"))
    rows.append(app_row)
    return InlineKeyboardMarkup(inline_keyboard=rows)


def grades_keyboard(grades: list[dict], prefix: str = "gr") -> InlineKeyboardMarkup:
    """1–11 grade picker; `prefix` lets admins reuse it (gr / ags / agl / agq)."""
    rows = []
    current = []
    for g in grades:
        current.append(_btn(g["name"], f"{prefix}:{g['id']}"))
        if len(current) == 4:
            rows.append(current)
            current = []
    if current:
        rows.append(current)
    return InlineKeyboardMarkup(inline_keyboard=rows)


def subjects_keyboard(subjects: list[dict]) -> InlineKeyboardMarkup:
    rows = []
    current: list[InlineKeyboardButton] = []
    for s in subjects:
        total = len(s.get("lessons", []))
        done = sum(1 for l in s.get("lessons", []) if l.get("passed"))
        label = f"{s['emoji']} {s['name']}" + (f" ({done}/{total})" if total else " 🚧")
        current.append(_btn(label, f"su:{s['id']}", enabled=total > 0))
        if len(current) == 2:
            rows.append(current)
            current = []
    if current:
        rows.append(current)
    rows.append([_btn("⬅️ Menyu", "nav:menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def lessons_keyboard(subject: dict) -> InlineKeyboardMarkup:
    """Lesson ladder: ✅ passed · 📖 o‘qilgan · ▶️ ochiq · 🔒 qulflangan."""
    rows = []
    for l in subject.get("lessons", []):
        if l.get("passed"):
            icon = "✅"
        elif l.get("viewed"):
            icon = "📖"
        elif l.get("unlocked"):
            icon = "▶️"
        else:
            icon = "🔒"
        rows.append([_btn(f"{icon} {l['level_order']}. {l['title']}", f"le:{l['id']}",
                          enabled=bool(l.get("unlocked")) or bool(l.get("passed")) or bool(l.get("viewed")))])
    rows.append([_btn("⬅️ Fanlar", "nav:subjects")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def lesson_actions_keyboard(lesson: dict) -> InlineKeyboardMarkup:
    lid = lesson["id"]
    rows = []
    if not lesson.get("viewed"):
        rows.append([_btn("✅ O‘qib bo‘ldim", f"vw:{lid}")])
    rows.append([_btn("🧩 Testni boshlash", f"qz:{lid}")])
    rows.append([_btn("⬅️ Bosqichlar", "nav:subjects")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def quiz_question_keyboard(question: dict, q_index: int, total_left: int) -> InlineKeyboardMarkup:
    """Options for one question + cancel."""
    rows = []
    current: list[InlineKeyboardButton] = []
    for j, opt in enumerate(question.get("options", [])):
        current.append(_btn(opt["text"], f"qa:{q_index}:{j}"))
        if len(current) == 2:
            rows.append(current)
            current = []
    if current:
        rows.append(current)
    rows.append([_btn(f"⏹ To‘xtatish ({total_left} savol qoldi)", "nav:subjects")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def quiz_result_keyboard(passed: bool, lesson_id: int) -> InlineKeyboardMarkup:
    rows = []
    if not passed:
        rows.append([_btn("🔁 Qayta urinish", f"qz:{lesson_id}")])
    rows.append([_btn("📚 Boshqa darslar", "nav:subjects")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def menu_only_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[_btn("🏠 Bosh menyu", "nav:menu")]])


def admin_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [_btn("📊 Holat", "adm:stat")],
            [_btn("🏫 Fan qo‘shish", "adm:addsubject")],
            [_btn("📖 Dars qo‘shish", "adm:addlesson")],
            [_btn("❓ Savol qo‘shish", "adm:addquestion")],
            [_btn("⬅️ Menyu", "nav:menu")],
        ]
    )


def admin_pick_row(buttons: list[tuple[str, str]], back_cb: str = "nav:admin") -> InlineKeyboardMarkup:
    """Generic 2-per-row picker from (text, callback) pairs — admin flows."""
    rows, current = [], []
    for text, cb in buttons:
        current.append(_btn(text, cb))
        if len(current) == 2:
            rows.append(current)
            current = []
    if current:
        rows.append(current)
    rows.append([_btn("⬅️ Bekor", back_cb)])
    return InlineKeyboardMarkup(inline_keyboard=rows)
