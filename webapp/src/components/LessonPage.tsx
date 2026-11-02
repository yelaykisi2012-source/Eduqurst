import { useEffect, useState } from "react";
import { api, ApiError } from "../api";
import type { LessonDetail, Material } from "../types";
import Card from "./ui/Card";
import Button from "./ui/Button";
import Badge from "./ui/Badge";
import {
  IconArrowLeft,
  IconPlay,
  IconDownload,
  IconExternalLink,
  IconFileText,
  IconCheck,
  IconStar,
  IconSparkles,
} from "./ui/Icons";

const isLink = (value: string) => /^https?:\/\//i.test(value.trim());

const formatBytes = (bytes: number | null) => {
  if (!bytes) return "";
  if (bytes >= 1_000_000) return `${(bytes / 1_000_000).toFixed(1)} MB`;
  return `${Math.max(1, Math.round(bytes / 1000))} KB`;
};

/** Uploaded file material (PDF/Video via Telegram file id).
 *
 * The file is fetched ONCE and kept as an object URL, then it can be opened
 * INSIDE the lesson (PDF viewer / video player) and still be downloaded. That
 * is what the teacher asked for: "men yuklagan dars pdf sayt ozida ochilsin,
 * video darslar ham ichida ochilsin, yuklab olamsiz".
 */
function FileMaterialCard({ material, token }: { material: Material; token: string }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [file, setFile] = useState<{ url: string; name: string } | null>(null);
  const [open, setOpen] = useState(false);

  const isVideo = material.kind === "video";

  useEffect(() => {
    return () => {
      if (file) URL.revokeObjectURL(file.url);
    };
  }, [file]);

  const load = async () => {
    if (file) return file;
    setBusy(true);
    setError("");
    try {
      const { blob, fileName } = await api.downloadMaterialFile(token, material.id);
      const loaded = { url: URL.createObjectURL(blob), name: fileName };
      setFile(loaded);
      return loaded;
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Faylni yuklab bo‘lmadi");
      return null;
    } finally {
      setBusy(false);
    }
  };

  const handleOpen = async () => {
    if (await load()) setOpen(true);
  };

  const handleDownload = async () => {
    const loaded = await load();
    if (!loaded) return;
    const a = document.createElement("a");
    a.href = loaded.url;
    a.download = loaded.name;
    document.body.appendChild(a);
    a.click();
    a.remove();
  };

  const meta = [material.file_name, formatBytes(material.file_size)].filter(Boolean).join(" · ");

  return (
    <div className="mt-3">
      {/* Below 420px the two buttons drop under the name instead of sitting
          beside it. Next to the title they left only ~180px for the file name,
          so even two lines still ended in "…"; on their own line the name gets
          the whole card and the teacher can read it. From 420px up the row is
          side-by-side again, which is what a tablet and a laptop expect. */}
      <div className="flex flex-col gap-3 p-4 rounded-2xl border border-blue-100 bg-white shadow-xs min-[420px]:flex-row min-[420px]:items-center">
        <div className="flex min-w-0 items-center gap-3">
          <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-blue-50 text-blue-600">
            {isVideo ? <IconPlay size={20} /> : <IconFileText size={20} />}
          </div>
          <div className="min-w-0 flex-1">
            <h4 className="line-clamp-2 text-sm font-bold leading-snug text-slate-800 [overflow-wrap:anywhere]">
              {material.title}
            </h4>
            <p className="text-xs text-slate-400 truncate">
              {meta || (isVideo ? "Video darslik" : "PDF fayl")}
            </p>
          </div>
        </div>
        <div className="flex shrink-0 items-center gap-1.5">
          <Button
            variant="secondary"
            size="sm"
            loading={busy && !file}
            onClick={handleOpen}
            icon={isVideo ? <IconPlay size={14} /> : <IconFileText size={14} />}
          >
            Ochish
          </Button>
          <Button
            variant="ghost"
            size="sm"
            onClick={handleDownload}
            aria-label="Faylni yuklab olish"
            icon={<IconDownload size={14} />}
          >
            {/* The name no longer shares its line with these buttons, so the word
                fits again — an arrow alone is harder for a pupil to trust. */}
            Yuklab olish
          </Button>
        </div>
      </div>

      {error && <p className="mt-1.5 text-xs font-semibold text-rose-500">{error}</p>}

      {open && file && isVideo && (
        <div className="mt-3 overflow-hidden rounded-2xl border border-slate-200 bg-black shadow-md">
          <video controls src={file.url} className="w-full max-h-96">
            Brauzeringiz video formatini qo‘llab-quvvatlamaydi.
          </video>
          <ViewerFooter name={file.name} onDownload={handleDownload} onClose={() => setOpen(false)} />
        </div>
      )}

      {open && file && !isVideo && (
        <div className="mt-3 overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-md">
          {/* Blob URLs render in the browser's own PDF viewer — no dependency,
              and the file never leaves the page. */}
          <iframe
            title={material.title || "PDF"}
            src={file.url}
            className="h-[70dvh] w-full bg-slate-50"
          />
          <ViewerFooter name={file.name} onDownload={handleDownload} onClose={() => setOpen(false)} />
        </div>
      )}
    </div>
  );
}

