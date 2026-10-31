"""
Web (non-Telegram) accounts: login + password registration.

These pupils have NO Telegram id; they must still get the same grade
onboarding, lessons, quizzes and stars as Telegram pupils. Security checks
cover hashing, duplicate/case-insensitive logins, generic credential errors
and the admin boundary.
"""
from __future__ import annotations

from fastapi.testclient import TestClient

from app.passwords import hash_password, verify_password
from tests.conftest import pick_grade


def register(
    client: TestClient, login: str, password: str = "maxfiy123", first_name: str = "Ali"
) -> dict:
    resp = client.post(
        "/api/auth/register",
        json={"login": login, "password": password, "first_name": first_name},
    )
    return resp


def headers_of(resp) -> dict:
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


class TestPasswordHashing:
    def test_roundtrip_and_wrong_password(self):
        stored = hash_password("maxfiy123")
        assert stored.startswith("scrypt$")
        assert "maxfiy123" not in stored  # plain text is never stored
        assert verify_password("maxfiy123", stored) is True
        assert verify_password("maxfiy124", stored) is False

    def test_missing_or_garbage_hash_never_matches(self):
        assert verify_password("maxfiy123", None) is False
        assert verify_password("maxfiy123", "") is False
        assert verify_password("maxfiy123", "pbkdf2_sha256$1$x$y") is False
        assert verify_password("maxfiy123", "scrypt$bad$data") is False


class TestRegister:
    def test_register_then_full_pupil_flow(self, client: TestClient):
        resp = register(client, "ali_web_1", first_name="Ali")
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["first_name"] == "Ali"
        assert "password" not in resp.text  # never echo credentials back
        headers = headers_of(resp)

        me = client.get("/api/me", headers=headers)
        assert me.status_code == 200, me.text
        profile = me.json()
        assert profile["first_name"] == "Ali"
        assert profile["needs_grade_selection"] is True  # never guessed
        assert profile["is_admin"] is False

        # No grade yet → lessons are blocked with the same honest code.
        assert client.get("/api/subjects", headers=headers).json()["detail"]["error"] == "grade_not_selected"

        grade_id = pick_grade(client, headers, "1-sinf")
        assert client.get("/api/me", headers=headers).json()["grade_id"] == grade_id

        subjects = client.get("/api/subjects", headers=headers)
        assert subjects.status_code == 200, subjects.text
        assert len(subjects.json()) >= 1  # seeded 1-sinf content is usable

    def test_empty_first_name_falls_back_to_login(self, client: TestClient):
        resp = register(client, "ali_web_2", first_name="   ")
        assert resp.status_code == 201, resp.text
        assert resp.json()["first_name"] == "ali_web_2"

    def test_login_is_stored_lowercase_and_case_insensitive(self, client: TestClient):
        assert register(client, "Ali_Web_3").status_code == 201
        resp = client.post(
            "/api/auth/login", json={"login": "ALI_WEB_3", "password": "maxfiy123"}
        )
        assert resp.status_code == 200, resp.text
        # the account profile is reachable with that token
        assert client.get("/api/me", headers=headers_of(resp)).status_code == 200

    def test_duplicate_login_is_rejected_case_insensitively(self, client: TestClient):
        assert register(client, "ali_web_4").status_code == 201
        resp = register(client, "ALI_WEB_4")
        assert resp.status_code == 409
        assert resp.json()["detail"]["error"] == "login_taken"

    def test_invalid_logins_are_rejected(self, client: TestClient):
        for bad in ["ab", "ali web", "ali-web", "али", "x" * 33]:
            resp = register(client, bad)
            assert resp.status_code == 422, (bad, resp.text)
            assert resp.json()["detail"]["error"] == "invalid_login", bad

    def test_short_password_is_rejected(self, client: TestClient):
        resp = register(client, "ali_web_5", password="12345")
        assert resp.status_code == 422
        assert resp.json()["detail"]["error"] == "weak_password"


class TestPasswordLogin:
    def test_wrong_password_and_unknown_login_share_one_error(self, client: TestClient):
        assert register(client, "ali_web_6").status_code == 201
        wrong = client.post(
            "/api/auth/login", json={"login": "ali_web_6", "password": "notmaxfiy"}
        )
        unknown = client.post(
            "/api/auth/login", json={"login": "nobody_here_6", "password": "maxfiy123"}
        )
        assert wrong.status_code == 401
        assert unknown.status_code == 401
        # identical error → the endpoint cannot reveal which logins exist
        assert wrong.json()["detail"]["error"] == "invalid_credentials"
        assert wrong.json()["detail"] == unknown.json()["detail"]

    def test_login_token_reaches_progress(self, client: TestClient):
        reg = register(client, "ali_web_7")
        assert reg.status_code == 201
        login = client.post(
            "/api/auth/login", json={"login": "ali_web_7", "password": "maxfiy123"}
        )
        headers = headers_of(login)
        pick_grade(client, headers, "1-sinf")
        progress = client.get("/api/me/progress", headers=headers)
        assert progress.status_code == 200, progress.text
        assert progress.json()["grade_name"] == "1-sinf"
        assert progress.json()["stars_total"] == 0  # fresh account, nothing faked


class TestWebAccountBoundaries:
    def test_web_account_is_never_admin(self, client: TestClient):
        reg = register(client, "ali_web_8")
        headers = headers_of(reg)
        resp = client.get("/api/admin/overview", headers=headers)
        assert resp.status_code == 403
        assert resp.json()["detail"]["error"] == "not_admin"

    def test_web_account_token_is_required(self, client: TestClient):
        assert client.get("/api/me").status_code in (401, 403)
