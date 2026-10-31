import type { SubjectItem } from "../types";
import Card from "./ui/Card";
import Button from "./ui/Button";
import Badge from "./ui/Badge";
import ProgressBar from "./ui/ProgressBar";
import EmptyState from "./ui/EmptyState";
import {
  IconArrowLeft,
  IconCheck,
  IconLock,
  IconPlay,
  IconBook,
  IconChevronRight,
} from "./ui/Icons";

interface SubjectLessonsProps {
  subject: SubjectItem;
  onOpenLesson: (lessonId: number) => void;
  onBack: () => void;
}

export default function SubjectLessons({
  subject,
  onOpenLesson,
  onBack,
}: SubjectLessonsProps) {
  const total = subject.lessons.length;
  const passedCount = subject.lessons.filter((l) => l.passed).length;
  const percent = total > 0 ? Math.round((passedCount / total) * 100) : 0;

  return (
    <div className="mx-auto max-w-3xl animate-fade-in py-2">
      {/* Back button */}
      <div className="mb-4">
        <Button
          variant="ghost"
          size="sm"
          icon={<IconArrowLeft size={16} />}
          onClick={onBack}
        >
          Bosh sahifaga qaytish
        </Button>
      </div>

      {/* Subject Header Banner */}
      <Card variant="elevated" className="mb-6 p-6 sm:p-7 bg-white border border-slate-100">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
          <div className="flex items-center gap-4">
            <div className="flex h-16 w-16 items-center justify-center rounded-2xl bg-gradient-to-br from-blue-50 to-indigo-100/70 border border-blue-100 text-4xl shadow-xs">
              <span aria-hidden>{subject.emoji}</span>
            </div>
            <div>
              <span className="text-xs font-bold uppercase tracking-wider text-blue-600">
                O‘quv fani
              </span>
              <h1 className="text-2xl font-black text-slate-900">{subject.name}</h1>
              <p className="text-xs font-semibold text-slate-500 mt-0.5">
                {total > 0
                  ? `${passedCount} / ${total} bosqich yakunlangan`
                  : "Ushbu fanda darslar tayyorlanmoqda"}
              </p>
            </div>
          </div>

          {total > 0 && (
            <div className="w-full sm:w-48 bg-slate-50 p-3 rounded-2xl border border-slate-100">
              <div className="flex items-center justify-between text-xs font-bold text-slate-700 mb-1.5">
                <span>Progress</span>
                <span className="text-blue-600">{percent}%</span>
              </div>
              <ProgressBar value={percent} size="sm" />
            </div>
          )}
        </div>
      </Card>

      {/* Empty State when no lessons exist */}
      {total === 0 ? (
        <EmptyState
          title="Darslar hozircha tayyorlanmoqda"
          description="Ushbu fan uchun darslar va topshiriqlar yaqin kunlarda yuklanadi. Boshqa fanlar yoki sinflar bilan tanishib ko‘rishingiz mumkin."
          actionText="Bosh sahifaga qaytish"
          onAction={onBack}
        />
      ) : (
        /* Lessons Ladder */
        <div className="space-y-3">
          <div className="flex items-center justify-between px-1">
            <h2 className="text-xs font-bold uppercase tracking-wider text-slate-500">
              Darslar ketma-ketligi
            </h2>
            <span className="text-xs font-medium text-slate-400">
              Bosqichma-bosqich o‘rganing
            </span>
          </div>

          <div className="relative space-y-3">
            {subject.lessons.map((lesson) => {
              const isLocked = !lesson.unlocked;
              const isPassed = lesson.passed;
              const isViewed = lesson.viewed && !lesson.passed;
              const isCurrent = lesson.unlocked && !lesson.passed;

              return (
                <div key={lesson.id} className="relative">
                  {/* Lesson Card */}
                  <div
                    onClick={() => {
                      if (!isLocked) onOpenLesson(lesson.id);
                    }}
                    className={`flex items-center gap-4 p-4 sm:p-5 rounded-3xl border transition-all duration-200 ${
                      isLocked
                        ? "bg-slate-50/70 border-slate-200/60 opacity-70 cursor-not-allowed"
                        : isPassed
                          ? "bg-white border-emerald-100 hover:border-emerald-300 shadow-xs hover:shadow-sm cursor-pointer"
                          : isCurrent
                            ? "bg-white border-blue-300 shadow-md shadow-blue-500/5 ring-2 ring-blue-500/10 cursor-pointer"
                            : "bg-white border-slate-200/80 hover:border-blue-200 shadow-xs cursor-pointer"
                    }`}
                  >
                    {/* Status Badge Icon */}
                    <div
                      className={`flex h-12 w-12 shrink-0 items-center justify-center rounded-2xl font-bold transition-all ${
                        isPassed
                          ? "bg-emerald-50 text-emerald-600 border border-emerald-200"
                          : isViewed
                            ? "bg-blue-50 text-blue-600 border border-blue-200"
                            : isCurrent
                              ? "bg-[#3478F6] text-white shadow-sm shadow-blue-500/30"
                              : "bg-slate-100 text-slate-400 border border-slate-200"
                      }`}
                    >
                      {isPassed ? (
                        <IconCheck size={20} />
                      ) : isViewed ? (
                        <IconBook size={20} />
                      ) : isCurrent ? (
                        <IconPlay size={18} />
                      ) : (
                        <IconLock size={18} />
                      )}
                    </div>

                    {/* Lesson Content */}
                    <div className="flex-1 min-w-0">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="text-xs font-extrabold text-blue-600">
                          {lesson.level_order}-bosqich
                        </span>
                        {isPassed && (
                          <Badge variant="emerald" size="sm">
                            Tugatilgan
                          </Badge>
                        )}
                        {isViewed && (
                          <Badge variant="amber" size="sm">
                            Test kutilmoqda
                          </Badge>
                        )}
                        {isCurrent && !isViewed && (
                          <Badge variant="blue" size="sm">
                            Boshlashga tayyor
                          </Badge>
                        )}
                      </div>

                      <h3 className="text-sm sm:text-base font-bold text-slate-900 mt-0.5 truncate">
                        {lesson.title}
                      </h3>

                      <p className="text-xs text-slate-400 mt-0.5">
                        {isPassed
                          ? "Dars o‘qildi va test muvaffaqiyatli topshirildi ⭐"
                          : isViewed
                            ? "Nazariy qism o‘qildi. Testni topshiring"
                            : isCurrent
                              ? "Dars materiallarini o‘rganishni boshlang"
                              : "Avvalgi bosqich testini topshiring"}
                      </p>
                    </div>

                    {/* Action Arrow */}
                    <div className="shrink-0">
                      {isLocked ? (
                        <div className="text-slate-300">
                          <IconLock size={18} />
                        </div>
                      ) : (
                        <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-slate-50 text-slate-500 group-hover:bg-blue-50 group-hover:text-blue-600 transition-colors">
                          <IconChevronRight size={18} />
                        </div>
                      )}
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}
