"""
pupil_guard.py — register every Telegram user in the backend BEFORE any
handler asks the backend about them.

Why: every button (Darslar / Profilim / Yutuqlar / Admin) calls an internal
endpoint that looks the pupil up by telegram_id. If that row is missing —
brand-new user pressing an old menu button, a restored database, a second bot
instance pointed at another backend — the API answers 404 `pupil_not_found`
and the child only sees "Avval /start bosing." even though Telegram has
already identified them.

The guard makes navigation work from ANY entry point: the first update from a
user (per bot process) registers them via the same idempotent upsert used by
/start. Failures are swallowed here — the actual handler then shows its
honest offline/business message, so we never hide a real backend problem.
"""
from __future__ import annotations

import logging

from aiogram import BaseMiddleware

import backend_client

logger = logging.getLogger(__name__)


class PupilGuard(BaseMiddleware):
    """One cheap upsert per user per process; cached afterwards."""

    def __init__(self) -> None:
        super().__init__()
        self._known: set[int] = set()

    async def __call__(self, handler, event, data):  # noqa: ANN001
        user = data.get("event_from_user")
        if user is not None and not getattr(user, "is_bot", False):
            if user.id not in self._known:
                try:
                    await backend_client.upsert_pupil(
                        user.id,
                        first_name=user.first_name or "",
                        username=user.username,
                    )
                    self._known.add(user.id)
                except (
                    backend_client.BackendOffline,
                    backend_client.BackendBusiness,
                ) as e:
                    # Backend down / rejected: let the handler report it honestly.
                    logger.info("PupilGuard: ro'yxatga olish o'tkazib yuborildi (%s)", e)
        return await handler(event, data)
