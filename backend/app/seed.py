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


# ---------------------------------------------------------------------------
# Sample content for grades 2..4 (age-appropriate Uzbek curriculum snippets).
# Shape: grade_no -> [(subject name, slug, emoji, [ (lesson title, explanation,
#        [ (question text, options, correct option index) ]) ]) ]
# Grades 5..11 stay empty until the admin panel fills them with real content.
# ---------------------------------------------------------------------------
GRADES_2_4: dict[int, list[tuple[str, str, str, list[tuple[str, str, list[tuple[str, list[str], int]]]]]]] = {
    2: [
        (
            "Matematika", "matematika", "📐",
            [
                (
                    "100 ichida qo'shish va ayirish",
                    "Ikki xonali sonlarda ham xuddi bir xonali kabi ishlaymiz:\n\n"
                    "20 + 30 = 50 (o'nliklarni qo'shamiz: 2 + 3 = 5)\n"
                    "70 − 40 = 30 (7 o'nlikdan 4 o'nlikni olamiz)\n\n"
                    "Agar birlar yetishmasa, o'nlikdan \"qarzga\" olamiz: 32 − 5 → 32 dan 2 ni olsak 30, "
                    "yana 3 ni olsak 27. Demak 32 − 5 = 27!",
                    [
                        ("30 + 40 nechchi?", ["60", "70", "80"], 1),
                        ("80 − 30 nechchi?", ["40", "50", "60"], 1),
                        ("45 + 5 nechchi?", ["40", "50", "55"], 1),
                    ],
                ),
                (
                    "Ko'paytirish nima?",
                    "Ko'paytirish — bir xil sonni tez-tez qo'shishning qisqa yo'li!\n\n"
                    "2 + 2 + 2 = 6 → buni 2 × 3 = 6 deb yozamiz.\n"
                    "5 + 5 + 5 = 15 → 5 × 3 = 15.\n\n"
                    "\"×\" belgisi \"marta\" degani: 4 × 2 — \"4 ni 2 marta olish\".",
                    [
                        ("2 × 4 nechchi?", ["6", "8", "10"], 1),
                        ("5 × 3 nechchi?", ["10", "15", "20"], 1),
                        ("3 + 3 + 3 qisqa yozuvda?", ["3 × 3", "3 × 2", "9 × 1"], 0),
                    ],
                ),
                (
                    "Soat va vaqt",
                    "Soatda ikki milliq bor: qisqasi — soatni, uzuni — daqiqani ko'rsatadi.\n\n"
                    "1 soat = 60 daqiqa.\n"
                    "Kun = 24 soat. Tong, kunduz, kech va tunda bo'linadi.\n\n"
                    "Soat 3 ni ko'rsatsa, maktabdan chiqish vaqti kelgan demak! 🕒",
                    [
                        ("1 soatda nechchi daqiqa bor?", ["30", "50", "60"], 2),
                        ("Kunda nechchi soat bor?", ["12", "24", "48"], 1),
                        ("Soatning uzun milliqi nimani ko'rsatadi?", ["soatni", "daqiqani", "kunni"], 1),
                    ],
                ),
            ],
        ),
        (
            "Ona tili", "ona-tili", "📖",
            [
                (
                    "Bo'g'inlar",
                    "So'zlar bo'g'inlarga bo'linadi. Har bir bo'g'inda kamida bitta unli tovush bo'ladi!\n\n"
                    "KITOB → KI-TOB (2 bo'g'in)\n"
                    "MAKTAB → MAK-TAB (2 bo'g'in)\n"
                    "ANOR → A-NOR (2 bo'g'in)\n\n"
                    "Qo'lingni jag'ingga qo'yib gapirib ko'r — jag' har bir bo'ginda pastga tushadi!",
                    [
                        ("\"maktab\" so'zida nechta bo'g'in bor?", ["1", "2", "3"], 1),
                        ("\"olma\" so'zi qanday bo'g'inlanadi?", ["ol-ma", "o-lma", "olm-a"], 0),
                        ("\"dars\" so'zida nechta bo'g'in bor?", ["1", "2", "3"], 0),
                    ],
                ),
                (
                    "Yakka va ko'plik",
                    "Bitta narsa — YAKKA: olma, kitob, dost.\n"
                    "Bir nechta narsa — KO'PLIK: olmalar, kitoblar, do'stlar.\n\n"
                    "O'zbek tilida ko'plikda \"-lar\" qo'shimchasi ishlatiladi:\n"
                    "kitob → kitoblar, maktab → maktablar.\n\n"
                    "Diqqat: son bilan kelganda ham ko'plik aytiladi: \"3 ta olma\" (olmalar emas).",
                    [
                        ("\"daraxt\" ning ko'pligi?", ["daraxtlar", "daraxtlar", "daraxtsiz"], 0),
                        ("Qaysi so'z yakka?", ["kitoblar", "kitob", "dasturlar"], 1),
                        ("\"5 ta ... olma\" — qaysi to'g'ri?", ["olmalar", "olma", "olmalarni"], 1),
                    ],
                ),
            ],
        ),
    ],
    3: [
        (
            "Matematika", "matematika", "📐",
            [
                (
                    "Ko'paytirish jadvali",
                    "Ko'paytirish jadvalini yodlasang — barcha masalalar osonlashadi!\n\n"
                    "2 ga: 2, 4, 6, 8, 10, 12, 14, 16, 18 (har safar 2 qo'shiladi)\n"
                    "5 ga: 5, 10, 15, 20, 25... (oxiri 0 yoki 5 bo'ladi)\n"
                    "10 ga: sonning ortiga 0 qo'shasang bo'ldi: 7 × 10 = 70 🎉",
                    [
                        ("6 × 5 nechchi?", ["25", "30", "35"], 1),
                        ("7 × 2 nechchi?", ["12", "14", "16"], 1),
                        ("9 × 10 nechchi?", ["90", "91", "19"], 0),
                    ],
                ),
                (
                    "Bo'lish — ko'paytirishning teskarisi",
                    "Bo'lish — biror narsani teng bo'lish degani.\n\n"
                    "12 ta olmani 3 do'stga teng bo'lsak: 12 : 3 = 4 (har biriga 4 tadan).\n"
                    "Tekshirish: 4 × 3 = 12 ✅\n\n"
                    "Ko'paytirishni bilsang — bo'lishni ham bilasan!",
                    [
                        ("15 : 3 nechchi?", ["3", "5", "6"], 1),
                        ("20 : 5 nechchi?", ["4", "5", "10"], 0),
                        ("18 : 2 nechchi?", ["8", "9", "10"], 1),
                    ],
                ),
                (
                    "Masalalar yechish",
                    "Masala yechishning 4 qadami:\n\n"
                    "1️⃣ O'qi — nima ma'lum, nima nomalum?\n"
                    "2️⃣ Reja tuz — qaysi amal kerak?\n"
                    "3️⃣ Hisobla\n"
                    "4️⃣ Tekshir — javob mantiqiymi?\n\n"
                    "Masalan: 3 qutida 4 tadan qalam bor. Jami? 3 × 4 = 12 qalam. ✏️",
                    [
                        ("2 xonada 5 tadan stul bor. Jami nechchi stul?", ["7", "10", "12"], 1),
                        ("15 ta shirini 5 bolaga teng bo'lishdi. Har biriga?", ["3", "4", "5"], 0),
                        ("Anvar 8 ta olma sotib oldi, 3 tasini yedi. Qancha qoldi?", ["5", "6", "11"], 0),
                    ],
                ),
            ],
        ),
        (
            "Ona tili", "ona-tili", "📖",
            [
                (
                    "Ot so'z turkumi",
                    "OT — narsalarning nomidir. Otga \"kim?\" yoki \"nima?\" deb savol beramiz.\n\n"
                    "Bola KIM? ✅ (ot)\n"
                    "Kitob NIMA? ✅ (ot)\n"
                    "Yugurish — harakat, bu ot emas!\n\n"
                    "Otlar Jonli (odam, hayvon, o'simlik) va Jonsiz (mehmon, stol, suv) bo'ladi.",
                    [
                        ("Qaysi so'z ot?", ["chiroyli", "darakht", "yugurdi"], 1),
                        ("Otgaga qanday savol beriladi?", ["qanday?", "kim? nima?", "qachon?"], 1),
                        ("\"O'qituvchi\" — qaysi ot?", ["jonli", "jonsiz", "harakat"], 0),
                    ],
                ),
                (
                    "Sifat so'z turkumi",
                    "SIFAT — narsaning rangi, shakli, ta'mi va holatini bildiradi.\n"
                    "Sifatga \"qanday?\" degan savol beriladi.\n\n"
                    "Ko'k osmon (qanday? — ko'k) 🌌\n"
                    "Shirin olma (qanday? — shirin) 🍎\n"
                    "Baland tog' (qanday? — baland) ⛰️",
                    [
                        ("\"chiroyli gul\" da qaysi so'z sifat?", ["gul", "chiroyli", "ikkalasi"], 1),
                        ("Sifatga qanday savol beriladi?", ["kim?", "nima?", "qanday?"], 2),
                        ("Qaysi so'z sifat?", ["tez", "kosha", "yugurish"], 0),
                    ],
                ),
            ],
        ),
    ],
    4: [
        (
            "Matematika", "matematika", "📐",
            [
                (
                    "Ko'p xonali sonlar",
                    "4 xonali sonlarni o'qimni o'rganamiz: 3 572\n\n"
                    "3 — mingliklar | 5 — yuzliklar | 7 — o'nliklar | 2 — birlar\n\n"
                    "3 572 = 3000 + 500 + 70 + 2 — \"uch ming besh yuz yetti yil ikki\".\n"
                    "Sonlarni xonalariga ajratib yozish — katta yordamchi! 🧠",
                    [
                        ("4 026 sonida nechta yuzlik bor?", ["2", "0", "4"], 1),
                        ("3 ming + 5 yuz = ?", ["305", "3500", "350"], 1),
                        ("\"2 ming 1 yuz 5\" raqamda?", ["215", "2105", "2015"], 1),
                    ],
                ),
                (
                    "Kasrlar bilan tanishuv",
                    "Pitsani 4 teng bo'lakka bo'ldik. 1 bo'lak olding — sen pitsaning 1/4 qismini olding! 🍕\n\n"
                    "Kasr ikki qismdan: SONURATCH (yuqorida) va MAHRACH (pastda).\n"
                    "1/2 — birdan ikki bo'lakdan biri (YARIM).\n"
                    "3/4 — to'rt bo'lakdan uchta.\n\n"
                    "Chizma chizib ko'rsang — hamma narsa tushunarli bo'ladi!",
                    [
                        ("Olmani 2 teng qismga bo'lsak, 1 qismi — ?", ["1/2", "2/1", "1/3"], 0),
                        ("3/4 kasrda mahrach nechchi?", ["3", "4", "7"], 1),
                        ("Qaysi kasr katta: 1/2 yoki 1/4?", ["1/2", "1/4", "teng"], 0),
                    ],
                ),
                (
                    "Perimetr va maydon",
                    "PERIMETR — shaklning tashqi chegarasi uzunligi. Barcha tomonlarni qo'shasan.\n"
                    "To'g'ri burchakli uchburchak... emas, to'rtburchak: a + b + a + b.\n\n"
                    "MAYDON — shakl ichidagi joy. To'rtburchakda: a × b.\n\n"
                    "Xona 5 m va 3 m: perimetr = 16 m, maydon = 15 m² 📏",
                    [
                        ("Tomoni 4 sm bo'lgan kvadrat perimetri?", ["8", "16", "20"], 1),
                        ("5 m × 2 m to'rtburchak maydoni?", ["7 m²", "10 m²", "14 m²"], 1),
                        ("Perimetr nimani o'lchaydi?", ["ichki joy", "chegara uzunligi", "og'irlik"], 1),
                    ],
                ),
            ],
        ),
        (
            "Ona tili", "ona-tili", "📖",
            [
                (
                    "Fe'l so'z turkumi",
                    "FE'L — harakat, ish-harakatni bildiradi. \"Nima qildi?\" savoliga javob beradi.\n\n"
                    "Bola O'QIDI 📖 | Qush UCHDI 🐦 | Oy YORIDI 🌙\n\n"
                    "Fe'llar zamonga bo'linadi:\n"
                    "o'tgan zamon (-di): yozdi\n"
                    "hozirgi zamon (-moqda): yozmoqda\n"
                    "kelasi zamon (-adi): yozadi",
                    [
                        ("Qaysi so'z fe'l?", ["kitob", "sekindi", "yugurdi"], 2),
                        ("\"U qo'shiq aytmoqda\" — qaysi zamon?", ["o'tgan", "hozirgi", "kelasi"], 1),
                        ("Fe'lga qanday savol beriladi?", ["qanday?", "kim?", "nima qildi?"], 2),
                    ],
                ),
                (
                    "Gapning bosh a'zolari",
                    "Har bir gapda ikki BOSH a'zo bor:\n\n"
                    "EGA — kim haqida gap ketayotgan (kim? nima?)\n"
                    "KO'LLIK — nima qildi? (nega? qachon?)\n\n"
                    "\"Salima kitob o'qidi.\" → Salima (ega) o'qidi (kolluk).\n"
                    "Ega odatda ot, kolluk fe'l bo'ladi!",
                    [
                        ("\"Bola bog'da o'ynadi\" — gapning ega?", ["bog'da", "bola", "o'ynadi"], 1),
                        ("Kolluk nimani bildiradi?", ["kimni", "ish-harakatni", "joyini"], 1),
                        ("\"Quyosh chiqdi\" — kolluk qaysi?", ["quyosh", "chiqdi", "yo'q"], 1),
                    ],
                ),
            ],
        ),
    ],
}


