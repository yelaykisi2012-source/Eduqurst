/**
 * QuizPage.tsx — the test itself.
 *
 * Rules mirrored from the backend:
 * - options never carry the correct-answer flag; grading is server-side;
 * - every attempt sends a fresh idempotency key (crypto.randomUUID) so a
 *   double-tap can never grant stars twice;
 * - failing is safe: the result screen offers a free retry.
 */
import { useEffect, useState } from "react";
import { api, ApiError } from "../api";
import type { Quiz } from "../types";
import { BackButton } from "./SubjectLessons";

export default function QuizPage({
  token,
  lessonId,
  onBack,
  onResult,
}: {
  token: string;
  lessonId: number;
  onBack: () => void;
  onResult: (r: Awaited<ReturnType<typeof api.submitQuiz>>) => void;
}) {
  const [quiz, setQuiz] = useState<Quiz | null>(null);
  const [answers, setAnswers] = useState<Record<number, number>>({}); // qid -> optionId
  const [texts, setTexts] = useState<Record<number, string>>({}); // qid -> typed answer
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let alive = true;
    api
      .quiz(token, lessonId)
      .then((q) => alive && setQuiz(q))
      .catch((e: unknown) =>
        alive && setError(e instanceof ApiError ? e.message : "Yuklab bo'lmadi"),
      );
    return () => {
      alive = false;
    };
  }, [token, lessonId]);

  const answeredCount = quiz
    ? quiz.questions.filter(
        (q) => (q.kind === "text" ? (texts[q.id] ?? "").trim() : answers[q.id] !== undefined),
      ).length
    : 0;
  const allAnswered = quiz ? answeredCount === quiz.questions.length : false;

  const submit = async () => {
    if (!quiz || !allAnswered || busy) return;
    setBusy(true);
    setError("");
    try {
      const result = await api.submitQuiz(token, lessonId, {
        idempotency_key: crypto.randomUUID(),
        answers: quiz.questions.map((q) =>
          q.kind === "text"
            ? { question_id: q.id, text: (texts[q.id] ?? "").trim() }
            : { question_id: q.id, option_id: answers[q.id] },
        ),
      });
      onResult(result);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Yuborib bo'lmadi");
    } finally {
      setBusy(false);
    }
  };

  if (error && !quiz)
    return (
      <section className="mt-6 rounded-2xl border-2 border-dashed border-rose-200 bg-rose-50 p-5 text-center">
        <p className="text-sm font-bold text-rose-700">Xatolik</p>
        <p className="mt-1 text-xs text-rose-500">{error}</p>
        <button onClick={onBack} className="mt-3 text-sm font-bold text-blue-500 underline">
          ← Orqaga
        </button>
      </section>
    );
  if (!quiz)
    return <p className="mt-8 text-center text-sm font-medium text-blue-500">Test yuklanmoqda… ⏳</p>;

  return (
    <section className="mt-6">
      <BackButton onClick={onBack} />
      <h2 className="mt-2 text-xl font-extrabold text-blue-900">{quiz.lesson_title}</h2>
      <p className="mt-1 text-xs font-semibold text-blue-400">
        {answeredCount}/{quiz.questions.length} savolga javob berildi ·
        o'tish uchun {quiz.pass_threshold_percent}% kerak
      </p>

      <div className="mt-4 space-y-4">
        {quiz.questions.map((q, qi) => (
          <div key={q.id} className="rounded-2xl bg-white p-4 shadow-md">
            <p className="text-sm font-bold text-blue-900">
              {qi + 1}. {q.text}
            </p>
            {q.image_url && (
              <img src={q.image_url} alt="" className="mt-2 max-h-40 rounded-xl" />
            )}
            {q.kind === "text" ? (
              <input
                value={texts[q.id] ?? ""}
                onChange={(e) => setTexts((t) => ({ ...t, [q.id]: e.target.value }))}
                placeholder="Javobingizni yozing…"
                className="mt-3 w-full rounded-xl border-2 border-blue-200 px-3 py-2 text-sm outline-none focus:border-blue-500"
              />
            ) : (
              <div className="mt-3 space-y-2">
                {q.options.map((o) => {
                  const picked = answers[q.id] === o.id;
                  return (
                    <button
                      key={o.id}
                      onClick={() => setAnswers((a) => ({ ...a, [q.id]: o.id }))}
                      className={`w-full rounded-xl border-2 px-3 py-2.5 text-left text-sm font-semibold transition-colors ${
                        picked
                          ? "border-blue-600 bg-blue-600 text-white"
                          : "border-blue-100 bg-blue-50 text-blue-900"
                      }`}
                    >
                      {picked ? "● " : "○ "}
                      {o.text}
                    </button>
                  );
                })}
              </div>
            )}
          </div>
        ))}
      </div>

      {error && <p className="mt-3 text-center text-sm font-semibold text-rose-600">{error}</p>}

      <button
        onClick={submit}
        disabled={!allAnswered || busy}
        className="mt-5 w-full rounded-2xl bg-gradient-to-br from-emerald-500 to-emerald-600 px-4 py-4 text-center text-base font-bold text-white shadow-md transition-transform active:scale-95 disabled:opacity-40"
      >
        {busy ? "Tekshirilmoqda…" : allAnswered ? "Javoblarni yuborish 🚀" : "Hammasiga javob bering 🙂"}
      </button>
    </section>
  );
}
