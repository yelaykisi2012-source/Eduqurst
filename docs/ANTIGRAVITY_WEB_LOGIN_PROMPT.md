# Antigravity uchun prompt — «Menda Telegram yo'q» kirish/ro'yxatdan o'tish

Quyidagi matnni Antigravity'ga to'liq nusxalab bering.

---

## Vazifa: Telegram bo'lmagan o'quvchilar uchun login/parol bilan kirish

EduQuest Mini App'ning mavjud `WebLogin.tsx` ekranida Telegram Login Widget bor.
Endi Telegram hisobi **yo'q** o'quvchilar ham sayt orqali ro'yxatdan o'tib,
kirishi kerak. Backend tomoni allaqachon tayyor va jonli serverda ishlaydi —
faqat frontend UI va ulanish kerak.

### 1) Umumiy talablar

- Telegram widget **asosiy va o'zgarmas** bo'lib qoladi.
- Uning ostida kichik matnli havola/tugma: **«Menda Telegram yo'q»**.
- Bosilganda ochiladigan panelda ikkita tab: **«Kirish»** va **«Ro'yxatdan o'tish»**.
- Mavjud dizayn tizimidan foydalaning (`components/ui/Button`, `Card`, `Icons`),
  yangi npm paket qo'shmang, sayt rang/uslubini buzmang.
- Mobil qurilmada ham qulay: inputlar to'liq kenglikda, `font-size >= 16px`,
  `autoComplete="username"`, `autoComplete="current-password"` /
  `"new-password"`, parol maydoni `type="password"`.
- Parol hech qachon `console.log` qilinmaydi va saqlanmaydi. Faqat backend
  qaytargan JWT `storeToken()` orqali saqlanadi (mavjud mexanizm).
- Email, SMS, «parolni tiklash» qo'shilmaydi — parolni admin qo'lda yangilaydi.

### 2) Backend API shartnomasi (o'zgarmaydi)

`api.ts` dagi mavjud `req()` yordamchisidan foydalaning. Barcha xatolar
`ApiError` bo'lib keladi: `error.code` — mashina kodi, `error.message` —
o'zbekcha matn (backend `detail.message_uz`). Mavjud metodlarga tegilmang.

**Ro'yxatdan o'tish** `POST /api/auth/register` (201 javob):

```json
{ "login": "ali_2026", "password": "maxfiy123", "first_name": "Ali" }
```

Javob (login bilan bir xil):
```json
{ "access_token": "<JWT>", "token_type": "bearer", "first_name": "Ali" }
```

**Kirish** `POST /api/auth/login` (200 javob):

```json
{ "login": "ali_2026", "password": "maxfiy123" }
```

Xato kodlari (`detail.error`):

| HTTP | error | Ma'nosi / foydalanuvchiga ko'rsatiladigan matn |
|---|---|---|
| 422 | `invalid_login` | Login 3–32 belgi, faqat lotin harflari, raqamlar va `_` |
| 422 | `weak_password` | Parol kamida 6 belgi |
| 409 | `login_taken` | Bu login band |
| 401 | `invalid_credentials` | Login yoki parol noto'g'ri (ataylab umumiy) |
| 503 | (matn) | Server sozlanmagan — administratorga xabar bering |

Login serverda kichik harflarga keltiriladi (`Ali_2026` = `ali_2026`).
`first_name` bo'sh bo'lsa server login'ni ism sifatida ishlatadi. JWT boshqa
Telegram o'quvchilar bilan **bir xil** — sinf tanlash, darslar, testlar,
yulduzchalar hammasi avtomatik ishlaydi. Yangi hisobda sinf tanlanmagan bo'ladi
va mavjud `GradePicker` onboarding oqimi ochiladi.

### 3) `api.ts` ga qo'shiladigan metodlar (mavjudlarini o'zgartirmasdan)

```ts
register: (body: { login: string; password: string; first_name: string }) =>
  req<{ access_token: string; first_name: string }>("/api/auth/register", {
    method: "POST",
    body,
  }),

passwordLogin: (body: { login: string; password: string }) =>
  req<{ access_token: string; first_name: string }>("/api/auth/login", {
    method: "POST",
    body,
  }),
```

### 4) `WebLogin.tsx` tuzilishi

