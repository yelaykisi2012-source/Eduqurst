"""app/schemas.py — Pydantic request/response models (API contract)."""
from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


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
    # True once the person typed the school's teacher code: they get the
    # teachers' room and may write the e'lonxona.
    is_teacher: bool = False
    # False when the school has not set TEACHER_CODE yet — the Mini App then
    # hides the "Men o'qituvchiman" form instead of offering a dead button.
    can_claim_teacher: bool = False
    # Consecutive local (Asia/Tashkent) days with activity — shown as 🔥.
    current_streak: int = 0
    max_streak: int = 0
    # Relative capability URL of the profile picture (see app/avatars.py).
    # None = no picture yet, so the Mini App draws initials instead.
    avatar_url: str | None = None


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


# ---------- certificates ----------
class CertificateOut(BaseModel):
    code: str
    subject_id: int
    subject_name: str
    grade_name: str
    pupil_name: str
    score_percent: int
    stars: int
    # "course" | "exam" + the 5-point mark the exam produced ("5", "4", "2.5").
    issued_via: str = "course"
    mark: str | None = None
    issued_at: datetime
    verify_url: str


class EligibleCertificateOut(BaseModel):
    """A finished course; `certificate` is set once it has been issued."""

    subject_id: int
    subject_name: str
    emoji: str
    total_lessons: int
    score_percent: int
    certificate: CertificateOut | None = None


class CertificateVerifyOut(BaseModel):
    valid: bool
    code: str
    pupil_name: str
    grade_name: str
    subject_name: str
    score_percent: int
    stars: int
    issued_via: str = "course"
    mark: str | None = None
    issued_at: datetime


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


class AdminPairCreate(BaseModel):
    left: str = Field(min_length=1, max_length=120)
    right: str = Field(min_length=1, max_length=120)


class AdminQuestionCreate(BaseModel):
    text: str = Field(min_length=3, max_length=1000)
    kind: str = Field(default="single", pattern="^(single|text|matching)$")
    options: list[AdminOptionCreate] = Field(default_factory=list, max_length=6)
    # Only for kind="matching": the left→right pairs (rights become options).
    pairs: list[AdminPairCreate] = Field(default_factory=list, max_length=6)


class AdminQuestionOut(BaseModel):
    id: int
    text: str
    kind: str
    option_count: int
    correct_count: int
    # True = this question is part of the mandatory exam paper of its subject.
    is_exam: bool = False


class AdminQuestionOptionOut(BaseModel):
    id: int
    text: str
    is_correct: bool


class AdminPairOut(BaseModel):
    left: str
    right: str


class AdminQuestionDetailOut(AdminQuestionOut):
    """Admin-only view: includes which option is correct (never sent to pupils)."""

    options: list[AdminQuestionOptionOut]
    pairs: list[AdminPairOut] = Field(default_factory=list)


class AdminExamFlagIn(BaseModel):
    """Admin marks a question in/out of the mandatory exam paper."""

    is_exam: bool


class AdminExamCoverageOut(BaseModel):
    """How close a subject is to a ready exam paper (20 flagged questions)."""

    subject_id: int
    subject_name: str
    grade_id: int
    grade_name: str
    flagged: int  # questions marked is_exam inside this subject
    ready: bool  # at least EXAM_SIZE across subject + same-grade fillers
    exam_size: int  # questions in a paper, so the UI never hardcodes it


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


class MatchPromptOut(BaseModel):
    """Left-hand item of a matching question (right choices are `options`)."""

    id: int
    text: str


class QuizQuestionOut(BaseModel):
    id: int
    text: str
    kind: str
    image_url: str | None
    options: list[QuizOptionOut]
    prompts: list[MatchPromptOut] = Field(default_factory=list)


class QuizOut(BaseModel):
    lesson_id: int
    lesson_title: str
    pass_threshold_percent: int
    questions: list[QuizQuestionOut]


# ---------- quiz submit ----------
class MatchPairIn(BaseModel):
    prompt_id: int
    option_id: int


class AnswerIn(BaseModel):
    question_id: int
    option_id: int | None = None
    text: str | None = None
    pairs: list[MatchPairIn] = Field(default_factory=list)


class QuizSubmitRequest(BaseModel):
    idempotency_key: str = Field(min_length=8, max_length=64)
    answers: list[AnswerIn]


class MistakeOut(BaseModel):
    """A wrong answer, revealed ONLY after the quiz was submitted."""

    question_id: int
    question_text: str
    kind: str
    your_answer: str
    correct_answer: str
    explanation: str = ""


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
    # Wrong answers with the correct option + supportive hint ("Xatolarni ko'rish").
    mistakes: list[MistakeOut] = []


