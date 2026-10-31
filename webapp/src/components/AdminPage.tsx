/**
 * AdminPage.tsx — content management for admins only (is_admin === true).
 *
 * Flow: pick a grade -> see its subjects -> add subject / pick subject ->
 * see its lessons -> add lesson -> add quiz questions to a lesson.
 *
 * Everything here calls the /api/admin/* endpoints; the backend double-checks
 * on every request that the caller really is an admin (403 otherwise), so even
 * if someone hacked the UI they could not write anything.
 */
import { useCallback, useEffect, useState } from "react";
import { api, ApiError } from "../api";
import type { AdminLesson, GradeOverview } from "../types";

interface Props {
  token: string;
  notify: (msg: string) => void;
}

const input =
  "w-full rounded-xl border border-blue-200 bg-white px-3 py-2 text-sm text-slate-800 outline-none focus:border-blue-400";
const label = "mt-3 block text-xs font-bold uppercase tracking-wide text-blue-400";
const btnPrimary =
  "mt-4 w-full rounded-xl bg-blue-600 px-4 py-2.5 text-sm font-bold text-white shadow enabled:hover:bg-blue-700 disabled:opacity-50";
const btnGhost =
  "rounded-xl border-2 border-dashed border-blue-200 bg-blue-50 px-3 py-2 text-xs font-bold text-blue-600";

function errText(e: unknown): string {
  return e instanceof ApiError ? e.message : "Aloqa xatosi: serverga yetib bo‘lmadi.";
}

