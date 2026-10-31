"""app/certificates.py — course completion certificates.

A subject counts as completed when EVERY published lesson in it is passed.
The certificate is issued once per pupil + subject, stores a name snapshot and
carries an unguessable code whose verification URL is printed as a QR code on
the PDF (and served as a small public HTML page).
"""
from __future__ import annotations

import html
import io
import math
import secrets

import qrcode
from reportlab.lib.colors import HexColor
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas as pdf_canvas
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import gamification
from app.config import get_settings
from app.models import Certificate, Grade, LessonProgress, Subject, User

NAVY = HexColor("#0F2B5B")
GOLD = HexColor("#C9A227")
LIGHT_GOLD = HexColor("#E8CF8A")
CREAM = HexColor("#FBF7EA")
INK = HexColor("#1F2A44")
MUTED = HexColor("#6B7280")
WHITE = HexColor("#FFFFFF")


def verify_url(code: str) -> str:
    base = get_settings().PUBLIC_BASE_URL.rstrip("/")
    return f"{base}/api/certificates/verify/{code}"


def completed_course(db: Session, user_id: int, subject: Subject) -> dict | None:
    """Return {total_lessons, score_percent} when the course is finished."""
    lessons = [lesson for lesson in subject.lessons if lesson.is_published]
    if not lessons:
        return None
    progress = {
        p.lesson_id: p
        for p in db.scalars(
            select(LessonProgress).where(
                LessonProgress.user_id == user_id,
                LessonProgress.lesson_id.in_([lesson.id for lesson in lessons]),
            )
        ).all()
    }
    scores: list[int] = []
    for lesson in lessons:
        entry = progress.get(lesson.id)
        if entry is None or not entry.passed:
            return None
        scores.append(entry.best_score_percent)
    return {
        "total_lessons": len(lessons),
        "score_percent": round(sum(scores) / len(scores)),
    }


def get_or_issue(
    db: Session, user: User, grade: Grade, subject: Subject, result: dict
) -> Certificate:
    """Return the existing certificate or issue a new one (idempotent)."""
    cert = db.scalar(
        select(Certificate).where(
            Certificate.user_id == user.id, Certificate.subject_id == subject.id
        )
    )
    if cert is not None:
        return cert

    cert = Certificate(
        user_id=user.id,
        subject_id=subject.id,
        code=secrets.token_urlsafe(9),
        pupil_name=user.first_name or "O‘quvchi",
        grade_name=grade.name,
        subject_name=subject.name,
        score_percent=result["score_percent"],
        stars=gamification.stars_total(db, user.id),
    )
    db.add(cert)
    try:
        db.commit()
    except IntegrityError:
        # Two parallel downloads raced; the unique index decides.
        db.rollback()
        cert = db.scalar(
            select(Certificate).where(
                Certificate.user_id == user.id,
                Certificate.subject_id == subject.id,
            )
        )
        if cert is None:  # pragma: no cover - defensive
            raise
    return cert


# ---------------------------------------------------------------------------
# PDF drawing
# ---------------------------------------------------------------------------
def _centered(
    c: pdf_canvas.Canvas,
    text: str,
    x: float,
    y: float,
    font: str,
    size: float,
    color,
    spacing: float = 0,
) -> None:
    c.setFillColor(color)
    c.setFont(font, size)
    if spacing <= 0:
        c.drawCentredString(x, y, text)
        return
    width = stringWidth(text, font, size) + spacing * (len(text) - 1)
    t = c.beginText(x - width / 2, y)
    t.setFont(font, size)
    t.setCharSpace(spacing)
    t.setFillColor(color)
    t.textOut(text)
    t.setCharSpace(0)  # PDF text state persists after ET — reset or every later string is spaced
    c.drawText(t)


def _fit(c: pdf_canvas.Canvas, text: str, font: str, size: float, max_width: float) -> float:
    while size > 6 and stringWidth(text, font, size) > max_width:
        size -= 0.5
    return size


def _wrap_pixels(
    text: str, font: str, size: float, max_width: float
) -> list[str]:
    """Wrap by measured width, not by character count (PDF fonts differ)."""
    lines: list[str] = []
    current = ""
    for word in text.split():
        candidate = f"{current} {word}".strip()
        if current and stringWidth(candidate, font, size) > max_width:
            lines.append(current)
            current = word
        else:
            current = candidate
    if current:
        lines.append(current)
    return lines


def _star(c: pdf_canvas.Canvas, cx: float, cy: float, outer: float, inner: float) -> None:
    path = c.beginPath()
    for i in range(10):
        angle = math.pi / 2 + i * math.pi / 5
        radius = outer if i % 2 == 0 else inner
        x = cx + radius * math.cos(angle)
        y = cy + radius * math.sin(angle)
        if i == 0:
            path.moveTo(x, y)
        else:
            path.lineTo(x, y)
    path.close()
    c.drawPath(path, stroke=0, fill=1)