# ---------- mandatory exam (majburiy sertifikat) ----------
class ExamCardOut(BaseModel):
    """One subject's exam, as the pupil sees it in the list."""

    subject_id: int
    subject_name: str
    emoji: str
    total: int  # questions in the paper (0 when the exam is not configured)
    available: bool  # False until the admin flags enough exam questions
    locked_until: datetime | None  # set for 30 days after a failed sitting
    best_score_percent: int | None  # best PASSED sitting, if any
    best_mark: str | None
    passed: bool
    certificate_code: str | None


class ExamPaperOut(BaseModel):
    """The frozen paper. Correct answers are never included."""

    attempt_id: int
    subject_id: int
    subject_name: str
    total: int
    pass_percent: int
    lock_days: int
    questions: list[QuizQuestionOut]


class ExamSubmitRequest(BaseModel):
    attempt_id: int
    answers: list[AnswerIn]


class ExamResultOut(BaseModel):
    attempt_id: int
    total_count: int
    correct_count: int
    score_percent: int
    mark: str  # 5-point scale: "5" | "4" | "2.5"
    passed: bool
    stars_earned: int
    stars_total: int
    locked_until: datetime | None
    certificate: CertificateOut | None = None
    message_uz: str
    mistakes: list[MistakeOut] = []


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


# ---------- parent weekly digest (bot internal) ----------
class ParentCodeOut(BaseModel):
    code: str | None = None
    expires_at: datetime | None = None
    linked: bool = False
    parent_name: str | None = None


class ParentLinkRequest(BaseModel):
    code: str = Field(min_length=4, max_length=16)
    parent_telegram_id: int = Field(ge=1)
    parent_name: str = Field(default="", max_length=128)


class ParentLinkResult(BaseModel):
    pupil_first_name: str
    grade_name: str | None = None
    parent_name: str | None = None


class ParentStatusOut(BaseModel):
    linked: bool = False
    parent_name: str | None = None


class ParentUnlinkRequest(BaseModel):
    telegram_id: int = Field(ge=1)


class ParentDigestPupil(BaseModel):
    user_id: int
    first_name: str
    grade_name: str | None = None
    lessons_passed_week: int = 0
    stars_week: int = 0
    current_streak: int = 0
    lessons_passed_total: int = 0
    stars_total: int = 0
    active_week: bool = False


class ParentDigestGroup(BaseModel):
    parent_telegram_id: int
    parent_name: str | None = None
    pupils: list[ParentDigestPupil]


class WeeklyDigestOut(BaseModel):
    week_start: date
    week_end: date
    parents: list[ParentDigestGroup]


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


# ---------- profile picture (avatar) ----------
class AvatarOut(BaseModel):
    """What the Mini App shows after an upload/remove.

    `avatar_url` is the capability path; `size_bytes` is the STORED (already
    downscaled) size, which is what the pupil's storage actually costs us.
    """

    avatar_url: str
    mime: str
    width: int
    size_bytes: int
    # "upload" = picked in the Mini App, "telegram" = pushed by the bot.
    source: str
    updated_at: datetime


# ---------- community chat ----------
class ChatSendRequest(BaseModel):
    """Post to a room. `kind="news"` is the e'lonxona (staff-only writer).

    A room is addressed by `room_id` now (that is what the "+" button returns),
    but the old (kind, grade_id) pair still works — a Mini App build already
    open on a pupil's phone must keep working the day the server changes.

    `kind` is validated by app/chat.py (400/422 with an Uzbek message) rather
    than by a pydantic pattern, so a wrong room fails the same way everywhere.
    """

    text: str
    room_id: int | None = Field(default=None, ge=1)
    kind: str = "grade"
    # Required for kind="grade"; ignored for news (the room is a grade's, news is not).
    grade_id: int | None = Field(default=None, ge=1)


class ChatMediaOut(BaseModel):
    """The one file attached to a message, already reduced to what a bubble needs.

    `url` is a relative capability path (/api/chat/media/{slug}) — the Mini App
    prefixes its API base. A video's URL is the backend proxy, so the bot token
    never appears in anything the browser sees.
    """

    kind: str                 # "image" | "gif" | "video"
    url: str
    mime: str
    width: int | None = None
    height: int | None = None
    size_bytes: int = 0


