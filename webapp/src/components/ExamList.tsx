import { useCallback, useEffect, useState } from "react";
import { api, ApiError } from "../api";
import type { ExamCard } from "../types";
import Card from "./ui/Card";
import Button from "./ui/Button";
import Badge from "./ui/Badge";
import {
  IconExam,
  IconLock,
  IconTrophy,
  IconStar,
  IconArrowRight,
  IconRefresh,
} from "./ui/Icons";

interface ExamListProps {
  token: string;
  onOpen: (subjectId: number) => void;
}

/** The deadline is stored in UTC; pupils read it in their own calendar day. */
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

/**
 * ExamList — the second road to a certificate.
 *
 * A pupil who already knows the material but never sat every lesson can prove it
 * here: 20 of the hardest questions of that subject, 90%+ to pass, one month of
 * waiting after a failed try. Everything is decided by the server; this list only
 * mirrors what /api/exams reports.
 */
export default function ExamList({ token, onOpen }: ExamListProps) {
  const [cards, setCards] = useState<ExamCard[] | null>(null);
  const [error, setError] = useState("");
  const [retry, setRetry] = useState(0);

  const load = useCallback(async () => {
    setError("");
    try {
      setCards(await api.exams(token));
    } catch (e) {
      if (e instanceof ApiError && e.code === "grade_not_selected") {
        setError("Avval sinfingizni tanlang — imtihonlar shu sinf bo‘yicha tuziladi.");
      } else {
        setError(
          e instanceof ApiError
            ? e.message
            : "Imtihonlar ro‘yxatini yuklab bo‘lmadi. Internetni tekshiring.",
        );
      }
    }
  }, [token]);

  useEffect(() => {
    setCards(null);
    void load();
  }, [load, retry]);

  const readyCount = (cards ?? []).filter((c) => c.available).length;
  const passedCount = (cards ?? []).filter((c) => c.passed).length;

  return (
    <div className="mx-auto max-w-2xl animate-fade-in py-1 pb-32 sm:pb-12">
      {/* Explainer */}
      <Card
        variant="elevated"
        padding="none"
        className="p-3.5 sm:p-6 bg-gradient-to-br from-violet-600 via-indigo-600 to-blue-700 text-white border-0 shadow-sm"
      >
        <div className="flex items-start gap-3">
          <div className="flex h-11 w-11 sm:h-13 sm:w-13 shrink-0 items-center justify-center rounded-xl sm:rounded-2xl bg-white/20 backdrop-blur-md shadow-inner">
            <IconExam size={24} />
          </div>
          <div className="min-w-0">
            <h1 className="text-base sm:text-xl font-black leading-tight">
              Majburiy imtihon
            </h1>
            <p className="text-[11px] sm:text-xs font-medium text-indigo-100 mt-1 leading-snug">
              Darslarni o‘qimasangiz ham bilimingizni isbotlab sertifikat olishingiz
              mumkin. Fan bo‘yicha eng qiyin 20 savol, bitta imtihon.
            </p>
          </div>
        </div>

        <div className="mt-3.5 grid grid-cols-3 gap-2">
          {[
            { top: "20", bottom: "savol" },
            { top: "90%", bottom: "o‘tish bali" },
            { top: "30 kun", bottom: "qayta urinish" },
          ].map((item) => (
            <div
              key={item.bottom}
              className="rounded-xl bg-white/15 backdrop-blur-md border border-white/20 px-2 py-2 text-center"
            >
              <span className="block text-sm sm:text-lg font-black leading-none">
                {item.top}
              </span>
              <span className="block text-[9px] sm:text-[10px] font-bold text-indigo-100 mt-1">
                {item.bottom}
              </span>
            </div>
          ))}
        </div>

        <p className="mt-2.5 text-[10px] sm:text-[11px] font-semibold text-indigo-100/90 leading-snug">
          Baholash: 17–20 to‘g‘ri → <b>5</b> · 5–16 → <b>4</b> · 1–4 → <b>2.5</b>.
          90% dan past bo‘lsa sertifikat bir oyga kechikadi.
        </p>
      </Card>

      {/* State: loading / error / empty */}
      {error && (
        <Card className="mt-3.5 p-4 border-rose-200 bg-rose-50/50 text-center">
          <p className="text-xs font-bold text-rose-700">{error}</p>
          <Button
            variant="secondary"
            size="sm"
            className="mt-3"
            icon={<IconRefresh size={14} />}
            onClick={() => setRetry((v) => v + 1)}
          >
            Qayta urinish
          </Button>
        </Card>
      )}

      {cards === null && !error && (
        <div className="py-10 text-center">
          <div className="inline-block h-8 w-8 animate-spin rounded-full border-4 border-indigo-500 border-t-transparent" />
          <p className="mt-3 text-sm font-semibold text-slate-500">
            Imtihonlar sanab chiqilmoqda…
          </p>
        </div>
      )}

      {cards !== null && cards.length === 0 && !error && (
        <Card className="mt-3.5 p-6 text-center">
          <span className="text-4xl mb-2 block">🗂️</span>
          <h3 className="text-sm font-bold text-slate-800">Hozircha imtihon yo‘q</h3>
          <p className="mt-1.5 text-xs text-slate-500 leading-snug">
            Sizning sinfingizda imtihon uchun ochilgan fan topilmadi. Ustoz admin
            panelidan fan qo‘shgandan so‘ng imtihonlar shu yerda paydo bo‘ladi.
          </p>
        </Card>
      )}

      {cards !== null && cards.length > 0 && (
        <div className="mt-3.5 space-y-2.5">
          <div className="flex items-center justify-between px-0.5">
            <h2 className="text-xs sm:text-sm font-black text-slate-700">
              Fanlar bo‘yicha imtihonlar
            </h2>
            <span className="text-[10px] sm:text-[11px] font-bold text-slate-400">
              {passedCount}/{readyCount} topshirilgan
            </span>
          </div>

          {cards.map((card) => {
            const locked = Boolean(card.locked_until);
            const canStart = card.available && !locked;
            return (
              <Card
                key={card.subject_id}
                variant="default"
                className="p-3 sm:p-4"
              >
                <div className="flex items-start gap-2.5">
                  <span className="text-2xl shrink-0" aria-hidden>
                    {card.emoji}
                  </span>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-1.5 flex-wrap">
                      <h3 className="text-sm sm:text-base font-bold text-slate-900 truncate">
                        {card.subject_name}
                      </h3>
                      {card.passed && (
                        <Badge variant="emerald" size="sm" icon={<IconTrophy size={11} />}>
                          O‘tdi · baho {card.best_mark ?? "—"}
                        </Badge>
                      )}
                      {!card.passed && locked && (
                        <Badge variant="rose" size="sm" icon={<IconLock size={11} />}>
                          Qulflangan
                        </Badge>
                      )}
                      {!card.passed && !locked && !card.available && (
                        <Badge variant="slate" size="sm">
                          Tayyorlanmoqda
                        </Badge>
                      )}
                    </div>

                    <p className="mt-1 text-[11px] sm:text-xs font-semibold text-slate-500 leading-snug">
                      {card.passed ? (
                        <>
                          Eng yaxshi natija {card.best_score_percent}% · baho{" "}
                          {card.best_mark ?? "—"}
                          {card.certificate_code ? ` · sertifikat ${card.certificate_code}` : ""}
                        </>
                      ) : locked ? (
                        <>
                          {retryDay(card.locked_until as string)} sanasiga qadar qulflangan —
                          shu kundan keyin qayta urinib bo‘ladi.
                        </>
                      ) : card.available ? (
                        <>
                          {card.total} savol · 18 tasi to‘g‘ri bo‘lsa (90%) sertifikat
                          olinadi
                        </>
                      ) : (
                        <>
                          Admin hali {card.total}/20 savolni imtihonga belgilamagan — bu fan
                          ochilganda shu yerda ko‘rinadi.
                        </>
                      )}
                    </p>
                  </div>
                </div>

                <div className="mt-3 flex items-center justify-between gap-2">
                  {card.certificate_code ? (
                    <span className="inline-flex items-center gap-1 text-[10px] sm:text-[11px] font-bold text-amber-600">
                      <IconStar size={12} filled className="text-amber-500" />
                      Sertifikat rasmiylashtirilgan
                    </span>
                  ) : (
                    <span className="text-[10px] sm:text-[11px] font-semibold text-slate-400">
                      Muvaffaqiyatli imtihon — QR-kodli sertifikat
                    </span>
                  )}
                  <Button
                    variant={canStart ? "primary" : "secondary"}
                    size="sm"
                    disabled={!canStart}
                    onClick={() => onOpen(card.subject_id)}
                    iconRight={canStart ? <IconArrowRight size={13} /> : <IconLock size={12} />}
                  >
                    {card.passed
                      ? "Qayta urinish"
                      : canStart
                        ? "Imtihonni boshlash"
                        : locked
                          ? "Qulflangan"
                          : "Tayyor emas"}
                  </Button>
                </div>
              </Card>
            );
          })}
        </div>
      )}
    </div>
  );
}
