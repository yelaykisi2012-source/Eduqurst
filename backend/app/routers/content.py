"""
app/routers/content.py — subjects, lessons, materials, quiz fetch.

Grade scoping:
- only content of the pupil's OWN selected grade is listed;
- if the pupil has not picked a grade yet, these endpoints return HTTP 409
  ({error: "grade_not_selected"}) so the Mini App runs the onboarding flow;
- a lesson from a different grade is not readable/quizzable (403) — this
  prevents accidental mixing of content between grades.

Only published content is visible; locked lessons are listed but flagged
unlocked=false so the Mini App can show a 🔒 instead of hiding progress.
"""
import json
import random
import urllib.parse
import urllib.request

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app import streaks
from app.gamification import get_progress, is_lesson_unlocked
from app.grades import assert_lesson_in_grade, require_grade
from app.models import Lesson, LessonMaterial, LessonProgress, Subject, User
from app.schemas import (
    LessonDetail,
    LessonSummary,
    MatchPromptOut,
    MaterialOut,
    QuizOut,
    QuizOptionOut,
    QuizQuestionOut,
    SubjectWithLessons,
)
from app.security import get_current_user

router = APIRouter(prefix="/api", tags=["content"])

_NOT_FOUND = HTTPException(status.HTTP_404_NOT_FOUND, detail="Topilmadi")

_TG_API = "https://api.telegram.org"


