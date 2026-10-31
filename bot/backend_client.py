"""
backend_client.py — async client for the FastAPI backend (bot side).

Auth: the shared BOT_TOKEN travels in the X-Bot-Token header — the same
secret both .env files already hold. Strangers without it get 401.

Failure model (so the bot can react instead of crashing):
  BackendOffline  — no network / backend down / timeout
  BackendBusiness — the backend answered a 4xx/5xx with a structured error
                    (e.g. code="grade_not_selected" → run grade onboarding)

pupil_summary() stays best-effort (returns None) because /start must work
even when the backend sleeps; every other call raises so the handler can
show an honest error message.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

import aiohttp

import config

logger = logging.getLogger(__name__)

_TIMEOUT = aiohttp.ClientTimeout(total=20)  # Render free tier can be slow to wake


class BackendOffline(Exception):
    """Network-level failure: cannot reach the backend at all."""


class BackendBusiness(Exception):
    """The backend reached us back but refused (4xx/5xx) with a reason."""

    def __init__(self, status: int, code: str, message: str) -> None:
        super().__init__(f"HTTP {status} [{code}] {message}")
        self.status = status
        self.code = code
        self.message = message


async def _call(
    method: str,
    path: str,
    *,
    params: dict[str, Any] | None = None,
    json_body: dict[str, Any] | None = None,
) -> Any:
    if not config.API_URL or not config.BOT_TOKEN:
        raise BackendOffline("API_URL yoki BOT_TOKEN sozlanmagan (bot/.env)")
    url = f"{config.API_URL}/api/internal{path}"
    try:
        async with aiohttp.ClientSession(timeout=_TIMEOUT) as session:
            async with session.request(
                method, url, params=params, json=json_body,
                headers={"X-Bot-Token": config.BOT_TOKEN},
            ) as resp:
                if resp.status < 400:
                    if resp.status == 204:
                        return None
                    return await resp.json()
                code, msg = "error", f"Server xatosi (HTTP {resp.status})"
                try:
                    data = await resp.json()
                    detail = data.get("detail") if isinstance(data, dict) else None
                    if isinstance(detail, str):
                        msg = detail
                    elif isinstance(detail, dict):
                        code = detail.get("error", "error")
                        msg = detail.get("message_uz") or msg
                except Exception:
                    pass
                if resp.status == 422:
                    msg = "Maʼlumot formati yaroqsiz — qayta tekshirib yuboring."
                raise BackendBusiness(resp.status, code, msg)
    except (aiohttp.ClientError, asyncio.TimeoutError, OSError) as e:
        raise BackendOffline(str(e)) from e


# ---------- pupil-facing ----------

async def pupil_summary(telegram_id: int) -> dict[str, Any] | None:
    """Best-effort stats for /start personalisation. None = unavailable."""
    try:
        return await _call("GET", "/pupil-summary", params={"telegram_id": telegram_id})
    except (BackendOffline, BackendBusiness) as e:
        logger.warning("pupil-summary: %s", e)
        return None


async def upsert_pupil(telegram_id: int, first_name: str = "", username: str | None = None) -> dict[str, Any]:
    return await _call(
        "POST", "/pupils",
        json_body={"telegram_id": telegram_id, "first_name": first_name, "username": username},
    )


async def grades(telegram_id: int) -> list[dict[str, Any]]:
    return await _call("GET", "/grades", params={"telegram_id": telegram_id})


async def set_grade(telegram_id: int, grade_id: int) -> dict[str, Any]:
    return await _call(
        "POST", "/pupil/grade",
        json_body={"telegram_id": telegram_id, "grade_id": grade_id},
    )


async def subjects(telegram_id: int) -> list[dict[str, Any]]:
    return await _call("GET", "/pupil/subjects", params={"telegram_id": telegram_id})


async def lesson(telegram_id: int, lesson_id: int) -> dict[str, Any]:
    return await _call("GET", f"/pupil/lesson/{lesson_id}", params={"telegram_id": telegram_id})


async def mark_viewed(telegram_id: int, lesson_id: int) -> dict[str, Any]:
    return await _call("POST", f"/pupil/lesson/{lesson_id}/viewed", params={"telegram_id": telegram_id})


async def quiz(telegram_id: int, lesson_id: int) -> dict[str, Any]:
    return await _call("GET", f"/pupil/lesson/{lesson_id}/quiz", params={"telegram_id": telegram_id})


async def submit_quiz(telegram_id: int, lesson_id: int, idempotency_key: str, answers: list[dict[str, Any]]) -> dict[str, Any]:
    return await _call(
        "POST", f"/pupil/lesson/{lesson_id}/quiz/submit",
        json_body={"telegram_id": telegram_id, "idempotency_key": idempotency_key, "answers": answers},
    )


async def progress(telegram_id: int) -> dict[str, Any]:
    return await _call("GET", "/pupil/progress", params={"telegram_id": telegram_id})


# ---------- admin-facing (backend double-checks ADMIN_TELEGRAM_IDS) ----------

async def admin_overview(telegram_id: int) -> list[dict[str, Any]]:
    return await _call("GET", "/admin/overview", params={"telegram_id": telegram_id})


async def admin_create_subject(telegram_id: int, grade_id: int, name: str, emoji: str) -> dict[str, Any]:
    return await _call(
        "POST", "/admin/subjects",
        json_body={"telegram_id": telegram_id, "data": {"grade_id": grade_id, "name": name, "emoji": emoji}},
    )


async def admin_lessons(telegram_id: int, subject_id: int) -> list[dict[str, Any]]:
    return await _call("GET", f"/admin/subjects/{subject_id}/lessons", params={"telegram_id": telegram_id})


async def admin_create_lesson(
    telegram_id: int, subject_id: int, title: str, explanation: str,
    stars_reward: int, pass_threshold_percent: int,
) -> dict[str, Any]:
    return await _call(
        "POST", f"/admin/subjects/{subject_id}/lessons",
        json_body={
            "telegram_id": telegram_id,
            "data": {
                "title": title,
                "explanation": explanation,
                "stars_reward": stars_reward,
                "pass_threshold_percent": pass_threshold_percent,
            },
        },
    )


async def admin_create_question(
    telegram_id: int, lesson_id: int, text: str, kind: str, options: list[dict[str, Any]],
) -> dict[str, Any]:
    return await _call(
        "POST", f"/admin/lessons/{lesson_id}/questions",
        json_body={"telegram_id": telegram_id, "data": {"text": text, "kind": kind, "options": options}},
    )


async def admin_create_material(
    telegram_id: int, lesson_id: int, kind: str, title: str, content: str,
) -> dict[str, Any]:
    """kind: video | pdf | live | text (content = URL or written notes)."""
    return await _call(
        "POST", f"/admin/lessons/{lesson_id}/materials",
        json_body={
            "telegram_id": telegram_id,
            "data": {"kind": kind, "title": title, "content": content},
        },
    )


async def health() -> bool:
    """Cheap keep-alive ping for the Render backend (best-effort)."""
    if not config.API_URL:
        return False
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as session:
            async with session.get(f"{config.API_URL}/api/health") as resp:
                return resp.status == 200
    except (aiohttp.ClientError, asyncio.TimeoutError, OSError):
        return False
