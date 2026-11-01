import type { QuizQuestion } from "../types";
import type { AnswerState } from "../answering";
import { IconCheck } from "./ui/Icons";

const OPTION_LETTERS = ["A", "B", "C", "D", "E", "F"];

interface AnswerInputsProps {
  question: QuizQuestion;
  state: AnswerState;
  onSelectOption: (optionId: number) => void;
  onText: (value: string) => void;
  onMatch: (promptId: number, optionId: number | null) => void;
  onClearMatches: () => void;
}

/**
 * AnswerInputs — the four question kinds, rendered once and shared by the lesson
 * quiz and the mandatory exam. It never shows which option is correct: grading is
 * done by the server, so the browser has nothing to leak.
 */
export default function AnswerInputs({
  question,
  state,
  onSelectOption,
  onText,
  onMatch,
  onClearMatches,
}: AnswerInputsProps) {
  if (question.kind === "text") {
    return (
      <div className="mt-4">
        <label className="block text-xs font-bold uppercase tracking-wider text-slate-400 mb-2">
          Javobingizni kiriting:
        </label>
        <input
          type="text"
          value={state.texts[question.id] ?? ""}
          onChange={(e) => onText(e.target.value)}
          placeholder="Javobni yozing…"
          className="w-full rounded-2xl border-2 border-slate-200 bg-white px-4 py-3 text-sm font-semibold text-slate-800 outline-none transition-colors focus:border-blue-500 focus:ring-2 focus:ring-blue-500/10"
        />
      </div>
    );
  }

  if (question.kind === "matching") {
    const assigned = state.matches[question.id] ?? {};
    return (
      <div className="mt-4 space-y-2.5">
        <p className="text-[11px] sm:text-xs font-semibold text-slate-500">
          Har bir chap element uchun mos o‘ng javobni tanlang.
        </p>
        {question.prompts.map((prompt, promptIndex) => {
          const selected = assigned[prompt.id];
          return (
            <div
              key={prompt.id}
              className="flex flex-col sm:flex-row sm:items-center gap-2 rounded-2xl border border-slate-100 bg-white p-3"
            >
              <div className="flex items-center gap-2.5 flex-1 min-w-0">
                <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-indigo-50 text-indigo-700 font-black text-xs">
                  {promptIndex + 1}
                </span>
                <span className="text-sm font-semibold text-slate-800 break-words">
                  {prompt.text}
                </span>
              </div>
              <select
                value={selected ?? ""}
                onChange={(e) =>
                  onMatch(prompt.id, e.target.value ? Number(e.target.value) : null)
                }
                className={`w-full sm:w-48 shrink-0 rounded-xl border-2 px-3 py-2 text-sm font-semibold outline-none transition-colors cursor-pointer ${
                  selected !== undefined
                    ? "border-emerald-300 bg-emerald-50/60 text-emerald-900"
                    : "border-slate-200 bg-white text-slate-600 focus:border-blue-500"
                }`}
              >
                <option value="">Tanlang…</option>
                {question.options.map((opt) => (
                  <option key={opt.id} value={opt.id}>
                    {opt.text}
                  </option>
                ))}
              </select>
            </div>
          );
        })}
        {Object.keys(assigned).length > 0 && (
          <button
            onClick={onClearMatches}
            className="text-[11px] font-bold text-slate-400 hover:text-rose-500 hover:underline cursor-pointer"
          >
            Tanlovni tozalash
          </button>
        )}
      </div>
    );
  }

  // single / image → a list of lettered choices
  const selectedId = state.options[question.id];
  return (
    <div className="space-y-3 mt-4">
      {question.options.map((opt, optIndex) => {
        const isSelected = selectedId === opt.id;
        const letter = OPTION_LETTERS[optIndex] || `${optIndex + 1}`;
        return (
          <button
            key={opt.id}
            onClick={() => onSelectOption(opt.id)}
            className={`w-full flex items-center gap-3.5 p-4 rounded-2xl border-2 text-left transition-all duration-150 cursor-pointer active:scale-[0.99] ${
              isSelected
                ? "border-blue-500 bg-blue-50/70 shadow-xs ring-2 ring-blue-500/10"
                : "border-slate-100 bg-white hover:border-slate-300 hover:bg-slate-50/50"
            }`}
          >
            <span
              className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-xl font-black text-xs transition-colors ${
                isSelected ? "bg-blue-600 text-white" : "bg-slate-100 text-slate-600"
              }`}
            >
              {letter}
            </span>
            <span
              className={`flex-1 text-sm font-semibold leading-snug ${
                isSelected ? "text-blue-900" : "text-slate-800"
              }`}
            >
              {opt.text}
            </span>
            <div
              className={`flex h-5 w-5 shrink-0 items-center justify-center rounded-full border transition-colors ${
                isSelected
                  ? "border-blue-600 bg-blue-600 text-white"
                  : "border-slate-300 bg-white"
              }`}
            >
              {isSelected && <IconCheck size={12} />}
            </div>
          </button>
        );
      })}
    </div>
  );
}
