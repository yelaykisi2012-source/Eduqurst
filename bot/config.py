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