export default function AdminPage({ token, notify }: Props) {
  const [overview, setOverview] = useState<GradeOverview[] | null>(null);
  const [loadError, setLoadError] = useState("");
  const [gradeId, setGradeId] = useState<number | null>(null);
  const [subjectId, setSubjectId] = useState<number | null>(null);
  const [lessons, setLessons] = useState<AdminLesson[] | null>(null);
  const [showSubjectForm, setShowSubjectForm] = useState(false);
  const [showLessonForm, setShowLessonForm] = useState(false);
  const [questionLessonId, setQuestionLessonId] = useState<number | null>(null);
  const [materialLessonId, setMaterialLessonId] = useState<number | null>(null);
  const [formKey, setFormKey] = useState(0); // remount forms after a successful add

  const loadOverview = useCallback(async () => {
    try {
      setOverview(await api.adminOverview(token));
      setLoadError("");
    } catch (e) {
      setLoadError(errText(e));
    }
  }, [token]);

  useEffect(() => {
    void loadOverview();
  }, [loadOverview]);

  const loadLessons = useCallback(
    async (sid: number) => {
      try {
        setLessons(await api.adminLessons(token, sid));
      } catch (e) {
        setLessons([]);
        notify(errText(e));
      }
    },
    [token, notify],
  );

  const pickGrade = (g: number) => {
    setGradeId(g);
    setSubjectId(null);
    setLessons(null);
    setShowSubjectForm(false);
    setShowLessonForm(false);
    setQuestionLessonId(null);
    setMaterialLessonId(null);
  };

  const pickSubject = (s: number) => {
    setSubjectId(s);
    setShowLessonForm(false);
    setQuestionLessonId(null);
    setMaterialLessonId(null);
    void loadLessons(s);
  };

  /** Called after any successful create: refresh lists + friendly toast. */
  const afterCreate = async (what: string) => {
    notify(`${what} qo‘shildi ✅`);
    setShowSubjectForm(false);
    setShowLessonForm(false);
    setQuestionLessonId(null);
    setMaterialLessonId(null);
    setFormKey((k) => k + 1);
    await loadOverview();
    if (subjectId !== null) void loadLessons(subjectId);
  };

  if (loadError && overview === null) {
    return (
      <section className="mt-6 rounded-2xl border-2 border-dashed border-rose-200 bg-rose-50 p-5 text-center">
        <p className="text-sm font-bold text-rose-700">Admin panel ochilmadi</p>
        <p className="mt-1 text-xs text-rose-500">{loadError}</p>
      </section>
    );
  }
  if (overview === null) {
    return <p className="mt-8 text-center text-sm font-medium text-blue-500">Yuklanmoqda… ⏳</p>;
  }

  const activeGrade = overview.find((g) => g.grade_id === gradeId) ?? null;
  const activeSubject = activeGrade?.subjects.find((s) => s.id === subjectId) ?? null;

  return (
    <section className="mt-6 space-y-5">
      <div className="rounded-2xl bg-blue-900 p-4 text-white shadow-md">
        <p className="text-sm font-extrabold">🛠 Admin panel</p>
        <p className="mt-1 text-xs text-blue-200">
          Sinf tanlang, fan va darslarni to‘ldiring. O‘quvchilar bu kontentni Mini
          App’da ko‘radi.
        </p>
      </div>

      {/* 1) Grade chips */}
      <div>
        <h3 className="text-xs font-bold uppercase tracking-wide text-blue-400">1. Sinf</h3>
        <div className="mt-2 flex flex-wrap gap-1.5">
          {overview.map((g) => (
            <button
              key={g.grade_id}
              onClick={() => pickGrade(g.grade_id)}
              className={
                g.grade_id === gradeId
                  ? "rounded-full bg-blue-600 px-3 py-1.5 text-xs font-bold text-white"
                  : "rounded-full border border-blue-200 bg-white px-3 py-1.5 text-xs font-semibold text-blue-600 hover:border-blue-400"
              }
            >
              {g.grade_name}
            </button>
          ))}
        </div>
      </div>

      {/* 2) Subjects of the chosen grade */}
      {activeGrade && (
        <div>
          <div className="flex items-center justify-between">
            <h3 className="text-xs font-bold uppercase tracking-wide text-blue-400">
              2. Fanlar ({activeGrade.subjects.length})
            </h3>
            <button onClick={() => setShowSubjectForm((v) => !v)} className={btnGhost}>
              + Yangi fan
            </button>
          </div>

          {showSubjectForm && (
            <SubjectForm key={formKey} token={token} gradeId={activeGrade.grade_id} onDone={() => afterCreate("Fan")} />
          )}

          <div className="mt-2 space-y-2">
            {activeGrade.subjects.length === 0 && !showSubjectForm && (
              <p className="rounded-xl bg-slate-50 p-3 text-center text-xs text-slate-500">
                Bu sinfda hozircha fan yo‘q. «+ Yangi fan» bilan qo‘shing.
              </p>
            )}
            {activeGrade.subjects.map((s) => (
              <button
                key={s.id}
                onClick={() => pickSubject(s.id)}
                className={
                  s.id === subjectId
                    ? "flex w-full items-center justify-between rounded-xl border-2 border-blue-500 bg-blue-50 px-3 py-2.5 text-left"
                    : "flex w-full items-center justify-between rounded-xl border border-blue-100 bg-white px-3 py-2.5 text-left hover:border-blue-300"
                }
              >
                <span className="text-sm font-semibold text-slate-800">
                  {s.emoji} {s.name}
                </span>
                <span className="text-xs text-blue-500">{s.lesson_count} dars →</span>
              </button>
            ))}
          </div>
        </div>
      )}

      {/* 3) Lessons of the chosen subject */}
      {activeSubject && (
        <div>
          <div className="flex items-center justify-between">
            <h3 className="text-xs font-bold uppercase tracking-wide text-blue-400">
              3. Darslar — {activeSubject.emoji} {activeSubject.name}
            </h3>
            <button onClick={() => setShowLessonForm((v) => !v)} className={btnGhost}>
              + Yangi dars
            </button>
          </div>

          {showLessonForm && (
            <LessonForm key={formKey} token={token} subjectId={activeSubject.id} onDone={() => afterCreate("Dars")} />
          )}

          <div className="mt-2 space-y-2">
            {lessons === null && <p className="text-xs text-slate-400">Darslar yuklanmoqda…</p>}
            {lessons !== null && lessons.length === 0 && !showLessonForm && (
              <p className="rounded-xl bg-slate-50 p-3 text-center text-xs text-slate-500">
                Bu fandda hozircha dars yo‘q. «+ Yangi dars» bilan qo‘shing.
              </p>
            )}
            {lessons?.map((l) => (
              <div key={l.id} className="rounded-xl border border-blue-100 bg-white px-3 py-2.5">
                <div className="flex items-center justify-between">
                  <span className="text-sm font-semibold text-slate-800">
                    {l.level_order}. {l.title}
                  </span>
                  <span className="text-xs text-slate-400">
                    {l.question_count} savol · {l.material_count} material
                  </span>
                </div>
                <div className="mt-1.5 flex flex-wrap gap-x-4 gap-y-1">
                  <button
                    onClick={() =>
                      setQuestionLessonId((cur) => (cur === l.id ? null : l.id))
                    }
                    className="text-xs font-bold text-blue-500 underline-offset-2 hover:underline"
                  >
                    {questionLessonId === l.id ? "Savol formasini yopish ▲" : "+ Savol qo‘shish"}
                  </button>
                  <button
                    onClick={() =>
                      setMaterialLessonId((cur) => (cur === l.id ? null : l.id))
                    }
                    className="text-xs font-bold text-emerald-600 underline-offset-2 hover:underline"
                  >
                    {materialLessonId === l.id ? "Material formasini yopish ▲" : "🎞 + Material"}
                  </button>
                </div>
                {questionLessonId === l.id && (
                  <QuestionForm
                    key={formKey}
                    token={token}
                    lessonId={l.id}
                    onDone={() => afterCreate("Savol")}
                  />
                )}
                {materialLessonId === l.id && (
                  <MaterialForm
                    key={formKey}
                    token={token}
                    lessonId={l.id}
                    onDone={() => afterCreate("Material")}
                  />
                )}
              </div>
            ))}
          </div>
        </div>
      )}
    </section>
  );
}