def _ensure_grade_content(db: Session, grades: dict[str, Grade]) -> bool:
    """Add sample subjects/lessons/quizzes for grades 2..4 (idempotent).

    Content is written per grade with grade-scoped slugs ("matematika-2"),
    because Subject.slug is globally unique. Re-running never duplicates:
    each subject is skipped when its slug already exists.
    """
    created = False
    for grade_no, subjects in GRADES_2_4.items():
        grade = grades[f"{grade_no}-sinf"]
        for s_idx, (s_name, s_slug, s_emoji, lessons) in enumerate(subjects, start=1):
            slug = f"{s_slug}-{grade_no}"
            if db.scalar(select(Subject).where(Subject.slug == slug)) is not None:
                continue
            subject = Subject(
                grade_id=grade.id, name=s_name, slug=slug, emoji=s_emoji,
                order_index=s_idx,
            )
            db.add(subject)
            db.flush()
            for l_order, (title, explanation, questions) in enumerate(lessons, start=1):
                lesson = Lesson(
                    subject_id=subject.id, title=title, level_order=l_order,
                    explanation=explanation, stars_reward=5,
                    pass_threshold_percent=60,
                )
                db.add(lesson)
                db.flush()
                for q_order, (text, opts, correct) in enumerate(questions, start=1):
                    _add_question(db, lesson, q_order, text, opts, correct)
            created = True
    return created


def seed(db: Session) -> bool:
    """Ensure grades 1..11 + achievements; create sample content once.

    Returns True only when new sample content was inserted this run.
    """
    _ensure_achievements(db)
    grades = _ensure_grades(db)
    db.flush()

    inserted = False

    # ---- 1-sinf sample content (original demo) ----
    if db.scalar(select(Subject).where(Subject.slug == "matematika")) is None:
        _seed_grade1(db, grades)
        inserted = True

    # ---- 2..4-sinf sample content ----
    if _ensure_grade_content(db, grades):
        inserted = True

    db.commit()
    return inserted


def _seed_grade1(db: Session, grades: dict[str, Grade]) -> None:
    """The original 1-sinf demonstration content (kept as-is)."""
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


def main() -> None:
    Base.metadata.create_all(engine)  # dev convenience; Alembic owns prod schema
    with SessionLocal() as db:
        created = seed(db)
        print("Kontent qo'shildi ✅" if created else "Allaqachon seedlangan, o'tkazib yuborildi ⏭")


if __name__ == "__main__":
    main()