function ViewerFooter({
  name,
  onDownload,
  onClose,
}: {
  name: string;
  onDownload: () => void;
  onClose: () => void;
}) {
  return (
    <div className="flex items-center justify-between gap-2 border-t border-slate-100 bg-slate-50/80 px-3 py-2">
      <span className="min-w-0 truncate text-[11px] font-bold text-slate-500">{name}</span>
      <div className="flex shrink-0 items-center gap-1.5">
        <Button variant="ghost" size="sm" onClick={onDownload} icon={<IconDownload size={13} />}>
          Yuklab olish
        </Button>
        <Button variant="secondary" size="sm" onClick={onClose}>
          Yopish
        </Button>
      </div>
    </div>
  );
}

/** Standard lesson material card */
function MaterialItem({ material, token }: { material: Material; token: string }) {
  const { kind, title, content } = material;

  if (material.file_id) {
    return <FileMaterialCard material={material} token={token} />;
  }

  // Legacy image or link in text
  if (kind === "image" || (kind === "text" && isLink(content))) {
    return (
      <div className="mt-3 overflow-hidden rounded-2xl border border-slate-200/80 bg-white p-4 shadow-xs">
        {title && <h4 className="text-xs font-bold uppercase tracking-wider text-slate-400 mb-2">{title}</h4>}
        {kind === "image" ? (
          <img src={content} alt={title} className="w-full rounded-xl object-contain max-h-80" />
        ) : (
          <a
            href={content}
            target="_blank"
            rel="noreferrer"
            className="flex items-center gap-2 text-sm font-bold text-blue-600 hover:underline break-all"
          >
            <span>{content}</span>
            <IconExternalLink size={14} />
          </a>
        )}
      </div>
    );
  }

  // External link formats (video, pdf, live)
  if (kind === "video" || kind === "pdf" || kind === "live") {
    const isLive = kind === "live";
    const isPdf = kind === "pdf";
    return (
      <a
        href={content}
        target="_blank"
        rel="noreferrer"
        className="mt-3 flex items-center justify-between p-4 rounded-2xl border border-slate-200/80 bg-white hover:border-blue-300 hover:bg-blue-50/30 transition-all shadow-xs group"
      >
        <div className="flex items-center gap-3 min-w-0">
          <div
            className={`flex h-11 w-11 shrink-0 items-center justify-center rounded-xl ${
              isLive
                ? "bg-rose-50 text-rose-600 border border-rose-200"
                : isPdf
                  ? "bg-amber-50 text-amber-600 border border-amber-200"
                  : "bg-blue-50 text-blue-600 border border-blue-200"
            }`}
          >
            {isLive ? <span className="h-3 w-3 rounded-full bg-rose-500 animate-pulse" /> : isPdf ? <IconFileText size={20} /> : <IconPlay size={18} />}
          </div>
          <div className="min-w-0">
            <h4 className="text-sm font-bold text-slate-800 group-hover:text-blue-600 transition-colors truncate">
              {title}
            </h4>
            <span className="text-xs text-slate-400">
              {isLive ? "Jonli dars havolasi" : isPdf ? "Elektron qo‘llanma (PDF)" : "Video darslik"}
            </span>
          </div>
        </div>
        <div className="flex items-center gap-1.5 text-xs font-bold text-blue-600">
          <span>Ochish</span>
          <IconExternalLink size={14} />
        </div>
      </a>
    );
  }

  // Written notes / text
  return (
    <div className="mt-3 rounded-2xl border border-blue-100/80 bg-blue-50/40 p-4">
      {title && <h4 className="text-xs font-bold uppercase tracking-wider text-blue-600 mb-1.5">{title}</h4>}
      <p className="text-sm leading-relaxed text-slate-700 whitespace-pre-line">{content}</p>
    </div>
  );
}

