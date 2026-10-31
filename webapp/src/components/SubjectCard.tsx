import Card from "./ui/Card";
import ProgressBar from "./ui/ProgressBar";
import { IconChevronRight, IconCheck } from "./ui/Icons";

interface SubjectCardProps {
  title: string;
  emoji: string;
  totalLessons: number;
  passedLessons: number;
  onClick: () => void;
  accentColor?: string;
}

export default function SubjectCard({
  title,
  emoji,
  totalLessons,
  passedLessons,
  onClick,
}: SubjectCardProps) {
  const percent = totalLessons > 0 ? Math.round((passedLessons / totalLessons) * 100) : 0;
  const isCompleted = totalLessons > 0 && passedLessons === totalLessons;
  const hasLessons = totalLessons > 0;

  return (
    <Card
      variant="interactive"
      padding="none"
      onClick={onClick}
      className="group relative overflow-hidden p-3 sm:p-4 transition-all duration-150 hover:-translate-y-0.5 active:scale-[0.99]"
    >
      <div className="flex items-center gap-3 sm:gap-3.5">
        {/* Emoji / Icon Container */}
        <div className="flex h-11 w-11 sm:h-12 sm:w-12 shrink-0 items-center justify-center rounded-xl sm:rounded-2xl bg-gradient-to-br from-blue-50 to-indigo-50/80 border border-blue-100/70 text-2xl sm:text-3xl shadow-2xs group-hover:scale-105 transition-transform">
          <span aria-hidden>{emoji}</span>
        </div>

        {/* Title & Info */}
        <div className="flex-1 min-w-0">
          <div className="flex items-center justify-between gap-1.5">
            <h3 className="text-sm sm:text-base font-bold text-slate-900 group-hover:text-blue-600 transition-colors truncate">
              {title}
            </h3>
            {isCompleted && (
              <span className="shrink-0 flex items-center gap-1 rounded-full bg-emerald-50 px-2 py-0.5 text-[10px] sm:text-[11px] font-bold text-emerald-600 border border-emerald-200">
                <IconCheck size={11} />
                <span>Bajarildi</span>
              </span>
            )}
          </div>

          <p className="text-[11px] sm:text-xs font-medium text-slate-400 mt-0.5 truncate">
            {hasLessons
              ? `${passedLessons} / ${totalLessons} dars yakunlangan`
              : "Darslar tayyorlanmoqda"}
          </p>

          {/* Progress bar */}
          {hasLessons && (
            <div className="mt-2">
              <ProgressBar
                value={percent}
                size="sm"
                gradient={isCompleted ? "emerald" : "blue"}
              />
            </div>
          )}
        </div>

        {/* Chevron arrow */}
        <div className="flex h-7 w-7 sm:h-8 sm:w-8 shrink-0 items-center justify-center rounded-lg sm:rounded-xl text-slate-300 group-hover:text-blue-600 group-hover:translate-x-0.5 transition-all">
          <IconChevronRight size={16} />
        </div>
      </div>
    </Card>
  );
}
