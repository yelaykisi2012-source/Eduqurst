"""app/schemas.py — Pydantic request/response models (API contract)."""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ---------- auth ----------
class TelegramLoginRequest(BaseModel):
    init_data: str = Field(min_length=10)


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
    duplicate: bool  # True if this idempotency_key was already processed


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