interface LessonPageProps {
  token: string;
  lessonId: number;
  onBack: () => void;
  onStartQuiz: () => void;
  onViewed: () => void;
}

export default function LessonPage({
  token,
  lessonId,
  onBack,
  onStartQuiz,
  onViewed,
}: LessonPageProps) {
  const [lesson, setLesson] = useState<LessonDetail | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [justEarned, setJustEarned] = useState(false);
  const [earnedTitles, setEarnedTitles] = useState<string[]>([]);

  useEffect(() => {
    let alive = true;
    api
      .lesson(token, lessonId)
      .then((d) => alive && setLesson(d))
      .catch((e: unknown) =>
        alive && setError(e instanceof ApiError ? e.message : "Dars yuklanmadi"),
      );
    return () => {
      alive = false;
    };
  }, [token, lessonId]);

  const handleMarkViewed = async () => {
    setBusy(true);
    try {
      const r = await api.markViewed(token, lessonId);
      setLesson((l) => (l ? { ...l, viewed: true } : l));
      if (r.stars_granted) {
        setJustEarned(true);
        window.Telegram?.WebApp?.HapticFeedback?.notificationOccurred("success");
      }
      setEarnedTitles(r.new_achievement_titles ?? []);
      onViewed();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Xatolik yuz berdi");
    } finally {
      setBusy(false);
    }
  };

  if (error) {
    return (
      <div className="mx-auto max-w-2xl py-6 animate-fade-in text-center">
        <Card className="p-8">
          <span className="text-4xl mb-3 block">⚠️</span>
          <h3 className="text-lg font-bold text-slate-800">Xatolik yuz berdi</h3>
          <p className="mt-1 text-sm text-slate-500 mb-6">{error}</p>
          <Button variant="secondary" onClick={onBack}>
            Orqaga qaytish
          </Button>
        </Card>
      </div>
    );
  }

  if (!lesson) {
    return (
      <div className="mx-auto max-w-2xl py-12 text-center animate-fade-in">
        <div className="inline-block h-8 w-8 animate-spin rounded-full border-4 border-blue-500 border-t-transparent" />
        <p className="mt-4 text-sm font-semibold text-slate-500">Dars yuklanmoqda…</p>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-3xl animate-fade-in py-1 pb-32 sm:pb-12">
      {/* Top back button */}
      <div className="mb-2">
        <Button
          variant="ghost"
          size="sm"
          icon={<IconArrowLeft size={14} />}
          onClick={onBack}
        >
          Darslar ro‘yxatiga qaytish
        </Button>
      </div>

      {/* Lesson Hero Header */}
      <Card variant="elevated" padding="none" className="mb-3.5 sm:mb-6 p-4 sm:p-6">
        <div className="flex flex-wrap items-center justify-between gap-1.5 mb-1.5">
          <div className="flex items-center gap-1.5">
            <Badge variant="blue" size="sm">
              {lesson.subject_name}
            </Badge>
            <span className="text-[11px] sm:text-xs font-bold text-slate-400">
              · {lesson.level_order}-bosqich
            </span>
          </div>
          <div className="flex items-center gap-1 px-2.5 py-0.5 rounded-full bg-amber-50 text-amber-700 border border-amber-200/80 text-[11px] sm:text-xs font-bold">
            <IconStar size={13} filled className="text-amber-500" />
            <span>+{lesson.stars_reward} ⭐</span>
          </div>
        </div>

        <h1 className="text-lg sm:text-2xl font-black text-slate-900 tracking-tight leading-snug">
          {lesson.title}
        </h1>

        {/* Video dars link if top-level */}
        {lesson.video_url && isLink(lesson.video_url) && (
          <div className="mt-3">
            <a
              href={lesson.video_url}
              target="_blank"
              rel="noreferrer"
              className="flex items-center justify-center gap-2 w-full rounded-2xl bg-gradient-to-r from-rose-500 to-red-600 px-4 py-2.5 text-xs sm:text-sm font-extrabold text-white shadow-xs hover:shadow-md transition-all active:scale-[0.99]"
            >
              <IconPlay size={16} />
              <span>Video darsni ochish</span>
            </a>
          </div>
        )}
      </Card>

      {/* Lesson Explanation / Text Content */}
      <div className="mb-4 sm:mb-6">
        <div className="flex items-center gap-1.5 px-1 mb-1.5">
          <IconFileText size={16} className="text-blue-600" />
          <h2 className="text-[11px] sm:text-xs font-bold uppercase tracking-wider text-slate-500">
            Dars mavzusi va tushuntirishi
          </h2>
        </div>

        <Card padding="none" className="p-4 sm:p-6 leading-relaxed text-slate-800 text-sm sm:text-base whitespace-pre-line border border-slate-100 shadow-2xs">
          {lesson.explanation}
        </Card>
      </div>

      {/* Materials List */}
      {lesson.materials.length > 0 && (
        <div className="mb-4 sm:mb-6">
          <h3 className="text-[11px] sm:text-xs font-bold uppercase tracking-wider text-slate-500 px-1 mb-1.5">
            Qo‘shimcha materiallar ({lesson.materials.length})
          </h3>
          <div className="space-y-2">
            {lesson.materials.map((m) => (
              <MaterialItem key={m.id} material={m} token={token} />
            ))}
          </div>
        </div>
      )}

      {/* Action / Quiz Unlock Area */}
      <Card variant="flat" padding="none" className="p-4 sm:p-6 text-center border border-slate-200">
        {!lesson.viewed ? (
          <div>
            <h3 className="text-base font-bold text-slate-800">
              Darsni to‘liq o‘rganib bo‘ldingizmi?
            </h3>
            <p className="mt-1 text-xs text-slate-500 max-w-md mx-auto">
              Nazariy qismni o‘qib bo‘lgach, "O‘qib bo‘ldim" tugmasini bosing. Sizga yulduzcha beriladi va test topshirish imkoniyati ochiladi!
            </p>
            <div className="mt-5 max-w-sm mx-auto">
              <Button
                variant="primary"
                size="lg"
                fullWidth
                loading={busy}
                onClick={handleMarkViewed}
                icon={<IconCheck size={20} />}
              >
                O‘qib bo‘ldim ✅
              </Button>
            </div>
          </div>
        ) : (
          <div className="space-y-4">
            <div className="inline-flex items-center gap-2 px-4 py-2 rounded-full bg-emerald-50 text-emerald-700 border border-emerald-200 text-xs font-bold">
              <IconCheck size={16} />
              <span>{justEarned ? "Ajoyib! Yulduzcha hisobingizga qo‘shildi ⭐" : "Bu dars muvaffaqiyatli o‘qilgan ✅"}</span>
            </div>

            {earnedTitles.length > 0 && (
              <p className="text-xs font-bold text-amber-600">
                🏆 Yangi yutuq: {earnedTitles.join(", ")}
              </p>
            )}

            <div>
              <h3 className="text-lg font-extrabold text-slate-900">
                Bilimlarni sinab ko‘rish vaqti keldi!
              </h3>
              <p className="mt-1 text-xs text-slate-500">
                O‘tish bali: {lesson.pass_threshold_percent}%. Muvaffaqiyatli o‘tsangiz, keyingi dars ochiladi.
              </p>
            </div>

            <div className="max-w-sm mx-auto">
              <Button
                variant="accent"
                size="lg"
                fullWidth
                onClick={onStartQuiz}
                icon={<IconSparkles size={20} />}
              >
                Testni boshlash 🚀
              </Button>
            </div>
          </div>
        )}
      </Card>
    </div>
  );
}
