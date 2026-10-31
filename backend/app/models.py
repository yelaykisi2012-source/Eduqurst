"""
app/models.py — PostgreSQL (SQLAlchemy) data model.

Relationship map:
  Grade 1 ─< Subject ─< Lesson ─< Question ─< AnswerOption
                     Lesson ─< LessonMaterial
  User ─< QuizAttempt >— Lesson
  User ─< LessonProgress >— Lesson      (unlock/revisit state)
  User ─< StarLedger                    (every star grant is recorded once)
  User ─< UserAchievement >— Achievement
  AdminAccount                          (dashboard login, Stage 8)
"""
from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    """A pupil. Only minimal Telegram info is stored (child privacy).

    Two ways to own an account:
      * Telegram  -> telegram_id is set (bot / Mini App initData login)
      * Web       -> login + password_hash are set (login/password on the site)
    Exactly one path is used per pupil; both end up with the SAME JWT and the
    same grade/progress/gamification data. telegram_id is nullable so web
    accounts (no Telegram) can exist without faking an id.
    """

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    telegram_id: Mapped[int | None] = mapped_column(
        BigInteger, unique=True, index=True, nullable=True
    )
    # Web account credentials (nullable: Telegram pupils have none).
    # login is stored lowercase; password_hash is a scrypt$... string.
    login: Mapped[str | None] = mapped_column(String(32), unique=True, index=True)
    password_hash: Mapped[str | None] = mapped_column(String(255))
    username: Mapped[str | None] = mapped_column(String(64))
    first_name: Mapped[str] = mapped_column(String(128), default="")
    last_name: Mapped[str | None] = mapped_column(String(128))
    # The pupil's chosen grade (1..11). Nullable: a brand-new pupil has not
    # picked one yet, so the app must run the grade-selection onboarding first.
    # We NEVER guess it from name/username/telegram_id — it is only ever set
    # explicitly by the pupil via POST /api/me/grade.
    grade_id: Mapped[int | None] = mapped_column(
        ForeignKey("grades.id"), index=True, nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    # Daily engagement streak. "Day" is Asia/Tashkent (UTC+5), so it flips at
    # local midnight; last_active_date stores that local date.
    current_streak: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    max_streak: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    last_active_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    grade: Mapped[Grade | None] = relationship()
    attempts: Mapped[list[QuizAttempt]] = relationship(back_populates="user")
    progress: Mapped[list[LessonProgress]] = relationship(back_populates="user")
    stars: Mapped[list[StarLedger]] = relationship(back_populates="user")


class Grade(Base):
    __tablename__ = "grades"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(64), unique=True)  # "1-sinf"
    order_index: Mapped[int] = mapped_column(Integer, default=0)

    subjects: Mapped[list[Subject]] = relationship(back_populates="grade")


class Subject(Base):
    __tablename__ = "subjects"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    grade_id: Mapped[int] = mapped_column(ForeignKey("grades.id"), index=True)
    name: Mapped[str] = mapped_column(String(64))
    slug: Mapped[str] = mapped_column(String(64), unique=True)  # "matematika"
    emoji: Mapped[str] = mapped_column(String(8), default="📘")
    order_index: Mapped[int] = mapped_column(Integer, default=0)
    is_published: Mapped[bool] = mapped_column(Boolean, default=True)

    grade: Mapped[Grade] = relationship(back_populates="subjects")
    lessons: Mapped[list[Lesson]] = relationship(back_populates="subject")


