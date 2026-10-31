/**
 * Pages.tsx — the two simple tab pages: Yutuqlar (achievements) and Profil.
 * All data already exists in `progress` / `profile` loaded at boot; these
 * pages just present it, so no extra API calls are needed.
 */
import type { Profile, Progress } from "../types";

export function AchievementsPage({ progress }: { progress: Progress | null }) {
  const earned = progress?.achievements.filter((a) => a.earned).length ?? 0;
  const total = progress?.achievements.length ?? 0;
  return (
    <section className="mt-6">
      <h2 className="text-xl font-extrabold text-blue-900">🏆 Yutuqlar</h2>
      <p className="mt-1 text-xs font-semibold text-blue-400">
        {earned}/{total} ta yutuq olingan · ⭐ {progress?.stars_total ?? 0} yulduzcha
      </p>
      <div className="mt-4 space-y-3">
        {(progress?.achievements ?? []).map((a) => (
          <div
            key={a.code}
            className={`flex items-center gap-3 rounded-2xl p-4 shadow-sm ${
              a.earned ? "bg-white" : "bg-slate-100 opacity-70"
            }`}
          >
            <span className={`text-3xl ${a.earned ? "" : "grayscale"}`} aria-hidden>
              {a.icon}
            </span>
            <div className="flex-1">
              <p className="text-sm font-bold text-blue-900">{a.title}</p>
              <p className="text-xs text-slate-500">{a.description}</p>
            </div>
            <span className="text-xs font-bold">
              {a.earned ? "✅" : "🔒"}
            </span>
          </div>
        ))}
      </div>
    </section>
  );
}

export function ProfilePage({
  profile,
  progress,
  onChangeGrade,
  onLogout,
}: {
  profile: Profile | null;
  progress: Progress | null;
  onChangeGrade: () => void;
  /** Present only for browser sessions (no Telegram Mini App identity). */
  onLogout?: () => void;
}) {
  return (
    <section className="mt-6">
      <h2 className="text-xl font-extrabold text-blue-900">👤 Profil</h2>
      <div className="mt-4 rounded-2xl bg-white p-5 shadow-md">
        <p className="text-lg font-bold text-blue-900">
          {profile?.first_name || progress?.first_name || "Qahramon"}
        </p>
        <p className="text-sm text-slate-500">
          Sinf: <b className="text-blue-700">{profile?.grade_name ?? progress?.grade_name ?? "—"}</b>
        </p>
        <div className="mt-4 grid grid-cols-3 gap-2 text-center">
          <Stat label="Yulduzcha" value={`⭐ ${progress?.stars_total ?? 0}`} />
          <Stat label="O'qilgan" value={`📖 ${progress?.lessons_viewed ?? 0}`} />
          <Stat label="Tugatilgan" value={`✅ ${progress?.lessons_passed ?? 0}`} />
        </div>
      </div>

      {progress && progress.subjects.length > 0 && (
        <div className="mt-4 rounded-2xl bg-white p-5 shadow-md">
          <p className="text-sm font-bold text-blue-900">Fanlar bo'yicha progress</p>
          <div className="mt-3 space-y-2">
            {progress.subjects.map((s) => (
              <div key={s.subject_name} className="flex items-center gap-2">
                <span className="w-6 text-center">{s.emoji}</span>
                <span className="w-28 truncate text-xs font-semibold text-slate-600">
                  {s.subject_name}
                </span>
                <div className="h-2 flex-1 overflow-hidden rounded-full bg-blue-100">
                  <div
                    className="h-full rounded-full bg-blue-500"
                    style={{
                      width: `${s.total_lessons ? Math.round((s.passed_lessons / s.total_lessons) * 100) : 0}%`,
                    }}
                  />
                </div>
                <span className="w-10 text-right text-[11px] font-bold text-blue-500">
                  {s.passed_lessons}/{s.total_lessons}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      <button
        onClick={onChangeGrade}
        className="mt-5 w-full rounded-2xl bg-white px-4 py-3 text-sm font-bold text-blue-600 shadow-md transition-transform active:scale-95"
      >
        Sinfni o'zgartirish 🔄
      </button>
      <p className="mt-2 text-center text-[11px] text-slate-400">
        Sinf o'zgarsa ham eski progress'ingiz o'chmaydi — u o'sha sinfga bog'langan qoladi.
      </p>

      {onLogout && (
        <button
          onClick={onLogout}
          className="mt-5 w-full rounded-2xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm font-bold text-rose-600 shadow-sm transition-transform active:scale-95"
        >
          Chiqish 🚪
        </button>
      )}
    </section>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-xl bg-blue-50 py-3">
      <p className="text-base font-extrabold text-blue-800">{value}</p>
      <p className="text-[11px] font-semibold text-blue-400">{label}</p>
    </div>
  );
}
