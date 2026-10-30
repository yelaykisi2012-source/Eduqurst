"""
scripts/e2e_neon.py — end-to-end proof against the RUNNING backend + Neon.

Forges a valid initData signature (same HMAC Telegram uses, with OUR bot
token), then walks the full pupil journey and asserts real DB effects.

Usage (backend/ venv active, server running on :8000):
    python scripts/e2e_neon.py
"""
from __future__ import annotations

import hashlib
import hmac
import json
import sys
import time
import uuid
from urllib.parse import parse_qsl, urlencode

import httpx

sys.path.insert(0, ".")
from app.config import get_settings  # noqa: E402

BASE = "http://127.0.0.1:8000"
settings = get_settings()


def make_init_data(user: dict) -> str:
    params = {
        "auth_date": str(int(time.time())),
        "query_id": "e2e",
        "user": json.dumps(user, separators=(",", ":")),
    }
    check = urlencode(sorted(params.items()))
    secret = hmac.new(b"WebAppData", settings.BOT_TOKEN.encode(), hashlib.sha256).digest()
    params["hash"] = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
    return urlencode(sorted(params.items()))


def main() -> None:
    results: list[str] = []
    ok = True

    def check(name: str, cond: bool, detail: str = "") -> None:
        nonlocal ok
        ok = ok and cond
        results.append(f"{'PASS' if cond else 'FAIL'} | {name} {detail}")

    with httpx.Client(base_url=BASE, timeout=30) as c:
        r = c.get("/api/health")
        check("health", r.status_code == 200, r.text[:60])

        # 1) login with a fresh random telegram id (real signature)
        tg_id = 9_000_000_000 + int(time.time()) % 1_000_000
        r = c.post("/api/auth/telegram", json={"init_data": make_init_data(
            {"id": tg_id, "first_name": "E2e-Sinovchi"})})
        check("telegram login (valid initData)", r.status_code == 200, f"-> {r.status_code}")
        if r.status_code != 200:
            print("\n".join(results)); sys.exit(1)
        auth = {"Authorization": f"Bearer {r.json()['access_token']}"}

        # 2) tampered initData must be rejected
        bad = make_init_data({"id": tg_id + 1, "first_name": "Xaklik"})
        pairs = dict(parse_qsl(bad))
        pairs["hash"] = ("1" if pairs["hash"][0] != "1" else "2") + pairs["hash"][1:]
        bad = urlencode(sorted(pairs.items()))
        r = c.post("/api/auth/telegram", json={"init_data": bad})
        check("tampered initData rejected (401)", r.status_code == 401)

        # 3) subjects + lock state
        r = c.get("/api/subjects", headers=auth)
        math = next(s for s in r.json() if s["slug"] == "matematika")
        l1 = math["lessons"][0]
        check("subjects from Neon", len(r.json()) == 3, f"lesson1='{l1['title']}'")
        check("level 2 locked initially", math["lessons"][1]["unlocked"] is False)

        # 4) view lesson -> stars + first_lesson achievement
        r = c.post(f"/api/lessons/{l1['id']}/viewed", headers=auth)
        check("mark viewed (+2 stars)", r.json()["stars_granted"] is True)
        check("first_lesson awarded", "first_lesson" in r.json()["new_achievements"])

        # 5) quiz: questions come WITHOUT correct-answer info
        r = c.get(f"/api/lessons/{l1['id']}/quiz", headers=auth)
        quiz = r.json()
        check("quiz 5 questions, no leak", len(quiz["questions"]) == 5 and "is_correct" not in str(quiz))

        # 6) submit correct answers (from seed) -> pass, unlock, stars
        correct = ["4", "6", "7", "5", "9"]
        answers = [
            {"question_id": q["id"],
             "option_id": next(o for o in q["options"] if o["text"] == t)["id"]}
            for q, t in zip(quiz["questions"], correct)
        ]
        key = uuid.uuid4().hex
        r = c.post(f"/api/lessons/{l1['id']}/quiz/submit", headers=auth,
                   json={"idempotency_key": key, "answers": answers})
        res = r.json()
        check("quiz passed 100%", res["passed"] and res["score_percent"] == 100)
        check("next level unlocked", res["next_level_unlocked"] is True)
        check("message encouraging", "ochildi" in res["message_uz"], f"-> {res['message_uz']}")

        # 7) double-submit same key -> no extra stars
        r2 = c.post(f"/api/lessons/{l1['id']}/quiz/submit", headers=auth,
                    json={"idempotency_key": key, "answers": answers})
        check("idempotent replay", r2.json()["duplicate"] is True
              and r2.json()["stars_total"] == res["stars_total"],
              f"stars={r2.json()['stars_total']}")

        # 8) level 2 now unlocked, progress persisted in Neon
        r = c.get("/api/subjects", headers=auth)
        math = next(s for s in r.json() if s["slug"] == "matematika")
        check("level 2 unlocked after pass", math["lessons"][1]["unlocked"] is True)
        r = c.get("/api/me/progress", headers=auth)
        p = r.json()
        check("progress persisted", p["lessons_passed"] == 1 and p["stars_total"] >= 10,
              f"stars={p['stars_total']} viewed={p['lessons_viewed']}")

    print("\n".join(results))
    print("E2E NATIJA:", "HAMMASI O'TDI ✅" if ok else "KUSHLAR BOR ❌")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
