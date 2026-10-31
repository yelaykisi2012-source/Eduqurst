import { useState } from "react";
import type { Grade } from "../types";
import Card from "./ui/Card";
import Button from "./ui/Button";
import { IconCheck, IconGraduationCap, IconArrowLeft } from "./ui/Icons";

interface GradePickerProps {
  grades: Grade[];
  busy: boolean;
  currentGradeId?: number | null;
  onPick: (grade: Grade) => void;
  onCancel?: () => void;
}

export default function GradePicker({
  grades,
  busy,
  currentGradeId,
  onPick,
  onCancel,
}: GradePickerProps) {
  const [selectedId, setSelectedId] = useState<number | null>(currentGradeId ?? null);

  // Categorize grades for clean navigation
  const primaryGrades = grades.filter((g) => {
    const num = parseInt(g.name, 10);
    return num >= 1 && num <= 4;
  });

  const middleGrades = grades.filter((g) => {
    const num = parseInt(g.name, 10);
    return num >= 5 && num <= 9;
  });

  const highGrades = grades.filter((g) => {
    const num = parseInt(g.name, 10);
    return num >= 10 && num <= 11;
  });

  const handleSelect = (grade: Grade) => {
    setSelectedId(grade.id);
    onPick(grade);
  };

  const renderGradeGrid = (list: Grade[], stageLabel: string, badgeColor: string) => {
    if (list.length === 0) return null;
    return (
      <div className="mb-4 sm:mb-5">
        <div className="flex items-center gap-1.5 mb-2">
          <span className={`h-2 w-2 rounded-full ${badgeColor}`} />
          <h3 className="text-[10px] sm:text-xs font-bold uppercase tracking-wider text-slate-400">
            {stageLabel}
          </h3>
        </div>
        <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-2">
          {list.map((g) => {
            const isSelected = selectedId === g.id;
            return (
              <button
                key={g.id}
                disabled={busy}
                onClick={() => handleSelect(g)}
                className={`relative flex items-center justify-between p-2 sm:p-3 rounded-xl border text-left transition-all duration-150 cursor-pointer active:scale-95 disabled:opacity-50 ${
                  isSelected
                    ? "bg-blue-50/90 border-blue-500 shadow-2xs ring-2 ring-blue-500/20"
                    : "bg-white border-slate-200/80 hover:border-blue-300 hover:bg-slate-50/60 shadow-2xs"
                }`}
              >
                <div>
                  <span className="block text-xs sm:text-sm font-black text-slate-900 leading-tight">
                    {g.name}
                  </span>
                  <span className="block text-[9.5px] sm:text-[10px] font-semibold text-slate-400 mt-0.5">
                    O‘quv kursi
                  </span>
                </div>
                <div
                  className={`flex h-5 w-5 sm:h-6 sm:w-6 items-center justify-center rounded-lg transition-all ${
                    isSelected
                      ? "bg-blue-600 text-white shadow-2xs"
                      : "bg-slate-100 text-slate-300 group-hover:bg-slate-200"
                  }`}
                >
                  <IconCheck size={12} />
                </div>
              </button>
            );
          })}
        </div>
      </div>
    );
  };

  return (
    <div className="mx-auto max-w-2xl animate-fade-in py-1 pb-32 sm:pb-12">
      {/* Top bar with back/cancel */}
      {onCancel && (
        <div className="mb-2">
          <Button
            variant="ghost"
            size="sm"
            icon={<IconArrowLeft size={14} />}
            onClick={onCancel}
          >
            Orqaga qaytish
          </Button>
        </div>
      )}

      {/* Hero card */}
      <Card variant="elevated" padding="none" className="mb-3 sm:mb-5 bg-gradient-to-br from-blue-600 via-blue-700 to-indigo-800 text-white p-3.5 sm:p-5 shadow-sm">
        <div className="flex items-center gap-2.5">
          <div className="flex h-9 w-9 sm:h-11 sm:w-11 items-center justify-center rounded-xl bg-white/20 backdrop-blur-md text-white shadow-2xs shrink-0">
            <IconGraduationCap size={18} />
          </div>
          <div>
            <span className="text-[9.5px] sm:text-xs font-bold uppercase tracking-wider text-blue-200">
              Qadam 1 / 1
            </span>
            <h2 className="text-base sm:text-xl font-black text-white leading-tight">
              Sinfingizni tanlang
            </h2>
          </div>
        </div>
        <p className="mt-1.5 text-[11px] sm:text-xs text-blue-100 leading-relaxed max-w-lg">
          O‘zingiz o‘qiydigan sinfni belgilang. Darslar va testlar sizning sinfingizga mos ravishda taqdim etiladi.
        </p>
      </Card>

      {/* Grade groupings */}
      <div className="space-y-1.5">
        {renderGradeGrid(primaryGrades, "Boshlang‘ich maktab (1–4-sinflar)", "bg-emerald-500")}
        {renderGradeGrid(middleGrades, "O‘rta maktab (5–9-sinflar)", "bg-blue-500")}
        {renderGradeGrid(highGrades, "Yuqori sinf (10–11-sinflar)", "bg-purple-500")}
      </div>
    </div>
  );
}
