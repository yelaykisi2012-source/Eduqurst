"""Weekly league: week window, Top-10 order, ties, own rank, grade isolation."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient
from sqlalchemy import select

from app import leaderboard as league
from app.db import SessionLocal
from app.models import StarLedger, User


def _register(client: TestClient, login: str, first_name: str) -> dict:
    resp = client.post(
        "/api/auth/register",
        json={"login": login, "password": "Probe12345", "first_name": first_name},
    )
    assert resp.status_code == 201, resp.text
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


def _grade_id(client: TestClient, headers: dict, name: str) -> int:
    grades = client.get("/api/grades", headers=headers).json()
    return next(g["id"] for g in grades if g["name"] == name)


def _pick(client: TestClient, headers: dict, grade_id: int) -> None:
    resp = client.post("/api/me/grade", json={"grade_id": grade_id}, headers=headers)
    assert resp.status_code == 200, resp.text


def _add_stars(login: str, amount: int, when: datetime, ref: int) -> int:
    """Insert a ledger row directly; returns the user id."""
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.login == login))
        assert user is not None
        db.add(
            StarLedger(
                user_id=user.id,
                amount=amount,
                reason="probe",
                reference_id=ref,
                created_at=when,
            )
        )
        db.commit()
        return user.id


def test_week_bounds_are_tashkent_mondays():
    # Wednesday 2026-10-28 10:00 UTC == 15:00 Tashkent; week began Mon the 26th.
    start_day, end_day, start, end = league.week_bounds(
        datetime(2026, 10, 28, 10, 0, tzinfo=timezone.utc)
    )
    assert start_day.isoformat() == "2026-10-26"
    assert end_day.isoformat() == "2026-11-02"
    assert start == datetime(2026, 10, 25, 19, 0, tzinfo=timezone.utc)
    assert end == datetime(2026, 11, 1, 19, 0, tzinfo=timezone.utc)


def test_leaderboard_top_ties_me_and_isolation(client: TestClient):
    ali = _register(client, "league_a", "Ali")
    bek = _register(client, "league_b", "Bekzod")
    dil = _register(client, "league_c", "Dilnoza")
    other = _register(client, "league_x", "Boshqa")
    none = _register(client, "league_none", "Sinf yoq")

    g9 = _grade_id(client, ali, "9-sinf")
    g11 = _grade_id(client, other, "11-sinf")
    _pick(client, ali, g9)
    _pick(client, bek, g9)
    _pick(client, dil, g9)
    _pick(client, other, g11)
    # `none` intentionally has no grade → the API must ask for onboarding.

    _, _, start, _ = league.week_bounds()
    inside = start + timedelta(hours=2)
    last_week = start - timedelta(days=1)

    ali_id = _add_stars("league_a", 10, inside, 1)
    _add_stars("league_a", 5, inside + timedelta(minutes=5), 2)
    bek_id = _add_stars("league_b", 15, inside + timedelta(minutes=10), 3)
    dil_id = _add_stars("league_c", 4, inside + timedelta(minutes=15), 4)
    _add_stars("league_a", 100, last_week, 5)  # previous week must not count
    _add_stars("league_x", 99, inside, 6)  # other grade must not leak in

    board = client.get("/api/leaderboard", headers=bek).json()
    assert board["grade_id"] == g9
    assert board["grade_name"] == "9-sinf"
    assert board["participants"] == 3

    top = board["top"]
    assert [row["user_id"] for row in top] == [ali_id, bek_id, dil_id]
    assert [row["stars"] for row in top] == [15, 15, 4]
    assert [row["rank"] for row in top] == [1, 1, 3]
    assert [row["is_me"] for row in top] == [False, True, False]
    assert board["me"] == {"rank": 1, "stars": 15}

    # A pupil from 9-sinf can look at 11-sinf, but has no standing there.
    # (Other tests may have earned 11-sinf stars on the shared test DB, so we
    # assert membership rather than an exact list.)
    foreign = client.get(
        f"/api/leaderboard?grade_id={g11}", headers=ali
    ).json()
    foreign_names = [row["first_name"] for row in foreign["top"]]
    assert "Boshqa" in foreign_names
    assert "Ali" not in foreign_names
    assert foreign["me"] is None

    # No grade yet → 409 onboarding (same shape as the rest of the API).
    resp = client.get("/api/leaderboard", headers=none)
    assert resp.status_code == 409
    assert resp.json()["detail"]["error"] == "grade_not_selected"

    # Unknown grade → 404.
    resp = client.get("/api/leaderboard?grade_id=99999", headers=ali)
    assert resp.status_code == 404
    assert resp.json()["detail"]["error"] == "grade_not_found"
