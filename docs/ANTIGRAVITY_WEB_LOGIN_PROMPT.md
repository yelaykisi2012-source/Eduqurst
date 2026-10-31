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

### 6) Qabul mezonlari

1. `npm run build` xatosiz o'tadi (`tsc --noEmit` ham).
2. Brauzerda (Telegram tashqarisida) yangi hisob yaratish → sinf tanlash →
   darslar ochiladi; sahifa yangilanganda sessiya saqlanadi.
3. Chiqish → qayta kirish ishlaydi.
4. Noto'g'ri parol → «Login yoki parol noto'g'ri.» xatosi, sahifa buzilmaydi.
5. Band login → «Bu login allaqachon band. Boshqa login tanlang.»
6. Telegram widget avvalgidek ishlaydi (regressiya yo'q).
7. Dizayn mavjud uslubda, mobil va desktopda toza ko'rinadi.

### 7) Tegmaslik kerak bo'lgan narsalar

- `api.login` / `api.webLogin` va Telegram initData oqimi.
- Backend endpointlari, JWT saqlash mexanizmi, `GradePicker` mantiqi.
- `.env` fayllari va `VITE_API_URL`.
