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
import io
import json
import os
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

# Config is imported by the handlers; keep test values local (never real ones).
os.environ.setdefault("BOT_TOKEN", "012345:TEST_TOKEN_NOT_REAL")
os.environ.setdefault("API_URL", "http://127.0.0.1:9")
os.environ.setdefault("MINI_APP_URL", "https://example.com/app")
os.environ.setdefault("ADMIN_USER_IDS", "999000111")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from aiogram import Bot  # noqa: E402
from aiogram.exceptions import TelegramForbiddenError  # noqa: E402
from aiogram.types import CallbackQuery, Chat, Document, Message, User, Video  # noqa: E402

import aiohttp  # noqa: E402

import backend_client  # noqa: E402
import weekly_digest  # noqa: E402
from handlers import admin as admin_handlers  # noqa: E402
from handlers import learn as learn_handlers  # noqa: E402
from handlers import profile as profile_handlers  # noqa: E402
from handlers import start as start_handlers  # noqa: E402
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
        kb.profile_keyboard(),
        kb.parent_panel_keyboard(linked=True),
        kb.parent_panel_keyboard(linked=False),
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
            "nav:avatar": "cb_avatar",
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


class FakeProfilePhotoBot:
    """Stands in for aiogram's Bot — the three Telegram calls, no network."""

    def __init__(self, photos=None, file_path="photos/file_2.jpg", payload=b"JPEGDATA"):
        if photos is None:
            # Telegram returns one entry per photo, sizes small → large.
            photos = [[SimpleNamespace(file_id="id_small"), SimpleNamespace(file_id="id_big")]]
        self.photos = photos
        self.file_path = file_path
        self.payload = payload
        self.queried_user = None
        self.asked_file_id = None
        self.download_error = None

    async def get_user_profile_photos(self, user_id, limit=1):
        self.queried_user = user_id
        return SimpleNamespace(total_count=len(self.photos), photos=self.photos)

    async def get_file(self, file_id):
        self.asked_file_id = file_id
        return SimpleNamespace(file_id=file_id, file_path=self.file_path)

    async def download_file(self, file_path):
        if self.download_error is not None:
            raise self.download_error
        return io.BytesIO(self.payload)


class AvatarSyncTests(unittest.TestCase):
    """«🖼 Rasmimni qo‘yish» — the pupil's Telegram photo onto their profile."""

    PUPIL_ID = 999000111

    def _callback(self):
        target = SimpleNamespace(
            from_user=User(id=BOT_ACCOUNT_ID, is_bot=True, first_name="EduQuest"),
            chat=Chat(id=self.PUPIL_ID, type="private"),
            answers=[],
        )

        async def answer(text, reply_markup=None, **kwargs):
            target.answers.append(text)

        target.answer = answer
        return SimpleNamespace(
            data="nav:avatar",
            from_user=User(id=self.PUPIL_ID, is_bot=False, first_name="Pupil"),
            message=target,
            answer=AsyncMock(),
        )

    def _press(self, bot, side_effect=None, return_value=None):
        cb = self._callback()
        mocked = AsyncMock(side_effect=side_effect, return_value=return_value)
        with patch("backend_client.set_avatar", new=mocked):
            asyncio.run(profile_handlers.cb_avatar(cb, bot))
        return cb, mocked

    def test_pupil_id_is_used_not_the_bots(self):
        """The old live bug class: a callback's message belongs to the BOT."""
        bot = FakeProfilePhotoBot()
        _, set_avatar = self._press(
            bot, return_value={"avatar_url": "/api/avatars/1/x.png", "width": 256}
        )
        self.assertEqual(bot.queried_user, self.PUPIL_ID)
        self.assertEqual(set_avatar.await_args.args[0], self.PUPIL_ID)

    def test_largest_size_is_downloaded(self):
        bot = FakeProfilePhotoBot()
        self._press(bot, return_value={"width": 256})
        self.assertEqual(bot.asked_file_id, "id_big")

    def test_success_tells_where_the_photo_shows_up(self):
        cb, _ = self._press(FakeProfilePhotoBot(), return_value={"width": 256})
        self.assertIn("qo‘yildi", cb.message.answers[-1])
        self.assertIn("256 px", cb.message.answers[-1])
        self.assertIn("Mini App", cb.message.answers[-1])

    def test_no_telegram_photo_says_so_and_uploads_nothing(self):
        bot = FakeProfilePhotoBot(photos=[])
        cb, set_avatar = self._press(bot)
        set_avatar.assert_not_awaited()
        self.assertIn("📷", cb.message.answers[-1])
        self.assertIn("yo‘q", cb.message.answers[-1])

    def test_backend_rejection_reason_reaches_the_pupil(self):
        error = backend_client.BackendBusiness(
            422, "avatar_rejected", "Rasm juda katta — 5 MB dan kichikroq fayl tanlang."
        )
        cb, _ = self._press(FakeProfilePhotoBot(), side_effect=error)
        self.assertIn("Rasm juda katta", cb.message.answers[-1])
        self.assertNotIn("formati yaroqsiz", cb.message.answers[-1])

    def test_unregistered_pupil_is_sent_to_start(self):
        error = backend_client.BackendBusiness(404, "pupil_not_found", "x")
        cb, _ = self._press(FakeProfilePhotoBot(), side_effect=error)
        self.assertIn("/start", cb.message.answers[-1])

    def test_offline_backend_is_admitted_not_hidden(self):
        error = backend_client.BackendOffline("connection refused")
        cb, _ = self._press(FakeProfilePhotoBot(), side_effect=error)
        self.assertIn("🔌", cb.message.answers[-1])

    def test_download_failure_never_claims_success(self):
        bot = FakeProfilePhotoBot()
        bot.download_error = ValueError("telegram said no")
        cb, set_avatar = self._press(bot)
        set_avatar.assert_not_awaited()
        self.assertTrue(cb.message.answers[-1].startswith("⚠️"))

    def test_missing_file_path_never_claims_success(self):
        bot = FakeProfilePhotoBot(file_path=None)
        cb, set_avatar = self._press(bot)
        set_avatar.assert_not_awaited()
        self.assertTrue(cb.message.answers[-1].startswith("⚠️"))

    def test_empty_bytes_never_claims_success(self):
        bot = FakeProfilePhotoBot(payload=b"")
        cb, set_avatar = self._press(bot)
        set_avatar.assert_not_awaited()
        self.assertTrue(cb.message.answers[-1].startswith("⚠️"))


