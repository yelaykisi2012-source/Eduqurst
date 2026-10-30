"""
scripts/smoke_grades.py — real HTTP end-to-end smoke for the grade system.

Starts a REAL uvicorn server as a separate process on 127.0.0.1:8013 backed by
a throwaway SQLite DB (seeded with grades 1..11 + 1-sinf sample content), then
drives it over the network with httpx exactly like the Mini App does:

  login(forged valid initData) -> /api/me -> /api/grades -> /api/me/grade
  -> /api/subjects (scoped to chosen grade) -> cross-grade lesson 403

This is NOT a unit test — it proves real HTTP transport + the seeded grades.
Run from backend/ (venv active):  python scripts/smoke_grades.py
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import subprocess
import sys
import time
from urllib.parse import urlencode

import httpx

BOT_TOKEN = "0123456789:SMOKE_FAKE_TOKEN_NOT_REAL"
JWT_SECRET = "smoke-secret-not-real-0123456789abcdefg"
DB_FILE = "smoke_grades.db"
PORT = 8013
BASE = f"http://127.0.0.1:{PORT}"

SERVER_ENV = {
    **os.environ,
    "DATABASE_URL": f"sqlite:///./{DB_FILE}",
    "BOT_TOKEN": BOT_TOKEN,
    "JWT_SECRET": JWT_SECRET,
    "CORS_ORIGINS": "*",
}


def forge_init_data(user: dict) -> str:
    """Build a VALID initData string the way Telegram does (HMAC with bot token)."""
    params = {
        "auth_date": str(int(time.time())),
        "query_id": "smoke",
        "user": json.dumps(user, separators=(",", ":")),
    }
    check_string = urlencode(sorted(params.items()))
    secret = hmac.new(b"WebAppData", BOT_TOKEN.encode(), hashlib.sha256).digest()
    digest = hmac.new(secret, check_string.encode(), hashlib.sha256).hexdigest()
    params["hash"] = digest
    return urlencode(sorted(params.items()))


def main() -> int:
    # Fresh DB seeded by the server process's own import-time create_all is NOT
    # enough (routers don't seed), so seed explicitly before launching server.
    if os.path.exists(DB_FILE):
        os.remove(DB_FILE)
    subprocess.run(
        [sys.executable, "-m", "app.seed"], env=SERVER_ENV, check=True
    )

    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app",
         "--host", "127.0.0.1", "--port", str(PORT), "--log-level", "warning"],
        env=SERVER_ENV,
    )

    checks: list[tuple[str, bool]] = []

    def check(name: str, cond: bool) -> None:
        checks.append((name, cond))

    try:
        # Wait for the server to answer the health probe.
        up = False
        for _ in range(100):
            try:
                if httpx.get(f"{BASE}/api/health", timeout=1).status_code == 200:
                    up = True
                    break
            except Exception:
                time.sleep(0.1)
        check("server is live", up)

        with httpx.Client(base_url=BASE, timeout=5) as c:
            login = c.post("/api/auth/telegram", json={"init_data": forge_init_data(
                {"id": 900001, "first_name": "SmokeTest"}
            )})
            check("login 200 over HTTP", login.status_code == 200)
            token = login.json()["access_token"]
            H = {"Authorization": f"Bearer {token}"}

            me = c.get("/api/me", headers=H).json()
            check("needs_grade_selection True", me["needs_grade_selection"] is True)

            subj = c.get("/api/subjects", headers=H)
            check("subjects 409 before grade", subj.status_code == 409)
            check("code grade_not_selected", subj.json()["detail"]["error"] == "grade_not_selected")

            grades = c.get("/api/grades", headers=H).json()
            check("11 grades", len(grades) == 11)
            check(
                "names 1-sinf..11-sinf",
                grades[0]["name"] == "1-sinf" and grades[-1]["name"] == "11-sinf",
            )

            g5 = next(g for g in grades if g["name"] == "5-sinf")
            c.post("/api/me/grade", json={"grade_id": g5["id"]}, headers=H)
            check("grade 5 subjects empty", c.get("/api/subjects", headers=H).json() == [])

            g1 = next(g for g in grades if g["name"] == "1-sinf")
            c.post("/api/me/grade", json={"grade_id": g1["id"]}, headers=H)
            subs = c.get("/api/subjects", headers=H).json()
            check("grade 1 has 3 subjects", len(subs) == 3)
            math_l1 = next(s for s in subs if s["slug"] == "matematika")["lessons"][0]["id"]

            g3 = next(g for g in grades if g["name"] == "3-sinf")
            c.post("/api/me/grade", json={"grade_id": g3["id"]}, headers=H)
            blocked = c.get(f"/api/lessons/{math_l1}", headers=H)
            check("cross-grade lesson 403", blocked.status_code == 403)
            check("code wrong_grade", blocked.json()["detail"]["error"] == "wrong_grade")
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=8)
        except Exception:
            proc.kill()
        time.sleep(0.5)  # let the OS release the SQLite file handle
        try:
            if os.path.exists(DB_FILE):
                os.remove(DB_FILE)
        except Exception as exc:  # cleanup must never mask the real results
            print(f"(note: could not delete {DB_FILE}: {exc})")

    passed = sum(1 for _, ok in checks if ok)
    for name, ok in checks:
        print(f"  {'PASS' if ok else 'FAIL'}  {name}")
    print(f"\nSMOKE: {passed}/{len(checks)} checks passed")
    return 0 if passed == len(checks) else 1


if __name__ == "__main__":
    raise SystemExit(main())
