"""weekly_digest.py — Sunday parent report (the bot is the scheduler).

Why the bot and not a server cron: the bot is already a long-running process
that owns the Telegram connection, and the Render backend has no free cron.
The backend only supplies the data; delivery state (which parent already got
this week's message) is kept in a local JSON file so a restart never spams
the same parent twice.

Schedule: Sunday 18:00 Asia/Tashkent by default, configurable with
DIGEST_WEEKDAY (0=Mon … 6=Sun) and DIGEST_HOUR in bot/.env.
"""
from __future__ import annotations

import asyncio
import html
import json
import logging
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError

import backend_client
import config

logger = logging.getLogger(__name__)

TASHKENT = timezone(timedelta(hours=5))
INTERVAL_SECONDS = 30 * 60
STATE_PATH = Path(__file__).with_name(".digest_state.json")
MONTHS_UZ = [
    "yanvar", "fevral", "mart", "aprel", "may", "iyun",
    "iyul", "avgust", "sentabr", "oktabr", "noyabr", "dekabr",
]

GREETING = "📲 <b>Haftalik hisobot</b>"


def esc(value: object) -> str:
    return html.escape(str(value), quote=False)


def date_uz(day: date) -> str:
    return f"{day.day}-{MONTHS_UZ[day.month - 1]}"


def week_range_label(start: date, end: date) -> str:
    return f"{date_uz(start)} – {date_uz(end - timedelta(days=1))}"


def week_start_for(now: datetime) -> date:
    local = now.astimezone(TASHKENT)
    return local.date() - timedelta(days=local.weekday())


def digest_due(now: datetime) -> bool:
    local = now.astimezone(TASHKENT)
    return (
        local.weekday() == config.DIGEST_WEEKDAY
        and local.hour >= config.DIGEST_HOUR
    )


def format_digest(
    group: dict, week_start: date, week_end: date, mini_app_url: str = ""
) -> str:
    """One parent message with every linked child (HTML-safe)."""
    lines = [
        GREETING,
        f"🗓 {week_range_label(week_start, week_end)}",
        "",
    ]
    pupils = group.get("pupils") or []
    for index, pupil in enumerate(pupils):
        grade = pupil.get("grade_name") or "sinf tanlanmagan"
        lines.append(f"👧 <b>{esc(pupil.get('first_name') or 'O‘quvchi')}</b> · {esc(grade)}")
        if pupil.get("active_week"):
            lines.append(
                f"✅ Bu hafta: <b>{int(pupil.get('lessons_passed_week') or 0)}</b> dars · "
                f"⭐ <b>+{int(pupil.get('stars_week') or 0)}</b> yulduz"
            )
            lines.append(
                f"🔥 Seriya: <b>{int(pupil.get('current_streak') or 0)} kun</b> · "
                f"Jami: <b>{int(pupil.get('lessons_passed_total') or 0)}</b> dars, "
                f"⭐ {int(pupil.get('stars_total') or 0)}"
            )
        else:
            lines.append(
                "😴 Bu hafta hali dars o‘tilmadi. Farzandingiz bilan birga "
                "kichik bir darsdan boshlang!"
            )
        if index < len(pupils) - 1:
            lines.append("")
    lines.append("")
    lines.append("EduQuest — o‘yin bilan o‘qish 🤖")
    if mini_app_url:
        lines.append(f"🚀 Mini App: {esc(mini_app_url)}")
    return "\n".join(lines)


def _load_state(path: Path, week_start: date) -> set[int]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return set()
    if raw.get("week") != week_start.isoformat():
        return set()
    return {int(x) for x in raw.get("sent", []) if str(x).lstrip("-").isdigit()}


def _save_state(path: Path, week_start: date, sent: set[int]) -> None:
    payload = json.dumps(
        {"week": week_start.isoformat(), "sent": sorted(sent)}, ensure_ascii=False
    )
    tmp = path.with_suffix(".tmp")
    try:
        tmp.write_text(payload, encoding="utf-8")
        tmp.replace(path)
    except OSError:
        logger.warning("Digest holatini saqlab bo‘lmadi: %s", path, exc_info=True)


async def run_digest_round(
    bot: Bot,
    *,
    now: datetime | None = None,
    state_path: Path | None = None,
) -> int:
    """Send this week's digest to parents who have not received it yet.

    Returns how many messages were delivered. Safe to call repeatedly.
    """
    moment = now or datetime.now(timezone.utc)
    if not digest_due(moment):
        return 0
    week_start = week_start_for(moment)
    path = state_path or STATE_PATH
    sent = _load_state(path, week_start)
    try:
        data = await backend_client.weekly_digest(week_start.isoformat())
    except (backend_client.BackendOffline, backend_client.BackendBusiness) as e:
        logger.warning("Haftalik hisobot ma’lumoti olinmadi: %s", e)
        return 0
    week_end = date.fromisoformat(data["week_end"])
    delivered = 0
    for group in data.get("parents") or []:
        parent_id = int(group["parent_telegram_id"])
        if parent_id in sent:
            continue
        text = format_digest(group, week_start, week_end, config.MINI_APP_URL)
        try:
            await bot.send_message(parent_id, text, disable_web_page_preview=True)
        except (TelegramForbiddenError, TelegramBadRequest):
            # The parent blocked the bot or the chat no longer exists: retrying
            # every 30 minutes would never help, so mark the week as done.
            logger.info("Hisobot yuborilmadi (chat yopiq): parent=%s", parent_id)
            sent.add(parent_id)
            _save_state(path, week_start, sent)
            continue
        except Exception:
            logger.warning("Hisobot yuborishda xatolik: parent=%s", parent_id, exc_info=True)
            continue
        sent.add(parent_id)
        _save_state(path, week_start, sent)
        delivered += 1
    if delivered:
        logger.info("Haftalik hisobot yuborildi: %s ta ota-ona", delivered)
    return delivered


async def digest_loop(bot: Bot) -> None:
    """Background task started from main.main()."""
    while True:
        try:
            await run_digest_round(bot)
        except Exception:  # never kill the polling loop because of a digest bug
            logger.exception("Haftalik hisobot tekshiruvida kutilmagan xato")
        await asyncio.sleep(INTERVAL_SECONDS)