def _corners(c: pdf_canvas.Canvas, w: float, h: float) -> None:
    c.setStrokeColor(GOLD)
    c.setLineWidth(1.1)
    for x, y, sx, sy in (
        (50, 50, 1, 1),
        (w - 50, 50, -1, 1),
        (50, h - 50, 1, -1),
        (w - 50, h - 50, -1, -1),
    ):
        c.line(x, y, x + sx * 34, y)
        c.line(x, y, x, y + sy * 34)
        c.line(x + sx * 10, y + sy * 10, x + sx * 44, y + sy * 10)
        c.line(x + sx * 10, y + sy * 10, x + sx * 10, y + sy * 44)
        c.setFillColor(NAVY)
        c.circle(x + sx * 18, y + sy * 18, 2.2, stroke=0, fill=1)


def _metric_box(
    c: pdf_canvas.Canvas, x: float, y: float, w: float, h: float, label: str, value: str
) -> None:
    c.setFillColor(NAVY)
    c.roundRect(x, y, w, h, 8, stroke=0, fill=1)
    c.setStrokeColor(GOLD)
    c.setLineWidth(1.2)
    c.roundRect(x, y, w, h, 8, stroke=1, fill=0)
    c.setFillColor(LIGHT_GOLD)
    c.setFont("Helvetica-Bold", 8)
    c.drawCentredString(x + w / 2, y + h - 17, label.upper())
    size = _fit(c, value, "Helvetica-Bold", 16, w - 24)
    _centered(c, value, x + w / 2, y + 17, "Helvetica-Bold", size, WHITE)


def _seal(c: pdf_canvas.Canvas, cx: float, cy: float) -> None:
    c.setFillColor(GOLD)
    c.circle(cx, cy, 44, stroke=0, fill=1)
    c.setFillColor(CREAM)
    c.circle(cx, cy, 38, stroke=0, fill=1)
    c.setStrokeColor(NAVY)
    c.setLineWidth(1.4)
    c.circle(cx, cy, 38, stroke=1, fill=0)
    c.setFillColor(GOLD)
    _star(c, cx, cy + 3, 20, 8)
    c.setFillColor(NAVY)
    c.setFont("Helvetica-Bold", 6.5)
    c.drawCentredString(cx, cy - 27, "EDUQUEST")