/* ---------- forms ---------- */

function SubjectForm({
  token,
  gradeId,
  onDone,
}: {
  token: string;
  gradeId: number;
  onDone: () => Promise<void> | void;
}) {
  const [name, setName] = useState("");
  const [emoji, setEmoji] = useState("📘");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  const submit = async () => {
    setBusy(true);
    setErr("");
    try {
      await api.adminCreateSubject(token, { grade_id: gradeId, name: name.trim(), emoji: emoji.trim() || "📘" });
      await onDone();
    } catch (e) {
      setErr(errText(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="mt-2 rounded-xl border border-blue-100 bg-white p-3 shadow-sm">
      <label className={label}>Fan nomi (masalan: Fizika)</label>
      <input className={input} value={name} onChange={(e) => setName(e.target.value)} placeholder="Fizika" />
      <label className={label}>Emoji</label>
      <input className={input} value={emoji} onChange={(e) => setEmoji(e.target.value)} maxLength={4} placeholder="📘" />
      {err && <p className="mt-2 text-xs font-semibold text-rose-600">{err}</p>}
      <button
        onClick={submit}
        disabled={busy || name.trim().length < 2}
        className={btnPrimary}
      >
        {busy ? "Saqlanmoqda…" : "Fan saqlash"}
      </button>
    </div>
  );
}

function LessonForm({
  token,
  subjectId,
  onDone,
}: {
  token: string;
  subjectId: number;
  onDone: () => Promise<void> | void;
}) {
  const [title, setTitle] = useState("");
  const [explanation, setExplanation] = useState("");
  const [stars, setStars] = useState(5);
  const [threshold, setThreshold] = useState(60);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  const submit = async () => {
    setBusy(true);
    setErr("");
    try {
      await api.adminCreateLesson(token, subjectId, {
        title: title.trim(),
        explanation: explanation.trim(),
        stars_reward: stars,
        pass_threshold_percent: threshold,
      });
      await onDone();
    } catch (e) {
      setErr(errText(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="mt-2 rounded-xl border border-blue-100 bg-white p-3 shadow-sm">
      <label className={label}>Dars nomi</label>
      <input className={input} value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Masalan: Sonlarni tanib olamiz" />
      <label className={label}>Dars matni (tushuntirish)</label>
      <textarea
        className={`${input} min-h-24`}
        value={explanation}
        onChange={(e) => setExplanation(e.target.value)}
        placeholder="O‘quvchi shu matnni o‘qiydi. Kamida 10 ta belgi kerak."
      />
      <div className="mt-3 grid grid-cols-2 gap-3">
        <div>
          <label className={label}>⭐ sovrin (1–50)</label>
          <input
            className={input}
            type="number"
            min={1}
            max={50}
            value={stars}
            onChange={(e) => setStars(Number(e.target.value) || 1)}
          />
        </div>
        <div>
          <label className={label}>O‘tish chegarasi % (10–100)</label>
          <input
            className={input}
            type="number"
            min={10}
            max={100}
            value={threshold}
            onChange={(e) => setThreshold(Number(e.target.value) || 10)}
          />
        </div>
      </div>
      {err && <p className="mt-2 text-xs font-semibold text-rose-600">{err}</p>}
      <button
        onClick={submit}
        disabled={busy || title.trim().length < 2 || explanation.trim().length < 10}
        className={btnPrimary}
      >
        {busy ? "Saqlanmoqda…" : "Dars saqlash"}
      </button>
    </div>
  );
}

interface OptionRow {
  text: string;
  is_correct: boolean;
}

function QuestionForm({
  token,
  lessonId,
  onDone,
}: {
  token: string;
  lessonId: number;
  onDone: () => Promise<void> | void;
}) {
  const [text, setText] = useState("");
  const [kind, setKind] = useState<"single" | "text">("single");
  const [options, setOptions] = useState<OptionRow[]>([
    { text: "", is_correct: true },
    { text: "", is_correct: false },
  ]);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  const setOption = (i: number, patch: Partial<OptionRow>) =>
    setOptions((prev) => prev.map((o, j) => (j === i ? { ...o, ...patch } : o)));

  /** single -> radio (exactly one correct); text -> checkbox (>=1 correct). */
  const markCorrect = (i: number) => {
    if (kind === "single") setOptions((prev) => prev.map((o, j) => ({ ...o, is_correct: j === i })));
    else setOptions((prev) => prev.map((o, j) => (j === i ? { ...o, is_correct: !o.is_correct } : o)));
  };

  const ready =
    text.trim().length >= 3 &&
    options.every((o) => o.text.trim().length > 0) &&
    options.some((o) => o.is_correct);

  const submit = async () => {
    setBusy(true);
    setErr("");
    try {
      await api.adminCreateQuestion(token, lessonId, {
        text: text.trim(),
        kind,
        options: options.map((o) => ({ text: o.text.trim(), is_correct: o.is_correct })),
      });
      await onDone();
    } catch (e) {
      setErr(errText(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="mt-2 rounded-xl border border-blue-100 bg-blue-50/50 p-3">
      <label className={label}>Savol matni</label>
      <input className={input} value={text} onChange={(e) => setText(e.target.value)} placeholder="Masalan: 3 + 4 nechaga teng?" />

      <label className={label}>Savol turi</label>
      <div className="flex gap-2">
        {(
          [
            ["single", "🔘 Bir variantli"],
            ["text", "⌨️ Matnli (yozib javob)"],
          ] as const
        ).map(([k, lbl]) => (
          <button
            key={k}
            onClick={() => {
              setKind(k);
              if (k === "single") setOptions((prev) => prev.map((o, j) => ({ ...o, is_correct: j === 0 })));
            }}
            className={
              kind === k
                ? "flex-1 rounded-lg bg-blue-600 px-2 py-1.5 text-xs font-bold text-white"
                : "flex-1 rounded-lg border border-blue-200 bg-white px-2 py-1.5 text-xs font-semibold text-blue-600"
            }
          >
            {lbl}
          </button>
        ))}
      </div>

      <label className={label}>
        Javob variantlari — {kind === "single" ? "bittasi to‘g‘ri" : "to‘g‘ri javob(lar) belgilang"}
      </label>
      <div className="space-y-1.5">
        {options.map((o, i) => (
          <div key={i} className="flex items-center gap-2">
            <button
              onClick={() => markCorrect(i)}
              title="To‘g‘ri javob"
              className={
                o.is_correct
                  ? "h-7 w-7 shrink-0 rounded-full bg-emerald-500 text-xs font-bold text-white"
                  : "h-7 w-7 shrink-0 rounded-full border border-slate-300 bg-white text-xs text-slate-400"
              }
            >
              ✓
            </button>
            <input
              className={input}
              value={o.text}
              onChange={(e) => setOption(i, { text: e.target.value })}
              placeholder={`Variant ${i + 1}`}
            />
            {options.length > 2 && (
              <button
                onClick={() => setOptions((prev) => prev.filter((_, j) => j !== i))}
                className="shrink-0 text-slate-400 hover:text-rose-500"
                title="O‘chirish"
              >
                ✕
              </button>
            )}
          </div>
        ))}
      </div>
      {options.length < 6 && (
        <button
          onClick={() => setOptions((prev) => [...prev, { text: "", is_correct: kind === "text" }])}
          className="mt-2 text-xs font-bold text-blue-500 hover:underline"
        >
          + Variant qo‘shish
        </button>
      )}

      {err && <p className="mt-2 text-xs font-semibold text-rose-600">{err}</p>}
      <button onClick={submit} disabled={busy || !ready} className={btnPrimary}>
        {busy ? "Saqlanmoqda…" : "Savol saqlash"}
      </button>
    </div>
  );
}

const MATERIAL_KINDS = [
  { kind: "video", label: "▶️ Video" },
  { kind: "pdf", label: "📄 PDF" },
  { kind: "live", label: "🔴 Jonli dars" },
  { kind: "text", label: "📝 Yozma matn" },
] as const;

const isUrl = (value: string) => /^https?:\/\//i.test(value.trim());

function MaterialForm({
  token,
  lessonId,
  onDone,
}: {
  token: string;
  lessonId: number;
  onDone: () => Promise<void> | void;
}) {
  const [kind, setKind] = useState<string>("video");
  const [title, setTitle] = useState("");
  const [content, setContent] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  const needsUrl = kind !== "text";
  const ready =
    title.trim().length >= 2 &&
    content.trim().length >= 1 &&
    (!needsUrl || isUrl(content));

  const submit = async () => {
    setBusy(true);
    setErr("");
    try {
      await api.adminCreateMaterial(token, lessonId, {
        kind,
        title: title.trim(),
        content: content.trim(),
      });
      await onDone();
    } catch (e) {
      setErr(errText(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="mt-2 rounded-xl border border-emerald-100 bg-emerald-50/50 p-3">
      <label className={label}>Material formati</label>
      <div className="grid grid-cols-2 gap-2">
        {MATERIAL_KINDS.map((k) => (
          <button
            key={k.kind}
            onClick={() => setKind(k.kind)}
            className={
              kind === k.kind
                ? "rounded-lg bg-emerald-600 px-2 py-1.5 text-xs font-bold text-white"
                : "rounded-lg border border-emerald-200 bg-white px-2 py-1.5 text-xs font-semibold text-emerald-700"
            }
          >
            {k.label}
          </button>
        ))}
      </div>

      <label className={label}>Sarlavha</label>
      <input
        className={input}
        value={title}
        onChange={(e) => setTitle(e.target.value)}
        maxLength={160}
        placeholder={kind === "live" ? "Masalan: Jonli dars — 5-noyabr" : "Masalan: Sonlarni qo‘shish"}
      />

      <label className={label}>{needsUrl ? "Havola (https:// …)" : "Yozma matn"}</label>
      <textarea
        className={`${input} min-h-20`}
        value={content}
        onChange={(e) => setContent(e.target.value)}
        maxLength={5000}
        placeholder={
          needsUrl
            ? "https://youtu.be/… yoki https://…/hujjat.pdf"
            : "O‘quvchi dars ichida o‘qiydigan qisqa tushuntirish"
        }
      />
      {needsUrl && content.trim() !== "" && !isUrl(content) && (
        <p className="mt-1 text-xs font-semibold text-rose-600">
          Havola http:// yoki https:// bilan boshlanishi kerak.
        </p>
      )}

      {err && <p className="mt-2 text-xs font-semibold text-rose-600">{err}</p>}
      <button onClick={submit} disabled={busy || !ready} className={btnPrimary}>
        {busy ? "Saqlanmoqda…" : "Material saqlash"}
      </button>
    </div>
  );
}
