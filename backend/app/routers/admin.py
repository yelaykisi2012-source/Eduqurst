"""
app/routers/admin.py — content management for admins only.

Who is an admin? A pupil whose Telegram id appears in ADMIN_TELEGRAM_IDS
(backend/.env). The check runs on EVERY request: JWT proves who you are,
the allowlist proves you may admin. Everyone else gets 403.

What can an admin do? Create subjects / lessons / quiz questions for any
grade — this is how grades 5..11 get filled with real content.
Deletion is intentionally NOT exposed yet (safer while learning).
"""
from __future__ import annotations

import unicodedata

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.models import AnswerOption, Grade, Lesson, LessonMaterial, Question, Subject, User
from app.schemas import (
    AdminLessonCreate,
    AdminLessonOut,
    AdminMaterialCreate,
    AdminMaterialOut,
    AdminQuestionCreate,
    AdminQuestionOut,
    AdminSubjectCreate,
    AdminSubjectOut,
    GradeOverview,
)
from app.security import get_current_user

router = APIRouter(prefix="/api/admin", tags=["admin"])


def get_admin(user: User = Depends(get_current_user)) -> User:
    ids = get_settings().admin_id_set
    if user.telegram_id not in ids:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            detail={"error": "not_admin", "message_uz": "Siz admin emassiz."},
        )
    return user


def _slugify(name: str) -> str:
    """'Ona tili' -> 'ona-tili' (ascii, lowercase, hyphens)."""
    s = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    s = "".join(c if c.isalnum() else "-" for c in s.lower()).strip("-")
    return s or "fan"


def _unique_slug(db: Session, base: str) -> str:
    slug, n = base, 2
    while db.scalar(select(Subject).where(Subject.slug == slug)) is not None:
        slug = f"{base}-{n}"
        n += 1
    return slug


@router.get("/overview", response_model=list[GradeOverview])
def overview(db: Session = Depends(get_db), admin: User = Depends(get_admin)):
    """Every grade with its subject/lesson counts — the admin dashboard data."""
    out: list[GradeOverview] = []
    for grade in db.scalars(select(Grade).order_by(Grade.order_index)).all():
        subjects = db.scalars(
            select(Subject).where(Subject.grade_id == grade.id).order_by(Subject.order_index)
        ).all()
        out.append(
            GradeOverview(
                grade_id=grade.id,
                grade_name=grade.name,
                subjects=[
                    AdminSubjectOut(
                        id=s.id, name=s.name, slug=s.slug, emoji=s.emoji,
                        grade_id=s.grade_id,
                        lesson_count=db.scalar(
                            select(func.count(Lesson.id)).where(Lesson.subject_id == s.id)
                        ) or 0,
                    )
                    for s in subjects
                ],
            )
        )
    return out


@router.post("/subjects", response_model=AdminSubjectOut, status_code=201)
def create_subject(
    body: AdminSubjectCreate, db: Session = Depends(get_db), admin: User = Depends(get_admin)
):
    grade = db.get(Grade, body.grade_id)
    if grade is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Sinf topilmadi")
    subject = Subject(
        grade_id=grade.id,
        name=body.name,
        slug=_unique_slug(db, _slugify(body.name)),
        emoji=body.emoji,
        order_index=body.order_index
        or ((db.scalar(
            select(func.max(Subject.order_index)).where(Subject.grade_id == grade.id)
        ) or 0) + 1),
    )
    db.add(subject)
    db.commit()
    return AdminSubjectOut(
        id=subject.id, name=subject.name, slug=subject.slug, emoji=subject.emoji,
        grade_id=subject.grade_id, lesson_count=0,
    )


