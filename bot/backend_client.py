"""
backend_client.py — tiny async client for the FastAPI backend.

The bot authenticates with the shared BOT_TOKEN (X-Bot-Token header) —
the same secret both sides already have in their .env files.

Design rule: the bot must NEVER crash because the backend is slow or
down. Every call is best-effort and returns None on any problem; the
handler then falls back to the plain generic greeting.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

import aiohttp

import config

logger = logging.getLogger(__name__)

_TIMEOUT = aiohttp.ClientTimeout(total=5)


async def pupil_summary(telegram_id: int) -> dict[str, Any] | None:
    """GET /api/internal/pupil-summary — None if unavailable (never raises)."""
    if not config.API_URL or not config.BOT_TOKEN:
        return None
    url = f"{config.API_URL}/api/internal/pupil-summary"
    try:
        async with aiohttp.ClientSession(timeout=_TIMEOUT) as session:
            async with session.get(
                url,
                params={"telegram_id": telegram_id},
                headers={"X-Bot-Token": config.BOT_TOKEN},
            ) as resp:
                if resp.status != 200:
                    logger.warning("pupil-summary HTTP %s", resp.status)
                    return None
                return await resp.json()
    except (aiohttp.ClientError, asyncio.TimeoutError) as e:
        logger.warning("pupil-summary failed: %s", e)
        return None