def build_pdf(cert: Certificate) -> bytes:
    """Render the certificate as an A4-landscape PDF (bytes)."""
    buf = io.BytesIO()
    page_w, page_h = landscape(A4)
    c = pdf_canvas.Canvas(buf, pagesize=(page_w, page_h))
    c.setTitle(f"EduQuest sertifikat — {cert.subject_name}")
    c.setAuthor("EduQuest")

    c.setFillColor(CREAM)
    c.rect(0, 0, page_w, page_h, stroke=0, fill=1)
    c.setStrokeColor(NAVY)
    c.setLineWidth(6)
    c.rect(20, 20, page_w - 40, page_h - 40)
    c.setStrokeColor(GOLD)
    c.setLineWidth(1.3)
    c.rect(30, 30, page_w - 60, page_h - 60)
    c.setStrokeColor(NAVY)
    c.setLineWidth(0.6)
    c.rect(36, 36, page_w - 72, page_h - 72)
    _corners(c, page_w, page_h)

    # Logo badge
    c.setFillColor(NAVY)
    c.circle(page_w / 2, page_h - 72, 20, stroke=0, fill=1)
    c.setStrokeColor(GOLD)
    c.setLineWidth(1.2)
    c.circle(page_w / 2, page_h - 72, 20, stroke=1, fill=0)
    _centered(c, "E", page_w / 2, page_h - 79, "Times-Bold", 24, GOLD)
    _centered(c, "E D U Q U E S T", page_w / 2, page_h - 102, "Helvetica-Bold", 8, NAVY)

    # Title
    _centered(c, "SERTIFIKAT", page_w / 2, page_h - 150, "Times-Bold", 38, GOLD, 4)
    _centered(
        c,
        "Kursni muvaffaqiyatli tamomlagani uchun",
        page_w / 2,
        page_h - 174,
        "Times-Italic",
        13,
        NAVY,
    )

    # Pupil name with gold flourish
    name_size = _fit(c, cert.pupil_name, "Times-Italic", 30, 540)
    _centered(c, cert.pupil_name, page_w / 2, page_h - 236, "Times-Italic", name_size, NAVY)
    name_width = stringWidth(cert.pupil_name, "Times-Italic", name_size)
    c.setStrokeColor(GOLD)
    c.setLineWidth(1.1)
    c.line(
        page_w / 2 - name_width / 2 - 24,
        page_h - 244,
        page_w / 2 + name_width / 2 + 24,
        page_h - 244,
    )

    # Description
    description = (
        f"{cert.grade_name} o‘quvchisi “{cert.subject_name}” kursini muvaffaqiyatli "
        "yakunlaganligi uchun ushbu sertifikat taqdim etiladi."
    )
    description_size = 11.0
    if stringWidth(description, "Helvetica", description_size) > 680:
        description_size = _fit(c, description, "Helvetica", 10.5, 680)
    lines = _wrap_pixels(description, "Helvetica", description_size, 680)[:2]
    for index, line in enumerate(lines):
        _centered(
            c,
            line,
            page_w / 2,
            page_h - 270 - index * 15,
            "Helvetica",
            description_size,
            INK,
        )

    # Three metric boxes
    box_w, box_h, gap = 190, 62, 18
    total = box_w * 3 + gap * 2
    left = (page_w - total) / 2
    top = 205
    _metric_box(c, left, top, box_w, box_h, "Kurs nomi", cert.subject_name)
    _metric_box(
        c, left + box_w + gap, top, box_w, box_h, "Natija", f"{cert.score_percent}%"
    )
    _metric_box(
        c,
        left + (box_w + gap) * 2,
        top,
        box_w,
        box_h,
        "Yulduzlar",
        f"{cert.stars}",
    )

    # Date + code (left)
    issued = cert.issued_at.strftime("%d.%m.%Y")
    c.setFillColor(INK)
    c.setFont("Helvetica-Bold", 9)
    c.drawString(62, 176, f"Berilgan sana: {issued}")
    c.setFillColor(MUTED)
    c.setFont("Helvetica", 7.5)
    c.drawString(62, 164, f"Sertifikat kodi: {cert.code}")

    # QR verification (bottom-left)
    qr = qrcode.QRCode(border=1, box_size=10)
    qr.add_data(verify_url(cert.code))
    qr.make(fit=True)
    image = qr.make_image(fill_color="#0F2B5B", back_color="#FBF7EA").convert("RGB")
    image = image.resize((240, 240))
    c.drawImage(
        ImageReader(image), 62, 66, width=70, height=70, preserveAspectRatio=True, mask="auto"
    )
    c.setFillColor(MUTED)
    c.setFont("Helvetica", 6.5)
    c.drawString(62, 56, "Tekshirish uchun skanerlang")

    # Seal + signature (bottom-right)
    seal_x = page_w - 175
    _seal(c, seal_x, 120)
    c.setStrokeColor(NAVY)
    c.setLineWidth(0.8)
    c.line(seal_x - 66, 78, seal_x + 66, 78)
    _centered(c, "EduQuest jamoasi", seal_x, 66, "Times-Italic", 9, NAVY)

    c.showPage()
    c.save()
    return buf.getvalue()


def verify_page(cert: Certificate) -> str:
    """Small public HTML page shown when the QR code is scanned."""
    issued = cert.issued_at.strftime("%d.%m.%Y")
    rows = [
        ("O‘quvchi", cert.pupil_name),
        ("Sinf", cert.grade_name),
        ("Kurs", cert.subject_name),
        ("Natija", f"{cert.score_percent}%"),
        ("Yulduzlar", f"{cert.stars}"),
        ("Berilgan sana", issued),
        ("Sertifikat kodi", cert.code),
    ]
    table = "".join(
        f'<div class="row"><span>{html.escape(label)}</span>'
        f"<b>{html.escape(value)}</b></div>"
        for label, value in rows
    )
    return f"""<!doctype html>
<html lang="uz">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>EduQuest — sertifikat tekshiruvi</title>
</head>
<body style="margin:0;font-family:Arial,Helvetica,sans-serif;background:#FBF7EA;color:#0F2B5B;">
  <div style="max-width:520px;margin:32px auto;padding:0 16px;">
    <div style="background:#0F2B5B;color:#FBF7EA;border-radius:18px 18px 0 0;padding:22px 24px;">
      <div style="font-size:12px;letter-spacing:2px;color:#E8CF8A;">EDUQUEST</div>
      <h1 style="margin:6px 0 0;font-size:22px;">Sertifikat haqiqiy ✅</h1>
      <p style="margin:6px 0 0;font-size:13px;color:#C9D6EE;">
        Bu hujjat EduQuest platformasi tomonidan berilgan.
      </p>
    </div>
    <div style="background:#fff;border:1px solid #E5D9B8;border-top:0;border-radius:0 0 18px 18px;padding:18px 24px 24px;">
      {table}
    </div>
  </div>
</body>
</html>"""
