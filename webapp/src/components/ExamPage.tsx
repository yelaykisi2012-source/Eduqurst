import { useEffect, useState } from "react";
import { api, ApiError } from "../api";
import type { ExamPaper, ExamResult } from "../types";
import type { AnswerState } from "../answering";
import {
  EMPTY_STATE,
  answeredCount,
  isAnswered,
  toPayload,
  withMatch,
} from "../answering";
import Card from "./ui/Card";
import Button from "./ui/Button";
import ProgressBar from "./ui/ProgressBar";
import AnswerInputs from "./AnswerInputs";
import {
  IconArrowLeft,
  IconArrowRight,
  IconExam,
  IconLock,
  IconSparkles,
} from "./ui/Icons";

interface ExamPageProps {
  token: string;
  subjectId: number;
  onBack: () => void;
  onResult: (result: ExamResult) => void;
}

/**
 * ExamPage — the mandatory exam paper.
 *
 * The server freezes the paper on the first call, so a refresh or an accidental
 * back-tap never reshuffles the questions and never loses the answered ones the
 * pupil already gave (they stay in this screen until submit). Submitting twice
 * returns the recorded result — the attempt id is the idempotency key.
 */
export default function ExamPage({
  token,
  subjectId,
  onBack,
  onResult,
}: ExamPageProps) {
  const [paper, setPaper] = useState<ExamPaper | null>(null);
  const [currentIndex, setCurrentIndex] = useState(0);
  const [state, setState] = useState<AnswerState>(EMPTY_STATE);
  const [error, setError] = useState("");
  const [blocked, setBlocked] = useState<{ text: string; locked: boolean } | null>(null);
  const [busy, setBusy] = useState(false);
  const [confirming, setConfirming] = useState(false);

  useEffect(() => {
    let alive = true;
    api
      .examPaper(token, subjectId)
      .then((p) => {
        if (!alive) return;
        setPaper(p);
        window.Telegram?.WebApp?.HapticFeedback?.impactOccurred("medium");
      })
      .catch((e: unknown) => {
        if (!alive) return;
        if (e instanceof ApiError && (e.code === "exam_locked" || e.code === "exam_not_configured")) {
          setBlocked({ text: e.message, locked: e.code === "exam_locked" });
        } else {
          setError(e instanceof ApiError ? e.message : "Imtihon yuklanmadi");
        }
      });
    return () => {
      alive = false;
    };
  }, [token, subjectId]);

  if (blocked) {
    return (
      <div className="mx-auto max-w-lg py-8 animate-fade-in text-center">
        <Card className="p-6 sm:p-8 border-amber-200 bg-amber-50/60">
          <span className="text-4xl mb-3 block">
            {blocked.locked ? "🔒" : "🧩"}
          </span>
          <h3 className="text-base font-black text-slate-800">
            {blocked.locked ? "Imtihon vaqtincha qulflangan" : "Imtihon hali tayyor emas"}
          </h3>
          <p className="mt-2 text-xs sm:text-sm font-semibold text-slate-600 leading-snug">
            {blocked.text}
          </p>
          <Button variant="primary" size="sm" className="mt-5" onClick={onBack}>
            Ro‘yxatga qaytish
          </Button>
        </Card>
      </div>
    );
  }

  if (error) {
    return (
      <div className="mx-auto max-w-lg py-8 animate-fade-in text-center">
        <Card className="p-6 sm:p-8 border-rose-200 bg-rose-50/50">
          <span className="text-4xl mb-3 block">⚠️</span>
          <h3 className="text-base font-bold text-rose-800">Xatolik yuz berdi</h3>
          <p className="mt-2 text-xs text-rose-600">{error}</p>
          <Button variant="secondary" size="sm" className="mt-5" onClick={onBack}>
            Orqaga qaytish
          </Button>
        </Card>
      </div>
    );
  }

  if (!paper) {
    return (
      <div className="mx-auto max-w-2xl py-12 text-center animate-fade-in">
        <div className="inline-block h-8 w-8 animate-spin rounded-full border-4 border-indigo-500 border-t-transparent" />
        <p className="mt-4 text-sm font-semibold text-slate-500">
          Imtihon varaqasi tayyorlanmoqda…
        </p>
      </div>
    );
  }

  const questions = paper.questions;
  const currentQuestion = questions[currentIndex];
  const isFirst = currentIndex === 0;
  const isLast = currentIndex === questions.length - 1;
  const answered = answeredCount(questions, state);
  const allAnswered = answered === questions.length;
  const progressPercent = Math.round(((currentIndex + 1) / questions.length) * 100);

  const handleSelectOption = (optionId: number) => {
    window.Telegram?.WebApp?.HapticFeedback?.selectionChanged();
    setState((prev) => ({
      ...prev,
      options: { ...prev.options, [currentQuestion.id]: optionId },
    }));
  };

  const handleText = (value: string) =>
    setState((prev) => ({ ...prev, texts: { ...prev.texts, [currentQuestion.id]: value } }));

  const handleMatch = (promptId: number, optionId: number | null) => {
    window.Telegram?.WebApp?.HapticFeedback?.selectionChanged();
    setState((prev) => withMatch(prev, currentQuestion.id, promptId, optionId));
  };

  const handleClearMatches = () =>
    setState((prev) => ({ ...prev, matches: { ...prev.matches, [currentQuestion.id]: {} } }));

  const handleSubmit = async () => {
    if (!allAnswered || busy) return;
    setBusy(true);
    setError("");
    setConfirming(false);
    try {
      window.Telegram?.WebApp?.HapticFeedback?.notificationOccurred("warning");
      const result = await api.submitExam(token, subjectId, {
        attempt_id: paper.attempt_id,
        answers: toPayload(questions, state),
      });
      onResult(result);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Natijani yuborib bo‘lmadi");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="mx-auto max-w-2xl animate-fade-in py-1 pb-32 sm:pb-12">
      {/* Header: back + rules chip */}
      <div className="flex items-center justify-between gap-2 mb-2">
        <Button variant="ghost" size="sm" icon={<IconArrowLeft size={14} />} onClick={onBack}>
          Ro‘yxatga qaytish
        </Button>
        <span className="flex items-center gap-1 text-[11px] sm:text-xs font-black text-indigo-600">
          <IconExam size={13} />
          {paper.subject_name}
        </span>
      </div>

      {/* Exam banner: what passes, what happens after */}
      <Card
        variant="elevated"
        padding="none"
        className="mb-3 p-2.5 sm:p-3.5 border-indigo-200 bg-indigo-50/70"
      >
        <p className="text-[11px] sm:text-xs font-bold text-indigo-900 leading-snug">
          {questions.length} savol · {paper.pass_percent}% va undan yuqori bo‘lsa imtihondan
          o‘tasiz va sertifikat olasiz.
        </p>
        <p className="mt-0.5 text-[10px] sm:text-[11px] font-semibold text-indigo-700/80 leading-snug">
          O‘tmagan bo‘lsangiz bu fan imtihoni {paper.lock_days} kunga qulflanadi. Javoblaringiz
          yuborilmaguncha saqlanib turadi.
        </p>
      </Card>

      {/* Progress */}
      <Card
        variant="flat"
        padding="none"
        className="mb-3.5 sm:mb-5 p-3 sm:p-4 border border-slate-200"
      >
        <div className="flex items-center justify-between text-xs font-extrabold text-slate-700 mb-1.5">
          <span>
            Savol{" "}
            <span className="text-indigo-600 font-black">{currentIndex + 1}</span> /{" "}
            {questions.length}
          </span>
          <span className="text-slate-400 font-semibold text-[11px]">
            {answered} ta javob berilgan
          </span>
        </div>
        <ProgressBar value={progressPercent} size="sm" />
      </Card>

      {/* Current question */}
      <Card
        variant="elevated"
        padding="none"
        className="mb-3.5 sm:mb-5 p-4 sm:p-6 animate-scale-in"
      >
        <div className="flex items-start gap-2.5 mb-3 sm:mb-4">
          <span className="flex h-7 w-7 sm:h-8 sm:w-8 shrink-0 items-center justify-center rounded-lg sm:rounded-xl bg-indigo-100 text-indigo-700 font-black text-xs sm:text-sm">
            {currentIndex + 1}
          </span>
          <h2 className="text-sm sm:text-base font-bold text-slate-900 leading-snug">
            {currentQuestion.text}
          </h2>
        </div>

        {currentQuestion.image_url && (
          <div className="mb-4 overflow-hidden rounded-xl border border-slate-200 bg-slate-50">
            <img
              src={currentQuestion.image_url}
              alt=""
              className="w-full max-h-48 object-contain"
            />
          </div>
        )}

        <AnswerInputs
          question={currentQuestion}
          state={state}
          onSelectOption={handleSelectOption}
          onText={handleText}
          onMatch={handleMatch}
          onClearMatches={handleClearMatches}
        />
      </Card>

      {error && (
        <p className="mb-4 text-center text-xs font-bold text-rose-600">{error}</p>
      )}

      {/* One-way door: the exam cannot be retaken for a month, so ask first */}
      {confirming && (
        <Card className="mb-3.5 p-4 border-rose-200 bg-rose-50/60">
          <h3 className="text-sm font-black text-rose-800">Natijani yuborasizmi?</h3>
          <p className="mt-1 text-[11px] sm:text-xs font-semibold text-rose-700 leading-snug">
            Yuborgandan keyin javoblarni o‘zgartirib bo‘lmaydi. 90% dan past bo‘lsa bu
            fan imtihoni {paper.lock_days} kunga qulflanadi.
          </p>
          <div className="mt-3 flex gap-2">
            <Button variant="secondary" size="sm" onClick={() => setConfirming(false)}>
              Yo‘q, qaytay
            </Button>
            <Button
              variant="accent"
              size="sm"
              loading={busy}
              onClick={handleSubmit}
              icon={<IconSparkles size={14} />}
            >
              Ha, yuborish
            </Button>
          </div>
        </Card>
      )}

      {/* Navigation */}
      <div className="flex items-center justify-between gap-3">
        <Button
          variant="secondary"
          size="md"
          disabled={isFirst}
          onClick={() => setCurrentIndex((prev) => prev - 1)}
          icon={<IconArrowLeft size={16} />}
        >
          Oldingi
        </Button>

        {!isLast ? (
          <Button
            variant="primary"
            size="md"
            onClick={() => setCurrentIndex((prev) => prev + 1)}
            iconRight={<IconArrowRight size={16} />}
          >
            Keyingi savol
          </Button>
        ) : !confirming ? (
          <Button
            variant="accent"
            size="md"
            disabled={!allAnswered}
            onClick={() => setConfirming(true)}
            icon={<IconExam size={16} />}
          >
            {allAnswered ? "Yakunlash" : `Qolgan savol: ${questions.length - answered}`}
          </Button>
        ) : (
          <Button
            variant="accent"
            size="md"
            disabled={!allAnswered}
            onClick={() => setConfirming(true)}
            icon={<IconLock size={15} />}
          >
            Tasdiqlash
          </Button>
        )}
      </div>

      {/* Jump dots */}
      <div className="mt-8 pt-6 border-t border-slate-200/60">
        <p className="text-center text-xs font-bold uppercase tracking-wider text-slate-400 mb-3">
          Imtihon varaqasi
        </p>
        <div className="flex flex-wrap items-center justify-center gap-2">
          {questions.map((q, idx) => {
            const isDone = isAnswered(q, state);
            const isCurrent = idx === currentIndex;
            return (
              <button
                key={q.id}
                onClick={() => setCurrentIndex(idx)}
                className={`flex h-8 w-8 items-center justify-center rounded-xl text-xs font-extrabold transition-all cursor-pointer ${
                  isCurrent
                    ? "bg-indigo-600 text-white ring-2 ring-indigo-500/30 scale-110 shadow-xs"
                    : isDone
                      ? "bg-emerald-100 text-emerald-800 border border-emerald-300"
                      : "bg-slate-100 text-slate-500 hover:bg-slate-200"
                }`}
              >
                {idx + 1}
              </button>
            );
          })}
        </div>
      </div>
    </div>
  );
}
