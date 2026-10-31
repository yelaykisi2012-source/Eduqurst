"""
Pytest fixtures: isolated SQLite test DB + a helper that forges VALID
Telegram initData exactly the way Telegram does (HMAC with bot token).
The test bot token is fake and local-only.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import time
from urllib.parse import urlencode

# Env must be set BEFORE importing any app module (config/db read it at import).
os.environ["DATABASE_URL"] = "sqlite:///./test_eduquest.db"
os.environ["BOT_TOKEN"] = "0123456789:TEST_FAKE_TOKEN_NOT_REAL"
os.environ["JWT_SECRET"] = "test-secret-not-a-real-one-0123456789abcdef"  # >=32 bayt
os.environ["CORS_ORIGINS"] = "*"
os.environ["ADMIN_TELEGRAM_IDS"] = "999000111"  # the admin used by admin tests

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.db import Base, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.seed import seed  # noqa: E402
from app.config import get_settings  # noqa: E402

TEST_BOT_TOKEN = os.environ["BOT_TOKEN"]


def make_init_data(
    user: dict, *, tamper: bool = False, auth_date: int | None = None
) -> str:
    """Forge valid initData. `auth_date=0` omits the field entirely."""
    params: dict[str, str] = {
        "query_id": "testquery",
        "user": json.dumps(user, separators=(",", ":")),
    }
    if auth_date is None:
        params["auth_date"] = str(int(time.time()))
    elif auth_date > 0:
        params["auth_date"] = str(auth_date)
    check_string = urlencode(sorted(params.items()))
    secret = hmac.new(b"WebAppData", TEST_BOT_TOKEN.encode(), hashlib.sha256).digest()
    digest = hmac.new(secret, check_string.encode(), hashlib.sha256).hexdigest()
    if tamper:
        digest = ("0" * len(digest))  # broken signature
    params["hash"] = digest
    return urlencode(sorted(params.items()))


@pytest.fixture(scope="session", autouse=True)
def _prepare_db():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    from app.db import SessionLocal

    with SessionLocal() as db:
        seed(db)
    yield
    Base.metadata.drop_all(engine)


@pytest.fixture()
def client() -> TestClient:
    return TestClient(app)


def login_as(client: TestClient, user: dict) -> dict:
    """Full Telegram login for an arbitrary pupil; returns auth headers."""
    init_data = make_init_data(user)
    resp = client.post("/api/auth/telegram", json={"init_data": init_data})
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


def pick_grade(client: TestClient, headers: dict, grade_name: str) -> int:
    """Select the grade whose name matches (e.g. '1-sinf'); returns its id."""
    grades = client.get("/api/grades", headers=headers).json()
    grade = next(g for g in grades if g["name"] == grade_name)
    resp = client.post("/api/me/grade", json={"grade_id": grade["id"]}, headers=headers)
    assert resp.status_code == 200, resp.text
    return grade["id"]


@pytest.fixture()
def token(client: TestClient) -> str:
    """Login as a test pupil and return the API bearer token."""
    init_data = make_init_data({"id": 111222333, "first_name": "Aziza", "username": "aziza_test"})
    resp = client.post("/api/auth/telegram", json={"init_data": init_data})
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


@pytest.fixture()
def grade1_auth(client: TestClient) -> dict:
    """A logged-in pupil who has chosen 1-sinf (where the sample content lives)."""
    headers = login_as(client, {"id": 111222333, "first_name": "Aziza", "username": "aziza_test"})
    pick_grade(client, headers, "1-sinf")
    return headers


@pytest.fixture()
def auth(grade1_auth: dict) -> dict:
    """Default auth used by content tests: a pupil who has picked 1-sinf."""
    return grade1_auth