class ChatMessageOut(BaseModel):
    """One message in a feed.

    The author is a first name + (optional) avatar only — never the telegram id,
    so a pupil's number cannot be harvested from the chat (rule: minimal data
    about children). `status` lets the composer show an honest state:
    "approved" (public), "pending" (waiting for a teacher) or "rejected"
    (with `reject_reason`). Those two only ever appear for YOUR OWN messages.
    """

    id: int
    room_id: int | None = None
    kind: str
    grade_id: int | None
    grade_name: str | None
    author_id: int
    author_name: str
    avatar_url: str | None
    text: str
    media: ChatMediaOut | None = None
    status: str
    reject_reason: str | None = None
    is_me: bool
    created_at: datetime


class ChatRoomOut(BaseModel):
    """A room the pupil may open: the e'lonxona, their own class, the teachers'
    room (staff only) and every group chat the "+" button created.

    `can_read` is on the object as well as in the fact that it is listed, because
    the app has to draw a locked row honestly instead of hiding a room that
    exists (a pupil sees "🧑‍🏫 O‘qituvchilar xonasi — faqat o‘qituvchilar" rather
    than wondering why a chat is missing).
    """

    id: int
    kind: str
    grade_id: int | None
    name: str
    bio: str | None = None
    emoji: str
    avatar_url: str | None = None
    can_post: bool
    can_read: bool = True
    is_current_grade: bool
    # How many people the room lists (0 for class rooms: those are the whole grade).
    member_count: int = 0
    # True when this person opened it — the app then offers rename/people actions.
    is_mine: bool = False
    owner_name: str | None = None
    is_closed: bool = False
    # Cache-busting hint for the poller: newest id the server has for this room.
    latest_id: int | None = None


class ChatFeedOut(BaseModel):
    room_id: int | None = None
    kind: str
    grade_id: int | None
    messages: list[ChatMessageOut]
    # Newest id in this response — the client sends it back as after_id next poll.
    latest_id: int | None
    premoderation: bool


class ChatSendOut(BaseModel):
    message: ChatMessageOut
    premoderation: bool
    message_uz: str


class ChatPendingItem(BaseModel):
    """A queued message + everything an admin needs to decide."""

    id: int
    kind: str
    grade_id: int | None
    grade_name: str | None
    author_id: int
    author_name: str
    avatar_url: str | None
    text: str
    created_at: datetime
    media: ChatMediaOut | None = None


class ChatPendingOut(BaseModel):
    """The moderation queue + the badge count."""

    count: int
    premoderation: bool
    items: list[ChatPendingItem]


class ChatReviewRequest(BaseModel):
    """Rejection needs a reason; approve/delete do not."""

    reason: str | None = Field(default=None, max_length=160)

    @field_validator("reason")
    @classmethod
    def _strip_reason(cls, value: str | None) -> str | None:
        value = (value or "").strip()
        return value or None


class ChatRoomCreateRequest(BaseModel):
    """The "+" button: a name is enough, a bio and an icon are optional.

    app/chat.py enforces the real bounds (3-48 / 200) so every room field fails
    with the same Uzbek-shaped 422 as the rest of the chat API.
    """

    name: str
    bio: str | None = None
    emoji: str | None = None


class ChatRoomUpdateRequest(BaseModel):
    """Rename / describe / close. Only fields present are touched.

    `is_closed` is how an owner stops a chat that got out of hand without
    deleting the history the teacher may still want to read.
    """

    name: str | None = None
    bio: str | None = None
    emoji: str | None = None
    is_closed: bool | None = None


class ChatRoomOutResult(BaseModel):
    """One room, echoed after create/update (the app re-renders the header)."""

    room: ChatRoomOut
    message_uz: str


class ChatMemberAddRequest(BaseModel):
    """Add one person by the id the people-search returned."""

    user_id: int = Field(ge=1)


class ChatMemberOut(BaseModel):
    id: int
    name: str
    grade_name: str | None
    avatar_url: str | None
    role: str            # "owner" | "member"
    is_teacher: bool = False
    # Lets the panel say "leave" to yourself and "chiqarish" to an owner — the
    # app must not guess that from a first name.
    is_me: bool = False


class ChatPersonOut(BaseModel):
    """A row in the "add people" list — deliberately thin (minimal child data)."""

    id: int
    name: str
    grade_name: str | None
    avatar_url: str | None
    is_teacher: bool = False
    is_me: bool = False


class ChatPeopleOut(BaseModel):
    people: list[ChatPersonOut]


class TeacherCodeRequest(BaseModel):
    """The secret the school hands to its teachers (Settings.TEACHER_CODE)."""

    code: str = Field(min_length=1, max_length=64)
