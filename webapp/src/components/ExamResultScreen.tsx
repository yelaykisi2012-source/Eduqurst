import { useEffect, useState } from "react";
import { api, ApiError } from "../api";
import type { ExamResult } from "../types";
import Card from "./ui/Card";
import Button from "./ui/Button";
import {
  IconStar,
  IconTrophy,
  IconArrowRight,
  IconHelpCircle,
  IconChevronDown,
  IconDownload,
  IconFileText,
} from "./ui/Icons";

interface ExamResultScreenProps {
  token: string;
  result: ExamResult;
  onDone: () => void;
}

function retryDay(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "";
  return new Intl.DateTimeFormat("en-GB", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    timeZone: "Asia/Tashkent",
  }).format(date);
}

/** How many correct answers were needed — shown so a fail is easy to understand. */
function neededFor(total: number, percent: number): number {
  return Math.ceil((total * percent) / 100);
}

/**
 * ExamResultScreen — the verdict of the mandatory exam.
 *
 * A pass means two things at once: the 5-point mark and the certificate for this
 * subject. The PDF is the same QR-verified one the course route produces, so it is
 * offered right here; a fail states the retry date the server already fixed.
 */
export default function ExamResultScreen({
  token,
  result,
  onDone,
}: ExamResultScreenProps) {
  const mistakes = result.mistakes ?? [];
  const [showMistakes, setShowMistakes] = useState(false);
  const [busy, setBusy] = useState(false);
  const [downloaded, setDownloaded] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    window.Telegram?.WebApp?.HapticFeedback?.notificationOccurred(
      result.passed ? "success" : "error",
    );
  }, [result.passed]);

  const download = async () => {
    if (!result.certificate) return;
    setBusy(true);
    setError("");
    try {
      const { blob, fileName } = await api.downloadCertificate(
        token,
        result.certificate.subject_id,
      );
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = fileName;
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.setTimeout(() => URL.revokeObjectURL(url), 5000);
      setDownloaded(true);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Sertifikatni yuklab bo‘lmadi");
    } finally {
      setBusy(false);
    }
  };

  const required = neededFor(result.total_count, 90);

  return (
    <div className="mx-auto max-w-lg animate-scale-in py-2 pb-32 sm:pb-12">
      {/* Verdict */}
      <Card
        variant="elevated"
        className={`relative overflow-hidden p-4 sm:p-7 text-center text-white border-0 shadow-lg ${
          result.passed
            ? "bg-gradient-to-br from-emerald-500 via-teal-600 to-emerald-700"
            : "bg-gradient-to-br from-amber-500 via-orange-600 to-rose-700"
        }`}
      >
        <div className="mx-auto mb-2.5 flex h-14 w-14 sm:h-16 sm:w-16 items-center justify-center rounded-2xl bg-white/20 backdrop-blur-md text-3xl sm:text-4xl shadow-inner">
          <span aria-hidden>{result.passed ? "🎓" : "💪"}</span>
        </div>

        <h2 className="text-lg sm:text-2xl font-black tracking-tight leading-tight">
          {result.passed ? "Imtihondan o‘tdingiz!" : "Bu safar yetmadi"}
        </h2>
        <p className="mt-1.5 text-xs sm:text-sm font-semibold text-white/85">
          {result.message_uz}
        </p>

        <p className="mt-1 text-[11px] sm:text-xs font-bold text-white/75">
          {result.correct_count} / {result.total_count} to‘g‘ri · {result.score_percent}%
          {result.passed ? "" : ` · kamida ${required} ta kerak edi`}
        </p>

        {/* The 5-point mark, exactly as the teacher described it */}
        <div className="mt-3.5 inline-flex items-center gap-2 rounded-xl bg-white/25 backdrop-blur-md px-4 py-2 font-black text-white text-sm sm:text-base shadow-2xs">
          <IconTrophy size={18} className="text-amber-200" />
          <span>Baho: {result.mark}</span>
        </div>

        {result.passed && (
          <div className="mt-2.5 flex items-center justify-center gap-1.5 rounded-xl bg-white/15 px-3 py-1.5 text-[11px] sm:text-xs font-bold">
            <IconStar size={14} filled className="text-amber-300" />
            <span>
              +{result.stars_earned} yulduz (Jami: {result.stars_total}) · sertifikat
              rasmiylashtirildi
            </span>
          </div>
        )}

        {!result.passed && result.locked_until && (
          <div className="mt-2.5 flex items-center justify-center gap-1.5 rounded-xl bg-white/15 px-3 py-1.5 text-[11px] sm:text-xs font-bold">
            <span>🔒</span>
            <span>Qayta urinish: {retryDay(result.locked_until)} sanasidan</span>
          </div>
        )}
      </Card>

      {/* Certificate */}
      {result.passed && result.certificate && (
        <Card className="mt-4 p-3.5 sm:p-5 border-emerald-200 bg-emerald-50/60">
          <div className="flex items-start gap-3">
            <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-emerald-600 text-white">
              <IconFileText size={18} />
            </div>
            <div className="flex-1 min-w-0">
              <h3 className="text-sm font-black text-emerald-900">
                {result.certificate.subject_name} sertifikati
              </h3>
              <p className="mt-0.5 text-[11px] sm:text-xs font-semibold text-emerald-700 leading-snug">
                Majburiy imtihon bo‘yicha · baho {result.certificate.mark ?? result.mark} ·
                kod {result.certificate.code}
              </p>
              <p className="mt-0.5 text-[10px] sm:text-[11px] font-semibold text-emerald-600/80">
                PDF QR-kod bilan tasdiqlanadi — istalgan o‘rin tekshira oladi.
              </p>
            </div>
          </div>
          <div className="mt-3 flex flex-wrap gap-2">
            <Button
              variant="accent"
              size="sm"
              loading={busy}
              onClick={download}
              icon={busy ? undefined : <IconDownload size={14} />}
            >
              {downloaded ? "Qayta yuklash" : "Sertifikatni yuklash"}
            </Button>
            <a
              href={result.certificate.verify_url}
              target="_blank"
              rel="noreferrer"
              className="inline-flex items-center px-3 py-1.5 rounded-xl bg-white border border-emerald-200 text-[11px] sm:text-xs font-bold text-emerald-700 hover:bg-emerald-50 transition-colors"
            >
              Tasdiqlash sahifasi
            </a>
          </div>
          {error && (
            <p className="mt-2 text-[11px] font-bold text-rose-600">{error}</p>
          )}
        </Card>
      )}

      {/* Mistakes — the pupil can still learn from them during the lock month */}
      {mistakes.length > 0 && (
        <Card variant="default" className="mt-4 p-3.5 sm:p-5">
          <button
            type="button"
            onClick={() => setShowMistakes((v) => !v)}
            className="flex w-full items-center justify-between gap-2 cursor-pointer"
            aria-expanded={showMistakes}
          >
            <span className="flex items-center gap-1.5 text-xs sm:text-sm font-black text-slate-800">
              <IconHelpCircle size={16} className="text-rose-500" />
              Xatolarni ko‘rish ({mistakes.length})
            </span>
            <IconChevronDown
              size={16}
              className={`text-slate-400 transition-transform ${
                showMistakes ? "rotate-180" : ""
              }`}
            />
          </button>

          {showMistakes && (
            <ul className="mt-3 space-y-2.5">
              {mistakes.map((m, idx) => (
                <li
                  key={m.question_id}
                  className="rounded-xl bg-slate-50/80 border border-slate-200/70 p-2.5 sm:p-3"
                >
                  <p className="text-[11px] sm:text-xs font-bold text-slate-800 leading-snug">
                    {idx + 1}. {m.question_text}
                  </p>
                  <div className="mt-1.5 flex flex-wrap gap-1.5 text-[10px] sm:text-[11px] font-bold">
                    <span className="px-2 py-0.5 rounded-md bg-rose-50 text-rose-700 border border-rose-200/70">
                      Sizning javobingiz: {m.your_answer || "javob berilmagan"}
                    </span>
                    <span className="px-2 py-0.5 rounded-md bg-emerald-50 text-emerald-700 border border-emerald-200/70">
                      To‘g‘ri javob: {m.correct_answer || "—"}
                    </span>
                  </div>
                  {m.explanation && (
                    <p className="mt-1.5 text-[10px] sm:text-[11px] text-slate-500 leading-snug">
                      {m.explanation}
                    </p>
                  )}
                </li>
              ))}
            </ul>
          )}
        </Card>
      )}

      <div className="mt-4">
        <Button
          variant="primary"
          size="md"
          fullWidth
          onClick={onDone}
          iconRight={<IconArrowRight size={16} />}
        >
          Imtihonlar ro‘yxatiga qaytish
        </Button>
      </div>
    </div>
  );
}