class SetAvatarClientTests(unittest.TestCase):
    """The multipart POST itself: right URL, right auth, honest error text."""

    def _session(self, status, payload, calls):
        class _Response:
            def __init__(self):
                self.status = status

            async def json(self):
                if payload is None:
                    raise ValueError("no json body")
                return payload

            async def __aenter__(self):
                return self

            async def __aexit__(self, *exc):
                return False

        response = _Response()

        class _Session:
            def __init__(self, *args, **kwargs):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, *exc):
                return False

            def post(self, url, **kwargs):
                calls.append((url, kwargs))
                return response

            def request(self, method, url, **kwargs):
                calls.append((url, kwargs))
                return response

        return _Session

    def test_posts_multipart_to_the_internal_avatar_route(self):
        calls = []
        with patch("backend_client.aiohttp.ClientSession",
                   new=self._session(200, {"avatar_url": "/api/avatars/7/x.png", "width": 256}, calls)):
            out = asyncio.run(
                backend_client.set_avatar(7, b"JPEGDATA", filename="file_2.jpg")
            )
        url, kwargs = calls[0]
        self.assertEqual(url, f"{backend_client.config.API_URL}/api/internal/pupils/7/avatar")
        self.assertEqual(kwargs["headers"], {"X-Bot-Token": backend_client.config.BOT_TOKEN})
        self.assertIsInstance(kwargs["data"], aiohttp.FormData)
        self.assertTrue(kwargs["data"].is_multipart)
        self.assertEqual(out["width"], 256)

    def test_422_keeps_the_servers_uzbek_reason(self):
        """The generic 422 rewrite would hide 'Rasm juda katta' from the pupil."""
        calls = []
        body = {"detail": {"error": "avatar_rejected",
                           "message_uz": "Rasm juda katta — 5 MB dan kichikroq fayl tanlang."}}
        with patch("backend_client.aiohttp.ClientSession",
                   new=self._session(422, body, calls)):
            with self.assertRaises(backend_client.BackendBusiness) as caught:
                asyncio.run(backend_client.set_avatar(7, b"huge"))
        self.assertEqual(caught.exception.code, "avatar_rejected")
        self.assertIn("Rasm juda katta", caught.exception.message)

    def test_json_calls_still_get_the_generic_422_text(self):
        """Regression: the rewrite stays for every other internal endpoint."""
        calls = []
        body = {"detail": "Unprocessable Entity"}
        with patch("backend_client.aiohttp.ClientSession",
                   new=self._session(422, body, calls)):
            with self.assertRaises(backend_client.BackendBusiness) as caught:
                asyncio.run(backend_client._call("GET", "/pupil/progress", params={"telegram_id": 7}))
        self.assertIn("formati yaroqsiz", caught.exception.message)


