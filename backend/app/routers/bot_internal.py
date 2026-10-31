"""
app/routers/bot_internal.py — a tiny endpoint for the Python bot only.

Why: the bot knows a pupil's telegram_id (Telegram gives it in every update)
but it does NOT have the pupil's Mini App JWT. To personalise /start
("Salom, Dilnoza! 3-sinf, 12 ⭐") it asks the backend directly.

Security: the caller must send the shared BOT_TOKEN in the X-Bot-Token
header. Only the bot and the backend know this secret, so strangers get 401.
This endpoint never exposes anything beyond the pupil's own public-ish stats
(first name, grade name, star/lesson counts).
"""
from __future__ import annotations

import hmac
from datetime import date

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import gamification, parents, streaks
from app.config import get_settings
from app.db import get_db
from app.grades import user_grade
from app.models import LessonMaterial, LessonProgress, User
from app.routers import admin as admin_api
from app.routers import content as content_api
from app.routers import me as me_api
from app.routers import quiz as quiz_api
from app.schemas import (
    AdminLessonOut,
    AdminMaterialOut,
    AdminQuestionOut,
    AdminSubjectOut,
    BotAdminLessonCreate,
    BotAdminMaterialCreate,
    BotAdminQuestionCreate,
    BotAdminSubjectCreate,
    BotPupilUpsert,
    BotQuizSubmit,
    BotSetGrade,
    BotSummaryResponse,
    GradeOut,
    LessonDetail,
    ParentCodeOut,
    ParentLinkRequest,
    ParentLinkResult,
    ParentStatusOut,
    ParentUnlinkRequest,
    ProgressResponse,
    ProfileResponse,
    QuizOut,
    QuizSubmitRequest,
    QuizSubmitResult,
    SetGradeRequest,
    SubjectWithLessons,
    WeeklyDigestOut,
)

router = APIRouter(prefix="/api/internal", tags=["bot"])

_UNAUTHORIZED = HTTPException(
    status.HTTP_401_UNAUTHORIZED,
    detail={"error": "bad_bot_token", "message_uz": "Bot tokeni yaroqsiz."},
)


def require_bot_token(x_bot_token: str = Header(default="")) -> None:
    """Constant-time compare against our own BOT_TOKEN; 401 on any mismatch."""
    secret = get_settings().BOT_TOKEN
    if not secret or not x_bot_token or not hmac.compare_digest(x_bot_token, secret):
        raise _UNAUTHORIZED


@router.get("/pupil-summary", response_model=BotSummaryResponse, dependencies=[Depends(require_bot_token)])
def pupil_summary(
    telegram_id: int = Query(ge=1),
    db: Session = Depends(get_db),
) -> BotSummaryResponse:
    """Stats for /start personalisation. Unknown pupil => needs_onboarding=true
    (the bot then simply shows the plain welcome text — never invents data)."""
    user = db.scalar(select(User).where(User.telegram_id == telegram_id))
    if user is not None and streaks.touch(db, user):
        db.commit()
    return _summary(db, user)


def _summary(db: Session, user: User | None) -> BotSummaryResponse:
    if user is None:
        return BotSummaryResponse(known_user=False, needs_onboarding=True)
    grade = user_grade(db, user)
    viewed = db.scalar(
        select(func.count(LessonProgress.id)).where(
            LessonProgress.user_id == user.id, LessonProgress.lesson_viewed.is_(True)
        )
    ) or 0
    passed = db.scalar(
        select(func.count(LessonProgress.id)).where(
            LessonProgress.user_id == user.id, LessonProgress.passed.is_(True)
        )
    ) or 0
    return BotSummaryResponse(
        known_user=True,
        needs_onboarding=grade is None,
        first_name=user.first_name,
        grade_name=grade.name if grade else None,
        stars_total=gamification.stars_total(db, user.id),
        lessons_viewed=viewed,
        lessons_passed=passed,
        current_streak=user.current_streak or 0,
        max_streak=user.max_streak or 0,
    )


# ------------------------------------------------------------------
# Full pupil experience inside the bot: same rules as the Mini App.
# We CALL the existing routers as plain functions (same code path:
# grade scoping, unlock checks, server-side grading, idempotency).
# ------------------------------------------------------------------

_NOT_FOUND_PUPIL = HTTPException(
    status.HTTP_404_NOT_FOUND,
    detail={"error": "pupil_not_found", "message_uz": "Avval /start bosing."},
)


def _pupil(db: Session, telegram_id: int) -> User:
    user = db.scalar(select(User).where(User.telegram_id == telegram_id))
    if user is None:
        raise _NOT_FOUND_PUPIL
    return user


