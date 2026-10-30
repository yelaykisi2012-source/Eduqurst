# 🤖 EduQuest

Gamified Telegram Bot + Mini App for Grade-1 pupils (Uzbek Latin UI).
Mascot: **Quest** — a friendly blue-and-white robot.

Roadmap: [docs/ROADMAP.md](docs/ROADMAP.md)

```
Eduqurst/
├── bot/       # Python + aiogram — the Telegram bot (Stage 1 ✅)
├── webapp/    # React + TypeScript + Tailwind — the Mini App (grade onboarding built, build ✅)
├── backend/   # FastAPI + SQLAlchemy + Alembic — API incl. the Grade 1–11 system (pytest 15/15 ✅)
└── docs/      # ROADMAP.md (see the "Sinf tizimi" status block)
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
send `/start` → you get an Uzbek greeting and, once Part 2 is deployed,
the **🚀 Mini App'ni ochish** button.

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
python -m app.seed                  # demo content (idempotent)
python -m pytest tests/             # 15 unit tests (auth, grade 1–11, content, quiz)
python scripts/smoke_grades.py      # real-HTTP smoke of the grade system (starts its own server)
uvicorn app.main:app --port 8000    # API: http://127.0.0.1:8000/docs
python scripts/e2e_neon.py          # full journey vs Neon (server must run)
```

## Part 4 — Connect bot ↔ Mini App

The button only works over **public HTTPS**. Two easy options:

**A. Tunnel (fastest for testing):**
```bash
npm run tunnel     # OR download cloudflared / ngrok and expose port 5173
```
Copy the generated `https://…` URL into `bot/.env` as `MINI_APP_URL`,
restart the bot, and also set it in @BotFather:
`/mybot → your bot → Bot Settings → Mini App Settings → Set Mini App` —
paste the same URL. (The Web App URL must be set in BotFather for the
in-app button to open inside Telegram on all devices.)

**B. Deploy (Stage 6 proper):** push `webapp/` to Vercel/Netlify, use the
real domain in `MINI_APP_URL` and BotFather.

## Environment variables (bot/.env — NEVER commit)
| Variable | Where to get it | Needed for |
|---|---|---|
| `BOT_TOKEN` | @BotFather → /newbot | the bot at all |
| `MINI_APP_URL` | your tunnel or hosting | the launch button |
| `ADMIN_USER_IDS` | @userinfobot | admin rights (Stage 5) |

## Testing checklist for Stage 1
1. Bot answers `/start` in Uzbek ✔
2. Without `MINI_APP_URL` the bot says it isn't configured (no fake button) ✔
3. With `MINI_APP_URL` the 🚀 button appears and opens the Mini App inside Telegram ✔
4. Mini App shows Quest, your Telegram first name, ⭐ 0 and three subject cards ✔
5. Tapping a subject shows an honest "Tez orada" toast ✔