- Yuqorida hozirgi Telegram widget (o'zgartirmang).
- Ajratgich ostida: `<button type="button">Menda Telegram yo'q</button>` —
  dizaynda ikkilamchi (text) uslubda, katta tugma bilan raqobatlashmasin.
- Bosilganda silliq ochiladigan panel:
  - Tab tugmalari: «Kirish» / «Ro'yxatdan o'tish».
  - **Kirish**: Login, Parol, «Kirish» tugmasi.
  - **Ro'yxatdan o'tish**: Ism (ixtiyoriy), Login, Parol, Parolni takrorlang,
    «Ro'yxatdan o'tish» tugmasi. Parollar mos kelmasa — client-side xato,
    so'rov yuborilmaydi.
- Login input: `trim()` + kichik harfga keltirish; client-side tekshiruv
  `/^[a-z0-9_]{3,32}$/` (server ham tekshiradi, bu faqat tez javob uchun).
- So'rov davomida tugma `disabled` + yuklanish holati; ikki marta bosish
  ikki so'rov yubormasin.
- Xato matni panel ichida qizil alert sifatida `ApiError.message` dan olinadi;
  `login_taken` bo'lsa «Ro'yxatdan o'tish» tabida qolib, login maydonini
  belgilang. Muvaffaqiyatda xatoni tozalang.
- Props: mavjud `onAuth(user)` saqlanadi, yangi
  `onPasswordAuth: (accessToken: string) => void` qo'shiladi.

### 5) `App.tsx` ulanishi

```tsx
const handlePasswordAuth = useCallback(
  async (accessToken: string) => {
    try {
      setError("");
      setPhase("busy");
      storeToken(accessToken);
      setToken(accessToken);
      setWebSession(true);
      await bootstrap(accessToken); // /api/me → onboarding yoki home
    } catch (e) {
      setError(describe(e));
      setPhase("web_login");
    }
  },
  [bootstrap],
);
```

Va renderda:

```tsx
<WebLogin onAuth={handleWebLogin} onPasswordAuth={handlePasswordAuth} error={error} />
```

`bootstrap()` allaqachon `needs_grade_selection` bo'lsa `GradePicker`ni
ochadi — bu qismni o'zgartirmang. Logout mavjud holatda tokenni tozalaydi.

### 6) Dizayn va animatsiya — «wow» daraja (majburiy)

Hozirgi implementatsiya funksional, lekin vizual jihatdan oddiy (statik karta +
`animate-fade-in`). Foydalanuvchi talabi: **kirish bo'limi silliq, boy
animatsiya bilan ochilsin va sayt premium ko'rinsin** — bu o'quvchilarga
loyiha darajasini ko'rsatadi. Quyidagilar majburiy.

**6.1 Kompozitsiya (desktop >= 1024px)**

- Ikki ustunli sahna: chapda brend paneli, o'ngda shisha (glassmorphism)
  kirish kartasi. Karta kengligi maksimum 440px.
- Chap panel: katta «EduQuest» logotipi, «O'rganish — endi o'yin!» shiori,
  1–11 sinf badge'i, suzuvchi fan chiplari (📚 Matematika, ➗ Hisob, 🔤 Ona
  tili) va qisqa ishonch qatori (masalan, «16 yulduz · 11 sinf · bitta
  progress»). Bu panel faqat bezak, hech qanday soxta statistika yozilmasin —
  faqat mahsulot faktlari.
- Mobil va planshetda (< 1024px) bitta ustun: ixcham animatsion sarlavha +
  to'liq kenglikdagi karta. Ortiqcha panel yashiriladi.

**6.2 Ochilish choreography (timeline)**

- Fon blob'lari 0–400ms ichida yumshoq paydo bo'ladi.
- Karta: `opacity 0→1`, `translateY(28px)→0`, `scale(.985)→1`, 620ms,
  `cubic-bezier(0.16, 1, 0.3, 1)`.
- Logo/ikonka: `scale(.6) rotate(-8deg) blur(6px)` holatdan normal holatga,
  520ms, 80ms kechikish.
- Sarlavha va tavsif 60ms stagger bilan pastdan ko'tariladi.
- Telegram widget, ajratgich chizig'i (`scaleX(0)→1`, 400ms) va «Menda
  Telegram yo'q» havolasi ketma-ket, 120ms farq bilan chiqadi.
- Hech qanday element sakrab joy almashmasin; barcha animatsiya
  `transform`/`opacity`/`filter` bilan.

**6.3 Panel va tab animatsiyasi**

- «Menda Telegram yo'q» bosilganda panel `grid-template-rows: 0fr → 1fr`
  (yoki o'lchangan max-height) bilan 340ms ochilsin; ichki qism
  `overflow: hidden`; chevron 180ms aylanadi. Yopilish ham silliq.
- Tab tugmalari ostida siljiydigan oq pill (indicator) — `translateX`,
  260ms; faol tab rangi/yog'du animatsiyali.
- Tab almashganda forma 6px siljish + fade (220ms), maydonlar 45ms stagger
  bilan chiqadi; balandlik sakrashi bo'lmasin.
- `role="tablist"`, `aria-selected`, klaviatura bilan tab almashish ishlaydi.

**6.4 Maydonlar va mikro-interaksiyalar**

- Har bir input chapida ikonka (IconUser/IconLock), label yuqorida.
- Focus: chegara `#3478F6`, 4px `rgba(52,120,246,.14)` ring, 180ms silliq;
  `caret-color: #3478F6`.
- Parol maydonida ko'z tugmasi (ko'rsatish/yashirish) — ikonka morph,
  `aria-label` bilan; Caps Lock yoqilganda kichik ogohlantirish (ixtiyoriy).