class QuizMistakeReviewTests(unittest.TestCase):
    """The bot result message must help the pupil learn from wrong answers."""

    def test_mistakes_are_rendered_and_escaped(self):
        result = {
            "message_uz": "Yana bir bor urinib ko‘ramiz!",
            "correct_count": 0,
            "total_count": 1,
            "score_percent": 0,
            "passed": False,
            "stars_earned": 0,
            "stars_total": 4,
            "next_level_unlocked": False,
            "new_achievements": [],
            "new_achievement_titles": [],
            "mistakes": [{
                "question_id": 5,
                "question_text": "2 < 3mi?",
                "kind": "single",
                "your_answer": "Yo‘q",
                "correct_answer": "Ha",
                "explanation": "Kichik son chapda turadi.",
            }],
        }
        target = AsyncMock()
        state = AsyncMock()
        with patch.object(
            backend_client, "submit_quiz", new=AsyncMock(return_value=result)
        ):
            asyncio.run(learn_handlers._finish_quiz(target, state, 7, {}, 123))
        text = target.answer.await_args.args[0]
        self.assertIn("Xatolar ustida ishlash", text)
        self.assertIn("2 &lt; 3mi?", text)  # HTML-escaped, not raw
        self.assertIn("To‘g‘ri javob", text)
        self.assertIn("Kichik son chapda turadi.", text)


