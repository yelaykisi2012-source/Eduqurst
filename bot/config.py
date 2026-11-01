"""
config.py — the single place where we read secrets from the environment.

WHY THIS FILE EXISTS
--------------------
Rule #8 of the project: never hardcode tokens in the code.
Real values live in `bot/.env` (a plain-text file you create locally,
already excluded from git by .gitignore). The code only *reads* them.
"""
import os

from dotenv import load_dotenv

# Load variables from bot/.env into the environment (does nothing if file absent)
load_dotenv()

BOT_TOKEN: str = os.getenv("BOT_TOKEN", "").strip()

# Username without @ — shown to parents in the linking instructions.
BOT_USERNAME: str = os.getenv("BOT_USERNAME", "Edi_Quest_bot").strip().lstrip("@")

# HTTPS URL of the Mini App, used for the "open Mini App" button.
MINI_APP_URL: str = os.getenv("MINI_APP_URL", "").strip()

# Base URL of the FastAPI backend (e.g. https://eduqurst.onrender.com).
# Used to personalise /start with the pupil's grade and stars.
API_URL: str = os.getenv("API_URL", "").strip().rstrip("/")


def _parse_admin_ids(raw: str) -> set[int]:
    """ADMIN_USER_IDS='111,222' -> {111, 222}. Invalid entries are ignored."""
    ids: set[int] = set()
    for part in raw.split(","):
        part = part.strip()
        if part.lstrip("-").isdigit():
            ids.add(int(part))
    return ids


# Admin allowlist — used from Stage 5, but collected from day one.
ADMIN_USER_IDS: set[int] = _parse_admin_ids(os.getenv("ADMIN_USER_IDS", ""))


def _int_env(name: str, default: int) -> int:
    raw = os.getenv(name, "").strip()
    return int(raw) if raw.lstrip("-").isdigit() else default


def _bool_env(name: str, default: bool) -> bool:
    """Only an explicit true/false overrides; anything else keeps the default."""
    raw = os.getenv(name, "").strip().lower()
    if raw in ("1", "true", "yes", "on"):
        return True
    if raw in ("0", "false", "no", "off"):
        return False
    return default


# Parent weekly digest schedule (Asia/Tashkent). Sunday = 6, 18:00 local.
# The bot is the scheduler; backend only provides the data.
DIGEST_WEEKDAY: int = _int_env("DIGEST_WEEKDAY", 6)
DIGEST_HOUR: int = _int_env("DIGEST_HOUR", 18)

# How often the bot pings the backend. Two jobs in one number:
#   1. Render's free tier wakes slowly — pupils must not hit a cold API;
#   2. inside the shared container (serve.py) Render only counts INBOUND
#      traffic, and Telegram polling is outbound — this ping is inbound, so it
#      is what stops the service (and the bot living in it) being spun down.
# Must stay below the 15 minute spin-down, hence a 5 minute default.
KEEPALIVE_SECONDS: int = _int_env("KEEPALIVE_SECONDS", 300)

# Messages that arrived while the bot was offline (deploy, restart) are kept by
# Telegram for a day. On the server we catch up on them — dropping would delete
# real homework questions. Run the bot on a laptop and an old queue will fire
# at you; set DROP_PENDING_UPDATES=true in bot/.env to throw it away instead.
DROP_PENDING_UPDATES: bool = _bool_env("DROP_PENDING_UPDATES", False)
