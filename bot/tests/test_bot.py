"""
tests/test_bot.py — dependency-free checks for the Telegram bot UI.

Run:  python -m unittest discover -s tests -v   (inside bot/.venv)

What is covered:
- every inline button is real: has a URL, a Mini App target, or short
  callback_data (Telegram hard limit: 64 bytes); no dead buttons;
- every callback prefix the keyboards can emit has a matching handler in the
  router order used by main.py (admin -> learn -> profile);
- the quiz survives a lost FSM state (fallback handler instead of silence);
- materials of every format reach the lesson keyboard, including images and
  text materials that contain a link;
- long lesson text is chunked below Telegram's 4096-character limit;
- achievements are shown with human titles, not raw codes.
"""
from __future__ import annotations

import asyncio
import os
import sys
import unittest
from datetime import datetime, timezone

# Config is imported by the handlers; keep test values local (never real ones).
os.environ.setdefault("BOT_TOKEN", "012345:TEST_TOKEN_NOT_REAL")
os.environ.setdefault("API_URL", "http://127.0.0.1:9")
os.environ.setdefault("MINI_APP_URL", "https://example.com/app")
os.environ.setdefault("ADMIN_USER_IDS", "999000111")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from aiogram.types import CallbackQuery, Chat, Message, User  # noqa: E402

from handlers import admin as admin_handlers  # noqa: E402
from handlers import learn as learn_handlers  # noqa: E402
from handlers import profile as profile_handlers  # noqa: E402
from keyboards import inline as kb  # noqa: E402

ROUTERS = [
    admin_handlers.router,
    learn_handlers.router,
    profile_handlers.router,
]

GRADES = [{"id": i, "name": f"{i}-sinf", "order_index": i} for i in range(1, 12)]

SUBJECTS = [
    {
        "id": 1,
        "name": "Matematika",
        "emoji": "🔢",
        "lessons": [
            {"id": 10, "title": "Sonlar", "level_order": 1, "passed": False, "viewed": True, "unlocked": True},
            {"id": 11, "title": "Qo‘shish", "level_order": 2, "passed": False, "viewed": False, "unlocked": False},
        ],
    },
    {"id": 2, "name": "Bo‘sh fan", "emoji": "🚧", "lessons": []},
]

LESSON = {
    "id": 10,
    "subject_name": "Matematika",
    "title": "Sonlar",
    "explanation": "Matn",
    "level_order": 1,
    "stars_reward": 5,
    "pass_threshold_percent": 60,
    "viewed": False,
    "video_url": "https://youtu.be/lesson",
    "materials": [
        {"id": 1, "kind": "video", "title": "Video dars", "content": "https://youtu.be/v"},
        {"id": 2, "kind": "pdf", "title": "Mashqlar", "content": "https://example.com/a.pdf"},
        {"id": 3, "kind": "live", "title": "Dushanba 18:00", "content": "https://meet.example.com/x"},
        {"id": 4, "kind": "text", "title": "Eslatma", "content": "Yozma matn"},
        {"id": 5, "kind": "image", "title": "Rasm", "content": "https://example.com/a.png"},
        {"id": 6, "kind": "text", "title": "Qo‘shimcha havola", "content": "https://example.com/extra"},
    ],
}

QUESTION = {
    "id": 1,
    "text": "3 + 4 = ?",
    "kind": "single",
    "options": [{"id": 1, "text": "7"}, {"id": 2, "text": "8"}],
}


def all_buttons():
    """Every keyboard the bot can render, with realistic payloads."""
    keyboards = [
        kb.main_menu_keyboard("https://example.com/app", is_admin=True),
        kb.main_menu_keyboard("https://example.com/app", is_admin=False),
        kb.main_menu_keyboard("", is_admin=False),
        kb.grades_keyboard(GRADES),
        kb.grades_keyboard(GRADES, prefix="ag"),
        kb.subjects_keyboard(SUBJECTS),
        kb.lessons_keyboard(SUBJECTS[0]),
        kb.lesson_actions_keyboard(LESSON),
        kb.lesson_actions_keyboard({**LESSON, "viewed": True, "video_url": None}),
        kb.quiz_question_keyboard(QUESTION, 0, 5),
        kb.quiz_result_keyboard(True, 10),
        kb.quiz_result_keyboard(False, 10),
        kb.quiz_start_keyboard(10),
        kb.menu_only_keyboard(),
        kb.admin_menu_keyboard(),
        kb.material_kind_keyboard(),
        kb.admin_pick_row(
            [(f"9. {'x' * 80}", "ml:123456789"), ("Fan", "ms:1")],
            "adm:cancel",
        ),
    ]
    for markup in keyboards:
        for row in markup.inline_keyboard:
            for button in row:
                yield button


def fake_callback(data: str) -> CallbackQuery:
    return CallbackQuery(
        id="1",
        from_user=User(id=999000111, is_bot=False, first_name="Admin"),
        chat_instance="test-instance",
        data=data,
        message=Message(
            message_id=1,
            date=datetime.now(timezone.utc),
            chat=Chat(id=1, type="private"),
        ),
    )


