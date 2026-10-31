"""app/schemas.py — Pydantic request/response models (API contract)."""
from __future__ import annotations

from datetime import date

from pydantic import BaseModel, ConfigDict, Field


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ---------- auth ----------
class TelegramLoginRequest(BaseModel):
    init_data: str = Field(min_length=10)


class WebRegisterRequest(BaseModel):
    """A pupil without Telegram creates a login/password account."""

    login: str = Field(min_length=1, max_length=40)
    password: str = Field(min_length=1, max_length=128)
    first_name: str = Field(default="", max_length=128)


class WebPasswordLoginRequest(BaseModel):
    login: str = Field(min_length=1, max_length=40)
    password: str = Field(min_length=1, max_length=128)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    first_name: str


# ---------- grade / profile ----------
class GradeOut(ORMModel):
    id: int
    name: str
    order_index: int


class SetGradeRequest(BaseModel):
    # The pupil explicitly picks a grade (id of one of grades 1..11).
    # We never guess it — this value must be chosen by the pupil.
    grade_id: int = Field(ge=1)


class ProfileResponse(BaseModel):
    first_name: str
    grade_id: int | None
    grade_name: str | None
    # True when the pupil has not chosen a grade yet → app must run onboarding.
    needs_grade_selection: bool
    # True when this Telegram id is in ADMIN_TELEGRAM_IDS (Mini App shows admin tab).
    is_admin: bool = False
    # Consecutive local (Asia/Tashkent) days with activity — shown as 🔥.
    current_streak: int = 0
    max_streak: int = 0


# ---------- weekly league (leaderboard) ----------
class LeaderboardEntry(BaseModel):
    """One pupil in the weekly top list (by stars earned this week)."""

    rank: int
    user_id: int
    first_name: str
    stars: int
    is_me: bool = False


class LeaderboardMe(BaseModel):
    """The requesting pupil's own weekly standing."""

    rank: int
    stars: int


class LeaderboardResponse(BaseModel):
    grade_id: int
    grade_name: str
    # Local (Asia/Tashkent) Monday .. next Monday (end is exclusive).
    week_start: date
    week_end: date
    # Pupils of this grade who earned at least 1 star this week.
    participants: int
    top: list[LeaderboardEntry]
    me: LeaderboardMe | None = None


# ---------- admin ----------
class AdminSubjectCreate(BaseModel):
    grade_id: int = Field(ge=1)
    name: str = Field(min_length=2, max_length=64)
    emoji: str = Field(default="📘", max_length=8)
    order_index: int = 0


class AdminSubjectOut(BaseModel):
    id: int
    name: str
    slug: str
    emoji: str
    grade_id: int
    lesson_count: int
    is_published: bool = True


class AdminSubjectUpdate(BaseModel):
    """Partial update — only the sent fields change."""

    name: str | None = Field(default=None, min_length=2, max_length=64)
    emoji: str | None = Field(default=None, max_length=8)
    is_published: bool | None = None


class GradeOverview(BaseModel):
    grade_id: int
    grade_name: str
    subjects: list[AdminSubjectOut]


class AdminLessonCreate(BaseModel):
    title: str = Field(min_length=2, max_length=160)
    explanation: str = Field(min_length=10)
    stars_reward: int = Field(default=5, ge=1, le=50)
    pass_threshold_percent: int = Field(default=60, ge=10, le=100)


class AdminLessonUpdate(BaseModel):
    """Partial update of a lesson, including publish/unpublish."""

    title: str | None = Field(default=None, min_length=2, max_length=160)
    explanation: str | None = Field(default=None, min_length=10)
    stars_reward: int | None = Field(default=None, ge=1, le=50)
    pass_threshold_percent: int | None = Field(default=None, ge=10, le=100)
    is_published: bool | None = None


class AdminLessonOut(BaseModel):
    id: int
    title: str
    level_order: int
    subject_name: str
    question_count: int
    material_count: int = 0
    explanation: str = ""
    stars_reward: int = 5
    pass_threshold_percent: int = 60
    is_published: bool = True


class AdminMaterialCreate(BaseModel):
    # The four lesson formats a teacher can post + optional extras:
    #   video  -> a URL (YouTube, Vimeo, ...) OR an uploaded video file
    #             (file_id/file_name/file_size from the Telegram bot)
    #   pdf    -> a URL to the PDF OR an uploaded PDF file (file fields)
    #   live   -> content is a URL to the live room (Zoom/Meet/YouTube Live);
    #             title carries the schedule, e.g. "Dushanba 18:00"
    #   text   -> written notes (free text, no URL)
    kind: str = Field(default="text", pattern="^(video|pdf|live|text|image|slide)$")
    title: str = Field(min_length=2, max_length=160)
    content: str = Field(default="", max_length=5000)
    file_id: str | None = Field(default=None, max_length=512)
    file_name: str | None = Field(default=None, max_length=255)
    file_size: int | None = Field(default=None, ge=1)


