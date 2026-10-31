"""app/routers/certificates.py — course completion certificates."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import HTMLResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import certificates as certs
from app.db import get_db
from app.grades import require_grade
from app.models import Certificate, Subject, User
from app.schemas import (
    CertificateOut,
    CertificateVerifyOut,
    EligibleCertificateOut,
)
from app.security import get_current_user

router = APIRouter(prefix="/api", tags=["certificates"])


def _out(cert: Certificate) -> CertificateOut:
    return CertificateOut(
        code=cert.code,
        subject_id=cert.subject_id,
        subject_name=cert.subject_name,
        grade_name=cert.grade_name,
        pupil_name=cert.pupil_name,
        score_percent=cert.score_percent,
        stars=cert.stars,
        issued_at=cert.issued_at,
        verify_url=certs.verify_url(cert.code),
    )


@router.get("/certificates", response_model=list[CertificateOut])
def my_certificates(
    db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> list[CertificateOut]:
    """Certificates already issued to this pupil."""
    rows = db.scalars(
        select(Certificate)
        .where(Certificate.user_id == user.id)
        .order_by(Certificate.issued_at.desc())
    ).all()
    return [_out(cert) for cert in rows]


@router.get("/certificates/eligible", response_model=list[EligibleCertificateOut])
def eligible_certificates(
    db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> list[EligibleCertificateOut]:
    """Finished courses of the pupil's grade (and any certificate issued)."""
    grade = require_grade(db, user)
    issued = {
        cert.subject_id: cert
        for cert in db.scalars(
            select(Certificate).where(Certificate.user_id == user.id)
        ).all()
    }
    subjects = db.scalars(
        select(Subject)
        .where(Subject.grade_id == grade.id, Subject.is_published.is_(True))
        .order_by(Subject.order_index.asc(), Subject.id.asc())
    ).all()
    result: list[EligibleCertificateOut] = []
    for subject in subjects:
        finished = certs.completed_course(db, user.id, subject)
        if finished is None:
            continue
        cert = issued.get(subject.id)
        result.append(
            EligibleCertificateOut(
                subject_id=subject.id,
                subject_name=subject.name,
                emoji=subject.emoji,
                total_lessons=finished["total_lessons"],
                score_percent=cert.score_percent if cert else finished["score_percent"],
                certificate=_out(cert) if cert else None,
            )
        )
    return result


@router.get("/certificates/{subject_id}/pdf")
def certificate_pdf(
    subject_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Response:
    """Issue (once) and download the certificate PDF for a finished course."""
    # An already issued certificate always remains downloadable — even after a
    # grade change or if the course was later archived. It belongs to the pupil.
    existing = db.scalar(
        select(Certificate).where(
            Certificate.user_id == user.id, Certificate.subject_id == subject_id
        )
    )
    if existing is not None:
        return _pdf_response(existing)

    grade = require_grade(db, user)
    subject = db.get(Subject, subject_id)
    not_eligible = HTTPException(
        status.HTTP_404_NOT_FOUND,
        detail={
            "error": "not_eligible",
            "message_uz": "Sertifikat uchun kursning barcha darslarini tugating.",
        },
    )
    if subject is None or not subject.is_published or subject.grade_id != grade.id:
        raise not_eligible
    finished = certs.completed_course(db, user.id, subject)
    if finished is None:
        raise not_eligible

    cert = certs.get_or_issue(db, user, grade, subject, finished)
    return _pdf_response(cert)


def _pdf_response(cert: Certificate) -> Response:
    pdf = certs.build_pdf(cert)
    filename = f"EduQuest-sertifikat-{cert.code}.pdf"
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/certificates/verify/{code}")
def verify_certificate(
    code: str,
    request: Request,
    db: Session = Depends(get_db),
):
    """Public verification target of the QR code (HTML for phones, JSON for API)."""
    cert = db.scalar(select(Certificate).where(Certificate.code == code))
    wants_html = "text/html" in request.headers.get("accept", "")
    if cert is None:
        if wants_html:
            return HTMLResponse(
                "<h1 style='font-family:Arial;color:#0F2B5B'>Sertifikat topilmadi</h1>",
                status_code=404,
            )
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail={"error": "certificate_not_found", "message_uz": "Sertifikat topilmadi."},
        )
    if wants_html:
        return HTMLResponse(certs.verify_page(cert))
    return CertificateVerifyOut(
        valid=True,
        code=cert.code,
        pupil_name=cert.pupil_name,
        grade_name=cert.grade_name,
        subject_name=cert.subject_name,
        score_percent=cert.score_percent,
        stars=cert.stars,
        issued_at=cert.issued_at,
    )
