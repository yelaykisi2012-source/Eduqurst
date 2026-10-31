# 🤖 EduQuest

Gamified Telegram Bot + Mini App for pupils in grades 1–11 (Uzbek Latin UI).
Mascot: **Quest** — a friendly blue-and-white robot.

Current state, live links and pending items: [docs/ROADMAP.md](docs/ROADMAP.md)

```
Eduqurst/
├── bot/       # Python + aiogram — lessons, quizzes, profile, admin flows
├── webapp/    # React + TypeScript + Tailwind — the Telegram Mini App
├── backend/   # FastAPI + SQLAlchemy + Alembic — API, auth, gamification
└── docs/      # ROADMAP.md (joriy holat va qolgan qadamlar)
```

## Prerequisites
- Python 3.12+ (`py --version` on Windows)
- Node.js 20+ (`node --version`)
- A Telegram bot token from [@BotFather](https://t.me/BotFather)

## Part 1 — Run the bot

```bash
cd bot
py -m venv .venv                 # create isolated Python environment
.venv/Scripts/activate           # activate it (Windows)
pip install -r requirements.txt  # install aiogram + python-dotenv
copy .env.example .env           # then OPEN .env and paste your BOT_TOKEN
python main.py
```

You should see `EduQuest bot ishga tushdi`. Open Telegram, find your bot,
send `/start` → you get an Uzbek greeting and the **🚀 Mini App'ni ochish**
button (when `MINI_APP_URL` is set).

To stop the bot: press `Ctrl+C` in the terminal.

## Part 2 — Run the Mini App (webapp)

```bash
cd webapp
npm install
npm run dev        # opens http://localhost:5173
```

Open that URL in a browser to see the home screen (it will say you are
outside Telegram — that's correct and honest).

## Part 3 — Backend (FastAPI + Neon PostgreSQL) ✅ Stage complete

Neon project is declared in `neon.ts`; env vars are pulled to `.env.local`
via `neon deploy` (never committed). `backend/.env` holds the real values:
`DATABASE_URL` (pooled, app runtime), `DATABASE_URL_UNPOOLED` (direct,
Alembic migrations), `BOT_TOKEN`, `JWT_SECRET`.

```bash
cd backend
.venv/Scripts/activate
pip install -r requirements.txt
python -m alembic upgrade head      # schema on Neon (direct URL)
python -m app.seed                  # grades 1–11 + demo content (idempotent)
python -m pytest tests/             # 29 tests: auth, grade scoping, quiz, admin, bot API
uvicorn app.main:app --port 8000    # API: http://127.0.0.1:8000/docs
```

Bot tests (no extra dependency):

```bash
cd bot
.venv/Scripts/python.exe -m unittest discover -s tests -v   # 12 tests
```

## Part 4 — Connect bot ↔ Mini App

The button only works over **public HTTPS**. The Mini App is already
published on Qoder Sites:

```
https://eduquest-mini-app-7o3hx1m5a24.qoder.website
```

Put that URL into `bot/.env` as `MINI_APP_URL`, restart the bot, and set the
same URL in @BotFather:
`/mybot → your bot → Bot Settings → Mini App Settings → Set Mini App`.

For local testing you can still use a tunnel (`npm run tunnel`) and replace
`MINI_APP_URL` temporarily.

## Environment variables (bot/.env — NEVER commit)
| Variable | Where to get it | Needed for |
|---|---|---|
| `BOT_TOKEN` | @BotFather → /newbot | the bot at all |
| `MINI_APP_URL` | your tunnel or hosting | the launch button |
| `ADMIN_USER_IDS` | @userinfobot | bot admin panel |

Backend (Render → Environment): `DATABASE_URL`, `BOT_TOKEN`, `JWT_SECRET`,
`CORS_ORIGINS` (the published Mini App origin), `ADMIN_TELEGRAM_IDS`
(comma-separated admin Telegram ids).

## Testing checklist

1. Bot answers `/start` in Uzbek ✔
2. Grade picker (1–11) appears when no grade is saved ✔
3. Subjects → lessons → materials (video/PDF/live/text) → quiz → result ✔
4. Stars and achievements are granted once (idempotent) ✔
5. Mini App admin: create, edit, publish/hide, delete material/question ✔
6. Backend 29 tests, bot 12 tests, frontend build — all green ✔
7. Live Telegram click-through — pending the BotFather/restart steps above.
