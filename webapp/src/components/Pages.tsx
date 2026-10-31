import type { Profile, Progress } from "../types";
import Card from "./ui/Card";
import Button from "./ui/Button";
import Badge from "./ui/Badge";
import ProgressBar from "./ui/ProgressBar";
import {
  IconTrophy,
  IconCheck,
  IconGraduationCap,
  IconLock,
} from "./ui/Icons";

/** Achievements / Yutuqlar Page */
export function AchievementsPage({ progress }: { progress: Progress | null }) {
  const earnedCount = progress?.achievements.filter((a) => a.earned).length ?? 0;
  const totalCount = progress?.achievements.length ?? 0;
  const percent = totalCount > 0 ? Math.round((earnedCount / totalCount) * 100) : 0;

  return (
    <div className="mx-auto max-w-2xl animate-fade-in py-1 pb-32 sm:pb-12">
      {/* Header Banner */}
      <Card variant="elevated" className="mb-3.5 sm:mb-6 p-3.5 sm:p-6 bg-gradient-to-br from-indigo-600 to-purple-700 text-white border-0 shadow-sm">
        <div className="flex items-center gap-3">
          <div className="flex h-11 w-11 sm:h-13 sm:w-13 items-center justify-center rounded-xl sm:rounded-2xl bg-white/20 backdrop-blur-md text-2xl sm:text-3xl shadow-inner shrink-0">
            <IconTrophy size={24} />
          </div>
          <div className="flex-1 min-w-0">
            <span className="text-[10px] sm:text-xs font-bold uppercase tracking-wider text-indigo-200">
              Yutuqlar kolleksiyasi
            </span>
            <h1 className="text-base sm:text-xl font-black text-white leading-tight truncate">
              Mukofotlar va Medallar
            </h1>
            <p className="text-[11px] sm:text-xs font-medium text-indigo-100 mt-0.5 truncate">
              {earnedCount} / {totalCount} ta yutuq · ⭐ {progress?.stars_total ?? 0} yulduz
            </p>
          </div>
        </div>

        <div className="mt-3.5">
          <div className="flex justify-between text-[11px] sm:text-xs font-bold text-indigo-100 mb-1">
            <span>To‘plangan yutuqlar</span>
            <span>{percent}%</span>
          </div>
          <div className="h-1.5 sm:h-2 w-full rounded-full bg-white/20 overflow-hidden">
            <div
              className="h-full bg-amber-400 rounded-full transition-all duration-500"
              style={{ width: `${percent}%` }}
            />
          </div>
        </div>
      </Card>

      {/* Achievements List */}
      <div className="space-y-2 sm:space-y-3">
        {(progress?.achievements ?? []).map((item) => (
          <Card
            key={item.code}
            variant="default"
            className={`p-2.5 sm:p-4 flex items-center gap-3 transition-all ${
              item.earned
                ? "bg-white border-amber-200/70 shadow-2xs hover:border-amber-300"
                : "bg-slate-50/70 border-slate-200/60 opacity-60"
            }`}
          >
            <div
              className={`flex h-10 w-10 sm:h-12 sm:w-12 shrink-0 items-center justify-center rounded-xl text-2xl shadow-2xs ${
                item.earned
                  ? "bg-amber-50 text-amber-500 border border-amber-200/80"
                  : "bg-slate-100 text-slate-400 border border-slate-200 grayscale"
              }`}
            >
              <span aria-hidden>{item.icon}</span>
            </div>

            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-1.5 flex-wrap">
                <h3 className="text-xs sm:text-sm font-bold text-slate-900 truncate">
                  {item.title}
                </h3>
                {item.earned ? (
                  <Badge variant="amber" size="sm">
                    Egallandi
                  </Badge>
                ) : (
                  <Badge variant="slate" size="sm">
                    Qulflangan
                  </Badge>
                )}
              </div>
              <p className="text-[11px] sm:text-xs text-slate-500 mt-0.5 leading-snug">
                {item.description}
              </p>
            </div>

            <div className="shrink-0">
              {item.earned ? (
                <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-emerald-50 text-emerald-600 border border-emerald-200">
                  <IconCheck size={14} />
                </div>
              ) : (
                <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-slate-100 text-slate-400">
                  <IconLock size={14} />
                </div>
              )}
            </div>
          </Card>
        ))}
      </div>
    </div>
  );
}

