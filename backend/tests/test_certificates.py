"""Course certificates: eligibility, PDF issue (once), public QR verification."""
from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db import SessionLocal
from app.models import LessonProgress, Subject, User


def _register(client: TestClient, login: str, first_name: str) -> dict:
    resp = client.post(
        "/api/auth/register",
        json={"login": login, "password": "Probe12345", "first_name": first_name},
    )
    assert resp.status_code == 201, resp.text
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


def _pick_grade1(client: TestClient, headers: dict) -> int:
    grades = client.get("/api/grades", headers=headers).json()
    grade = next(g for g in grades if g["name"] == "1-sinf")
    resp = client.post("/api/me/grade", json={"grade_id": grade["id"]}, headers=headers)
    assert resp.status_code == 200, resp.text
    return grade["id"]


def _math(client: TestClient, headers: dict) -> dict:
    subjects = client.get("/api/subjects", headers=headers).json()
    return next(s for s in subjects if s["slug"] == "matematika")


def _pass_all_lessons(login: str, lesson_ids: list[int]) -> None:
    """Mark every published lesson of the course as passed (score varies)."""
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.login == login))
        assert user is not None
        for index, lesson_id in enumerate(lesson_ids):
            db.add(
                LessonProgress(
                    user_id=user.id,
                    lesson_id=lesson_id,
                    lesson_viewed=True,
                    passed=True,
                    best_score_percent=80 + index * 5,  # 80, 85, 90, 95 for 4 lessons
                )
            )
        db.commit()


def test_certificate_requires_full_course_then_issues_once(
    client: TestClient,
):
    headers = _register(client, "cert_probe", "Azizbek")
    _pick_grade1(client, headers)
    math = _math(client, headers)
    lesson_ids = [lesson["id"] for lesson in math["lessons"]]
    assert lesson_ids, "seed must have published lessons for 1-sinf matematika"

    # Nothing is finished yet.
    assert client.get("/api/certificates", headers=headers).json() == []
    assert client.get("/api/certificates/eligible", headers=headers).json() == []
    resp = client.get(
        f"/api/certificates/{math['id']}/pdf", headers=headers
    )
    assert resp.status_code == 404
    assert resp.json()["detail"]["error"] == "not_eligible"

    _pass_all_lessons("cert_probe", lesson_ids)

    eligible = client.get("/api/certificates/eligible", headers=headers).json()
    assert len(eligible) == 1
    course = eligible[0]
    assert course["subject_id"] == math["id"]
    assert course["total_lessons"] == len(lesson_ids)
    assert course["score_percent"] == round(
        sum(80 + index * 5 for index in range(len(lesson_ids))) / len(lesson_ids)
    )
    assert course["certificate"] is None  # not issued until the PDF is requested

    # First download issues the certificate.
    pdf = client.get(f"/api/certificates/{math['id']}/pdf", headers=headers)
    assert pdf.status_code == 200, pdf.text
    assert pdf.headers["content-type"].startswith("application/pdf")
    assert "attachment" in pdf.headers["content-disposition"]
    assert pdf.content.startswith(b"%PDF")
    assert len(pdf.content) > 1000

    issued = client.get("/api/certificates", headers=headers).json()
    assert len(issued) == 1
    cert = issued[0]
    assert cert["subject_id"] == math["id"]
    assert cert["pupil_name"] == "Azizbek"
    assert cert["grade_name"] == "1-sinf"
    assert cert["subject_name"] == "Matematika"
    assert len(cert["code"]) >= 8
    assert cert["verify_url"].endswith(f"/api/certificates/verify/{cert['code']}")

    # Second download is idempotent: same code, still one row.
    again = client.get(f"/api/certificates/{math['id']}/pdf", headers=headers)
    assert again.status_code == 200
    assert client.get("/api/certificates", headers=headers).json() == issued

    # Eligible list now links the issued document.
    eligible = client.get("/api/certificates/eligible", headers=headers).json()
    assert eligible[0]["certificate"]["code"] == cert["code"]

    # Public verification — JSON for API clients.
    verified = client.get(f"/api/certificates/verify/{cert['code']}")
    assert verified.status_code == 200
    body = verified.json()
    assert body["valid"] is True
    assert body["pupil_name"] == "Azizbek"
    assert body["subject_name"] == "Matematika"
    assert body["score_percent"] == cert["score_percent"]

    # Public verification — HTML page for phones scanning the QR.
    page = client.get(
        f"/api/certificates/verify/{cert['code']}", headers={"Accept": "text/html"}
    )
    assert page.status_code == 200
    assert "text/html" in page.headers["content-type"]
    assert "Sertifikat haqiqiy" in page.text
    assert "Azizbek" in page.text

    # Unknown codes are rejected in both formats.
    missing = client.get("/api/certificates/verify/does-not-exist")
    assert missing.status_code == 404
    assert missing.json()["detail"]["error"] == "certificate_not_found"
    missing_html = client.get(
        "/api/certificates/verify/does-not-exist", headers={"Accept": "text/html"}
    )
    assert missing_html.status_code == 404
    assert "Sertifikat topilmadi" in missing_html.text

    # Switching grade must not take an issued certificate away (progress kept).
    grades = client.get("/api/grades", headers=headers).json()
    grade2 = next(g for g in grades if g["name"] == "2-sinf")
    switched = client.post(
        "/api/me/grade", json={"grade_id": grade2["id"]}, headers=headers
    )
    assert switched.status_code == 200, switched.text
    still = client.get(f"/api/certificates/{math['id']}/pdf", headers=headers)
    assert still.status_code == 200
    assert still.content.startswith(b"%PDF")
    assert client.get("/api/certificates", headers=headers).json() == issued


def test_foreign_grade_subject_is_not_eligible(client: TestClient):
    headers = _register(client, "cert_grade", "Gulnora")
    _pick_grade1(client, headers)

    with SessionLocal() as db:
        foreign = db.scalar(
            select(Subject)
            .join(Subject.grade)
            .where(Subject.is_published.is_(True), Subject.grade.has(name="2-sinf"))
            .limit(1)
        )
        assert foreign is not None, "seed must fill 2-sinf"
        foreign_id = foreign.id

    resp = client.get(f"/api/certificates/{foreign_id}/pdf", headers=headers)
    assert resp.status_code == 404
    assert resp.json()["detail"]["error"] == "not_eligible"
