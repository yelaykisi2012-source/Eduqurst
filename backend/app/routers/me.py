"""app/routers/me.py — grades, profile, grade selection + progress for the Mini App."""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import avatars, gamification, streaks
from app import chat as chat_rules
from app.config import get_settings
from app.db import get_db
from app.grades import user_grade
from app.models import Achievement, Grade, Lesson, LessonProgress, Subject, User, UserAchievement
from app.schemas import (
    AchievementOut,
    GradeOut,
    ProfileResponse,
    ProgressResponse,
    SetGradeRequest,
    SubjectProgress,
    TeacherCodeRequest,
)
from app.security import get_current_user, is_admin_user

router = APIRouter(prefix="/api", tags=["me"])


def _profile(db: Session, user: User, grade: Grade | None) -> ProfileResponse:
    """Home-screen/profile payload.

    `avatar_url` is the capability path of the stored picture (see
    app/avatars.py) — None when the pupil has no picture, which is how the Mini
    App knows to fall back to initials.

    `can_claim_teacher` tells the app whether the school has handed out a code at
    all. Without it the "Men o‘qituvchiman" form would be a dead button.
    """
    row = avatars.get(db, user.id)
    return ProfileResponse(
        first_name=user.first_name,
        grade_id=grade.id if grade else None,
        grade_name=grade.name if grade else None,
        needs_grade_selection=grade is None,
        is_admin=is_admin_user(user),
        is_teacher=bool(user.is_teacher),
        can_claim_teacher=get_settings().teacher_code_set,
        current_streak=user.current_streak or 0,
        max_streak=user.max_streak or 0,
        avatar_url=avatars.public_path(user.id, row.slug) if row else None,
    )


@router.get("/grades", response_model=list[GradeOut])
def list_grades(
    db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> list[GradeOut]:
    """All selectable grades (1-sinf .. 11-sinf), ordered."""
    grades = db.scalars(select(Grade).order_by(Grade.order_index)).all()
    return [GradeOut.model_validate(g) for g in grades]


@router.get("/me", response_model=ProfileResponse)
def my_profile(
    db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> ProfileResponse:
    """Saved profile. If needs_grade_selection is true the app shows onboarding."""
    if streaks.touch(db, user):
        db.commit()
    return _profile(db, user, user_grade(db, user))


@router.post("/me/grade", response_model=ProfileResponse)
def select_grade(
    body: SetGradeRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ProfileResponse:
    """Persist the pupil's chosen grade (1..11). Never inferred from anything else.

    Changing grade does NOT delete progress: progress lives on each lesson
    (which keeps its own grade), so switching only changes what is displayed.
    """
    grade = db.get(Grade, body.grade_id)
    if grade is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail={"error": "grade_not_found", "message_uz": "Bunday sinf topilmadi."},
        )
    user.grade_id = grade.id
    db.commit()
    return _profile(db, user, grade)


@router.post("/me/teacher-code", response_model=ProfileResponse)
def claim_teacher(
    body: TeacherCodeRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ProfileResponse:
    """Type the school's teacher code ONCE and become staff.

    This is what opens the teachers' room (and the e'lonxona for writing). It is
    one-way by design: a person who proved they are a teacher keeps the role,
    because a pupil could otherwise "un-claim" a colleague's access. Removing a
    teacher is an admin/DB action, not a button in the Mini App.

    A wrong code returns the same 403 shape as the rest of the API and the
    account is throttled (see app/chat.py) — the code itself is never echoed.
    """
    if user.is_teacher:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail={
                "error": "already_teacher",
                "message_uz": "Siz allaqachon o‘qituvchisiz.",
            },
        )
    if not chat_rules.teacher_claim(db, user, body.code):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            detail={
                "error": "wrong_teacher_code",
                "message_uz": "Kod noto‘g‘ri. Kodni sizga maktab beradi.",
            },
        )
    return _profile(db, user, user_grade(db, user))


@router.get("/me/progress", response_model=ProgressResponse)
def my_progress(
    db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> ProgressResponse:
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

    # Subject progress is scoped to the pupil's grade (empty until they pick one).
    subjects_out: list[SubjectProgress] = []
    if grade is not None:
        for subject in db.scalars(
            select(Subject)
            .where(
                Subject.grade_id == grade.id,
                Subject.is_published.is_(True),
            )
            .order_by(Subject.order_index)
        ).all():
            total = db.scalar(
                select(func.count(Lesson.id)).where(
                    Lesson.subject_id == subject.id, Lesson.is_published.is_(True)
                )
            ) or 0
            done = db.scalar(
                select(func.count(LessonProgress.id))
                .join(Lesson, Lesson.id == LessonProgress.lesson_id)
                .where(
                    Lesson.subject_id == subject.id,
                    LessonProgress.user_id == user.id,
                    LessonProgress.passed.is_(True),
                )
            ) or 0
            subjects_out.append(
                SubjectProgress(
                    subject_name=subject.name, emoji=subject.emoji,
                    total_lessons=total, passed_lessons=done,
                )
            )

    earned_ids = set(
        db.scalars(
            select(UserAchievement.achievement_id).where(UserAchievement.user_id == user.id)
        ).all()
    )
    achievements_out = [
        AchievementOut(
            code=ach.code, title=ach.title, description=ach.description,
            icon=ach.icon, earned=ach.id in earned_ids,
        )
        for ach in db.scalars(select(Achievement).order_by(Achievement.id)).all()
    ]

    return ProgressResponse(
        first_name=user.first_name,
        grade_id=grade.id if grade else None,
        grade_name=grade.name if grade else None,
        stars_total=gamification.stars_total(db, user.id),
        lessons_viewed=viewed,
        lessons_passed=passed,
        subjects=subjects_out,
        achievements=achievements_out,
    )
