import { useEffect, useState } from "react";
import { api, ApiError } from "../api";
import type { Quiz, QuizResult } from "../types";
import Card from "./ui/Card";
import Button from "./ui/Button";
import ProgressBar from "./ui/ProgressBar";
import {
  IconArrowLeft,
  IconArrowRight,
  IconCheck,
  IconSparkles,
} from "./ui/Icons";

interface QuizPageProps {
  token: string;
  lessonId: number;
  onBack: () => void;
  onResult: (result: QuizResult) => void;
}

const OPTION_LETTERS = ["A", "B", "C", "D", "E", "F"];

export default function QuizPage({
  token,
  lessonId,
  onBack,
  onResult,
}: QuizPageProps) {
  const [quiz, setQuiz] = useState<Quiz | null>(null);
  const [currentIndex, setCurrentIndex] = useState(0);
  const [answers, setAnswers] = useState<Record<number, number>>({}); // question_id -> option_id
  const [texts, setTexts] = useState<Record<number, string>>({}); // question_id -> typed answer
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let alive = true;
    api
      .quiz(token, lessonId)
      .then((q) => alive && setQuiz(q))
      .catch((e: unknown) =>
        alive && setError(e instanceof ApiError ? e.message : "Test yuklanmadi"),
      );
    return () => {
      alive = false;
    };
  }, [token, lessonId]);

  if (error && !quiz) {
    return (
      <div className="mx-auto max-w-2xl py-6 animate-fade-in text-center">
        <Card className="p-8">
          <span className="text-4xl mb-3 block">⚠️</span>
          <h3 className="text-lg font-bold text-slate-800">Xatolik yuz berdi</h3>
          <p className="mt-1 text-sm text-slate-500 mb-6">{error}</p>
          <Button variant="secondary" onClick={onBack}>
            Orqaga qaytish
          </Button>
        </Card>
      </div>
    );
  }

  if (!quiz) {
    return (
      <div className="mx-auto max-w-2xl py-12 text-center animate-fade-in">
        <div className="inline-block h-8 w-8 animate-spin rounded-full border-4 border-blue-500 border-t-transparent" />
        <p className="mt-4 text-sm font-semibold text-slate-500">Test savollari tayyorlanmoqda…</p>
      </div>
    );
  }

  const questions = quiz.questions;
  const currentQuestion = questions[currentIndex];
  const isFirst = currentIndex === 0;
  const isLast = currentIndex === questions.length - 1;

  // Question answering status
  const isQuestionAnswered = (qId: number, kind: string) => {
    if (kind === "text") return (texts[qId] ?? "").trim().length > 0;
    return answers[qId] !== undefined;
  };

  const answeredCount = questions.filter((q) => isQuestionAnswered(q.id, q.kind)).length;
  const allAnswered = answeredCount === questions.length;
  const progressPercent = Math.round(((currentIndex + 1) / questions.length) * 100);

  const handleSelectOption = (optionId: number) => {
    window.Telegram?.WebApp?.HapticFeedback?.selectionChanged();
    setAnswers((prev) => ({ ...prev, [currentQuestion.id]: optionId }));
  };

  const handleSubmit = async () => {
    if (!allAnswered || busy) return;
    setBusy(true);
    setError("");
    try {
      window.Telegram?.WebApp?.HapticFeedback?.notificationOccurred("warning");
      const result = await api.submitQuiz(token, lessonId, {
        idempotency_key: crypto.randomUUID(),
        answers: questions.map((q) =>
          q.kind === "text"
            ? { question_id: q.id, text: (texts[q.id] ?? "").trim() }
            : { question_id: q.id, option_id: answers[q.id] },
        ),
      });
      onResult(result);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Natijalarni yuborib bo‘lmadi");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="mx-auto max-w-2xl animate-fade-in py-1 pb-32 sm:pb-12">
      {/* Header bar: Back + Title */}
      <div className="flex items-center justify-between mb-2">
        <Button
          variant="ghost"
          size="sm"
          icon={<IconArrowLeft size={14} />}
          onClick={onBack}
        >
          Darsga qaytish
        </Button>
        <span className="text-[11px] sm:text-xs font-bold text-slate-400">
          O‘tish bali: {quiz.pass_threshold_percent}%
        </span>
      </div>

      {/* Progress header */}
      <Card variant="flat" padding="none" className="mb-3.5 sm:mb-6 p-3 sm:p-4 border border-slate-200">
        <div className="flex items-center justify-between text-xs font-extrabold text-slate-700 mb-1.5">
          <span>
            Savol <span className="text-blue-600 font-black">{currentIndex + 1}</span> / {questions.length}
          </span>
          <span className="text-slate-400 font-semibold text-[11px]">
            {answeredCount} ta belgilandi
          </span>
        </div>
        <ProgressBar value={progressPercent} size="sm" />
      </Card>

      {/* Single Question Card */}
      <Card variant="elevated" padding="none" className="mb-3.5 sm:mb-6 p-4 sm:p-6 animate-scale-in">
        <div className="flex items-start gap-2.5 mb-3 sm:mb-4">
          <span className="flex h-7 w-7 sm:h-8 sm:w-8 shrink-0 items-center justify-center rounded-lg sm:rounded-xl bg-blue-100 text-blue-700 font-black text-xs sm:text-sm">
            {currentIndex + 1}
          </span>
          <h2 className="text-sm sm:text-base font-bold text-slate-900 leading-snug">
            {currentQuestion.text}
          </h2>
        </div>

        {/* Optional Question Image */}
        {currentQuestion.image_url && (
          <div className="mb-4 overflow-hidden rounded-xl border border-slate-200 bg-slate-50">
            <img
              src={currentQuestion.image_url}
              alt=""
              className="w-full max-h-48 object-contain"
            />
          </div>
        )}

        {/* Options / Text Input */}
        {currentQuestion.kind === "text" ? (
          <div className="mt-4">
            <label className="block text-xs font-bold uppercase tracking-wider text-slate-400 mb-2">
              Javobingizni kiriting:
            </label>
            <input
              type="text"
              value={texts[currentQuestion.id] ?? ""}
              onChange={(e) =>
                setTexts((prev) => ({ ...prev, [currentQuestion.id]: e.target.value }))
              }
              placeholder="Javobni yozing…"
              className="w-full rounded-2xl border-2 border-slate-200 bg-white px-4 py-3 text-sm font-semibold text-slate-800 outline-none transition-colors focus:border-blue-500 focus:ring-2 focus:ring-blue-500/10"
            />
          </div>
        ) : (
          <div className="space-y-3 mt-4">
            {currentQuestion.options.map((opt, optIndex) => {
              const isSelected = answers[currentQuestion.id] === opt.id;
              const letter = OPTION_LETTERS[optIndex] || `${optIndex + 1}`;

              return (
                <button
                  key={opt.id}
                  onClick={() => handleSelectOption(opt.id)}
                  className={`w-full flex items-center gap-3.5 p-4 rounded-2xl border-2 text-left transition-all duration-150 cursor-pointer active:scale-[0.99] ${
                    isSelected
                      ? "border-blue-500 bg-blue-50/70 shadow-xs ring-2 ring-blue-500/10"
                      : "border-slate-100 bg-white hover:border-slate-300 hover:bg-slate-50/50"
                  }`}
                >
                  <span
                    className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-xl font-black text-xs transition-colors ${
                      isSelected
                        ? "bg-blue-600 text-white"
                        : "bg-slate-100 text-slate-600"
                    }`}
                  >
                    {letter}
                  </span>
                  <span
                    className={`flex-1 text-sm font-semibold leading-snug ${
                      isSelected ? "text-blue-900" : "text-slate-800"
                    }`}
                  >
                    {opt.text}
                  </span>
                  <div
                    className={`flex h-5 w-5 shrink-0 items-center justify-center rounded-full border transition-colors ${
                      isSelected
                        ? "border-blue-600 bg-blue-600 text-white"
                        : "border-slate-300 bg-white"
                    }`}
                  >
                    {isSelected && <IconCheck size={12} />}
                  </div>
                </button>
              );
            })}
          </div>
        )}
      </Card>

      {/* Error notification */}
      {error && (
        <p className="mb-4 text-center text-xs font-bold text-rose-600">
          {error}
        </p>
      )}

      {/* Navigation Buttons: Prev / Next / Submit */}
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
        ) : (
          <Button
            variant="accent"
            size="md"
            loading={busy}
            disabled={!allAnswered}
            onClick={handleSubmit}
            icon={<IconSparkles size={18} />}
          >
            {allAnswered ? "Yakunlash va yuborish 🚀" : "Barchasiga javob bering"}
          </Button>
        )}
      </div>

      {/* Quick Question Jump Dots */}
      <div className="mt-8 pt-6 border-t border-slate-200/60">
        <p className="text-center text-xs font-bold uppercase tracking-wider text-slate-400 mb-3">
          Barcha savollar
        </p>
        <div className="flex flex-wrap items-center justify-center gap-2">
          {questions.map((q, idx) => {
            const isAnswered = isQuestionAnswered(q.id, q.kind);
            const isCurrent = idx === currentIndex;

            return (
              <button
                key={q.id}
                onClick={() => setCurrentIndex(idx)}
                className={`flex h-8 w-8 items-center justify-center rounded-xl text-xs font-extrabold transition-all cursor-pointer ${
                  isCurrent
                    ? "bg-blue-600 text-white ring-2 ring-blue-500/30 scale-110 shadow-xs"
                    : isAnswered
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
