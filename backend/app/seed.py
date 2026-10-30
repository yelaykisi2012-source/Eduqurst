"""
app/seed.py — grades 1..11 + demonstration content for 1-sinf (idempotent).

Run from backend/ with venv active:
    python -m app.seed
Grades 1..11 and achievements are always ensured. The sample lessons/quizzes
are created ONLY for 1-sinf (development sample) and only once — re-running is
safe and never duplicates. Grades 2..11 start empty and are filled via the
admin panel (Stage 8), so the content system stays dynamic per grade.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import SessionLocal, Base, engine
from app.models import Achievement, AnswerOption, Grade, Lesson, LessonMaterial, Question, Subject

# Grades 1..11 as stored in the `grades` table ("1-sinf" .. "11-sinf").
GRADE_NAMES: list[tuple[str, int]] = [(f"{n}-sinf", n) for n in range(1, 12)]

ACHIEVEMENTS = [
    ("first_lesson", "Birinchi dars", "Birinchi darsni tugatding!", "🎓", 1),
    ("first_quiz", "Birinchi test", "Birinchi testiyingdan o'tding!", "🧩", 1),
    ("star_10", "10 yulduz", "Jamg'ichiga 10 ta yulduz", "⭐", 10),
    ("star_50", "50 yulduz", "Katta yulduz jonkuyer!", "🌟", 50),
    ("subject_master", "Fan ustasi", "Bir fanning barcha darslarini tugatding", "🏆", 1),
]

MATH_L1_QUESTIONS = [
    ("1 dan 10 gacha sonlarni sanang: 1, 2, 3, ... keyin qaysi son keladi?",
     ["4", "6", "9"], 0),
    ("5 sonidan keyin qaysi son keladi?", ["4", "6", "10"], 1),
    ("Qaysi son eng katta: 3, 7 yoki 5?", ["3", "5", "7"], 2),
    ("2 va 3 ni qo'shsak nechchi chiqadi?", ["5", "6", "4"], 0),
    ("10 dan bir dona olinsa nechta qoladi?", ["8", "9", "10"], 1),
]

MATH_L2_QUESTIONS = [
    ("4 va 8 sonlaridan qaysi biri katta?", ["4", "8", "ular teng"], 1),
    ("6 dan kichik sonni tanlang:", ["9", "6", "3"], 2),
    ("Qaysi juftlik to'g'ri: 5 < 7 yoki 7 < 5?", ["5 < 7", "7 < 5"], 0),
]

MATH_L3_QUESTIONS = [
    ("3 + 4 nechchi?", ["6", "7", "8"], 1),
    ("2 + 2 nechchi?", ["3", "5", "4"], 2),
    ("5 + 5 nechchi?", ["10", "9", "11"], 0),
]

MATH_L4_QUESTIONS = [
    ("7 − 3 nechchi?", ["4", "3", "5"], 0),
    ("9 − 5 nechchi?", ["3", "4", "5"], 1),
    ("6 − 6 nechchi?", ["0", "6", "1"], 0),
]

ENGLISH_QUESTIONS = [
    ("Ingliz alifbosida nechta harf bor?", ["20", "26", "33"], 1),
    ("Ingliz alifbosining BIRINCHI harfi qaysi?", ["A", "B", "Z"], 0),
    ("Ingliz alifbosining OXIRGI harfi qaysi?", ["X", "Y", "Z"], 2),
    ("\"Kitob\" so'zi inglizchada nima?", ["apple", "book", "cat"], 1),
    ("Qaysi so'z \"olma\" degani?", ["orange", "banana", "apple"], 2),
]

UZBEK_QUESTIONS = [
    ("O'zbek alifbosida nechta harf bor (2021-yildagi lotin alifbosi)?", ["26", "29", "32"], 1),
    ("Qaysi so'z unli tovush bilan boshlanadi?", ["kitob", "olma", "maktab"], 1),
    ("\"Ona\" so'zida nechta tovush bor?", ["2", "3", "4"], 1),
    ("Qaysi harf undosh tovushni bildiradi?", ["a", "o", "b"], 2),
    ("\"Olma\" so'zining bo'g'inlari qanday?", ["ol-ma", "o-lma", "olm-a"], 0),
]


def _add_question(db: Session, lesson: Lesson, order: int, text: str,
                  options: list[str], correct_idx: int) -> None:
    q = Question(lesson_id=lesson.id, text=text, kind="single", order_index=order)
    db.add(q)
    db.flush()
    for i, opt_text in enumerate(options):
        feedback = "Ajoyib! 🎉" if i == correct_idx else "Diyonat qil, yana bir marta o'ylab ko'ring 😊"
        db.add(AnswerOption(
            question_id=q.id, text=opt_text, is_correct=(i == correct_idx),
            feedback=feedback, order_index=i,
        ))


def _ensure_achievements(db: Session) -> None:
    existing = {a.code for a in db.scalars(select(Achievement)).all()}
    for code, title, desc, icon, threshold in ACHIEVEMENTS:
        if code not in existing:
            db.add(Achievement(
                code=code, title=title, description=desc, icon=icon, threshold=threshold
            ))


def _ensure_grades(db: Session) -> dict[str, Grade]:
    """Idempotently make sure grades 1..11 exist. Returns name -> Grade."""
    grades = {g.name: g for g in db.scalars(select(Grade)).all()}
    for name, order in GRADE_NAMES:
        if name not in grades:
            grade = Grade(name=name, order_index=order)
            db.add(grade)
            db.flush()
            grades[name] = grade
    return grades


def seed(db: Session) -> bool:
    """Ensure grades 1..11 + achievements; create sample 1-sinf content once.

    Returns True only when new sample content was inserted this run.
    """
    _ensure_achievements(db)
    grades = _ensure_grades(db)
    db.flush()

    # Sample content lives ONLY in 1-sinf; skip if its subjects already exist.
    if db.scalar(select(Subject).where(Subject.slug == "matematika")) is not None:
        db.commit()
        return False

    grade = grades["1-sinf"]

    math = Subject(grade_id=grade.id, name="Matematika", slug="matematika", emoji="📐", order_index=1)
    english = Subject(grade_id=grade.id, name="Ingliz tili", slug="ingliz-tili", emoji="🔤", order_index=2)
    uzbek = Subject(grade_id=grade.id, name="Ona tili", slug="ona-tili", emoji="📖", order_index=3)
    db.add_all([math, english, uzbek])
    db.flush()

    # ---- Matematika: 4 bosqich ----
    l1 = Lesson(subject_id=math.id, title="1 dan 10 gacha sonlar", level_order=1,
                explanation=(
                    "Sonlar bizga har kuni kerak: 5 ta olma, 2 ta do'st, 10 ta barmoq!\n\n"
                    "Keling, 10 gacha sanab chiqamiz:\n"
                    "1 — bitta 🍎\n2 — juftlik 👟\n3 — uch 🚦\n4 — to'rt \n5 — besh ✋\n"
                    "6 — olti 🎲\n7 — yetti 🌈\n8 — sakkiz 🐙\n9 — to'qqiz 🎯\n10 — o'n 🔟\n\n"
                    "Qo'lingizdagi 10 barmoq — eng yaxshi yordamchi! Har bir sonning o'z joyi bor: "
                    "1 dan keyin 2, 2 dan keyin 3 keladi."
                ),
                stars_reward=5, pass_threshold_percent=60)
    l2 = Lesson(subject_id=math.id, title="Sonlarni taqqoslash", level_order=2,
                explanation=(
                    "Ikki sonni solishtiramiz: qaysi biri KATTA?\n\n"
                    "\"<\" belgisi kichiq tomonga ochiladi: 3 < 7 (uch yettidan kichik).\n"
                    "\"=\" tenglikni bildiradi: 5 = 5.\n\n"
                    "Maslahat: sonlarni 1 dan 10 gacha sanang — qaysi biri OLIN chiqsa, u KICHIK!"
                ),
                stars_reward=5, pass_threshold_percent=60)
    l3 = Lesson(subject_id=math.id, title="Qo'shish", level_order=3,
                explanation=(
                    "Qo'shish — ikki narsani birlashtirish.\n\n"
                    "2 ta olma 🍎🍎 + 3 ta olma 🍎🍎🍎 = 5 ta olma!\n"
                    "Belgisi: \"+\" va \"=\"\n\n"
                    "Barmoqlaringizni ishlatib ko'ring: 2 barmoq ko'taring, yana 3 ta qo'shing — 5 ta!"
                ),
                stars_reward=5, pass_threshold_percent=60)
    l4 = Lesson(subject_id=math.id, title="Ayirish", level_order=4,
                explanation=(
                    "Ayirish — biror narsani olib tashlash.\n\n"
                    "5 ta chiroq 💡💡💡💡 dan 2 tasi o'chdi → 3 ta qoldi.\n"
                    "Belgisi: \"−\"\n\n"
                    "5 − 2 = 3. Qolganini sanash orqali tekshiring!"
                ),
                stars_reward=5, pass_threshold_percent=60)
    db.add_all([l1, l2, l3, l4])
    db.flush()

    db.add(LessonMaterial(lesson_id=l1.id, kind="slide", title="Sonlar qatori",
                          content="1 2 3 4 5 6 7 8 9 10 — har kuni shunday tartibda sanang!",
                          order_index=1))

    for order, (text, opts, correct) in enumerate(MATH_L1_QUESTIONS, start=1):
        _add_question(db, l1, order, text, opts, correct)
    for order, (text, opts, correct) in enumerate(MATH_L2_QUESTIONS, start=1):
        _add_question(db, l2, order, text, opts, correct)
    for order, (text, opts, correct) in enumerate(MATH_L3_QUESTIONS, start=1):
        _add_question(db, l3, order, text, opts, correct)
    for order, (text, opts, correct) in enumerate(MATH_L4_QUESTIONS, start=1):
        _add_question(db, l4, order, text, opts, correct)

    # ---- Ingliz tili ----
    en = Lesson(subject_id=english.id, title="Ingliz alifbosi", level_order=1,
                explanation=(
                    "Ingliz tilida 26 ta harf bor! Ular A dan Z gacha tartiblanadi.\n\n"
                    "A B C D E F G H I J K L M N O P Q R S T U V W X Y Z\n\n"
                    "Ba'zi harflar ovoz chiqaradi (unli): A, E, I, O, U — qolganlari undosh.\n"
                    "Har kuni 5 ta harfni tanishing: bugun A, B, C, D, E!"
                ),
                stars_reward=5, pass_threshold_percent=60)
    db.add(en)
    db.flush()
    for order, (text, opts, correct) in enumerate(ENGLISH_QUESTIONS, start=1):
        _add_question(db, en, order, text, opts, correct)

    # ---- Ona tili ----
    uz = Lesson(subject_id=uzbek.id, title="Harflar va tovushlar", level_order=1,
                explanation=(
                    "O'zbek tilida ovozlar ikki xil bo'ladi:\n\n"
                    "🔵 UNLI tovushlar — og'iz ochiq chiqadi: a, o, i, u, e\n"
                    " UNDOSh tovushlar — til, lablar to'siq qiladi: b, k, m, s...\n\n"
                    "So'zlar bo'g'inlarga bo'linadi: OL-MA (2 bo'g'in), KI-TOB (2 bo'g'in).\n"
                    "Bitta unli tovush = bitta bo'g'in, odatda!"
                ),
                stars_reward=5, pass_threshold_percent=60)
    db.add(uz)
    db.flush()
    for order, (text, opts, correct) in enumerate(UZBEK_QUESTIONS, start=1):
        _add_question(db, uz, order, text, opts, correct)

    db.commit()
    return True


def main() -> None:
    Base.metadata.create_all(engine)  # dev convenience; Alembic owns prod schema
    with SessionLocal() as db:
        created = seed(db)
        print("Kontent qo'shildi ✅" if created else "Allaqachon seedlangan, o'tkazib yuborildi ⏭")


if __name__ == "__main__":
    main()
