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
      <div className="mb-6">
        <div className="flex items-center gap-2 mb-3">
          <span className={`h-2.5 w-2.5 rounded-full ${badgeColor}`} />
          <h3 className="text-xs font-bold uppercase tracking-wider text-slate-500">
            {stageLabel}
          </h3>
        </div>
        <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-3">
          {list.map((g) => {
            const isSelected = selectedId === g.id;
            return (
              <button
                key={g.id}
                disabled={busy}
                onClick={() => handleSelect(g)}
                className={`relative flex items-center justify-between p-4 rounded-2xl border text-left transition-all duration-200 cursor-pointer active:scale-95 disabled:opacity-50 ${
                  isSelected
                    ? "bg-blue-50/80 border-blue-500 shadow-sm shadow-blue-500/10 ring-2 ring-blue-500/20"
                    : "bg-white border-slate-200/80 hover:border-blue-300 hover:bg-slate-50/60 shadow-xs"
                }`}
              >
                <div>
                  <span className="block text-base font-extrabold text-slate-900">
                    {g.name}
                  </span>
                  <span className="block text-[11px] font-medium text-slate-400 mt-0.5">
                    Ta'lim bosqichi
                  </span>
                </div>
                <div
                  className={`flex h-7 w-7 items-center justify-center rounded-xl transition-all ${
                    isSelected
                      ? "bg-blue-600 text-white"
                      : "bg-slate-100 text-slate-300 group-hover:bg-slate-200"
                  }`}
                >
                  <IconCheck size={16} />
                </div>
              </button>
            );
          })}
        </div>
      </div>
    );
  };

  return (
    <div className="mx-auto max-w-2xl animate-fade-in py-4">
      {/* Top bar with back/cancel */}
      {onCancel && (
        <div className="mb-4">
          <Button
            variant="ghost"
            size="sm"
            icon={<IconArrowLeft size={16} />}
            onClick={onCancel}
          >
            Orqaga qaytish
          </Button>
        </div>
      )}

      {/* Hero card */}
      <Card variant="elevated" className="mb-6 bg-gradient-to-br from-blue-600 via-blue-700 to-indigo-800 text-white p-6 sm:p-8">
        <div className="flex items-center gap-3">
          <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-white/20 backdrop-blur-md text-white shadow-xs">
            <IconGraduationCap size={28} />
          </div>
          <div>
            <span className="text-xs font-bold uppercase tracking-wider text-blue-200">
              Qadam 1 / 1
            </span>
            <h2 className="text-xl sm:text-2xl font-black text-white">
              Sinfingizni tanlang
            </h2>
          </div>
        </div>
        <p className="mt-3 text-sm text-blue-100 leading-relaxed max-w-lg">
          O‘zingiz o‘qiydigan sinfni belgilang. Darslar va testlar sizning sinfingizga mos ravishda taqdim etiladi. Keyinchalik istalgan vaqtda profil orqali o‘zgartirish mumkin.
        </p>
      </Card>

      {/* Grade groupings */}
      <div className="space-y-2">
        {renderGradeGrid(primaryGrades, "Boshlang‘ich maktab (1–4-sinflar)", "bg-emerald-500")}
        {renderGradeGrid(middleGrades, "O‘rta maktab (5–9-sinflar)", "bg-blue-500")}
        {renderGradeGrid(highGrades, "Yuqori sinf (10–11-sinflar)", "bg-purple-500")}
      </div>
    </div>
  );
}
