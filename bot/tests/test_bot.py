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
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

# Config is imported by the handlers; keep test values local (never real ones).
os.environ.setdefault("BOT_TOKEN", "012345:TEST_TOKEN_NOT_REAL")
os.environ.setdefault("API_URL", "http://127.0.0.1:9")
os.environ.setdefault("MINI_APP_URL", "https://example.com/app")
os.environ.setdefault("ADMIN_USER_IDS", "999000111")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from aiogram import Bot  # noqa: E402
from aiogram.types import CallbackQuery, Chat, Document, Message, User, Video  # noqa: E402

import backend_client  # noqa: E402
from handlers import admin as admin_handlers  # noqa: E402
from handlers import learn as learn_handlers  # noqa: E402
from handlers import profile as profile_handlers  # noqa: E402
from keyboards import inline as kb  # noqa: E402
from pupil_guard import PupilGuard  # noqa: E402

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
        {"id": 7, "kind": "pdf", "title": "Kitob fayl", "content": "",
         "file_id": "BQAC1pdf", "file_name": "kitob.pdf", "file_size": 1000},
        {"id": 8, "kind": "video", "title": "Video fayl", "content": "",
         "file_id": "BAAC2mp4", "file_name": "dars.mp4", "file_size": 5000},
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


def fake_message(text: str | None = None, document: bool = False, video: bool = False) -> Message:
    return Message(
        message_id=1,
        date=datetime.now(timezone.utc),
        chat=Chat(id=1, type="private"),
        from_user=User(id=999000111, is_bot=False, first_name="Admin"),
        text=text,
        document=(
            Document(
                file_id="test-file-id", file_unique_id="test-unique",
                file_name="Welcome-to-the-English-Alphabet.pdf", file_size=11_000_000,
            )
            if document
            else None
        ),
        video=(
            Video(
                file_id="test-video-id", file_unique_id="test-video-unique",
                width=640, height=360, duration=10,
                file_name="dars.mp4", file_size=5_000_000,
            )
            if video
            else None
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

    def test_file_materials_get_callback_buttons(self):
        markup = kb.lesson_actions_keyboard(LESSON)
        callbacks = [b.callback_data for row in markup.inline_keyboard for b in row]
        assert "fl:7" in callbacks  # yuklangan PDF fayl
        assert "fl:8" in callbacks  # yuklangan video fayl
        labels = [b.text for row in markup.inline_keyboard for b in row]
        self.assertTrue(any("Kitob fayl" in label for label in labels))
        self.assertTrue(any("Video fayl" in label for label in labels))


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
            "fl:7": "cb_material_file",
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


class NonTextHandlerTests(unittest.TestCase):
    """A file sent where text is expected must be answered, never ignored."""

    def _first_message_handler(self, raw_state: str | None, text: str | None = None, document: bool = False, video: bool = False) -> str | None:
        event = fake_message(text=text, document=document, video=video)
        # Command filters need a Bot instance; it never touches the network
        # because our test messages are not commands with bot mentions.
        fake_bot = Bot(token="012345:TEST_TOKEN_NOT_REAL")
        for router in ROUTERS:
            for handler in router.message.handlers:
                ok, _ = asyncio.run(handler.check(event, raw_state=raw_state, bot=fake_bot))
                if ok:
                    return getattr(handler.callback, "__name__", "?")
        return None

    def test_document_in_material_title_state_is_answered(self):
        state = admin_handlers.AdmStates.material_title.state
        self.assertEqual(self._first_message_handler(state, document=True), "adm_non_text")

    def test_document_in_material_content_state_goes_to_file_handler(self):
        # PDF fayl endi QABUL QILINADI: file_id bilan backendga saqlanadi.
        state = admin_handlers.AdmStates.material_content.state
        self.assertEqual(self._first_message_handler(state, document=True), "adm_material_pdf_file")

    def test_video_in_material_content_state_goes_to_file_handler(self):
        state = admin_handlers.AdmStates.material_content.state
        self.assertEqual(self._first_message_handler(state, video=True), "adm_material_video_file")

    def test_plain_text_in_material_title_still_reaches_text_handler(self):
        state = admin_handlers.AdmStates.material_title.state
        self.assertEqual(self._first_message_handler(state, text="Alifbo"), "adm_material_title")

    def test_document_during_quiz_is_answered(self):
        state = learn_handlers.QuizStates.running.state
        self.assertEqual(self._first_message_handler(state, document=True), "msg_quiz_non_text")

    def test_text_answer_during_quiz_still_reaches_text_handler(self):
        state = learn_handlers.QuizStates.running.state
        self.assertEqual(self._first_message_handler(state, text="7"), "msg_text_answer")


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


class PupilGuardTests(unittest.TestCase):
    """Buttons must work even if /start was missed, lost or handled elsewhere."""

    def _user(self, uid: int = 999000111, is_bot: bool = False) -> User:
        return User(id=uid, is_bot=is_bot, first_name="Admin")

    def _run(self, guard: PupilGuard, users: list[User]) -> tuple[list[int], object]:
        seen: list[int] = []

        async def handler(event, data):
            seen.append(data["event_from_user"].id)
            return "ok"

        async def run():
            for u in users:
                result = await guard(handler, object(), {"event_from_user": u})
                self.assertEqual(result, "ok")
            return True

        asyncio.run(run())
        return seen, None

    def test_registers_once_per_user(self):
        from unittest.mock import AsyncMock, patch

        guard = PupilGuard()
        with patch("backend_client.upsert_pupil", new=AsyncMock(return_value={})) as up:
            self._run(guard, [self._user(), self._user()])
        self.assertEqual(up.await_count, 1)
        self.assertEqual(up.await_args.args[0], 999000111)

    def test_backend_offline_never_blocks_the_handler(self):
        from unittest.mock import AsyncMock, patch

        import backend_client

        guard = PupilGuard()
        failing = AsyncMock(side_effect=backend_client.BackendOffline("down"))
        with patch("backend_client.upsert_pupil", new=failing):
            seen, _ = self._run(guard, [self._user()])
        self.assertEqual(seen, [999000111])

    def test_other_bots_are_ignored(self):
        from unittest.mock import AsyncMock, patch

        guard = PupilGuard()
        with patch("backend_client.upsert_pupil", new=AsyncMock(return_value={})) as up:
            seen, _ = self._run(guard, [self._user(is_bot=True)])
        self.assertEqual(seen, [999000111])
        self.assertEqual(up.await_count, 0)


BOT_ACCOUNT_ID = 9025391756  # @Edi_Quest_bot — author of every inline keyboard

PROGRESS = {
    "first_name": "A S A D B E K",
    "grade_id": 1,
    "grade_name": "1-sinf",
    "stars_total": 16,
    "lessons_viewed": 1,
    "lessons_passed": 1,
    "subjects": [
        {"subject_name": "Matematika", "emoji": "📐", "total_lessons": 4, "passed_lessons": 1},
    ],
    "achievements": [],
}


class CallbackPupilIdTests(unittest.TestCase):
    """LIVE BUG (2026-10-31): every inline button answered "Avval /start bosing."

    Root cause: screens called the backend with `cb.message.from_user.id`.
    For a callback that message was written by the BOT, so the bot's own id
    (9025391756) got queried and the backend correctly answered 404
    pupil_not_found. The pupil's id is always `cb.from_user.id`.
    """

    PUPIL_ID = 999000111

    def _bot_message(self):
        target = SimpleNamespace(
            from_user=User(id=BOT_ACCOUNT_ID, is_bot=True, first_name="EduQuest"),
            chat=Chat(id=self.PUPIL_ID, type="private"),
            answers=[],
        )

        async def answer(text, reply_markup=None, **kwargs):
            target.answers.append(text)

        target.answer = answer
        return target

    def _callback(self, data: str):
        return SimpleNamespace(
            data=data,
            from_user=User(id=self.PUPIL_ID, is_bot=False, first_name="Pupil"),
            message=self._bot_message(),
            answer=AsyncMock(),
        )

    def test_subjects_button_queries_the_pupil(self):
        cb = self._callback("nav:subjects")
        with patch("backend_client.subjects", new=AsyncMock(return_value=[])) as mocked:
            asyncio.run(learn_handlers.cb_subjects(cb))
        mocked.assert_awaited_once_with(self.PUPIL_ID)
        self.assertTrue(cb.message.answers, "the screen must answer")

    def test_subjects_screen_lists_content(self):
        cb = self._callback("nav:subjects")
        with patch("backend_client.subjects", new=AsyncMock(return_value=SUBJECTS)):
            asyncio.run(learn_handlers.cb_subjects(cb))
        self.assertTrue(cb.message.answers)
        self.assertIn("Fanlaringiz", cb.message.answers[-1])

    def test_grade_onboarding_keeps_the_pupil_id(self):
        cb = self._callback("nav:subjects")
        error = backend_client.BackendBusiness(409, "grade_not_selected", "x")
        with patch("backend_client.subjects", new=AsyncMock(side_effect=error)), \
                patch.object(learn_handlers, "show_grade_picker", new=AsyncMock()) as picker:
            asyncio.run(learn_handlers.cb_subjects(cb))
        picker.assert_awaited_once_with(cb.message, self.PUPIL_ID)

    def test_grade_picker_queries_the_pupil(self):
        target = self._bot_message()
        with patch("backend_client.grades", new=AsyncMock(return_value=GRADES)) as mocked:
            asyncio.run(learn_handlers.show_grade_picker(target, self.PUPIL_ID))
        mocked.assert_awaited_once_with(self.PUPIL_ID)

    def test_profile_button_queries_the_pupil(self):
        cb = self._callback("nav:profile")
        with patch("backend_client.progress", new=AsyncMock(return_value=PROGRESS)) as mocked:
            asyncio.run(profile_handlers.cb_profile(cb))
        mocked.assert_awaited_once_with(self.PUPIL_ID)
        self.assertTrue(cb.message.answers)
        self.assertIn("A S A D B E K", cb.message.answers[-1])

    def test_achievements_button_queries_the_pupil(self):
        cb = self._callback("nav:ach")
        achievements = [{
            "code": "first_lesson", "icon": "🥇", "title": "Birinchi dars",
            "description": "Birinchi darsni o‘qing", "earned": True,
        }]
        with patch(
            "backend_client.progress",
            new=AsyncMock(return_value={**PROGRESS, "achievements": achievements}),
        ) as mocked:
            asyncio.run(profile_handlers.cb_achievements(cb))
        mocked.assert_awaited_once_with(self.PUPIL_ID)
        self.assertTrue(cb.message.answers)


if __name__ == "__main__":
    unittest.main()
