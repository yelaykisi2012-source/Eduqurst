"""
app/models.py — PostgreSQL (SQLAlchemy) data model.

Relationship map:
  Grade 1 ─< Subject ─< Lesson ─< Question ─< AnswerOption
                     Lesson ─< LessonMaterial
  User ─< QuizAttempt >— Lesson
  User ─< ExamAttempt >— Subject       (mandatory exam: 20 admin-picked questions)
  User ─< LessonProgress >— Lesson      (unlock/revisit state)
  User ─< StarLedger                    (every star grant is recorded once)
  User ─< UserAchievement >— Achievement
  AdminAccount                          (dashboard login, Stage 8)
"""
from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
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
    # Parent weekly digest (bot-only; nullable). The pupil generates a short
    # one-time code, the parent sends it to the bot, and that Telegram id then
    # receives a Sunday summary. One parent may be linked to several pupils.
    parent_telegram_id: Mapped[int | None] = mapped_column(
        BigInteger, index=True, nullable=True
    )
    parent_name: Mapped[str | None] = mapped_column(String(128))
    parent_link_code: Mapped[str | None] = mapped_column(
        String(16), unique=True, nullable=True
    )
    parent_link_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

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
    # Admin-marked "imtihon savoli": only these questions build the mandatory
    # final exam of a subject (see app/exams.py). Nothing is auto-picked, so the
    # teacher stays in control of what the exam asks.
    is_exam: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false", index=True
    )

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


class ExamAttempt(Base):
    """One sitting of the mandatory subject exam (20 admin-picked questions).

    Unlike the lesson quiz, the paper has to survive between "open exam" and
    "submit", so the chosen question ids are frozen here. `answers` stores the
    graded result per question (JSON) — that is what the certificate and the
    mistake review are rebuilt from later.

    A failed sitting sets `locked_until`: the pupil may not sit this exam again
    for 30 days (the rule the teacher asked for: below 90% = not passed,
    certificate postponed by a month).
    """

    __tablename__ = "exam_attempts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    subject_id: Mapped[int] = mapped_column(ForeignKey("subjects.id"), index=True)
    question_ids: Mapped[list] = mapped_column(JSON, default=list)
    answers: Mapped[list] = mapped_column(JSON, default=list)
    total_count: Mapped[int] = mapped_column(Integer, default=0)
    correct_count: Mapped[int] = mapped_column(Integer, default=0)
    score_percent: Mapped[int] = mapped_column(Integer, default=0)
    # 5-point scale the teacher uses: "2.5" | "4" | "5" (None until submitted).
    mark: Mapped[str | None] = mapped_column(String(4), nullable=True)
    passed: Mapped[bool] = mapped_column(Boolean, default=False)
    submitted: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    locked_until: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    submitted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    user: Mapped[User] = relationship()
    subject: Mapped[Subject] = relationship()


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
    """An issued certificate (one per pupil + subject).

    Two routes reach the same document: finishing every lesson of the course
    (`issued_via="course"`) or passing the mandatory exam (`issued_via="exam"`,
    which also carries the 5-point `mark`). Names are snapshotted at issue time
    so later content renames do not change an already issued document. `code` is
    the unguessable public verify key.
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
    # "course" | "exam"; mark is only filled by the exam route ("5", "4", "2.5").
    issued_via: Mapped[str] = mapped_column(
        String(8), default="course", server_default="course"
    )
    mark: Mapped[str | None] = mapped_column(String(4), nullable=True)
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


class UserAvatar(Base):
    """A pupil's profile picture, stored as small re-encoded bytes.

    Why a separate table: every authenticated request loads the User row, and
    kilobytes of image data must not ride along with it.

    Why bytes instead of a Telegram file_id (how lesson files are stored):
    a chat list shows dozens of avatars at once, and relaying each one through
    the Telegram API would be slow and rate-limited. A 256px JPEG is ~15 KB.

    `slug` is the privacy mechanism. The image route is public (an `<img>` tag
    cannot send a JWT), but it is only reachable as
    /api/avatars/{user_id}/{slug} — a fresh random slug per upload that cannot
    be enumerated, exactly like a certificate code. Re-posting a photo rotates
    the slug, so an old shared URL stops working.

    The bytes are always produced by `app.avatars.normalise()`: centre-cropped
    square, max 256px, re-encoded. That also drops EXIF (GPS/camera data from a
    phone photo can never reach the browser) and rejects anything not really an
    image.
    """

    __tablename__ = "user_avatars"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), unique=True, index=True
    )
    slug: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    mime: Mapped[str] = mapped_column(String(16), default="image/jpeg")
    width: Mapped[int] = mapped_column(Integer, default=256)
    size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    # "upload" (file picked in the Mini App) | "telegram" (pushed by the bot).
    source: Mapped[str] = mapped_column(String(12), default="upload", server_default="upload")
    data: Mapped[bytes] = mapped_column(LargeBinary)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class ChatMessage(Base):
    """One message in a community chat room.

    Rooms: each grade has its own room (`kind="grade"`, `grade_id` set) so a
    5-sinf pupil never reads an 11-sinf conversation, plus one school-wide
    announcement channel (`kind="news"`, `grade_id` NULL) that only admins may
    write to — the "e'lonxona" the teacher asked for.

    `status` is what makes moderation possible without a rewrite:
      * approved — visible in the room
      * pending  — waiting for an admin (used when CHAT_PREMODERATION is on)
      * rejected — an admin said no (the author still sees it with the reason)
      * deleted  — removed after the fact; the room no longer shows it
    """

    __tablename__ = "chat_messages"
    __table_args__ = (
        Index("ix_chat_room_visible", "kind", "grade_id", "status", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # "grade" | "news"
    kind: Mapped[str] = mapped_column(String(8), default="grade", server_default="grade")
    grade_id: Mapped[int | None] = mapped_column(
        ForeignKey("grades.id", ondelete="CASCADE"), index=True, nullable=True
    )
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    text: Mapped[str] = mapped_column(String(500))
    # "pending" | "approved" | "rejected" | "deleted"
    status: Mapped[str] = mapped_column(String(9), default="approved", server_default="approved")
    reject_reason: Mapped[str | None] = mapped_column(String(160), nullable=True)
    reviewed_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    # Two FKs point at users (author + the admin who decided), so each
    # relationship must name its own join path or SQLAlchemy cannot pick one.
    user: Mapped[User] = relationship(foreign_keys=[user_id])
    reviewer: Mapped[User | None] = relationship(foreign_keys=[reviewed_by])
    grade: Mapped[Grade | None] = relationship()
