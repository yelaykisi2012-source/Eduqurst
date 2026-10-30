/**
 * LessonPage.tsx — reads the lesson (explanation + materials), then the
 * pupil taps "O'qib bo'ldim" which records the view on the server (small
 * star reward) and unlocks the quiz button.
 */
import { useEffect, useState } from "react";
import { api, ApiError } from "../api";
import type { LessonDetail } from "../types";
import { BackButton } from "./SubjectLessons";

export default function LessonPage({
  token,
  lessonId,
  onBack,
  onStartQuiz,
  onViewed,
}: {
  token: string;
  lessonId: number;
  onBack: () => void;
  onStartQuiz: () => void;
  onViewed: () => void; // refresh home counts
}) {
  const [lesson, setLesson] = useState<LessonDetail | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [justEarned, setJustEarned] = useState(false);

  useEffect(() => {
    let alive = true;
    api
      .lesson(token, lessonId)
      .then((d) => alive && setLesson(d))
      .catch((e: unknown) =>
        alive && setError(e instanceof ApiError ? e.message : "Yuklab bo'lmadi"),
      );
    return () => {
      alive = false;
    };
  }, [token, lessonId]);

  const markViewed = async () => {
    setBusy(true);
    try {
      const r = await api.markViewed(token, lessonId);
      setLesson((l) => (l ? { ...l, viewed: true } : l));
      if (r.stars_granted) setJustEarned(true);
      onViewed();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Xatolik");
    } finally {
      setBusy(false);
    }
  };

  if (error)
    return (
      <section className="mt-6 rounded-2xl border-2 border-dashed border-rose-200 bg-rose-50 p-5 text-center">
        <p className="text-sm font-bold text-rose-700">Xatolik</p>
        <p className="mt-1 text-xs text-rose-500">{error}</p>
        <button onClick={onBack} className="mt-3 text-sm font-bold text-blue-500 underline">
          ← Orqaga
        </button>
      </section>
    );
  if (!lesson)
    return <p className="mt-8 text-center text-sm font-medium text-blue-500">Dars yuklanmoqda… ⏳</p>;

  return (
    <section className="mt-6">
      <BackButton onClick={onBack} />
      <p className="mt-2 text-xs font-bold uppercase tracking-wide text-blue-400">
        {lesson.subject_name} · {lesson.level_order}-bosqich
      </p>
      <h2 className="text-2xl font-extrabold text-blue-900">{lesson.title}</h2>

      <article className="mt-4 whitespace-pre-line rounded-2xl bg-white p-5 text-[15px] leading-relaxed text-slate-700 shadow-md">
        {lesson.explanation}
      </article>

      {lesson.materials.map((m) => (
        <div key={m.id} className="mt-3 rounded-2xl border-2 border-blue-100 bg-blue-50 p-4">
          {m.title && <p className="text-sm font-bold text-blue-800">📌 {m.title}</p>}
          {m.kind === "image" ? (
            <img src={m.content} alt={m.title} className="mt-2 w-full rounded-xl" />
          ) : (
            <p className="mt-1 whitespace-pre-line text-sm text-blue-900">{m.content}</p>
          )}
        </div>
      ))}

      <div className="mt-6 space-y-3">
        {!lesson.viewed ? (
          <button
            onClick={markViewed}
            disabled={busy}
            className="w-full rounded-2xl bg-gradient-to-br from-emerald-500 to-emerald-600 px-4 py-4 text-center text-base font-bold text-white shadow-md transition-transform active:scale-95 disabled:opacity-50"
          >
            {busy ? "Saqlanmoqda…" : "O'qib bo'ldim ✅"}
          </button>
        ) : (
          <>
            <p className="text-center text-sm font-semibold text-emerald-600">
              {justEarned ? "Barakalla! +⭐ qo'shib olindi" : "Bu dars o'qilgan ✅"}
            </p>
            <button
              onClick={onStartQuiz}
              className="w-full rounded-2xl bg-gradient-to-br from-blue-500 to-indigo-600 px-4 py-4 text-center text-base font-bold text-white shadow-md transition-transform active:scale-95"
            >
              Testni boshlash 🧩
            </button>
          </>
        )}
      </div>
    </section>
  );
}
