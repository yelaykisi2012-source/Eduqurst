# EduQuest — Backend’ni internetga chiqarish (fly.io / Railway)

Maqsad: FastAPI backend’ni **ochiq HTTPS URL**ga chiqarish. Shundan keyin Mini App
(React) shu URL’ga ulanadi va Telegram ichida sinf tanlash haqiqiy ishlaydi.

> Muhim: bu qadamlarda **faqat hisobga kirish (login)** qismini o‘zingiz bajarasiz.
> Kod va fayllar allaqachon tayyor. Maxfiy kalitlar `.env`da emas, platformaning
> “secrets” bo‘limida saqlanadi (git’ga tushmaydi).

---

## A variant — fly.io (tavsiya, doimiy URL)

### 0. Bir marta: flyctl’ni o‘rnatish va login
Git Bash’da:
```bash
powershell -Command "iwr https://fly.io/install.ps1 -useb | iex"
# terminalni qayta oching, keyin:
fly version
fly auth login        # brauzer ochilib hisobingizga kiritadi (bepul)
```

### 1. App yaratish (backend papkasida)
```bash
cd backend
fly launch --no-deploy --ha=false --no-create-db
```
- `--ha=false` → bitta mashina (bepul daraja uchun).
- `--no-create-db` → Postgres yaratmaydi (bizda Neon bor).
- So‘rasa **unique app name** tanlang (masalan `eduquest-api-xyz`). Bu `fly.toml`dagi
  `app = ...` nomini yangilaydi.
- `fly launch` Dockerfile’ni aniqlaydi va sozlaydi.

### 2. Maxfiy kalitlarni berish (NEVER git)
Neon dashboard’dan **pooled** (`...pooler.neon.tech...`) DATABASE_URL oling.
```bash
fly secrets set DATABASE_URL="postgresql+psycopg://user:pass@ep-xxx-pooler.us-east.aws.neon.tech/eduquest?sslmode=require"
fly secrets set BOT_TOKEN="<bot/.env dagi token>"
fly secrets set JWT_SECRET="$(python -c 'import secrets;print(secrets.token_urlsafe(32))')"
fly secrets set CORS_ORIGINS="https://eduquest-wte5pqe8k86.qoder.website"
```
> `DATABASE_URL_UNPOOLED` serverda shart emas (migratsiyani lokal’da qilamiz).

### 3. Deploy
```bash
fly deploy
fly apps open        # yoki: https://<siz-ning-nom>.fly.dev/api/health
```
Brauzerda `/api/health` ochilsa va `{"ok":true,...}` ko‘rinса — **backend jonli**.

### 4. URL’ni eslab qoling
```
https://<siz-ning-nom>.fly.dev
```
Buni keyingi qadamda (`VITE_API_URL`) ishlatamiz.

---

## B variant — Railway (TANLANGAN: GitHub orqali, kod push qilingan)
Kod allaqachon https://github.com/yelaykisi2012-source/Eduqurst da (`main` branch).
1. https://railway.app → “Login with GitHub” hisobi bilan kiring.
2. “New Project” → “Deploy from GitHub repo” → `yelaykisi2012-source/Eduqurst` repositasini tanlang.
3. **Muhim:** service ochilgacha “Configure GitHub App” so‘ravini ruxsat eting (repo ko‘rinmasa shu sababli).
4. Service yaratilgach: service → **Settings → Deploy → Root Directory** ni `backend` qilib belgilang.
   (Buni qilmasangiz Railway repo tepasidagi `package.json`ni ko‘rib Node deb o‘ylaydi va build chalamasligi mumkin.)
5. Railway `backend/requirements.txt` + `Procfile`ni avtomatik aniqlaydi (Python + uvicorn).
5. “Variables” bo‘limiga xuddi yuqoridagi 4 ta o‘zgaruvchini kiriting
   (`DATABASE_URL`, `BOT_TOKEN`, `JWT_SECRET`, `CORS_ORIGINS`).
6. “Settings → Networking → Generate Domain” → HTTPS URL oling.
7. `/api/health` ni ochib tekshiring.

---

## 5-qadam — Frontend’ni yangi backend’ga ulash va saytni joylash
Backend URL olgach, **men** davom ettiraman (sizdan faqat URL kerak):
```bash
# webapp/.env ichida:
VITE_API_URL=https://<siz-ning-nom>.fly.dev
# so'ng: npm run build  →  Qoder Sites'ga qayta joylash
```
Sayt manzili o‘zgarmaydi, shuning uchun bot’dagi `MINI_APP_URL` va BotFather sozlamasi
o‘zgarishsiz qoladi.

---

## Xavfsizlik eslatmalari
- `.env`, `neon.ts`, `.neon`, `*.db` git’ga tushmaydi (`.gitignore`da).
- `BOT_TOKEN`/`JWT_SECRET`/`DATABASE_URL` faqat `fly secrets` / Railway Variables’da.
- Frontend’ga hech qachon sirli kalit berilmaydi — u faqat JWT (qisqa muddatli token) oladi.
- Keyingi bor-yo‘g‘di yangilanish: `cd backend && fly deploy` (kod o‘zgarsa).

## Tekshirish ro‘yxati (deploy’dan keyin)
1. `https://<url>/api/health` → `{"ok": true}` ✔
2. Mini App Telegram’da ochilganda **sinf tanlash** ko‘rinadi (1–11) ✔ (kutilmoqda)
3. Sinf tanlansa, uy sahifada o‘sha sinf fanlari chiqadi ✔ (kutilmoqda)