class AdminMaterialOut(BaseModel):
    id: int
    kind: str
    title: str
    content: str
    order_index: int
    file_id: str | None = None
    file_name: str | None = None
    file_size: int | None = None


class AdminOptionCreate(BaseModel):
    text: str = Field(min_length=1, max_length=255)
    is_correct: bool = False


class AdminQuestionCreate(BaseModel):
    text: str = Field(min_length=3, max_length=1000)
    kind: str = Field(default="single", pattern="^(single|text)$")
    options: list[AdminOptionCreate] = Field(min_length=1, max_length=6)


class AdminQuestionOut(BaseModel):
    id: int
    text: str
    kind: str
    option_count: int
    correct_count: int


class AdminQuestionOptionOut(BaseModel):
    id: int
    text: str
    is_correct: bool


class AdminQuestionDetailOut(AdminQuestionOut):
    """Admin-only view: includes which option is correct (never sent to pupils)."""

    options: list[AdminQuestionOptionOut]


# ---------- content ----------
class LessonSummary(ORMModel):
    id: int
    title: str
    level_order: int
    is_published: bool
    viewed: bool
    passed: bool
    unlocked: bool


class SubjectWithLessons(ORMModel):
    id: int
    name: str
    slug: str
    emoji: str
    lessons: list[LessonSummary]


class MaterialOut(ORMModel):
    id: int
    kind: str
    title: str
    content: str
    order_index: int
    file_id: str | None = None
    file_name: str | None = None
    file_size: int | None = None


class LessonDetail(BaseModel):
    id: int
    subject_name: str
    title: str
    explanation: str
    video_url: str | None
    level_order: int
    stars_reward: int
    pass_threshold_percent: int
    materials: list[MaterialOut]
    viewed: bool
    passed: bool


class QuizOptionOut(BaseModel):
    id: int
    text: str


class QuizQuestionOut(BaseModel):
    id: int
    text: str
    kind: str
    image_url: str | None
    options: list[QuizOptionOut]


class QuizOut(BaseModel):
    lesson_id: int
    lesson_title: str
    pass_threshold_percent: int
    questions: list[QuizQuestionOut]


# ---------- quiz submit ----------
class AnswerIn(BaseModel):
    question_id: int
    option_id: int | None = None
    text: str | None = None


class QuizSubmitRequest(BaseModel):
    idempotency_key: str = Field(min_length=8, max_length=64)
    answers: list[AnswerIn]


class QuizSubmitResult(BaseModel):
    attempt_id: int
    total_count: int
    correct_count: int
    score_percent: int
    passed: bool
    stars_earned: int
    stars_total: int
    next_level_unlocked: bool
    message_uz: str
    new_achievements: list[str]
    new_achievement_titles: list[str] = []
    duplicate: bool  # True if this idempotency_key was already processed


# ---------- bot internal (X-Bot-Token protected) ----------
class BotSummaryResponse(BaseModel):
    known_user: bool = False
    needs_onboarding: bool = True
    first_name: str | None = None
    grade_name: str | None = None
    stars_total: int = 0
    lessons_viewed: int = 0
    lessons_passed: int = 0
    current_streak: int = 0
    max_streak: int = 0


class BotPupilUpsert(BaseModel):
    """Bot says: 'this real Telegram user just pressed /start' — create or refresh."""
    telegram_id: int = Field(ge=1)
    first_name: str = Field(default="", max_length=128)
    username: str | None = Field(default=None, max_length=64)


class BotSetGrade(BaseModel):
    telegram_id: int = Field(ge=1)
    # Still explicitly chosen by the pupil (via bot buttons) — never guessed.
    grade_id: int = Field(ge=1)


class BotQuizSubmit(BaseModel):
    telegram_id: int = Field(ge=1)
    idempotency_key: str = Field(min_length=8, max_length=64)
    answers: list[AnswerIn]


class BotAdminSubjectCreate(BaseModel):
    telegram_id: int = Field(ge=1)
    data: AdminSubjectCreate


class BotAdminLessonCreate(BaseModel):
    telegram_id: int = Field(ge=1)
    data: AdminLessonCreate


class BotAdminQuestionCreate(BaseModel):
    telegram_id: int = Field(ge=1)
    data: AdminQuestionCreate


class BotAdminMaterialCreate(BaseModel):
    telegram_id: int = Field(ge=1)
    data: AdminMaterialCreate


# ---------- progress / profile ----------
class SubjectProgress(BaseModel):
    subject_name: str
    emoji: str
    total_lessons: int
    passed_lessons: int


class AchievementOut(BaseModel):
    code: str
    title: str
    description: str
    icon: str
    earned: bool


class ProgressResponse(BaseModel):
    first_name: str
    grade_id: int | None
    grade_name: str | None
    stars_total: int
    lessons_viewed: int
    lessons_passed: int
    subjects: list[SubjectProgress]
    achievements: list[AchievementOut]
