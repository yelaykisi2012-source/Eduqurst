"""
app/bot_status.py — the notice board the bot thread writes to.

The bot and the API now share ONE container (see serve.py), because Render has
no free Background Worker instance type. That raises an obvious question: when
pupils say "bot javob bermayapti", is the bot thread alive at all? Without this
board we could only guess from the outside.

So the bot stamps a heartbeat here from its keep-alive loop, the supervisor
stamps phase changes, and GET /api/bot-status publishes the result.

Privacy: this holds booleans, counters and timestamps. Never a token, never a
pupil's name, never a telegram id — which is why the endpoint is public.
"""
from __future__ import annotations

import threading
import time

from fastapi import APIRouter

_lock = threading.Lock()

_STATE: dict[str, object] = {
    "phase": "not_started",   # not_started|starting|running|unreachable|crashed|stopped|disabled
    "started_at": None,       # wall-clock seconds of the current/last start attempt
    "restarts": 0,            # how many times the supervisor had to restart the bot
    "last_error": None,       # exception CLASS name
    "last_error_detail": None,  # one short line, scrubbed by serve.safe_error_detail()
    "last_heartbeat_at": None,
    "last_heartbeat_ok": None,
}


def update(**changes) -> None:
    """Record what the supervisor knows (phase, started_at, last_error)."""
    with _lock:
        _STATE.update(changes)


def heartbeat(ok: bool) -> None:
    """Called by the bot after each keep-alive ping to the API.

    The ping is what proves the bot's own event loop is still turning. A failed
    ping is NOT reported as "running": inside this container the API answers
    locally, so a ping that fails means the bot cannot reach its own backend and
    deserves its own phase rather than a green light.
    """
    with _lock:
        _STATE["last_heartbeat_at"] = time.time()
        _STATE["last_heartbeat_ok"] = bool(ok)
        _STATE["phase"] = "running" if ok else "unreachable"


def note_restart() -> None:
    with _lock:
        _STATE["restarts"] = int(_STATE["restarts"] or 0) + 1


def reset() -> None:
    """Test helper: put the board back to factory state."""
    with _lock:
        _STATE.update(
            {
                "phase": "not_started",
                "started_at": None,
                "restarts": 0,
                "last_error": None,
                "last_error_detail": None,
                "last_heartbeat_at": None,
                "last_heartbeat_ok": None,
            }
        )


def snapshot() -> dict[str, object]:
    """Human-readable state, with ages computed at read time."""
    with _lock:
        data = dict(_STATE)
    now = time.time()
    started_at = data["started_at"]
    beat = data["last_heartbeat_at"]
    return {
        "phase": data["phase"],
        "restarts": data["restarts"],
        "last_error": data["last_error"],
        "last_error_detail": data["last_error_detail"],
        "uptime_seconds": round(now - float(started_at), 1) if started_at else None,
        "last_heartbeat_ok": data["last_heartbeat_ok"],
        "heartbeat_age_seconds": round(now - float(beat), 1) if beat else None,
        "server_time": round(now, 1),
    }


router = APIRouter(tags=["meta"])


@router.get("/api/bot-status")
def bot_status() -> dict[str, object]:
    """Is the Telegram bot thread inside this container alive? (no secrets)"""
    return snapshot()