/** Student Profile Page */
export function ProfilePage({
  profile,
  progress,
  onChangeGrade,
  onLogout,
}: {
  profile: Profile | null;
  progress: Progress | null;
  onChangeGrade: () => void;
  onLogout?: () => void;
}) {
  const name = profile?.first_name || progress?.first_name || "O‘quvchi";
  const gradeLabel = profile?.grade_name ?? progress?.grade_name ?? "Belgilanmagan";
  const initial = name.charAt(0).toUpperCase();

  // Calculate learning level based on stars
  const stars = progress?.stars_total ?? 0;
  let levelTitle = "Boshlovchi";
  let levelBadge = "bg-blue-50 text-blue-700 border-blue-200";
  if (stars >= 100) {
    levelTitle = "Olimpiada qatnashchisi";
    levelBadge = "bg-purple-50 text-purple-700 border-purple-200";
  } else if (stars >= 50) {
    levelTitle = "A’lochi bilimdon";
    levelBadge = "bg-amber-50 text-amber-700 border-amber-200";
  } else if (stars >= 20) {
    levelTitle = "Izlanuvchi o‘quvchi";
    levelBadge = "bg-emerald-50 text-emerald-700 border-emerald-200";
  }

  return (
    <div className="mx-auto max-w-2xl animate-fade-in py-1 pb-32 sm:pb-12">
      {/* Profile Info Card */}
      <Card variant="elevated" className="mb-3.5 sm:mb-6 p-3.5 sm:p-6 bg-white shadow-sm">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
          <div className="flex items-center gap-3">
            <div className="flex h-12 w-12 sm:h-14 sm:w-14 items-center justify-center rounded-2xl bg-gradient-to-br from-[#3478F6] to-indigo-600 text-xl sm:text-2xl font-black text-white shadow-xs">
              {initial}
            </div>
            <div className="min-w-0">
              <div className="flex items-center gap-2">
                <h1 className="text-base sm:text-xl font-black text-slate-900 truncate">{name}</h1>
                <span className={`inline-flex px-2 py-0.5 rounded-full text-[10px] sm:text-[11px] font-bold border ${levelBadge}`}>
                  {levelTitle}
                </span>
              </div>
              <p className="text-[11px] font-semibold text-slate-400 mt-0.5">
                Ta'lim oluvchi profili
              </p>
            </div>
          </div>

          <Button
            variant="secondary"
            size="sm"
            onClick={onChangeGrade}
            icon={<IconGraduationCap size={14} />}
          >
            {gradeLabel} · O‘zgartirish
          </Button>
        </div>

        {/* Learning Statistics Bar */}
        <div className="mt-4 grid grid-cols-3 gap-2">
          <div className="p-2.5 sm:p-3 rounded-xl bg-amber-50/70 border border-amber-200/50 text-center">
            <span className="text-base sm:text-xl font-black text-amber-700">
              {stars}
            </span>
            <span className="block text-[10px] font-bold text-amber-600 mt-0.5">
              ⭐ Yulduzlar
            </span>
          </div>

          <div className="p-2.5 sm:p-3 rounded-xl bg-blue-50/70 border border-blue-200/50 text-center">
            <span className="text-base sm:text-xl font-black text-blue-700">
              {progress?.lessons_viewed ?? 0}
            </span>
            <span className="block text-[10px] font-bold text-blue-600 mt-0.5">
              📖 Darslar
            </span>
          </div>

          <div className="p-2.5 sm:p-3 rounded-xl bg-emerald-50/70 border border-emerald-200/50 text-center">
            <span className="text-base sm:text-xl font-black text-emerald-700">
              {progress?.lessons_passed ?? 0}
            </span>
            <span className="block text-[10px] font-bold text-emerald-600 mt-0.5">
              ✅ Yakunlandi
            </span>
          </div>
        </div>
      </Card>

      {/* Subject Progress Section */}
      {progress && progress.subjects.length > 0 && (
        <Card className="mb-3.5 sm:mb-6 p-3.5 sm:p-5">
          <h2 className="text-[11px] sm:text-xs font-bold uppercase tracking-wider text-slate-400 mb-3">
            Fanlar bo‘yicha o‘zlashtirish
          </h2>
          <div className="space-y-3">
            {progress.subjects.map((sub) => {
              const subPercent =
                sub.total_lessons > 0
                  ? Math.round((sub.passed_lessons / sub.total_lessons) * 100)
                  : 0;

              return (
                <div key={sub.subject_name} className="flex items-center gap-2.5">
                  <span className="text-xl shrink-0" aria-hidden>
                    {sub.emoji}
                  </span>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center justify-between text-[11px] sm:text-xs font-bold text-slate-800 mb-1">
                      <span className="truncate">{sub.subject_name}</span>
                      <span className="text-slate-400 font-semibold">
                        {sub.passed_lessons}/{sub.total_lessons}
                      </span>
                    </div>
                    <ProgressBar value={subPercent} size="sm" />
                  </div>
                </div>
              );
            })}
          </div>
        </Card>
      )}

      {/* Settings / Actions */}
      <Card className="p-3.5 sm:p-5 space-y-2.5">
        <h3 className="text-[11px] sm:text-xs font-bold uppercase tracking-wider text-slate-400">
          Sozlamalar
        </h3>
        <Button
          variant="secondary"
          size="sm"
          fullWidth
          onClick={onChangeGrade}
          icon={<IconGraduationCap size={16} />}
        >
          Sinfni almashtirish ({gradeLabel})
        </Button>

        <p className="text-[10px] sm:text-[11px] text-slate-400 text-center px-1">
          Sinfni o‘zgartirganingizda to‘plangan yulduzlar va erishilgan natijalar saqlanib qoladi.
        </p>

        {onLogout && (
          <div className="pt-2 border-t border-slate-100">
            <Button
              variant="danger"
              size="sm"
              fullWidth
              onClick={onLogout}
            >
              Hisobdan chiqish
            </Button>
          </div>
        )}
      </Card>
    </div>
  );
}