- Ro'yxatdan o'tishda parol kuchi indikatori: 3 segment, rang/kenglik
  animatsiyasi; minimal talab 6 belgi.
- Asosiy tugma: gradient `#3478F6 → #2563EB`, hover `translateY(-1px)` +
  soya, active `scale(.985)`, hover'da yengil sheen (600ms) sweep.
  Yuklanishda spinner + «Kirilmoqda...»; muvaffaqiyatda qisqa check-pop
  (320ms) va keyin App'ga o'tish.
- Xato: banner `translateY(-6px)+fade` (200ms), maydon chegarasi rose rang,
  yengil shake (3×4px, 220ms). `aria-live="polite"`.

**6.5 Fon va atmosfera**

- `#F7F9FC` asosida yumshoq gradient mesh: ko'k (`#3478F6`), binafsha
  (`#8B5CF6`), amber (`#FFD54F`) blob'lar, `blur(70px)`, 18–24s sekin
  suzish. Nozik grid/naqsh ustiga mask bilan — faqat bezak.
- Desktopda pointer harakatiga yengil parallax (maksimum 6px); touch
  qurilmalarda o'chirilgan. Karta 3D tilt (maksimum 4°) faqat desktopda.
- O'qish qulayligi birinchi o'rinda: matn kontrasti AA darajadan past
  bo'lmasin, fon kartani bosib ketmasin.

**6.6 Telegram widget**

- Widget iframe'ini stillash mumkin emas — uni oq pill konteyner ichiga
  (border, padding, soya) joylashtiring, shunda dizaynga singib ketadi.
- Widget uchun aniq balandlik zaxirasi qoldiring — yuklanishda layout
  sakramasin. `data-onauth` va tozalash mantiqi o'zgartirilmaydi.

**6.7 Performance va accessibility**

- Yangi npm paket qo'shilmang (framer-motion va h.k. yo'q) — CSS
  keyframes/transition yetarli. `index.css` ga yangi keyframe'larni
  qo'shing (`fadeIn`/`scaleIn`/`pulseGlow` mavjud).
- Faqat `transform`/`opacity`/`filter`; `will-change` faqat animatsiya
  paytida; 60fps; layout shift yo'q.
- `@media (prefers-reduced-motion: reduce)`: barcha dekorativ animatsiya
  o'chadi, oddiy 120ms fade qoladi; tilt/parallax o'chadi.
- `:focus-visible` halqalari, label-input bog'lanishi, xatolar uchun
  `aria-live`.

**6.8 «Wow» nazorat ro'yxati**

- [ ] Ochilishda ketma-ket, silliq choreography — sakrash/jank yo'q.
- [ ] Panel, tab va maydon animatsiyalari 60fps.
- [ ] Hover/focus/active/loading/success holatlari jonli va izchil.
- [ ] Mobil 360px va desktop 1440px da tekshirilgan.
- [ ] `prefers-reduced-motion` fallback ishlaydi.
- [ ] Natija skrinshotga olib ko'rsa bo'ladigan premium darajada.

### 7) Qabul mezonlari

1. `npm run build` xatosiz o'tadi (`tsc --noEmit` ham).
2. Brauzerda (Telegram tashqarisida) yangi hisob yaratish → sinf tanlash →
   darslar ochiladi; sahifa yangilanganda sessiya saqlanadi.
3. Chiqish → qayta kirish ishlaydi.
4. Noto'g'ri parol → «Login yoki parol noto'g'ri.» xatosi, sahifa buzilmaydi.
5. Band login → «Bu login allaqachon band. Boshqa login tanlang.»
6. Telegram widget avvalgidek ishlaydi (regressiya yo'q).
7. Dizayn mavjud uslubda, mobil va desktopda toza ko'rinadi.
8. 6-bo'limdagi animatsiya va «wow» ro'yxati to'liq bajarilgan; kirish
   sahnasi ochilganda silliq, hech qanday layout sakrashi yo'q.

### 8) Tegmaslik kerak bo'lgan narsalar

- `api.login` / `api.webLogin` va Telegram initData oqimi.
- Backend endpointlari, JWT saqlash mexanizmi, `GradePicker` mantiqi.
- `.env` fayllari va `VITE_API_URL`.
