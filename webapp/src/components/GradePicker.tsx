/**
 * GradePicker.tsx — first-run onboarding: pick your grade (1..11).
 *
 * We never guess the grade. The list comes straight from the backend
 * (/api/grades), so if an admin later renames or adds grades the UI follows
 * automatically. The pupil must tap one; there is no default selection.
 */
import type { Grade } from "../types";

const GRADIENTS = [
  "from-blue-500 to-blue-700",
  "from-sky-400 to-blue-600",
  "from-indigo-500 to-blue-700",
];

export default function GradePicker({
  grades,
  busy,
  onPick,
}: {
  grades: Grade[];
  busy: boolean;
  onPick: (grade: Grade) => void;
}) {
  return (
    <section className="mt-6">
      <h2 className="px-1 text-sm font-bold uppercase tracking-wide text-blue-400">
        Sinfingizni tanlang
      </h2>
      <p className="mt-1 px-1 text-xs text-slate-500">
        Bu tanlov saqlanadi va keyingi safar avtomatik yuklanadi. Keyin profil
        sozlamalaridan o‘zgartirishingiz mumkin.
      </p>
      <div className="mt-3 grid grid-cols-3 gap-2">
        {grades.map((g, i) => (
          <button
            key={g.id}
            disabled={busy}
            onClick={() => onPick(g)}
            className={`rounded-xl bg-gradient-to-br ${GRADIENTS[i % GRADIENTS.length]} px-2 py-3 text-center text-sm font-bold text-white shadow-md transition-transform active:scale-95 disabled:opacity-50`}
          >
            {g.name}
          </button>
        ))}
      </div>
    </section>
  );
}
