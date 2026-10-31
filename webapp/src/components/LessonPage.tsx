/**
 * LessonPage.tsx — reads the lesson (explanation + materials), then the
 * pupil taps "O'qib bo'ldim" which records the view on the server (small
 * star reward) and unlocks the quiz button.
 */
import { useEffect, useState } from "react";
import { api, ApiError } from "../api";
import type { LessonDetail, Material } from "../types";
import { BackButton } from "./SubjectLessons";

const isLink = (value: string) => /^https?:\/\//i.test(value.trim());

const sizeLabel = (bytes: number | null) => {
  if (!bytes) return "";
  if (bytes >= 1_000_000) return `${(bytes / 1_000_000).toFixed(1)} MB`;
  return `${Math.max(1, Math.round(bytes / 1000))} KB`;
};

/**
 * An uploaded material (Telegram file): PDF downloads, video plays inline.
 * Bytes come from /api/materials/{id}/file with the token only in the header.
 */
function FileMaterialCard({ material, token }: { material: Material; token: string }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [videoUrl, setVideoUrl] = useState<string | null>(null);

  useEffect(
    () => () => {
      if (videoUrl) URL.revokeObjectURL(videoUrl);
    },
    [videoUrl],
  );

  const open = async () => {
    setBusy(true);
    setError("");
    try {
      const { blob, fileName } = await api.downloadMaterialFile(token, material.id);
      const url = URL.createObjectURL(blob);
      if (material.kind === "video") {
        setVideoUrl(url);
      } else {
        const a = document.createElement("a");
        a.href = url;
        a.download = fileName;
        document.body.appendChild(a);
        a.click();
        a.remove();
        setTimeout(() => URL.revokeObjectURL(url), 60_000);
      }
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Faylni yuklab bo‘lmadi");
    } finally {
      setBusy(false);
    }
  };

  const isVideo = material.kind === "video";
  const meta = [material.file_name, sizeLabel(material.file_size)].filter(Boolean).join(" · ");

  return (
    <div className="mt-3">
      <button
        onClick={open}
        disabled={busy}
        className="flex w-full items-center gap-3 rounded-2xl border-2 border-blue-200 bg-white px-4 py-3 text-left shadow-sm active:scale-[0.99] disabled:opacity-50"
      >
        <span className="text-xl">{isVideo ? "▶️" : "📥"}</span>
        <span className="min-w-0 flex-1">
          <span className="block truncate text-sm font-bold text-blue-900">{material.title}</span>
          <span className="block text-xs font-semibold text-blue-500">
            {busy ? "Yuklanmoqda…" : isVideo ? "Videoni ochish" : "PDF’ni yuklab olish"}
          </span>
        </span>
        {meta && <span className="shrink-0 text-[10px] font-medium text-slate-400">{meta}</span>}
      </button>
      {error && <p className="mt-1 text-xs font-semibold text-rose-500">{error}</p>}
      {videoUrl && (
        <video
          controls
          src={videoUrl}
          className="mt-2 w-full rounded-2xl border-2 border-blue-100 bg-black"
        >
          Brauzeringiz videoni qo‘llab-quvvatlamaydi.
        </video>
      )}
    </div>
  );
}

/** One lesson material in the four supported formats (+ legacy image). */
function MaterialCard({ material, token }: { material: Material; token: string }) {
  const { kind, title, content } = material;

  // Uploaded Telegram file (pdf/video) — no URL involved.
  if (material.file_id) {
    return <FileMaterialCard material={material} token={token} />;
  }

  if (kind === "image" || (kind === "text" && isLink(content))) {
    return (
      <div className="mt-3 rounded-2xl border-2 border-blue-100 bg-blue-50 p-4">
        {title && <p className="text-sm font-bold text-blue-800">📌 {title}</p>}
        {kind === "image" ? (
          <img src={content} alt={title} className="mt-2 w-full rounded-xl" />
        ) : (
          <a
            href={content}
            target="_blank"
            rel="noreferrer"
            className="mt-1 block break-all text-sm font-semibold text-blue-600 underline"
          >
            {content}
          </a>
        )}
      </div>
    );
  }

  if (kind === "video" || kind === "pdf" || kind === "live") {
    const icon = kind === "video" ? "▶️" : kind === "pdf" ? "📄" : "🔴";
    const label = kind === "video" ? "Videoni ko‘rish" : kind === "pdf" ? "PDF’ni ochish" : "Jonli darsga qo‘shilish";
    return (
      <a
        href={content}
        target="_blank"
        rel="noreferrer"
        className="mt-3 flex items-center gap-3 rounded-2xl border-2 border-blue-200 bg-white px-4 py-3 shadow-sm active:scale-[0.99]"
      >
        <span className="text-xl">{icon}</span>
        <span className="min-w-0 flex-1">
          <span className="block truncate text-sm font-bold text-blue-900">{title}</span>
          <span className="block text-xs font-semibold text-blue-500">{label}</span>
        </span>
        <span className="text-blue-400">→</span>
      </a>
    );
  }

  // text (yozma matn) and anything unknown → printed notes
  return (
    <div className="mt-3 rounded-2xl border-2 border-blue-100 bg-blue-50 p-4">
      {title && <p className="text-sm font-bold text-blue-800">📝 {title}</p>}
      <p className="mt-1 whitespace-pre-line text-sm leading-relaxed text-blue-900">{content}</p>
    </div>
  );
}

