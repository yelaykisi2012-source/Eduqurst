/**
 * ResultScreen.tsx — shown right after a quiz submission.
 * Everything here comes from the SERVER's verdict (score, stars, unlock),
 * never from the client. Failing shows a supportive retry, never a punish.
 */
import type { QuizResult } from "../types";

export default function ResultScreen({
  result,
  onRetry,
  onContinue,
}: {
  result: QuizResult;
  onRetry: () => void;
  onContinue: () => void;
}) {
  return (
    <section className="mt-8 flex flex-col items-center">
      <div
        className={`w-full rounded-3xl p-6 text-center shadow-lg ${
          result.passed ? "bg-gradient-to-br from-emerald-500 to-teal-600" : "bg-gradient-to-br from-blue-500 to-indigo-600"
        }`}
      >
        <p className="text-5xl">{result.passed ? "🎉" : "💪"}</p>
        <p className="mt-3 text-xl font-extrabold text-white">{result.message_uz}</p>
        <p className="mt-1 text-sm font-semibold text-white/80">
          {result.correct_count}/{result.total_count} to'g'ri · {result.score_percent}%
        </p>

        {result.passed && (
          <p className="mt-4 inline-block rounded-full bg-white/20 px-5 py-2 text-lg font-extrabold text-white">
            +{result.stars_earned} ⭐ (jami: {result.stars_total})
          </p>
        )}

        {result.next_level_unlocked && (
          <p className="mt-3 text-sm font-bold text-white">🔓 Yangi bosqich ochildi!</p>
        )}

        {result.new_achievements.length > 0 && (
          <p className="mt-2 text-sm font-semibold text-amber-100">
            🏆 Yangi yutuq: {result.new_achievements.join(", ")}
          </p>
        )}
      </div>

      <div className="mt-6 w-full space-y-3">
        {!result.passed && (
          <button
            onClick={onRetry}
            className="w-full rounded-2xl bg-gradient-to-br from-blue-500 to-indigo-600 px-4 py-4 text-base font-bold text-white shadow-md transition-transform active:scale-95"
          >
            Qayta urinish 🔁
          </button>
        )}
        <button
          onClick={onContinue}
          className="w-full rounded-2xl bg-white px-4 py-4 text-base font-bold text-blue-700 shadow-md transition-transform active:scale-95"
        >
          Davom etish →
        </button>
      </div>
    </section>
  );
}
