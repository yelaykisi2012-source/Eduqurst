/**
 * WebLogin.tsx — browser sign-in via the official Telegram Login Widget.
 *
 * Loads https://telegram.org/js/telegram-widget.js, which shows a
 * "Log in with Telegram" button. On success it calls the global
 * `onTelegramAuth(user)` with fields + a hash signed by Telegram; the backend
 * verifies that hash with our bot token before issuing a JWT.
 *
 * IMPORTANT: the widget only works on a domain registered for the bot in
 * BotFather (/setdomain), e.g. eduquest-mini-app-7o3hx1m5a24.qoder.website.
 */
import { useEffect, useRef } from "react";

import type { TelegramWebUser } from "../types";

const BOT_USERNAME = "Edi_Quest_bot";

export default function WebLogin({
  onAuth,
  error,
}: {
  onAuth: (user: TelegramWebUser) => void;
  error?: string;
}) {
  const boxRef = useRef<HTMLDivElement>(null);
  const authRef = useRef(onAuth);
  authRef.current = onAuth;

  useEffect(() => {
    const box = boxRef.current;
    if (!box) return;

    // telegram-widget.js looks this function up by name (data-onauth).
    window.onTelegramAuth = (user) => authRef.current(user as TelegramWebUser);

    const script = document.createElement("script");
    script.src = "https://telegram.org/js/telegram-widget.js?24";
    script.async = true;
    script.setAttribute("data-telegram-login", BOT_USERNAME);
    script.setAttribute("data-size", "large");
    script.setAttribute("data-radius", "12");
    script.setAttribute("data-onauth", "onTelegramAuth(user)");
    script.setAttribute("data-request-access", "write");
    box.appendChild(script);

    return () => {
      delete window.onTelegramAuth;
      box.innerHTML = "";
    };
  }, []);

  return (
    <section className="mt-6 rounded-3xl bg-white p-6 text-center shadow-md">
      <p className="text-4xl" aria-hidden>
        🔐
      </p>
      <h2 className="mt-2 text-xl font-extrabold text-blue-900">Telegram orqali kiring</h2>
      <p className="mt-2 text-sm leading-relaxed text-slate-500">
        Saytdan brauzerda foydalanmoqdasiz. Hisobingiz, sinfingiz va
        progress saqlanishi uchun Telegram hisobingiz bilan kiring.
      </p>

      <div ref={boxRef} className="mt-5 flex min-h-12 items-center justify-center" />

      <p className="mt-4 text-[11px] text-slate-400">
        Tugma ko‘rinmasa, sahifani yangilang yoki saytni{" "}
        <a
          className="font-semibold text-blue-500 underline"
          href={`https://t.me/${BOT_USERNAME}`}
          target="_blank"
          rel="noreferrer"
        >
          @{BOT_USERNAME}
        </a>{" "}
        orqali oching.
      </p>

      {error && (
        <p className="mt-4 rounded-xl border border-rose-200 bg-rose-50 px-3 py-2 text-xs font-semibold text-rose-700">
          {error}
        </p>
      )}
    </section>
  );
}
