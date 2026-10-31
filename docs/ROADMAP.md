# EduQuest — joriy holat (2026-10-31)

Slogan: **O‘rganish — endi o‘yin!** · UI: o‘zbek lotin · Qahramon: **Quest**

Texnologiyalar: aiogram 3 · React + TypeScript + Vite + Tailwind · FastAPI +
SQLAlchemy 2 + Alembic + Pydantic · PostgreSQL (Neon) · Render (backend) ·
Qoder Sites (Mini App).

## Jonli manzillar

| Qism | Manzil |
|---|---|
| Mini App | https://eduquest-mini-app-7o3hx1m5a24.qoder.website |
| Backend API | https://eduqurst.onrender.com (`/api/health`, `/docs`) |
| Bot | @Edi_Quest_bot |

## Bajarilgan va tekshirilgan

### O‘quvchi yo‘li
- `/start` → sinf tanlash (1–11) → fanlar → darslar → materiallar → test →
  natija → yulduzlar → keyingi bosqich.
- Sinf faqat o‘quvchi o‘zi tanlaydi; ism/username/Telegram ID bo‘yicha
  taxmin qilinmaydi. Sinf almashtirilsa progress o‘chmaydi.
- Dars materiallari 4 formatda: **video, PDF, jonli dars (havola), yozma matn**.
  Mini App va bot ikkalasi ham ko‘rsatadi; rasm/slayd ham qo‘llanadi.
- Test serverda baholanadi (to‘g‘ri javoblar frontendga yuborilmaydi),
  `idempotency_key` ikki marta yulduz berilishini to‘xtatadi.
- Yulduzlar, 5 ta yutuq, ketma-ket bosqich ochilishi, progress va natijalar
  Mini App hamda botda bir xil backend’dan olinadi.
- 1–4-sinflarda namunaviy kontent bor; 5–11-sinflar strukturaviy tayyor,
  admin to‘ldirishi mumkin (bo‘sh holat xabari ko‘rsatiladi).

### Admin
- Mini App: sinf → fan/dars yaratish, **tahrirlash**, **chiqarish/yashirish**,
  material va savollar ro‘yxati, ikki bosqichli tasdiq bilan o‘chirish.
- Bot: fan, dars, material (4 format) va savol qo‘shish oqimlari.
- Har bir admin so‘rovi backend’da `ADMIN_TELEGRAM_IDS` allowlist bilan
  qayta tekshiriladi (403 aks holda). Fan/dars butunlay o‘chirilmaydi —
  yashirish progress’ni saqlaydi.
- Yashirilgan dars ochilish zanjirini buzmaydi: oldingi **e’lon qilingan**
  dars hisobga olinadi.

### Xavfsizlik
- Telegram `initData` HMAC bilan tekshiriladi; `auth_date` majburiy,
  24 soatdan eski yoki kelajakdagi qiymat rad etiladi.
- Bot ↔ backend: `X-Bot-Token` + `hmac.compare_digest`.
- Sirlar faqat `.env` fayllarida; kodda yoki chatda emas.

### Testlar (oxirgi yugurish)
- Backend: `python -m pytest tests/ -q` → **29 passed** (auth, sinf
  izolyatsiyasi, 4 format, test baholash, idempotentlik, admin CRUD,
  yashirilgan kontent, unlock, auth_date).
- Bot: `python -m unittest discover -s tests` → **12 passed** (har bir
  tugma tirik, callback ≤64 bayt, barcha callback prefikslari handlerli,
  eskirgan test holati, material havolalari, uzun matn bo‘lishi).
- Mini App: `npm run build` → TypeScript xatosiz, production bundle.
- Jonli backend: health 200; yangi admin `PATCH`/`DELETE` OpenAPI’da;
  sayt origin’idan CORS `PATCH, DELETE` ruxsat etilgan.
- Jonli sayt: yangi `index-CUFWK7w2.js` bundle xizmat qilmoqda.

## Foydalanuvchi bajarishi kerak (jonli Telegram sinovi)

1. Render → Environment: `ADMIN_TELEGRAM_IDS=8560186698` qo‘shish
   (aks holda admin panel 403 qaytaradi).
2. @BotFather → bot → Mini App URL:
   `https://eduquest-mini-app-7o3hx1m5a24.qoder.website`.
3. Botni bitta nusxada qayta ishga tushirish (`python main.py`).
4. Telegram ichida `/start` → Mini App → sinf → dars → test yo‘lini sinash.

## Hali tasdiqlanmagan (tayyor deb ko‘rsatilmaydi)
- Telegram ichidagi jonli klik-test (yuqoridagi 4 qadamdan keyin).
- Production admin panel (Render env sozlanmaguncha).
- Sayt ↔ Telegram hisoblarini bog‘lash — hozir faqat initData login.
- 5–11-sinflar uchun real o‘quv kontenti (admin kiritadi).
