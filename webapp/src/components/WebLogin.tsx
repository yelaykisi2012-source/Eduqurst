import { useEffect, useRef } from "react";
import type { TelegramWebUser } from "../types";
import Card from "./ui/Card";
import { IconLock, IconExternalLink } from "./ui/Icons";

const BOT_USERNAME = "Edi_Quest_bot";

interface WebLoginProps {
  onAuth: (user: TelegramWebUser) => void;
  error?: string;
}

export default function WebLogin({ onAuth, error }: WebLoginProps) {
  const boxRef = useRef<HTMLDivElement>(null);
  const authRef = useRef(onAuth);
  authRef.current = onAuth;

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

  return (
    <div className="mx-auto max-w-md animate-fade-in py-8">
      <Card variant="elevated" className="p-8 text-center bg-white">
        <div className="mx-auto mb-4 flex h-16 w-16 items-center justify-center rounded-3xl bg-blue-50 text-blue-600 shadow-xs">
          <IconLock size={32} />
        </div>

        <h2 className="text-xl sm:text-2xl font-black text-slate-900">
          EduQuest tizimiga kirish
        </h2>

        <p className="mt-2 text-xs sm:text-sm text-slate-500 leading-relaxed">
          Saytdan to‘liq foydalanish va dars progressini saqlash uchun Telegram hisobingiz orqali kiring.
        </p>

        <div
          ref={boxRef}
          className="mt-6 flex min-h-12 items-center justify-center"
        />

        <div className="mt-6 pt-5 border-t border-slate-100 text-[11px] text-slate-400">
          <p>
            Kirish tugmasi chiqmasa, rasmiy bot orqali oching:
          </p>
          <a
            href={`https://t.me/${BOT_USERNAME}`}
            target="_blank"
            rel="noreferrer"
            className="mt-1 inline-flex items-center gap-1 font-bold text-blue-600 hover:underline"
          >
            <span>@{BOT_USERNAME}</span>
            <IconExternalLink size={12} />
          </a>
        </div>

        {error && (
          <div className="mt-4 rounded-2xl border border-rose-200 bg-rose-50 p-3 text-xs font-bold text-rose-700">
            {error}
          </div>
        )}
      </Card>
    </div>
  );
}