class Lesson(Base):
    """One learning level inside a subject (level_order = sequence)."""

    __tablename__ = "lessons"
    __table_args__ = (UniqueConstraint("subject_id", "level_order"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    subject_id: Mapped[int] = mapped_column(ForeignKey("subjects.id"), index=True)
    title: Mapped[str] = mapped_column(String(160))
    explanation: Mapped[str] = mapped_column(Text, default="")  # child-friendly Uzbek
    video_url: Mapped[str | None] = mapped_column(String(512))
    level_order: Mapped[int] = mapped_column(Integer, default=1)
    stars_reward: Mapped[int] = mapped_column(Integer, default=5)  # quiz pass reward
    pass_threshold_percent: Mapped[int] = mapped_column(Integer, default=60)  # admin-configurable
    is_published: Mapped[bool] = mapped_column(Boolean, default=True)

    subject: Mapped[Subject] = relationship(back_populates="lessons")
    materials: Mapped[list[LessonMaterial]] = relationship(
        back_populates="lesson", order_by="LessonMaterial.order_index"
    )
    questions: Mapped[list[Question]] = relationship(
        back_populates="lesson", order_by="Question.order_index"
    )


class LessonMaterial(Base):
    """Slides / images / extra text blocks shown before the quiz.

    Four main formats: video, pdf, live, text. Video and PDF materials can
    be EITHER a URL (content) or an uploaded Telegram file (file_id + name +
    size; the bot receives the file and Telegram stores it — the backend
    proxies it for the Mini App). Live lessons are URL-only (Zoom/Meet).
    """

    __tablename__ = "lesson_materials"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    lesson_id: Mapped[int] = mapped_column(ForeignKey("lessons.id"), index=True)
    kind: Mapped[str] = mapped_column(String(16), default="slide")  # slide|image|text
    title: Mapped[str] = mapped_column(String(160), default="")
    content: Mapped[str] = mapped_column(Text, default="")  # text or URL
    order_index: Mapped[int] = mapped_column(Integer, default=0)
    # Uploaded-file materials (video/pdf kinds only):
    file_id: Mapped[str | None] = mapped_column(String(512), nullable=True)
    file_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    file_size: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    lesson: Mapped[Lesson] = relationship(back_populates="materials")


class Question(Base):
    __tablename__ = "questions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    lesson_id: Mapped[int] = mapped_column(ForeignKey("lessons.id"), index=True)
    text: Mapped[str] = mapped_column(Text)
    # single | text | image | matching
    kind: Mapped[str] = mapped_column(String(16), default="single")
    image_url: Mapped[str | None] = mapped_column(String(512))
    order_index: Mapped[int] = mapped_column(Integer, default=0)

    lesson: Mapped[Lesson] = relationship(back_populates="questions")
    options: Mapped[list[AnswerOption]] = relationship(
        back_populates="question", order_by="AnswerOption.order_index"
    )
    prompts: Mapped[list[QuestionPrompt]] = relationship(
        back_populates="question", order_by="QuestionPrompt.order_index"
    )


class QuestionPrompt(Base):
    """Left-hand item of a matching question ("matching" kind).

    The matching right-hand choices live in AnswerOption and carry the same
    `pair_key`, so the two ids are independent and the correct pair can never
    be inferred from the ids sent to the pupil.
    """

    __tablename__ = "question_prompts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    question_id: Mapped[int] = mapped_column(ForeignKey("questions.id"), index=True)
    text: Mapped[str] = mapped_column(String(255))
    pair_key: Mapped[str] = mapped_column(String(32))
    order_index: Mapped[int] = mapped_column(Integer, default=0)

    question: Mapped[Question] = relationship(back_populates="prompts")


class AnswerOption(Base):
    __tablename__ = "answer_options"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    question_id: Mapped[int] = mapped_column(ForeignKey("questions.id"), index=True)
    text: Mapped[str] = mapped_column(String(255))
    is_correct: Mapped[bool] = mapped_column(Boolean, default=False)
    feedback: Mapped[str] = mapped_column(String(255), default="")  # supportive hint
    order_index: Mapped[int] = mapped_column(Integer, default=0)
    # For "matching": which QuestionPrompt this right-hand choice belongs to.
    pair_key: Mapped[str | None] = mapped_column(String(32))

    question: Mapped[Question] = relationship(back_populates="options")


class QuizAttempt(Base):
    """One submitted quiz. idempotency_key prevents double star grants."""

    __tablename__ = "quiz_attempts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    lesson_id: Mapped[int] = mapped_column(ForeignKey("lessons.id"), index=True)
    idempotency_key: Mapped[str] = mapped_column(String(64), unique=True)
    total_count: Mapped[int] = mapped_column(Integer, default=0)
    correct_count: Mapped[int] = mapped_column(Integer, default=0)
    score_percent: Mapped[int] = mapped_column(Integer, default=0)
    passed: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    user: Mapped[User] = relationship(back_populates="attempts")


class QuizAnswer(Base):
    """One answer of a submitted quiz — powers the "review mistakes" screen.

    Stored per attempt so the same review can be shown again later (duplicate
    submit, history) instead of only in the submission response.
    """

    __tablename__ = "quiz_answers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    attempt_id: Mapped[int] = mapped_column(
        ForeignKey("quiz_attempts.id"), index=True
    )
    question_id: Mapped[int] = mapped_column(ForeignKey("questions.id"), index=True)
    option_id: Mapped[int | None] = mapped_column(ForeignKey("answer_options.id"))
    text_answer: Mapped[str | None] = mapped_column(String(255))
    is_correct: Mapped[bool] = mapped_column(Boolean, default=False)


class LessonProgress(Base):
    """Per-user state of a lesson: viewed? passed? best score?"""

    __tablename__ = "lesson_progress"
    __table_args__ = (UniqueConstraint("user_id", "lesson_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    lesson_id: Mapped[int] = mapped_column(ForeignKey("lessons.id"), index=True)
    lesson_viewed: Mapped[bool] = mapped_column(Boolean, default=False)
    passed: Mapped[bool] = mapped_column(Boolean, default=False)
    best_score_percent: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    user: Mapped[User] = relationship(back_populates="progress")
    lesson: Mapped[Lesson] = relationship()


class StarLedger(Base):
    """Append-only star accounting. One grant per (reason, reference)."""

    __tablename__ = "star_ledger"
    __table_args__ = (UniqueConstraint("user_id", "reason", "reference_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    amount: Mapped[int] = mapped_column(Integer, default=0)
    reason: Mapped[str] = mapped_column(String(32))  # lesson_viewed|quiz_pass|achievement
    reference_id: Mapped[int] = mapped_column(Integer, default=0)  # lesson/attempt/achievement id
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    user: Mapped[User] = relationship(back_populates="stars")


class Achievement(Base):
    __tablename__ = "achievements"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(32), unique=True)
    title: Mapped[str] = mapped_column(String(128))
    description: Mapped[str] = mapped_column(String(255), default="")
    icon: Mapped[str] = mapped_column(String(16), default="🏅")
    threshold: Mapped[int] = mapped_column(Integer, default=1)

    awarded: Mapped[list[UserAchievement]] = relationship(back_populates="achievement")


class UserAchievement(Base):
    __tablename__ = "user_achievements"
    __table_args__ = (UniqueConstraint("user_id", "achievement_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    achievement_id: Mapped[int] = mapped_column(ForeignKey("achievements.id"))
    earned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    user: Mapped[User] = relationship()
    achievement: Mapped[Achievement] = relationship(back_populates="awarded")


class Certificate(Base):
    """An issued course-completion certificate (one per pupil + subject).

    Names are snapshotted at issue time so later content renames do not change
    an already issued document. `code` is the unguessable public verify key.
    """

    __tablename__ = "certificates"
    __table_args__ = (UniqueConstraint("user_id", "subject_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    subject_id: Mapped[int] = mapped_column(ForeignKey("subjects.id"), index=True)
    code: Mapped[str] = mapped_column(String(24), unique=True, index=True)
    pupil_name: Mapped[str] = mapped_column(String(128))
    grade_name: Mapped[str] = mapped_column(String(32))
    subject_name: Mapped[str] = mapped_column(String(128))
    score_percent: Mapped[int] = mapped_column(Integer, default=0)
    stars: Mapped[int] = mapped_column(Integer, default=0)
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AdminAccount(Base):
    """Dashboard login (Stage 8). Password stored only as PBKDF2 hash."""

    __tablename__ = "admin_accounts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))  # pbkdf2_sha256$iter$salt$hash
    role: Mapped[str] = mapped_column(String(16), default="content_admin")  # superadmin|content_admin
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
