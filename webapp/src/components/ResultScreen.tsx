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
    <div className="mx-auto max-w-lg animate-scale-in py-2 pb-32 sm:pb-12">
      {/* Result Card */}
      <Card
        variant="elevated"
        className={`relative overflow-hidden p-4 sm:p-7 text-center text-white border-0 shadow-lg ${
          isPassed
            ? "bg-gradient-to-br from-emerald-500 via-teal-600 to-emerald-700"
            : "bg-gradient-to-br from-blue-600 via-indigo-600 to-blue-800"
        }`}
      >
        {/* Glow badge / Icon */}
        <div className="mx-auto mb-2.5 flex h-14 w-14 sm:h-16 sm:w-16 items-center justify-center rounded-2xl bg-white/20 backdrop-blur-md text-3xl sm:text-4xl shadow-inner">
          <span aria-hidden>{isPassed ? "🎉" : "💪"}</span>
        </div>

        {/* Message */}
        <h2 className="text-lg sm:text-2xl font-black tracking-tight text-white leading-tight">
          {result.message_uz}
        </h2>

        <p className="mt-1.5 text-xs sm:text-sm font-semibold text-white/85">
          {result.correct_count} / {result.total_count} ta to‘g‘ri javob · {result.score_percent}% natija
        </p>

        {/* Stars pill */}
        {isPassed && (
          <div className="mt-3.5 inline-flex items-center gap-1.5 rounded-xl bg-white/25 backdrop-blur-md px-4 py-2 font-black text-white text-sm sm:text-base shadow-2xs">
            <IconStar size={18} filled className="text-amber-300" />
            <span>+{result.stars_earned} ⭐ mukofot (Jami: {result.stars_total})</span>
          </div>
        )}

        {/* Next level unlock */}
        {result.next_level_unlocked && (
          <div className="mt-3 flex items-center justify-center gap-1.5 rounded-xl bg-white/15 px-3 py-1.5 text-[11px] sm:text-xs font-bold text-white">
            <IconSparkles size={14} />
            <span>Yangi dars bosqichi ochildi!</span>
          </div>
        )}

        {/* Achievements */}
        {result.new_achievements.length > 0 && (
          <div className="mt-3 flex items-center justify-center gap-1.5 rounded-xl bg-amber-400/20 px-3 py-1.5 text-[11px] sm:text-xs font-bold text-amber-200">
            <IconTrophy size={14} />
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
      <div className="mt-4 space-y-2">
        {!isPassed && (
          <Button
            variant="primary"
            size="md"
            fullWidth
            onClick={onRetry}
            icon={<IconRefresh size={16} />}
          >
            Qayta topshirish 🔁
          </Button>
        )}

        <Button
          variant={isPassed ? "accent" : "secondary"}
          size="md"
          fullWidth
          onClick={onContinue}
          iconRight={<IconArrowRight size={16} />}
        >
          {isPassed ? "Davom etish →" : "Darslarga qaytish"}
        </Button>
      </div>
    </div>
  );
}