def _telegram_get_file(file_id: str) -> dict:
    """Ask Telegram where a file we received lives. Kept as a small helper so
    tests can monkeypatch it without network access."""
    token = get_settings().BOT_TOKEN
    url = f"{_TG_API}/bot{token}/getFile?file_id={urllib.parse.quote(file_id)}"
    req = urllib.request.Request(url, headers={"User-Agent": "eduquest"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _telegram_file_stream(path: str):
    """Stream the file bytes from Telegram without ever leaking the bot token."""
    token = get_settings().BOT_TOKEN
    url = f"{_TG_API}/file/bot{token}/{urllib.parse.quote(path)}"
    req = urllib.request.Request(url, headers={"User-Agent": "eduquest"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        while chunk := resp.read(65536):
            yield chunk


@router.get("/subjects", response_model=list[SubjectWithLessons])
def list_subjects(
    db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> list[SubjectWithLessons]:
    grade = require_grade(db, user)  # 409 -> grade onboarding
    out: list[SubjectWithLessons] = []
    subjects = db.scalars(
        select(Subject)
        .where(Subject.grade_id == grade.id, Subject.is_published.is_(True))
        .order_by(Subject.order_index)
    ).all()
    for subject in subjects:
        lessons = db.scalars(
            select(Lesson)
            .where(Lesson.subject_id == subject.id, Lesson.is_published.is_(True))
            .order_by(Lesson.level_order)
        ).all()
        summaries = []
        for lesson in lessons:
            prog = db.scalar(
                select(LessonProgress).where(
                    LessonProgress.user_id == user.id, LessonProgress.lesson_id == lesson.id
                )
            )
            summaries.append(
                LessonSummary(
                    id=lesson.id,
                    title=lesson.title,
                    level_order=lesson.level_order,
                    is_published=True,
                    viewed=bool(prog and prog.lesson_viewed),
                    passed=bool(prog and prog.passed),
                    unlocked=is_lesson_unlocked(db, user.id, lesson),
                )
            )
        out.append(
            SubjectWithLessons(
                id=subject.id, name=subject.name, slug=subject.slug,
                emoji=subject.emoji, lessons=summaries,
            )
        )
    return out


def _accessible_lesson(db: Session, user: User, lesson_id: int) -> Lesson:
    """Published lesson that also belongs to the pupil's grade (else 404/409/403)."""
    lesson = db.get(Lesson, lesson_id)
    if lesson is None or not lesson.is_published:
        raise _NOT_FOUND
    assert_lesson_in_grade(db, user, lesson)
    return lesson


@router.get("/lessons/{lesson_id}", response_model=LessonDetail)
def get_lesson(
    lesson_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> LessonDetail:
    lesson = _accessible_lesson(db, user, lesson_id)
    if not is_lesson_unlocked(db, user.id, lesson):
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Avval oldingi bosqichni tugating")
    prog = get_progress(db, user.id, lesson.id)
    return LessonDetail(
        id=lesson.id,
        subject_name=lesson.subject.name,
        title=lesson.title,
        explanation=lesson.explanation,
        video_url=lesson.video_url,
        level_order=lesson.level_order,
        stars_reward=lesson.stars_reward,
        pass_threshold_percent=lesson.pass_threshold_percent,
        materials=[MaterialOut.model_validate(m) for m in lesson.materials],
        viewed=prog.lesson_viewed,
        passed=prog.passed,
    )


@router.post("/lessons/{lesson_id}/viewed")
def mark_lesson_viewed(
    lesson_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> dict:
    """Called when the pupil finishes reading/watching, before the quiz."""
    lesson = _accessible_lesson(db, user, lesson_id)
    if not is_lesson_unlocked(db, user.id, lesson):
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Bosqich ochilmagan")
    streaks.touch(db, user)
    prog = get_progress(db, user.id, lesson.id)
    granted = False
    new_ach = []
    if not prog.lesson_viewed:
        prog.lesson_viewed = True
        from app import gamification  # local import to avoid cycle

        granted = gamification.add_stars(
            db, user.id, gamification.LESSON_VIEWED_STARS,
            gamification.REASON_LESSON_VIEWED, lesson.id,
        )
        db.flush()
        new_ach = gamification.evaluate_achievements(db, user)
    db.commit()
    return {
        "ok": True,
        "stars_granted": granted,
        "new_achievements": [a.code for a in new_ach],
        "new_achievement_titles": [a.title for a in new_ach],
    }


@router.get("/lessons/{lesson_id}/quiz", response_model=QuizOut)
def get_quiz(
    lesson_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> QuizOut:
    lesson = _accessible_lesson(db, user, lesson_id)
    if not is_lesson_unlocked(db, user.id, lesson):
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Bosqich ochilmagan")
    questions = []
    for q in lesson.questions:
        options = list(q.options)
        prompts: list[MatchPromptOut] = []
        if q.kind == "matching":
            # Matching right-hand choices are shuffled (stable per question) so
            # the admin order never gives the answer away.
            random.Random(q.id).shuffle(options)
            prompts = [MatchPromptOut(id=p.id, text=p.text) for p in q.prompts]
        questions.append(
            QuizQuestionOut(
                id=q.id,
                text=q.text,
                kind=q.kind,
                image_url=q.image_url,
                options=[QuizOptionOut(id=o.id, text=o.text) for o in options],
                prompts=prompts,
            )
        )
    if not questions:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Bu darsda test hali yo'q")
    # NOTE: correct answers (is_correct) are NEVER sent to the frontend.
    return QuizOut(
        lesson_id=lesson.id,
        lesson_title=lesson.title,
        pass_threshold_percent=lesson.pass_threshold_percent,
        questions=questions,
    )


_MEDIA_TYPES = {
    "pdf": "application/pdf",
    "mp4": "video/mp4",
    "mov": "video/quicktime",
    "webm": "video/webm",
    "m4v": "video/mp4",
}


@router.get("/materials/{material_id}/file")
def material_file(
    material_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> StreamingResponse:
    """Serve an uploaded video/PDF file. The pupil must be allowed to open the
    lesson (grade scoping, publishing). The bot token never reaches the client
    — we stream Telegram's bytes through the backend."""
    material = db.get(LessonMaterial, material_id)
    if material is None or not material.file_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Fayl topilmadi")
    _accessible_lesson(db, user, material.lesson_id)  # 403 wrong grade / 404 hidden
    try:
        info = _telegram_get_file(material.file_id)
    except Exception:  # network / Telegram outage
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, detail="Faylni olishda xatolik")
    if not info.get("ok"):
        description = str(info.get("description", "")).lower()
        if "too big" in description:
            raise HTTPException(
                status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail="Fayl juda katta — uni Telegram bot orqali oling.",
            )
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, detail="Faylni olishda xatolik")
    path = info["result"]["file_path"]
    filename = (material.file_name or path.rsplit("/", 1)[-1]).replace('"', "").replace("\n", "").replace("\r", "")
    ext = (filename.rsplit(".", 1)[-1] if "." in filename else "").lower()
    media_type = _MEDIA_TYPES.get(ext, "application/octet-stream")
    return StreamingResponse(
        _telegram_file_stream(path),
        media_type=media_type,
        headers={"Content-Disposition": f'inline; filename="{filename}"'},
    )