export default function LessonPage({
  token,
  lessonId,
  onBack,
  onStartQuiz,
  onViewed,
}: {
  token: string;
  lessonId: number;
  onBack: () => void;
  onStartQuiz: () => void;
  onViewed: () => void; // refresh home counts
}) {
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
        alive && setError(e instanceof ApiError ? e.message : "Yuklab bo'lmadi"),
      );
    return () => {
      alive = false;
    };
  }, [token, lessonId]);

  const markViewed = async () => {
    setBusy(true);
    try {
      const r = await api.markViewed(token, lessonId);
      setLesson((l) => (l ? { ...l, viewed: true } : l));
      if (r.stars_granted) setJustEarned(true);
      setEarnedTitles(r.new_achievement_titles ?? []);
      onViewed();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Xatolik");
    } finally {
      setBusy(false);
    }
  };

  if (error)
    return (
      <section className="mt-6 rounded-2xl border-2 border-dashed border-rose-200 bg-rose-50 p-5 text-center">
        <p className="text-sm font-bold text-rose-700">Xatolik</p>
        <p className="mt-1 text-xs text-rose-500">{error}</p>
        <button onClick={onBack} className="mt-3 text-sm font-bold text-blue-500 underline">
          ← Orqaga
        </button>
      </section>
    );
  if (!lesson)
    return <p className="mt-8 text-center text-sm font-medium text-blue-500">Dars yuklanmoqda… ⏳</p>;

  return (
    <section className="mt-6">
      <BackButton onClick={onBack} />
      <p className="mt-2 text-xs font-bold uppercase tracking-wide text-blue-400">
        {lesson.subject_name} · {lesson.level_order}-bosqich
      </p>
      <h2 className="text-2xl font-extrabold text-blue-900">{lesson.title}</h2>

      <article className="mt-4 whitespace-pre-line rounded-2xl bg-white p-5 text-[15px] leading-relaxed text-slate-700 shadow-md">
        {lesson.explanation}
      </article>

      {lesson.video_url && isLink(lesson.video_url) && (
        <a
          href={lesson.video_url}
          target="_blank"
          rel="noreferrer"
          className="mt-3 flex items-center justify-center gap-2 rounded-2xl bg-gradient-to-br from-rose-500 to-red-600 px-4 py-3 text-sm font-bold text-white shadow-md active:scale-[0.99]"
        >
          🎬 Video darsni ko‘rish
        </a>
      )}

      {lesson.materials.map((m) => (
        <MaterialCard key={m.id} material={m} token={token} />
      ))}

      <div className="mt-6 space-y-3">
        {!lesson.viewed ? (
          <button
            onClick={markViewed}
            disabled={busy}
            className="w-full rounded-2xl bg-gradient-to-br from-emerald-500 to-emerald-600 px-4 py-4 text-center text-base font-bold text-white shadow-md transition-transform active:scale-95 disabled:opacity-50"
          >
            {busy ? "Saqlanmoqda…" : "O'qib bo'ldim ✅"}
          </button>
        ) : (
          <>
            <p className="text-center text-sm font-semibold text-emerald-600">
              {justEarned ? "Barakalla! +⭐ qo'shib olindi" : "Bu dars o'qilgan ✅"}
            </p>
            {earnedTitles.length > 0 && (
              <p className="text-center text-sm font-semibold text-amber-600">
                🏆 Yangi yutuq: {earnedTitles.join(", ")}
              </p>
            )}
            <button
              onClick={onStartQuiz}
              className="w-full rounded-2xl bg-gradient-to-br from-blue-500 to-indigo-600 px-4 py-4 text-center text-base font-bold text-white shadow-md transition-transform active:scale-95"
            >
              Testni boshlash 🧩
            </button>
          </>
        )}
      </div>
    </section>
  );
}
