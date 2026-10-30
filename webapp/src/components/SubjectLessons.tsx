/**
 * SubjectLessons.tsx — the lesson ladder of one subject.
 *
 * The backend already tells us per lesson: viewed / passed / unlocked.
 * Locked lessons are shown with 🔒 (never hidden) so pupils can see what
 * is coming and stay motivated to finish the current one first.
 */
import type { SubjectItem } from "../types";

export default function SubjectLessons({
  subject,
  onOpenLesson,
  onBack,
}: {
  subject: SubjectItem;
  onOpenLesson: (lessonId: number) => void;
  onBack: () => void;
}) {
  const done = subject.lessons.filter((l) => l.passed).length;

  return (
    <section className="mt-6">
      <BackButton onClick={onBack} />
      <div className="mt-2 flex items-center gap-3">
        <span className="text-4xl" aria-hidden>
          {subject.emoji}
        </span>
        <div>
          <h2 className="text-xl font-extrabold text-blue-900">{subject.name}</h2>
          <p className="text-xs font-semibold text-blue-400">
            {done}/{subject.lessons.length} bosqich tugatilgan
          </p>
        </div>
      </div>

      <ol className="mt-4 space-y-2">
        {subject.lessons.map((l) => {
          const status = l.passed ? "✅" : l.viewed ? "🧩" : l.unlocked ? "▶" : "🔒";
          return (
            <li key={l.id}>
              <button
                disabled={!l.unlocked}
                onClick={() => onOpenLesson(l.id)}
                className={`flex w-full items-center gap-3 rounded-2xl px-4 py-3 text-left shadow-sm transition-transform active:scale-[0.98] ${
                  l.unlocked
                    ? "bg-white hover:bg-blue-50"
                    : "cursor-not-allowed bg-slate-100 opacity-70"
                }`}
              >
                <span
                  className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-full text-base font-bold ${
                    l.passed
                      ? "bg-emerald-100 text-emerald-600"
                      : l.unlocked
                        ? "bg-blue-100 text-blue-600"
                        : "bg-slate-200 text-slate-400"
                  }`}
                >
                  {status}
                </span>
                <span className="flex-1">
                  <span className="block text-sm font-bold text-blue-900">
                    {l.level_order}. {l.title}
                  </span>
                  <span className="block text-[11px] font-medium text-slate-400">
                    {l.passed
                      ? "Tugatilgan — yulduzcha olingan ⭐"
                      : l.viewed
                        ? "O'qilgan — testni topshiring"
                        : l.unlocked
                          ? "Boshlashga tayyor"
                          : "Avval oldingi bosqichni tugating"}
                  </span>
                </span>
              </button>
            </li>
          );
        })}
      </ol>
    </section>
  );
}

export function BackButton({ onClick }: { onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      className="text-sm font-bold text-blue-500 hover:underline"
    >
      ← Orqaga
    </button>
  );
}
