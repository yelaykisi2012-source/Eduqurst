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
      onClick={onClick}
      className="group relative overflow-hidden p-5 transition-all duration-200 hover:-translate-y-0.5"
    >
      <div className="flex items-start gap-4">
        {/* Emoji / Icon Container */}
        <div className="flex h-14 w-14 shrink-0 items-center justify-center rounded-2xl bg-gradient-to-br from-blue-50 to-indigo-50/80 border border-blue-100/60 text-3xl shadow-xs group-hover:scale-105 transition-transform">
          <span aria-hidden>{emoji}</span>
        </div>

        {/* Title & Info */}
        <div className="flex-1 min-w-0">
          <div className="flex items-center justify-between gap-2">
            <h3 className="text-base sm:text-lg font-bold text-slate-900 group-hover:text-blue-600 transition-colors truncate">
              {title}
            </h3>
            {isCompleted && (
              <span className="flex items-center gap-1 rounded-full bg-emerald-50 px-2 py-0.5 text-[11px] font-bold text-emerald-600 border border-emerald-200">
                <IconCheck size={12} />
                <span>Bajarildi</span>
              </span>
            )}
          </div>

          <p className="mt-1 text-xs font-medium text-slate-500">
            {hasLessons
              ? `${passedLessons} / ${totalLessons} dars tugatilgan`
              : "Darslar tayyorlanmoqda"}
          </p>

          {/* Progress bar */}
          {hasLessons && (
            <div className="mt-3">
              <ProgressBar
                value={percent}
                size="sm"
                gradient={isCompleted ? "emerald" : "blue"}
              />
            </div>
          )}
        </div>

        {/* Chevron arrow */}
        <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-xl text-slate-300 group-hover:text-blue-600 group-hover:translate-x-1 transition-all">
          <IconChevronRight size={18} />
        </div>
      </div>
    </Card>
  );
}