@router.post("/subjects/{subject_id}/lessons", response_model=AdminLessonOut, status_code=201)
def create_lesson(
    subject_id: int,
    body: AdminLessonCreate,
    db: Session = Depends(get_db),
    admin: User = Depends(get_admin),
):
    subject = db.get(Subject, subject_id)
    if subject is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Fan topilmadi")
    next_order = (
        db.scalar(
            select(func.max(Lesson.level_order)).where(Lesson.subject_id == subject_id)
        )
        or 0
    ) + 1
    lesson = Lesson(
        subject_id=subject_id,
        title=body.title,
        explanation=body.explanation,
        level_order=next_order,
        stars_reward=body.stars_reward,
        pass_threshold_percent=body.pass_threshold_percent,
    )
    db.add(lesson)
    db.commit()
    return AdminLessonOut(
        id=lesson.id, title=lesson.title, level_order=lesson.level_order,
        subject_name=subject.name,
        question_count=0,
    )


@router.get("/subjects/{subject_id}/lessons", response_model=list[AdminLessonOut])
def list_lessons(
    subject_id: int, db: Session = Depends(get_db), admin: User = Depends(get_admin)
):
    lessons = db.scalars(
        select(Lesson).where(Lesson.subject_id == subject_id).order_by(Lesson.level_order)
    ).all()
    return [
        AdminLessonOut(
            id=l.id, title=l.title, level_order=l.level_order,
            subject_name=l.subject.name,
            question_count=db.scalar(
                select(func.count(Question.id)).where(Question.lesson_id == l.id)
            ) or 0,
            material_count=db.scalar(
                select(func.count(LessonMaterial.id)).where(LessonMaterial.lesson_id == l.id)
            ) or 0,
        )
        for l in lessons
    ]


@router.post("/lessons/{lesson_id}/materials", response_model=AdminMaterialOut, status_code=201)
def create_material(
    lesson_id: int,
    body: AdminMaterialCreate,
    db: Session = Depends(get_db),
    admin: User = Depends(get_admin),
):
    """Attach one of the four lesson formats (video / pdf / live / text)
    — or an image/slide — to an existing lesson."""
    lesson = db.get(Lesson, lesson_id)
    if lesson is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Dars topilmadi")
    needs_url = body.kind in {"video", "pdf", "live", "image"}
    if needs_url and not body.content.strip().lower().startswith(("http://", "https://")):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Bu tur uchun havola http:// yoki https:// bilan boshlanishi kerak",
        )
    next_order = (
        db.scalar(
            select(func.max(LessonMaterial.order_index)).where(
                LessonMaterial.lesson_id == lesson_id
            )
        )
        or 0
    ) + 1
    material = LessonMaterial(
        lesson_id=lesson_id,
        kind=body.kind,
        title=body.title,
        content=body.content.strip(),
        order_index=next_order,
    )
    db.add(material)
    db.commit()
    return AdminMaterialOut(
        id=material.id, kind=material.kind, title=material.title,
        content=material.content, order_index=material.order_index,
    )


@router.post("/lessons/{lesson_id}/questions", response_model=AdminQuestionOut, status_code=201)
def create_question(
    lesson_id: int,
    body: AdminQuestionCreate,
    db: Session = Depends(get_db),
    admin: User = Depends(get_admin),
):
    lesson = db.get(Lesson, lesson_id)
    if lesson is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Dars topilmadi")
    correct = [o for o in body.options if o.is_correct]
    if body.kind == "single" and len(correct) != 1:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Bir variant to'g'ri deb belgilanishi kerak",
        )
    if body.kind == "text" and len(correct) < 1:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Matnli savolda kamida bitta to'g'ri javob kerak",
        )
    next_order = (
        db.scalar(select(func.max(Question.order_index)).where(Question.lesson_id == lesson_id))
        or 0
    ) + 1
    q = Question(lesson_id=lesson_id, text=body.text, kind=body.kind, order_index=next_order)
    db.add(q)
    db.flush()
    for i, o in enumerate(body.options):
        db.add(AnswerOption(
            question_id=q.id, text=o.text, is_correct=o.is_correct,
            feedback="Ajoyib! 🎉" if o.is_correct else "Diyonat qil, yana o'ylab ko'r 😊",
            order_index=i,
        ))
    db.commit()
    return AdminQuestionOut(
        id=q.id, text=q.text, kind=q.kind, option_count=len(body.options),
        correct_count=len(correct),
    )
