import { useEffect, useRef, useState, useCallback } from "react";
import type { TelegramWebUser } from "../types";
import Card from "./ui/Card";
import Button from "./ui/Button";
import {
  IconLock,
  IconExternalLink,
  IconUser,
  IconCheck,
  IconEye,
  IconEyeOff,
  IconChevronDown,
  IconSparkles,
  IconGraduationCap,
  IconStar,
} from "./ui/Icons";
import { api, ApiError } from "../api";

const BOT_USERNAME = "Edi_Quest_bot";
const LOGIN_REGEX = /^[a-z0-9_]{3,32}$/;

interface WebLoginProps {
  onAuth: (user: TelegramWebUser) => void;
  onPasswordAuth: (accessToken: string) => void;
  error?: string;
}

export default function WebLogin({ onAuth, onPasswordAuth, error }: WebLoginProps) {
  const boxRef = useRef<HTMLDivElement>(null);
  const cardRef = useRef<HTMLDivElement>(null);
  const authRef = useRef(onAuth);
  authRef.current = onAuth;

  // Form states
  const [showPasswordForm, setShowPasswordForm] = useState(false);
  const [tab, setTab] = useState<"login" | "register">("login");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [firstName, setFirstName] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [showConfirmPassword, setShowConfirmPassword] = useState(false);
  const [formError, setFormError] = useState("");
  const [busy, setBusy] = useState(false);
  const [isSuccess, setIsSuccess] = useState(false);

  // Parallax & 3D tilt states (desktop only)
  const [tilt, setTilt] = useState({ x: 0, y: 0 });
  const loginInputRef = useRef<HTMLInputElement>(null);

  // Telegram Login Widget initialization
  useEffect(() => {
    const box = boxRef.current;
    if (!box) return;

    window.onTelegramAuth = (user) => authRef.current(user as TelegramWebUser);

    const script = document.createElement("script");
    script.src = "https://telegram.org/js/telegram-widget.js?24";
    script.async = true;
    script.setAttribute("data-telegram-login", BOT_USERNAME);
    script.setAttribute("data-size", "large");
    script.setAttribute("data-radius", "16");
    script.setAttribute("data-onauth", "onTelegramAuth(user)");
    script.setAttribute("data-request-access", "write");
    box.appendChild(script);

    return () => {
      delete window.onTelegramAuth;
      box.innerHTML = "";
    };
  }, []);

  // Desktop 3D tilt calculation
  const handleMouseMove = useCallback((e: React.MouseEvent<HTMLDivElement>) => {
    // Only apply on screens >= 1024px and not touch
    if (window.innerWidth < 1024) return;
    const card = cardRef.current;
    if (!card) return;
    const rect = card.getBoundingClientRect();
    const x = e.clientX - rect.left - rect.width / 2;
    const y = e.clientY - rect.top - rect.height / 2;
    // max 3.5 deg tilt
    const tiltX = -(y / (rect.height / 2)) * 3.5;
    const tiltY = (x / (rect.width / 2)) * 3.5;
    setTilt({ x: tiltX, y: tiltY });
  }, []);

  const handleMouseLeave = useCallback(() => {
    setTilt({ x: 0, y: 0 });
  }, []);

  // Password strength calculation for registration
  const getPasswordStrength = (pwd: string) => {
    if (pwd.length < 6) return { score: 0, label: "Juda qisqa (kamida 6 ta)", color: "bg-slate-200" };
    let score = 1;
    if (pwd.length >= 8) score++;
    if (/[0-9]/.test(pwd) && /[a-zA-Z]/.test(pwd)) score++;
    if (/[^a-zA-Z0-9]/.test(pwd) || pwd.length >= 12) score = 3;

    if (score === 1) return { score: 1, label: "Zaif", color: "bg-rose-500" };
    if (score === 2) return { score: 2, label: "O‘rtacha", color: "bg-amber-500" };
    return { score: 3, label: "Kuchli", color: "bg-emerald-500" };
  };

  const strength = getPasswordStrength(password);

  const handlePasswordSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setFormError("");

    const cleanLogin = username.trim().toLowerCase();

    if (!cleanLogin) {
      setFormError("Iltimos, login kiriting.");
      return;
    }

    if (!LOGIN_REGEX.test(cleanLogin)) {
      setFormError("Login 3–32 belgi, faqat lotin harflari, raqamlar va _ bo‘lishi kerak.");
      return;
    }

    if (password.length < 6) {
      setFormError("Parol kamida 6 ta belgidan iborat bo‘lishi kerak.");
      return;
    }

    if (tab === "register" && password !== confirmPassword) {
      setFormError("Kiritilgan parollar bir-biriga mos kelmadi.");
      return;
    }

    setBusy(true);
    try {
      if (tab === "login") {
        const res = await api.passwordLogin({
          login: cleanLogin,
          password,
        });
        setIsSuccess(true);
        setTimeout(() => {
          onPasswordAuth(res.access_token);
        }, 300);
      } else {
        const res = await api.register({
          login: cleanLogin,
          password,
          first_name: firstName.trim(),
        });
        setIsSuccess(true);
        setTimeout(() => {
          onPasswordAuth(res.access_token);
        }, 300);
      }
    } catch (err) {
      if (err instanceof ApiError) {
        setFormError(err.message);
        if (err.code === "login_taken") {
          setTab("register");
          loginInputRef.current?.focus();
        }
      } else {
        setFormError("Serverga bog‘lanib bo‘lmadi. Qaytadan urinib ko‘ring.");
      }
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="relative min-h-[82dvh] flex items-center justify-center px-4 py-8 overflow-hidden">
      {/* Background soft mesh blobs */}
      <div className="pointer-events-none absolute -top-24 -left-24 h-96 w-96 rounded-full bg-blue-400/20 blur-[80px] animate-blob-1" />
      <div className="pointer-events-none absolute top-1/2 -right-24 h-[420px] w-[420px] rounded-full bg-purple-400/20 blur-[90px] animate-blob-2" />
      <div className="pointer-events-none absolute -bottom-20 left-1/3 h-80 w-80 rounded-full bg-amber-300/20 blur-[80px] animate-blob-3" />

      {/* Main 2-column container on desktop (>= 1024px) */}
      <div className="relative z-10 w-full max-w-5xl mx-auto flex flex-col lg:flex-row items-center justify-center gap-8 lg:gap-14">
        {/* ================= LEFT BRAND PANEL (Desktop only) ================= */}
        <div className="hidden lg:flex flex-col flex-1 max-w-lg space-y-6 text-left">
          {/* Brand header */}
          <div className="space-y-3">
            <div className="inline-flex items-center gap-2 px-3.5 py-1.5 rounded-full bg-blue-50 text-blue-700 border border-blue-200/80 text-xs font-black shadow-xs">
              <IconSparkles size={14} className="text-blue-500" />
              <span>EduQuest Ta'lim Platformasi</span>
            </div>

            <h1 className="text-4xl xl:text-5xl font-black text-slate-900 tracking-tight leading-[1.15]">
              O‘rganish — <br />
              <span className="bg-gradient-to-r from-blue-600 via-indigo-600 to-purple-600 bg-clip-text text-transparent">
                endi o‘yin!
              </span>
            </h1>

            <p className="text-base text-slate-600 leading-relaxed max-w-md">
              1-sinfdan 11-sinfgacha bo‘lgan o‘quvchilar uchun qiziqarli darslar, interaktiv testlar va yulduzli mukofotlar tizimi.
            </p>
          </div>

          {/* Floating subject pill badges */}
          <div className="flex flex-wrap gap-2.5 pt-2">
            <span className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-2xl bg-white border border-slate-200 shadow-xs text-xs font-extrabold text-slate-700">
              📚 Matematika
            </span>
            <span className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-2xl bg-white border border-slate-200 shadow-xs text-xs font-extrabold text-slate-700">
              🔤 Ona tili
            </span>
            <span className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-2xl bg-white border border-slate-200 shadow-xs text-xs font-extrabold text-slate-700">
              🇬🇧 Ingliz tili
            </span>
          </div>

          {/* Trust line */}
          <div className="flex items-center gap-4 pt-3 border-t border-slate-200/70 text-xs font-bold text-slate-500">
            <div className="flex items-center gap-1.5">
              <IconStar size={16} filled className="text-amber-500" />
              <span>Yulduzli mukofotlar</span>
            </div>
            <span>·</span>
            <div className="flex items-center gap-1.5">
              <IconGraduationCap size={16} className="text-blue-600" />
              <span>11 sinf</span>
            </div>
            <span>·</span>
            <span>Bitta yagona progress</span>
          </div>
        </div>

        {/* ================= RIGHT CARD (Glassmorphism & Tilt) ================= */}
        <div
          ref={cardRef}
          onMouseMove={handleMouseMove}
          onMouseLeave={handleMouseLeave}
          style={{
            transform: `perspective(1000px) rotateX(${tilt.x}deg) rotateY(${tilt.y}deg)`,
            transition: tilt.x === 0 ? "transform 0.4s ease-out" : "transform 0.1s ease-out",
          }}
          className="w-full max-w-[440px] animate-card-enter will-change-transform"
        >
          <Card
            variant="elevated"
            className="p-6 sm:p-8 bg-white/95 backdrop-blur-xl border border-slate-100/90 shadow-2xl shadow-blue-500/10 rounded-3xl"
          >
            {/* Logo / Header icon with smooth entrance */}
            <div className="mx-auto mb-4 flex h-16 w-16 items-center justify-center rounded-3xl bg-gradient-to-br from-blue-500 to-indigo-600 text-white shadow-lg shadow-blue-500/25 animate-icon-entrance">
              <IconLock size={28} />
            </div>

            <h2 className="text-2xl font-black text-slate-900 tracking-tight text-center">
              EduQuest tizimiga kirish
            </h2>

            <p className="mt-1.5 text-xs sm:text-sm text-slate-500 text-center leading-relaxed">
              Darslarni boshlash va natijalaringizni saqlash uchun hisobingizga kiring.
            </p>

            {/* Telegram Widget Container: Enclosed in clean white container with reserved height */}
            <div className="mt-6 flex flex-col items-center justify-center min-h-[56px] rounded-2xl bg-slate-50/80 p-2.5 border border-slate-200/80">
              <div ref={boxRef} className="flex items-center justify-center" />
            </div>

            {/* Official bot link */}
            <div className="mt-3 text-center text-[11px] text-slate-400">
              <span>Tugma ko‘rinmasa, bot orqali oching: </span>
              <a
                href={`https://t.me/${BOT_USERNAME}`}
                target="_blank"
                rel="noreferrer"
                className="font-bold text-blue-600 hover:underline inline-flex items-center gap-0.5"
              >
                <span>@{BOT_USERNAME}</span>
                <IconExternalLink size={10} />
              </a>
            </div>

            {/* Animated Divider */}
            <div className="relative my-6">
              <div className="absolute inset-0 flex items-center">
                <div className="w-full border-t border-slate-200 animate-divider" />
              </div>
              <div className="relative flex justify-center text-xs">
                <button
                  type="button"
                  onClick={() => {
                    setShowPasswordForm((prev) => !prev);
                    setFormError("");
                  }}
                  className="group inline-flex items-center gap-1.5 bg-white px-3.5 py-1 text-xs font-bold text-blue-600 hover:text-blue-700 hover:bg-blue-50/50 rounded-full border border-slate-200 shadow-2xs transition-all cursor-pointer select-none"
                >
                  <span>{showPasswordForm ? "Telegram bilan kirish" : "«Menda Telegram yo‘q»"}</span>
                  <IconChevronDown
                    size={14}
                    className={`transition-transform duration-200 ${
                      showPasswordForm ? "rotate-180 text-blue-700" : "text-slate-400 group-hover:text-blue-600"
                    }`}
                  />
                </button>
              </div>
            </div>

            {/* Smooth Accordion Panel (grid-template-rows transition) */}
            <div
              className={`accordion-grid ${
                showPasswordForm ? "accordion-grid-open" : "accordion-grid-closed"
              }`}
            >
              <div className="overflow-hidden">
                <div className="pt-2 text-left">
                  {/* Sliding Tabs */}
                  <div
                    role="tablist"
                    aria-label="Kirish usullari"
                    className="relative grid grid-cols-2 p-1 bg-slate-100 rounded-2xl mb-5 select-none"
                  >
                    {/* Sliding white pill indicator */}
                    <div
                      className="absolute inset-y-1 w-[calc(50%-4px)] rounded-xl bg-white shadow-xs transition-transform duration-260 ease-out"
                      style={{
                        transform: tab === "login" ? "translateX(4px)" : "translateX(calc(100% + 4px))",
                      }}
                    />

                    <button
                      type="button"
                      role="tab"
                      aria-selected={tab === "login"}
                      onClick={() => {
                        setTab("login");
                        setFormError("");
                      }}
                      className={`relative z-10 py-2 text-xs sm:text-sm font-bold text-center rounded-xl transition-colors cursor-pointer ${
                        tab === "login" ? "text-blue-600" : "text-slate-500 hover:text-slate-800"
                      }`}
                    >
                      Kirish
                    </button>
                    <button
                      type="button"
                      role="tab"
                      aria-selected={tab === "register"}
                      onClick={() => {
                        setTab("register");
                        setFormError("");
                      }}
                      className={`relative z-10 py-2 text-xs sm:text-sm font-bold text-center rounded-xl transition-colors cursor-pointer ${
                        tab === "register" ? "text-blue-600" : "text-slate-500 hover:text-slate-800"
                      }`}
                    >
                      Ro‘yxatdan o‘tish
                    </button>
                  </div>

                  {/* Form */}
                  <form onSubmit={handlePasswordSubmit} className="space-y-3.5">
                    {tab === "register" && (
                      <div className="animate-fade-in">
                        <label className="block text-xs font-bold uppercase tracking-wider text-slate-500 mb-1">
                          Ismingiz (ixtiyoriy)
                        </label>
                        <div className="relative">
                          <span className="absolute inset-y-0 left-0 pl-3.5 flex items-center pointer-events-none text-slate-400">
                            <IconUser size={18} />
                          </span>
                          <input
                            type="text"
                            value={firstName}
                            onChange={(e) => setFirstName(e.target.value)}
                            placeholder="Ali"
                            autoComplete="name"
                            className="w-full rounded-2xl border-2 border-slate-200 bg-white pl-10 pr-4 py-2.5 text-base text-slate-900 outline-none transition-all duration-180 focus:border-[#3478F6] focus:ring-4 focus:ring-blue-500/15 placeholder:text-slate-400 caret-[#3478F6]"
                          />
                        </div>
                      </div>
                    )}

                    <div>
                      <label className="block text-xs font-bold uppercase tracking-wider text-slate-500 mb-1">
                        Login
                      </label>
                      <div className="relative">
                        <span className="absolute inset-y-0 left-0 pl-3.5 flex items-center pointer-events-none text-slate-400">
                          <IconUser size={18} />
                        </span>
                        <input
                          ref={loginInputRef}
                          type="text"
                          value={username}
                          onChange={(e) => setUsername(e.target.value)}
                          placeholder="ali_2026"
                          autoComplete="username"
                          required
                          className="w-full rounded-2xl border-2 border-slate-200 bg-white pl-10 pr-4 py-2.5 text-base text-slate-900 outline-none transition-all duration-180 focus:border-[#3478F6] focus:ring-4 focus:ring-blue-500/15 placeholder:text-slate-400 lowercase caret-[#3478F6]"
                        />
                      </div>
                      <span className="block text-[11px] font-medium text-slate-400 mt-1">
                        3–32 belgi (faqat kichik lotin harflari, raqamlar va _)
                      </span>
                    </div>

                    <div>
                      <label className="block text-xs font-bold uppercase tracking-wider text-slate-500 mb-1">
                        Parol
                      </label>
                      <div className="relative">
                        <span className="absolute inset-y-0 left-0 pl-3.5 flex items-center pointer-events-none text-slate-400">
                          <IconLock size={18} />
                        </span>
                        <input
                          type={showPassword ? "text" : "password"}
                          value={password}
                          onChange={(e) => setPassword(e.target.value)}
                          placeholder="Kamida 6 belgi"
                          autoComplete={tab === "login" ? "current-password" : "new-password"}
                          required
                          className="w-full rounded-2xl border-2 border-slate-200 bg-white pl-10 pr-11 py-2.5 text-base text-slate-900 outline-none transition-all duration-180 focus:border-[#3478F6] focus:ring-4 focus:ring-blue-500/15 placeholder:text-slate-400 caret-[#3478F6]"
                        />
                        <button
                          type="button"
                          onClick={() => setShowPassword((prev) => !prev)}
                          aria-label={showPassword ? "Parolni yashirish" : "Parolni ko‘rsatish"}
                          className="absolute inset-y-0 right-0 pr-3.5 flex items-center text-slate-400 hover:text-slate-600 transition-colors cursor-pointer"
                        >
                          {showPassword ? <IconEyeOff size={18} /> : <IconEye size={18} />}
                        </button>
                      </div>

                      {/* Password strength bar in register mode */}
                      {tab === "register" && password.length > 0 && (
                        <div className="mt-2 space-y-1 animate-fade-in">
                          <div className="flex gap-1.5 h-1.5 w-full">
                            <div
                              className={`flex-1 rounded-full transition-all duration-300 ${
                                strength.score >= 1 ? strength.color : "bg-slate-200"
                              }`}
                            />
                            <div
                              className={`flex-1 rounded-full transition-all duration-300 ${
                                strength.score >= 2 ? strength.color : "bg-slate-200"
                              }`}
                            />
                            <div
                              className={`flex-1 rounded-full transition-all duration-300 ${
                                strength.score >= 3 ? strength.color : "bg-slate-200"
                              }`}
                            />
                          </div>
                          <span className="text-[10px] font-bold text-slate-500">
                            Parol darajasi: <span className="font-extrabold">{strength.label}</span>
                          </span>
                        </div>
                      )}
                    </div>

                    {tab === "register" && (
                      <div className="animate-fade-in">
                        <label className="block text-xs font-bold uppercase tracking-wider text-slate-500 mb-1">
                          Parolni tasdiqlang
                        </label>
                        <div className="relative">
                          <span className="absolute inset-y-0 left-0 pl-3.5 flex items-center pointer-events-none text-slate-400">
                            <IconLock size={18} />
                          </span>
                          <input
                            type={showConfirmPassword ? "text" : "password"}
                            value={confirmPassword}
                            onChange={(e) => setConfirmPassword(e.target.value)}
                            placeholder="Parolni qayta kiriting"
                            autoComplete="new-password"
                            required
                            className="w-full rounded-2xl border-2 border-slate-200 bg-white pl-10 pr-11 py-2.5 text-base text-slate-900 outline-none transition-all duration-180 focus:border-[#3478F6] focus:ring-4 focus:ring-blue-500/15 placeholder:text-slate-400 caret-[#3478F6]"
                          />
                          <button
                            type="button"
                            onClick={() => setShowConfirmPassword((prev) => !prev)}
                            aria-label={showConfirmPassword ? "Parolni yashirish" : "Parolni ko‘rsatish"}
                            className="absolute inset-y-0 right-0 pr-3.5 flex items-center text-slate-400 hover:text-slate-600 transition-colors cursor-pointer"
                          >
                            {showConfirmPassword ? <IconEyeOff size={18} /> : <IconEye size={18} />}
                          </button>
                        </div>
                      </div>
                    )}

                    {/* Form Error Alert with light shake */}
                    {formError && (
                      <div
                        role="alert"
                        aria-live="polite"
                        className="rounded-2xl border border-rose-200 bg-rose-50/90 p-3 text-xs font-bold text-rose-700 animate-shake"
                      >
                        {formError}
                      </div>
                    )}

                    {/* Submit Button */}
                    <div className="pt-2">
                      <Button
                        type="submit"
                        variant="primary"
                        size="md"
                        fullWidth
                        loading={busy}
                        disabled={busy || isSuccess}
                        icon={
                          isSuccess ? (
                            <IconCheck size={18} />
                          ) : tab === "login" ? (
                            <IconUser size={16} />
                          ) : (
                            <IconCheck size={16} />
                          )
                        }
                        className="shadow-md shadow-blue-500/25 hover:shadow-lg hover:shadow-blue-500/35 transition-all"
                      >
                        {isSuccess
                          ? "Muvaffaqiyatli! Kirilmoqda…"
                          : busy
                            ? "Tekshirilmoqda…"
                            : tab === "login"
                              ? "Tizimga kirish"
                              : "Ro‘yxatdan o‘tish"}
                      </Button>
                    </div>
                  </form>
                </div>
              </div>
            </div>

            {/* Global/external error alert */}
            {error && !showPasswordForm && (
              <div
                role="alert"
                aria-live="polite"
                className="mt-4 rounded-2xl border border-rose-200 bg-rose-50 p-3 text-xs font-bold text-rose-700 animate-fade-in"
              >
                {error}
              </div>
            )}
          </Card>
        </div>
      </div>
    </div>
  );
}