class ParentDigestTests(unittest.TestCase):
    """Parent linking panel + the Sunday digest scheduler (no network)."""

    SUNDAY = datetime(2026, 11, 1, 13, 30, tzinfo=timezone.utc)  # 18:30 Tashkent

    @staticmethod
    def _group(parent: int = 1001, name: str = "Ona") -> dict:
        return {
            "parent_telegram_id": parent,
            "parent_name": name,
            "pupils": [
                {
                    "user_id": 1,
                    "first_name": "Aziz",
                    "grade_name": "1-sinf",
                    "lessons_passed_week": 2,
                    "stars_week": 9,
                    "current_streak": 3,
                    "lessons_passed_total": 5,
                    "stars_total": 20,
                    "active_week": True,
                },
                {
                    "user_id": 2,
                    "first_name": "<Zuhra>",
                    "grade_name": None,
                    "lessons_passed_week": 0,
                    "stars_week": 0,
                    "current_streak": 0,
                    "lessons_passed_total": 1,
                    "stars_total": 4,
                    "active_week": False,
                },
            ],
        }

    def test_digest_due_only_sunday_after_configured_hour(self):
        self.assertTrue(weekly_digest.digest_due(self.SUNDAY))
        before = datetime(2026, 11, 1, 12, 30, tzinfo=timezone.utc)  # 17:30 local
        self.assertFalse(weekly_digest.digest_due(before))
        monday = datetime(2026, 11, 2, 13, 30, tzinfo=timezone.utc)
        self.assertFalse(weekly_digest.digest_due(monday))

    def test_week_start_is_local_monday(self):
        self.assertEqual(weekly_digest.week_start_for(self.SUNDAY).isoformat(), "2026-10-26")

    def test_format_escapes_names_and_marks_inactive_week(self):
        from datetime import date

        text = weekly_digest.format_digest(
            self._group(), date(2026, 10, 26), date(2026, 11, 2)
        )
        self.assertIn("26-oktabr – 1-noyabr", text)
        self.assertIn("Aziz", text)
        self.assertIn("2</b> dars", text)
        self.assertIn("+9", text)
        self.assertIn("&lt;Zuhra&gt;", text)
        self.assertIn("hali dars o‘tilmadi", text)

    def test_round_sends_each_parent_once_per_week(self):
        payload = {
            "week_start": "2026-10-26",
            "week_end": "2026-11-02",
            "parents": [self._group(1001), self._group(1002, "Ota")],
        }
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp) / "state.json"
            bot = AsyncMock()
            with patch.object(
                backend_client, "weekly_digest", new=AsyncMock(return_value=payload)
            ) as api:
                sent = asyncio.run(
                    weekly_digest.run_digest_round(
                        bot, now=self.SUNDAY, state_path=state
                    )
                )
            self.assertEqual(sent, 2)
            self.assertEqual(bot.send_message.await_count, 2)
            self.assertEqual(api.await_count, 1)
            saved = json.loads(state.read_text(encoding="utf-8"))
            self.assertEqual(saved, {"week": "2026-10-26", "sent": [1001, 1002]})

            with patch.object(
                backend_client, "weekly_digest", new=AsyncMock(return_value=payload)
            ):
                again = asyncio.run(
                    weekly_digest.run_digest_round(
                        bot, now=self.SUNDAY, state_path=state
                    )
                )
            self.assertEqual(again, 0)
            self.assertEqual(bot.send_message.await_count, 2)  # nothing re-sent

    def test_blocked_parent_is_not_retried_forever(self):
        payload = {
            "week_start": "2026-10-26",
            "week_end": "2026-11-02",
            "parents": [self._group(1003)],
        }

        async def forbidden(*args, **kwargs):
            raise TelegramForbiddenError(
                method=SimpleNamespace(), message="Forbidden: bot was blocked by the user"
            )

        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp) / "state.json"
            bot = AsyncMock()
            bot.send_message = AsyncMock(side_effect=forbidden)
            with patch.object(
                backend_client, "weekly_digest", new=AsyncMock(return_value=payload)
            ):
                sent = asyncio.run(
                    weekly_digest.run_digest_round(
                        bot, now=self.SUNDAY, state_path=state
                    )
                )
            self.assertEqual(sent, 0)
            self.assertIn(1003, json.loads(state.read_text(encoding="utf-8"))["sent"])

    def test_not_due_and_backend_offline_stay_silent(self):
        bot = AsyncMock()
        with patch.object(
            backend_client, "weekly_digest", new=AsyncMock()
        ) as api:
            before = datetime(2026, 11, 1, 12, 30, tzinfo=timezone.utc)
            self.assertEqual(
                asyncio.run(
                    weekly_digest.run_digest_round(
                        bot, now=before, state_path=Path(tempfile.gettempdir()) / "x.json"
                    )
                ),
                0,
            )
            api.assert_not_awaited()

            with patch.object(
                backend_client,
                "weekly_digest",
                new=AsyncMock(side_effect=backend_client.BackendOffline("down")),
            ):
                self.assertEqual(
                    asyncio.run(
                        weekly_digest.run_digest_round(
                            bot, now=self.SUNDAY, state_path=Path(tempfile.gettempdir()) / "y.json"
                        )
                    ),
                    0,
                )
            bot.send_message.assert_not_awaited()

    def test_pupil_panel_shows_link_and_unlink_button(self):
        target = AsyncMock()
        with patch.object(
            backend_client,
            "parent_status",
            new=AsyncMock(return_value={"linked": False, "parent_name": None}),
        ), patch.object(
            backend_client,
            "parent_code",
            new=AsyncMock(return_value={"code": "ABC234", "linked": False}),
        ):
            asyncio.run(start_handlers.show_parent_panel(target, 555001))
        text = target.answer.await_args.args[0]
        self.assertIn("ABC234", text)
        self.assertIn("t.me/", text)
        self.assertIn("/start ABC234", text)
        markup = target.answer.await_args.kwargs["reply_markup"]
        callbacks = [b.callback_data for row in markup.inline_keyboard for b in row]
        self.assertNotIn("pr:off", callbacks)

        target2 = AsyncMock()
        with patch.object(
            backend_client,
            "parent_status",
            new=AsyncMock(return_value={"linked": True, "parent_name": "Ona"}),
        ):
            asyncio.run(start_handlers.show_parent_panel(target2, 555001))
        self.assertIn("ulangan", target2.answer.await_args.args[0])
        markup2 = target2.answer.await_args.kwargs["reply_markup"]
        callbacks2 = [b.callback_data for row in markup2.inline_keyboard for b in row]
        self.assertIn("pr:off", callbacks2)

    def test_deep_link_confirms_parent_link(self):
        message = SimpleNamespace(
            text="/start ABC234",
            from_user=SimpleNamespace(id=1001, first_name="Ona"),
            answer=AsyncMock(),
        )
        with patch.object(
            backend_client,
            "link_parent",
            new=AsyncMock(
                return_value={"pupil_first_name": "Aziz", "grade_name": "1-sinf"}
            ),
        ) as link:
            asyncio.run(start_handlers.cmd_start_parent_code(message))
        link.assert_awaited_once_with("ABC234", 1001, "Ona")
        text = message.answer.await_args.args[0]
        self.assertIn("Bog‘landi", text)
        self.assertIn("Aziz", text)

    def test_parent_menu_button_and_callbacks_are_wired(self):
        markup = kb.main_menu_keyboard("https://example.com/app")
        callbacks = [b.callback_data for row in markup.inline_keyboard for b in row]
        self.assertIn("nav:parent", callbacks)
        handlers = {
            handler.callback.__name__
            for handler in start_handlers.router.callback_query.handlers
        }
        self.assertIn("cb_parent", handlers)
        self.assertIn("cb_parent_off", handlers)



    """kind="matching" questions: numbered prompts, lettered options, typed map."""

    PROMPTS = [{"id": 201, "text": "Olma"}, {"id": 202, "text": "Banan"}]
    OPTIONS = [{"id": 101, "text": "Banana"}, {"id": 102, "text": "Apple"}]

    def test_parse_accepts_common_formats(self):
        for raw in ("1-b, 2-a", "1 B 2 A", "1=b;2–a", "1-b 2-a"):
            pairs, hint = learn_handlers.parse_matches(raw, self.PROMPTS, self.OPTIONS)
            self.assertEqual(hint, "", raw)
            self.assertEqual(
                pairs,
                [
                    {"prompt_id": 201, "option_id": 102},
                    {"prompt_id": 202, "option_id": 101},
                ],
                raw,
            )

    def test_parse_rejects_duplicates(self):
        pairs, hint = learn_handlers.parse_matches("1-a, 2-a", self.PROMPTS, self.OPTIONS)
        self.assertEqual(pairs, [])
        self.assertIn("bir marta", hint)

    def test_parse_requires_every_prompt(self):
        pairs, hint = learn_handlers.parse_matches("1-b", self.PROMPTS, self.OPTIONS)
        self.assertEqual(pairs, [])
        self.assertIn("Barcha", hint)

    def test_parse_rejects_out_of_range(self):
        pairs, hint = learn_handlers.parse_matches("1-b, 3-a", self.PROMPTS, self.OPTIONS)
        self.assertEqual(pairs, [])
        self.assertIn("yo‘q", hint)

    def test_render_shows_numbered_prompts_and_lettered_options(self):
        target = AsyncMock()
        state = AsyncMock()
        question = {
            "id": 7,
            "kind": "matching",
            "text": "Juftlang",
            "prompts": self.PROMPTS,
            "options": self.OPTIONS,
        }
        asyncio.run(
            learn_handlers._render_question(target, [question], 3, 0, {}, state=state)
        )
        text = target.answer.await_args.args[0]
        self.assertIn("1. Olma", text)
        self.assertIn("2. Banan", text)
        self.assertIn("A. Banana", text)
        self.assertIn("B. Apple", text)
        self.assertIn("1-b, 2-a", text)
        # No inline option buttons: matching is answered by typing a mapping.
        self.assertNotIn("reply_markup", target.answer.await_args.kwargs)

    def test_typed_answer_becomes_pairs(self):
        question = {
            "id": 7,
            "kind": "matching",
            "text": "Juftlang",
            "prompts": self.PROMPTS,
            "options": self.OPTIONS,
        }
        message = SimpleNamespace(
            text="1-b, 2-a",
            from_user=SimpleNamespace(id=999000222),
            answer=AsyncMock(),
        )
        state = AsyncMock()
        state.get_data = AsyncMock(
            return_value={
                "lesson_id": 3,
                "questions": [question],
                "index": 0,
                "answers": {},
                "quiz_title": "Test",
            }
        )
        with patch.object(
            learn_handlers, "_finish_quiz", new=AsyncMock()
        ) as finish:
            asyncio.run(learn_handlers.msg_text_answer(message, state))
        finish.assert_awaited_once()
        answers = finish.await_args.args[3]
        self.assertEqual(
            answers["7"]["pairs"],
            [
                {"prompt_id": 201, "option_id": 102},
                {"prompt_id": 202, "option_id": 101},
            ],
        )

    def test_invalid_typed_answer_keeps_quiz_running(self):
        question = {
            "id": 7,
            "kind": "matching",
            "text": "Juftlang",
            "prompts": self.PROMPTS,
            "options": self.OPTIONS,
        }
        message = SimpleNamespace(
            text="bilmayman",
            from_user=SimpleNamespace(id=999000222),
            answer=AsyncMock(),
        )
        state = AsyncMock()
        state.get_data = AsyncMock(
            return_value={
                "lesson_id": 3,
                "questions": [question],
                "index": 0,
                "answers": {},
                "quiz_title": "Test",
            }
        )
        with patch.object(
            learn_handlers, "_finish_quiz", new=AsyncMock()
        ) as finish:
            asyncio.run(learn_handlers.msg_text_answer(message, state))
        finish.assert_not_awaited()
        self.assertIn("1-b, 2-a", message.answer.await_args.args[0])


if __name__ == "__main__":
    unittest.main()