class KeyboardTests(unittest.TestCase):
    def test_no_button_is_dead(self):
        for button in all_buttons():
            self.assertTrue(
                button.url or button.web_app or button.callback_data or button.enabled is False,
                f"dead button: {button.text!r}",
            )
            self.assertTrue(button.text.strip(), "empty button label")

    def test_callback_data_fits_telegram_limit(self):
        for button in all_buttons():
            if button.callback_data:
                self.assertLessEqual(
                    len(button.callback_data.encode("utf-8")), 64,
                    f"callback too long: {button.callback_data!r}",
                )

    def test_every_material_format_gets_a_button(self):
        markup = kb.lesson_actions_keyboard(LESSON)
        urls = [b.url for row in markup.inline_keyboard for b in row if b.url]
        assert "https://youtu.be/v" in urls          # video
        assert "https://example.com/a.pdf" in urls   # pdf
        assert "https://meet.example.com/x" in urls  # live
        assert "https://example.com/a.png" in urls   # image
        assert "https://example.com/extra" in urls   # text with a link
        assert "https://youtu.be/lesson" in urls     # legacy lesson.video_url

    def test_written_notes_are_not_link_buttons(self):
        markup = kb.lesson_actions_keyboard(LESSON)
        labels = [b.text for row in markup.inline_keyboard for b in row]
        self.assertFalse(any("Eslatma" in label for label in labels))


class HandlerCoverageTests(unittest.TestCase):
    """Every callback the keyboards emit must be handled in router order."""

    def _first_handler(self, data: str, raw_state: str | None) -> str | None:
        event = fake_callback(data)
        for router in ROUTERS:
            for handler in router.callback_query.handlers:
                ok, _ = asyncio.run(handler.check(event, raw_state=raw_state))
                if ok:
                    return getattr(handler.callback, "__name__", "?")
        return None

    def test_navigation_callbacks(self):
        cases = {
            "nav:menu": "cb_menu",
            "nav:subjects": "cb_subjects",
            "nav:profile": "cb_profile",
            "nav:ach": "cb_achievements",
            "nav:admin": "cb_admin_menu",
        }
        for data, expected in cases.items():
            self.assertEqual(self._first_handler(data, None), expected, data)

    def test_learning_callbacks(self):
        cases = {
            "gr:1": "cb_pick_grade",
            "su:1": "cb_subject",
            "le:10": "cb_lesson",
            "vw:10": "cb_viewed",
            "qz:10": "cb_quiz",
        }
        for data, expected in cases.items():
            self.assertEqual(self._first_handler(data, None), expected, data)

    def test_admin_flow_callbacks(self):
        cases = {
            "adm:stat": ("cb_stats", None),
            "adm:addsubject": ("adm_add_subject", None),
            "adm:addlesson": ("adm_add_lesson", None),
            "adm:addmaterial": ("adm_add_material", None),
            "adm:addquestion": ("adm_add_question", None),
            "ag:1": ("adm_grade_chosen", admin_handlers.AdmStates.pick_grade.state),
            "ls:1": ("adm_lesson_subject", admin_handlers.AdmStates.lesson_subject.state),
            "ms:1": ("adm_material_subject", admin_handlers.AdmStates.material_subject.state),
            "ml:1": ("adm_material_lesson", admin_handlers.AdmStates.material_lesson.state),
            "mk:text": ("adm_material_kind", admin_handlers.AdmStates.material_kind.state),
            "qs:1": ("adm_question_subject", admin_handlers.AdmStates.question_subject.state),
            "ql:1": ("adm_question_lesson", admin_handlers.AdmStates.question_lesson.state),
            "adm:cancel": ("cb_leave_admin", admin_handlers.AdmStates.pick_grade.state),
            "nav:menu": ("cb_leave_admin", admin_handlers.AdmStates.pick_grade.state),
        }
        for data, (expected, state) in cases.items():
            self.assertEqual(self._first_handler(data, state), expected, data)

    def test_quiz_answer_works_and_stale_buttons_are_answered(self):
        running = learn_handlers.QuizStates.running.state
        self.assertEqual(self._first_handler("qa:0:1", running), "cb_answer")
        # after a restart / lost state the same button still answers the pupil
        self.assertEqual(self._first_handler("qa:0:1", None), "cb_stale_answer")


class MessageHelperTests(unittest.TestCase):
    def test_long_text_is_split_below_telegram_limit(self):
        text = "\n".join("x" * 90 for _ in range(120))  # ~11k chars
        chunks = learn_handlers._split(text)
        self.assertGreater(len(chunks), 1)
        for chunk in chunks:
            self.assertLessEqual(len(chunk), learn_handlers.TELEGRAM_LIMIT)

    def test_achievement_titles_prefer_human_names(self):
        self.assertEqual(
            learn_handlers.achievement_titles(
                {"new_achievements": ["first_lesson"], "new_achievement_titles": ["Birinchi dars"]}
            ),
            ["Birinchi dars"],
        )
        # older backend without titles → codes still shown, never a crash
        self.assertEqual(
            learn_handlers.achievement_titles({"new_achievements": ["first_quiz"]}),
            ["first_quiz"],
        )
        self.assertEqual(learn_handlers.achievement_titles({}), [])

    def test_user_text_is_html_escaped(self):
        self.assertEqual(learn_handlers.esc("<b>x</b>"), "&lt;b&gt;x&lt;/b&gt;")

    def test_url_detection(self):
        self.assertTrue(learn_handlers.is_url("https://a.uz"))
        self.assertTrue(learn_handlers.is_url("HTTP://a.uz"))
        self.assertFalse(learn_handlers.is_url("yozma matn"))
        self.assertFalse(learn_handlers.is_url(None))


if __name__ == "__main__":
    unittest.main()
