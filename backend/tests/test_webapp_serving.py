"""
Tests for app/webapp.py — the API serving the compiled Mini App.

Each test builds a tiny fake dist in tmp_path, so nothing here depends on a real
`npm run build` output existing on the machine.
"""
from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app import webapp

INDEX = "<!doctype html><title>Mini App</title>"
SECRET = "bu fayl dist tashqarisida"


def _fake_dist(root: Path) -> Path:
    dist = root / "webapp" / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text(INDEX, encoding="utf-8")
    (dist / "assets" / "index-abc123.js").write_text("console.log(1)", encoding="utf-8")
    # Placed one level above dist: reachable only if the traversal guard fails.
    (dist.parent / "outside.txt").write_text(SECRET, encoding="utf-8")
    return dist


def _app_with(dist: Path | None = None) -> FastAPI:
    app = FastAPI()

    @app.get("/api/health")
    def health() -> dict:  # pragma: no cover - asserted below
        return {"ok": True}

    mounted = webapp.register_webapp(app, dist)
    app.state.mounted = mounted
    return app


def test_root_serves_index(tmp_path: Path):
    client = TestClient(_app_with(_fake_dist(tmp_path)))
    resp = client.get("/")
    assert resp.status_code == 200
    assert resp.text == INDEX
    assert "text/html" in resp.headers["content-type"]


def test_deep_link_falls_back_to_index(tmp_path: Path):
    """A Mini App opened on any path still boots — the router lives in JS."""
    client = TestClient(_app_with(_fake_dist(tmp_path)))
    resp = client.get("/profile")
    assert resp.status_code == 200
    assert resp.text == INDEX
    # index.html must be revalidated so a new deploy reaches every webview.
    assert resp.headers["cache-control"] == "no-cache"


def test_hashed_asset_is_served(tmp_path: Path):
    client = TestClient(_app_with(_fake_dist(tmp_path)))
    resp = client.get("/assets/index-abc123.js")
    assert resp.status_code == 200
    assert "console.log(1)" in resp.text


def test_api_routes_still_win(tmp_path: Path):
    client = TestClient(_app_with(_fake_dist(tmp_path)))
    resp = client.get("/api/health")
    assert resp.status_code == 200
    assert resp.json() == {"ok": True}


def test_unknown_api_path_stays_json_404(tmp_path: Path):
    client = TestClient(_app_with(_fake_dist(tmp_path)))
    resp = client.get("/api/yoq")
    assert resp.status_code == 404
    assert resp.json() == {"detail": "Not Found"}
    assert "text/html" not in resp.headers["content-type"]


def test_unknown_api_post_is_404_not_405(tmp_path: Path):
    """The catch-all must not turn old 404s into 405 Method Not Allowed."""
    client = TestClient(_app_with(_fake_dist(tmp_path)))
    resp = client.post("/api/yoq", json={})
    assert resp.status_code == 404


def test_path_traversal_cannot_escape_dist(tmp_path: Path):
    client = TestClient(_app_with(_fake_dist(tmp_path)))
    resp = client.get("/%2e%2e%2foutside.txt")
    assert resp.status_code == 200
    assert resp.text == INDEX  # shell, never the file outside dist
    assert SECRET not in resp.text


def test_missing_build_mounts_nothing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(webapp, "find_dist", lambda: None)
    app = _app_with(None)
    assert app.state.mounted is False
    client = TestClient(app)
    assert client.get("/").status_code == 404
    assert client.get("/api/health").status_code == 200


def test_find_dist_accepts_webapp_dist_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    dist = _fake_dist(tmp_path)
    monkeypatch.setenv("WEBAPP_DIST", str(dist))
    assert webapp.find_dist() == dist.resolve()
    client = TestClient(_app_with(None))
    assert client.get("/").text == INDEX