@router.post("/pupils", response_model=BotSummaryResponse, dependencies=[Depends(require_bot_token)])
def upsert_pupil(body: BotPupilUpsert, db: Session = Depends(get_db)) -> BotSummaryResponse:
    """The bot registers a pupil who pressed /start (Telegram verified the id
    for us — the bot only ever reports ids from real incoming updates)."""
    user = db.scalar(select(User).where(User.telegram_id == body.telegram_id))
    if user is None:
        user = User(
            telegram_id=body.telegram_id,
            first_name=body.first_name or "",
            username=body.username,
        )
        db.add(user)
    else:
        # Keep stored profile fresh with what Telegram tells us now.
        if body.first_name:
            user.first_name = body.first_name[:128]
        user.username = body.username or user.username
    streaks.touch(db, user)
    db.commit()
    return _summary(db, user)


@router.get("/grades", response_model=list[GradeOut], dependencies=[Depends(require_bot_token)])
def internal_grades(telegram_id: int = Query(ge=1), db: Session = Depends(get_db)):
    return me_api.list_grades(db=db, user=_pupil(db, telegram_id))


@router.post("/pupil/grade", response_model=ProfileResponse, dependencies=[Depends(require_bot_token)])
def internal_set_grade(body: BotSetGrade, db: Session = Depends(get_db)):
    user = _pupil(db, body.telegram_id)
    return me_api.select_grade(
        body=SetGradeRequest(grade_id=body.grade_id), db=db, user=user
    )


@router.get("/pupil/subjects", response_model=list[SubjectWithLessons], dependencies=[Depends(require_bot_token)])
def internal_subjects(telegram_id: int = Query(ge=1), db: Session = Depends(get_db)):
    return content_api.list_subjects(db=db, user=_pupil(db, telegram_id))


@router.get("/pupil/lesson/{lesson_id}", response_model=LessonDetail, dependencies=[Depends(require_bot_token)])
def internal_lesson(lesson_id: int, telegram_id: int = Query(ge=1), db: Session = Depends(get_db)):
    return content_api.get_lesson(lesson_id=lesson_id, db=db, user=_pupil(db, telegram_id))


@router.post("/pupil/lesson/{lesson_id}/viewed", dependencies=[Depends(require_bot_token)])
def internal_mark_viewed(lesson_id: int, telegram_id: int = Query(ge=1), db: Session = Depends(get_db)):
    return content_api.mark_lesson_viewed(lesson_id=lesson_id, db=db, user=_pupil(db, telegram_id))


@router.get("/materials/{material_id}", dependencies=[Depends(require_bot_token)])
def internal_material(material_id: int, telegram_id: int = Query(ge=1), db: Session = Depends(get_db)):
    """A lesson's file material (pdf/video) for the bot to re-send by file_id.
    Same pupil grade scoping as the Mini App — strangers get 404/403."""
    material = db.get(LessonMaterial, material_id)
    if material is None or not material.file_id:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail={"error": "material_not_found", "message_uz": "Fayl topilmadi."},
        )
    content_api._accessible_lesson(db, _pupil(db, telegram_id), material.lesson_id)
    return {
        "id": material.id,
        "kind": material.kind,
        "title": material.title,
        "file_id": material.file_id,
        "file_name": material.file_name,
        "file_size": material.file_size,
    }


@router.get("/pupil/lesson/{lesson_id}/quiz", response_model=QuizOut, dependencies=[Depends(require_bot_token)])
def internal_quiz(lesson_id: int, telegram_id: int = Query(ge=1), db: Session = Depends(get_db)):
    return content_api.get_quiz(lesson_id=lesson_id, db=db, user=_pupil(db, telegram_id))


@router.post("/pupil/lesson/{lesson_id}/quiz/submit", response_model=QuizSubmitResult, dependencies=[Depends(require_bot_token)])
def internal_quiz_submit(lesson_id: int, body: BotQuizSubmit, db: Session = Depends(get_db)):
    return quiz_api.submit_quiz(
        lesson_id=lesson_id,
        body=QuizSubmitRequest(idempotency_key=body.idempotency_key, answers=body.answers),
        db=db,
        user=_pupil(db, body.telegram_id),
    )


@router.get("/pupil/progress", response_model=ProgressResponse, dependencies=[Depends(require_bot_token)])
def internal_progress(telegram_id: int = Query(ge=1), db: Session = Depends(get_db)):
    return me_api.my_progress(db=db, user=_pupil(db, telegram_id))


# ------------------------------------------------------------------
# Admin inside the bot: bot token AND the pupil must be in
# ADMIN_TELEGRAM_IDS (backend/.env). Same handler functions as /api/admin.
# ------------------------------------------------------------------

def _internal_admin(db: Session, telegram_id: int) -> User:
    user = _pupil(db, telegram_id)
    if user.telegram_id not in get_settings().admin_id_set:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            detail={"error": "not_admin", "message_uz": "Siz admin emassiz."},
        )
    return user


@router.get("/admin/overview", dependencies=[Depends(require_bot_token)])
def internal_admin_overview(telegram_id: int = Query(ge=1), db: Session = Depends(get_db)):
    return admin_api.overview(db=db, admin=_internal_admin(db, telegram_id))


@router.post("/admin/subjects", response_model=AdminSubjectOut, status_code=201, dependencies=[Depends(require_bot_token)])
def internal_admin_create_subject(body: BotAdminSubjectCreate, db: Session = Depends(get_db)):
    return admin_api.create_subject(
        body=body.data, db=db, admin=_internal_admin(db, body.telegram_id)
    )


