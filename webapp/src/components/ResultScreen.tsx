import { useEffect } from "react";
import type { QuizResult } from "../types";
import Card from "./ui/Card";
import Button from "./ui/Button";
import {
  IconStar,
  IconTrophy,
  IconRefresh,
  IconArrowRight,
  IconSparkles,
} from "./ui/Icons";

interface ResultScreenProps {
  result: QuizResult;
  onRetry: () => void;
  onContinue: () => void;
}

export default function ResultScreen({
  result,
  onRetry,
  onContinue,
}: ResultScreenProps) {
  const isPassed = result.passed;

  useEffect(() => {
    if (isPassed) {
      window.Telegram?.WebApp?.HapticFeedback?.notificationOccurred("success");
    } else {
      window.Telegram?.WebApp?.HapticFeedback?.notificationOccurred("error");
    }
  }, [isPassed]);

  return (
    <div className="mx-auto max-w-xl animate-scale-in py-6">
      {/* Result Card */}
      <Card
        variant="elevated"
        className={`relative overflow-hidden p-8 text-center text-white border-0 shadow-xl ${
          isPassed
            ? "bg-gradient-to-br from-emerald-500 via-teal-600 to-emerald-700"
            : "bg-gradient-to-br from-blue-600 via-indigo-600 to-blue-800"
        }`}
      >
        {/* Glow badge / Icon */}
        <div className="mx-auto mb-4 flex h-20 w-20 items-center justify-center rounded-3xl bg-white/20 backdrop-blur-md text-4xl shadow-inner">
          <span aria-hidden>{isPassed ? "🎉" : "💪"}</span>
        </div>

        {/* Message */}
        <h2 className="text-2xl sm:text-3xl font-black tracking-tight text-white">
          {result.message_uz}
        </h2>

        <p className="mt-2 text-sm font-semibold text-white/80">
          {result.correct_count} / {result.total_count} ta to‘g‘ri javob · {result.score_percent}% natija
        </p>

        {/* Stars pill */}
        {isPassed && (
          <div className="mt-5 inline-flex items-center gap-2 rounded-2xl bg-white/25 backdrop-blur-md px-6 py-2.5 font-extrabold text-white text-lg shadow-sm">
            <IconStar size={22} filled className="text-amber-300" />
            <span>+{result.stars_earned} ⭐ mukofot (Jami: {result.stars_total})</span>
          </div>
        )}

        {/* Next level unlock */}
        {result.next_level_unlocked && (
          <div className="mt-4 flex items-center justify-center gap-2 rounded-xl bg-white/15 px-4 py-2 text-xs font-bold text-white">
            <IconSparkles size={16} />
            <span>Yangi dars bosqichi ochildi!</span>
          </div>
        )}

        {/* Achievements */}
        {result.new_achievements.length > 0 && (
          <div className="mt-4 flex items-center justify-center gap-2 rounded-xl bg-amber-400/20 px-4 py-2 text-xs font-bold text-amber-200">
            <IconTrophy size={16} />
            <span>
              Yangi yutuq:{" "}
              {(result.new_achievement_titles.length
                ? result.new_achievement_titles
                : result.new_achievements
              ).join(", ")}
            </span>
          </div>
        )}
      </Card>

      {/* Action Buttons */}
      <div className="mt-6 space-y-3">
        {!isPassed && (
          <Button
            variant="primary"
            size="lg"
            fullWidth
            onClick={onRetry}
            icon={<IconRefresh size={18} />}
          >
            Qayta topshirish 🔁
          </Button>
        )}

        <Button
          variant={isPassed ? "accent" : "secondary"}
          size="lg"
          fullWidth
          onClick={onContinue}
          iconRight={<IconArrowRight size={18} />}
        >
          {isPassed ? "Davom etish →" : "Darslarga qaytish"}
        </Button>
      </div>
    </div>
  );
}
