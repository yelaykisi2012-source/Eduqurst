# EduQuest — 10 bosqichli yo‘l xaritasi

Slogan: **O‘rganish — endi o‘yin!** · UI tili: o‘zbek lotin · Qahramon: **Quest** (oq-ko‘k robot)

Texnologiyalar: aiogram 3 (bot) · React + TypeScript + Vite + Tailwind + React Router (Mini App) ·
FastAPI + SQLAlchemy + Alembic + Pydantic (backend) · PostgreSQL (baza) · Alohida admin panel.

## Bosqichlar

| # | Bosqich | Holat |
|---|---|---|
| 1 | Loyiha strukturasi va konfiguratsiya | ✅ tayyor |
| 2 | Telegram bot + Mini App autentifikatsiyasi | 🟡 bot tayyor (/start, /help, /app); Mini App initData orqali backend'ga xavfsiz login qiladi (backend HTTP'da tasdiqlangan); Telegram ichida jonli sinov qilinmagan |
| 3 | Mini App bosh sahifa, sinf tanlash va fanlar | 🟡 sinf onboarding (1–11) + sinf bo'yicha fanlar UI qurildi va production build o'tdi; dars/viktorina sahifalari keyingi bosqich |
| 4 | Backend API, baza va **sinf tizimi (1–11)** | 🟡 sinf tizimi qurildi va testlandi (pytest 15/15 + live HTTP smoke 11/11); **migratsiya hali Neon'ga qo'llanmagan** |
| 5 | Darslar va o'quv materiallari | ⏳ (faqat 1-sinf namunaviy kontent bor) |
| 6 | Interaktiv viktorina dvigateli | ⏳ |
| 7 | Yulduzlar, yutuqlar, progress, daraja ochish | ⏳ |
| 8 | Admin dashboard | ⏳ |
| 9 | Ulanish + to'liq o'quvchi sayohati testi | ⏳ |
| 10 | Production deploy hujjatlari | ⏳ |

## Sinf tizimi (1–11) — holat (2026-10-30)

Bajarilgan va **tekshirilgan**:
- `User.grade_id` (nullable, hech qachon taxmin qilmaydi) + Alembic migratsiyasi `7c1f2a90b4de`.
- Seed 1–11 sinflarni idempotent yaratadi; namunaviy darslar faqat 1-sinf'da.
- `GET /api/grades`, `GET /api/me`, `POST /api/me/grade`; `/api/subjects` + dars/quiz foydalanuvchi sinfi bo'yicha (sinf bo'lmasa 409 `grade_not_selected`, boshqa sinf darsi 403 `wrong_grade`).
- Sinf almashtirilganda progress (o'z sinfida) saqlanadi.
- **pytest 15/15** + **live HTTP smoke 11/11** (real uvicorn) — `python -m pytest tests/` va `python scripts/smoke_grades.py`.

Hali **qilinmagan** (tayyor deb ko'rsatilmaydi):
- Migratsiyani Neon Postgres'ga qo'llash (alembic zanjiri Postgresga xos).
- Mini App'ni Telegram ichida backend bilan jonli sinash (build va API dalollari bor, E2E yo'q).
- Bot `/start` profilingini sinf bilan individualizatsiya qilish.
- Sayt ↔ Telegram hisoblarini xavfsiz bog'lash (hozir faqat Telegram initData login).
- Admin panel orqali 2–11 sinflarga kontent kiritish.

## Bajarilgan (bosqich 1–3 qismi)

```
Eduqurst/
├── bot/            # aiogram 3 — ishlaydi, @Edi_Quest_bot
│   ├── config.py            # .env o‘qiydi, sirli kalitlar kodda YO‘Q
│   ├── main.py              # entry point + BotFather buyruqlar ro‘yxati
│   ├── handlers/start.py    # /start, /app, /help, fallback
│   ├── keyboards/inline.py  # Mini App tugmasi (WebAppInfo)
│   └── .env                 # BOT_TOKEN, MINI_APP_URL, ADMIN_USER_IDS
├── webapp/         # React+TS+Tailwind — https://eduquest-wte5pqe8k86.qoder.website
│   └── src/        # App.tsx, QuestMascot.tsx (SVG), SubjectCard.tsx
├── backend/        # (bosqich 4) FastAPI + SQLAlchemy + Alembic
├── admin/          # (bosqich 8) alohida admin interfeysi
└── docs/
```

## Keyingi hal qilinishi shart bo‘lgan texnik qaror (bosqich 4 oldidan)

1. **PostgreSQL qayerda?** Kompyuterda Postgres va Docker yo‘q. Variantlar: lokal o‘rnatish,
   bulutli managed Postgres (Neon/Supabase), yoki rivojlantirishda SQLite → production’da Postgres.
2. **Backend qayerda host qilinadi?** Qoder Sites faqat statik fayl + TypeScript Function beradi;
   FastAPI (Python) alohida hosting talab qiladi (VPS, fly.io, Railway…).

## Tamoyillar

- Sirli kalitlar faqat `.env` ichida, git’ga tushmaydi.
- Frontend’dan kelgan `initData` server tomonida HMAC bilan tekshiriladi; ishonilmaydi.
- Bir xil so‘rovni takrorlab yulduz berilmaydi (idempotentlik).
- Tayyor bo‘lmagan funksiya “ishlaydi” deb ko‘rsatilmaydi — “Tez orada” deyiladi.