@router.get("/admin/subjects/{subject_id}/lessons", response_model=list[AdminLessonOut], dependencies=[Depends(require_bot_token)])
def internal_admin_lessons(subject_id: int, telegram_id: int = Query(ge=1), db: Session = Depends(get_db)):
    return admin_api.list_lessons(subject_id=subject_id, db=db, admin=_internal_admin(db, telegram_id))


@router.post("/admin/subjects/{subject_id}/lessons", response_model=AdminLessonOut, status_code=201, dependencies=[Depends(require_bot_token)])
def internal_admin_create_lesson(subject_id: int, body: BotAdminLessonCreate, db: Session = Depends(get_db)):
    return admin_api.create_lesson(
        subject_id=subject_id, body=body.data, db=db, admin=_internal_admin(db, body.telegram_id)
    )


@router.post("/admin/lessons/{lesson_id}/questions", response_model=AdminQuestionOut, status_code=201, dependencies=[Depends(require_bot_token)])
def internal_admin_create_question(lesson_id: int, body: BotAdminQuestionCreate, db: Session = Depends(get_db)):
    return admin_api.create_question(
        lesson_id=lesson_id, body=body.data, db=db, admin=_internal_admin(db, body.telegram_id)
    )


@router.post("/admin/lessons/{lesson_id}/materials", response_model=AdminMaterialOut, status_code=201, dependencies=[Depends(require_bot_token)])
def internal_admin_create_material(lesson_id: int, body: BotAdminMaterialCreate, db: Session = Depends(get_db)):
    """video / pdf / live / text — the four lesson formats, from the bot too."""
    return admin_api.create_material(
        lesson_id=lesson_id, body=body.data, db=db, admin=_internal_admin(db, body.telegram_id)
    )


# ---------- parent weekly digest ----------

_PARENT_ERRORS = {
    "code_invalid": "Kod topilmadi — yangi kod oling.",
    "code_expired": "Kod muddati tugagan — farzandingizdan yangi kod so‘rang.",
    "self_link": "O‘zingizni ota-ona sifatida ulay olmaysiz.",
}


def _pupil_or_404(db: Session, telegram_id: int) -> User:
    user = parents.pupil_by_telegram(db, telegram_id)
    if user is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail={"error": "pupil_not_found", "message_uz": "O‘quvchi topilmadi."},
        )
    return user


@router.get(
    "/parent/status",
    response_model=ParentStatusOut,
    dependencies=[Depends(require_bot_token)],
)
def parent_status(telegram_id: int = Query(ge=1), db: Session = Depends(get_db)):
    user = _pupil_or_404(db, telegram_id)
    return ParentStatusOut(
        linked=user.parent_telegram_id is not None, parent_name=user.parent_name
    )


@router.post(
    "/parent/code",
    response_model=ParentCodeOut,
    dependencies=[Depends(require_bot_token)],
)
def parent_code(telegram_id: int = Query(ge=1), db: Session = Depends(get_db)):
    """A one-time code the pupil hands to their parent (15 minutes)."""
    user = _pupil_or_404(db, telegram_id)
    if user.parent_telegram_id is not None:
        return ParentCodeOut(linked=True, parent_name=user.parent_name)
    code, expires = parents.issue_code(db, user)
    return ParentCodeOut(code=code, expires_at=expires)


@router.post(
    "/parent/link",
    response_model=ParentLinkResult,
    dependencies=[Depends(require_bot_token)],
)
def parent_link(body: ParentLinkRequest, db: Session = Depends(get_db)):
    try:
        user = parents.link_parent(
            db, body.code, body.parent_telegram_id, body.parent_name
        )
    except parents.ParentLinkError as e:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail={"error": e.code, "message_uz": _PARENT_ERRORS.get(e.code, "Kod yaroqsiz.")},
        )
    grade = user_grade(db, user)
    return ParentLinkResult(
        pupil_first_name=user.first_name or "O‘quvchi",
        grade_name=grade.name if grade else None,
        parent_name=user.parent_name,
    )


@router.post(
    "/parent/unlink",
    status_code=204,
    dependencies=[Depends(require_bot_token)],
)
def parent_unlink(body: ParentUnlinkRequest, db: Session = Depends(get_db)) -> None:
    user = _pupil_or_404(db, body.telegram_id)
    parents.unlink_parent(db, user)


@router.get(
    "/parents/weekly-digest",
    response_model=WeeklyDigestOut,
    dependencies=[Depends(require_bot_token)],
)
def parents_weekly_digest(
    week_start: date | None = Query(default=None),
    db: Session = Depends(get_db),
):
    """One week of progress for every linked parent (grouped by parent)."""
    try:
        data = parents.weekly_digests(db, week_start)
    except ValueError:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"error": "week_start_not_monday", "message_uz": "Hafta dushanbadan boshlanadi."},
        )
    return WeeklyDigestOut(**data)
