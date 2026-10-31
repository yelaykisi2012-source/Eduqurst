/**
 * AdminPage.tsx — content management for admins only (is_admin === true).
 *
 * Flow: pick a grade -> see its subjects -> add/edit/hide subjects ->
 * pick subject -> see its lessons -> add/edit/hide lessons -> add materials
 * and quiz questions, and delete individual materials/questions.
 *
 * Everything here calls the /api/admin/* endpoints; the backend double-checks
 * on every request that the caller really is an admin (403 otherwise), so even
 * if someone hacked the UI they could not write anything. Subjects and lessons
 * are never hard-deleted — hiding keeps pupil progress safe.
 */
import { useCallback, useEffect, useState } from "react";
import { api, ApiError } from "../api";
import type {
  AdminLesson,
  AdminQuestionDetail,
  AdminSubject,
  GradeOverview,
  Material,
} from "../types";

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
const miniBtn = "text-xs font-bold text-blue-500 underline-offset-2 hover:underline";
const miniDanger = "text-xs font-bold text-rose-500 underline-offset-2 hover:underline";

type Panel = "edit" | "question" | "material" | "materials" | "questions";

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
  const [editingSubjectId, setEditingSubjectId] = useState<number | null>(null);
  const [panel, setPanel] = useState<{ lessonId: number; kind: Panel } | null>(null);
  const [busyKey, setBusyKey] = useState<string | null>(null);
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

  const refresh = useCallback(async () => {
    await loadOverview();
    if (subjectId !== null) await loadLessons(subjectId);
  }, [loadOverview, loadLessons, subjectId]);

  const pickGrade = (g: number) => {
    setGradeId(g);
    setSubjectId(null);
    setLessons(null);
    setShowSubjectForm(false);
    setShowLessonForm(false);
    setEditingSubjectId(null);
    setPanel(null);
  };

  const pickSubject = (s: number) => {
    setSubjectId(s);
    setShowLessonForm(false);
    setEditingSubjectId(null);
    setPanel(null);
    void loadLessons(s);
  };

  const togglePanel = (lessonId: number, kind: Panel) => {
    setPanel((cur) =>
      cur && cur.lessonId === lessonId && cur.kind === kind ? null : { lessonId, kind },
    );
  };

  /** Called after any successful create: refresh lists + friendly toast. */
  const afterCreate = async (what: string) => {
    notify(`${what} qo‘shildi ✅`);
    setShowSubjectForm(false);
    setShowLessonForm(false);
    setPanel(null);
    setFormKey((k) => k + 1);
    await refresh();
  };

  /** Called after edit/hide: keep the current selection, refresh counts. */
  const afterChange = async (what: string, closeEditor = true) => {
    notify(`${what} ✅`);
    if (closeEditor) {
      setEditingSubjectId(null);
      setPanel((cur) => (cur && cur.kind === "edit" ? null : cur));
    }
    setFormKey((k) => k + 1);
    await refresh();
  };

  const toggleSubject = async (s: AdminSubject) => {
    setBusyKey(`subject-${s.id}`);
    try {
      await api.adminUpdateSubject(token, s.id, { is_published: !s.is_published });
      notify(s.is_published ? "Fan yashirildi 🙈" : "Fan chiqarildi 👁");
      await refresh();
    } catch (e) {
      notify(errText(e));
    } finally {
      setBusyKey(null);
    }
  };

  const toggleLesson = async (l: AdminLesson) => {
    setBusyKey(`lesson-${l.id}`);
    try {
      await api.adminUpdateLesson(token, l.id, { is_published: !l.is_published });
      notify(l.is_published ? "Dars yashirildi 🙈" : "Dars chiqarildi 👁");
      await refresh();
    } catch (e) {
      notify(errText(e));
    } finally {
      setBusyKey(null);
    }
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
            <SubjectForm
              key={`new-${formKey}`}
              token={token}
              gradeId={activeGrade.grade_id}
              onDone={() => afterCreate("Fan")}
            />
          )}

          <div className="mt-2 space-y-2">
            {activeGrade.subjects.length === 0 && !showSubjectForm && (
              <p className="rounded-xl bg-slate-50 p-3 text-center text-xs text-slate-500">
                Bu sinfda hozircha fan yo‘q. «+ Yangi fan» bilan qo‘shing.
              </p>
            )}
            {activeGrade.subjects.map((s) => (
              <div
                key={s.id}
                className={
                  s.id === subjectId
                    ? "rounded-xl border-2 border-blue-500 bg-blue-50 px-3 py-2.5"
                    : "rounded-xl border border-blue-100 bg-white px-3 py-2.5"
                }
              >
                <button
                  onClick={() => pickSubject(s.id)}
                  className="flex w-full items-center justify-between text-left"
                >
                  <span className="text-sm font-semibold text-slate-800">
                    {s.emoji} {s.name}{" "}
                    {!s.is_published && (
                      <span className="ml-1 rounded-full bg-slate-200 px-2 py-0.5 text-[10px] font-bold text-slate-600">
                        yashirilgan
                      </span>
                    )}
                  </span>
                  <span className="text-xs text-blue-500">{s.lesson_count} dars →</span>
                </button>
                <div className="mt-1.5 flex flex-wrap gap-x-4 gap-y-1">
                  <button
                    onClick={() =>
                      setEditingSubjectId((cur) => (cur === s.id ? null : s.id))
                    }
                    className={miniBtn}
                  >
                    ✏️ Tahrirlash
                  </button>
                  <button
                    onClick={() => void toggleSubject(s)}
                    disabled={busyKey === `subject-${s.id}`}
                    className={s.is_published ? miniDanger : miniBtn}
                  >
                    {s.is_published ? "🙈 Yashirish" : "👁 Chiqarish"}
                  </button>
                </div>
                {editingSubjectId === s.id && (
                  <SubjectEditForm
                    key={`edit-${s.id}`}
                    token={token}
                    subject={s}
                    onDone={(msg) => afterChange(msg)}
                    onCancel={() => setEditingSubjectId(null)}
                  />
                )}
              </div>
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
            <LessonForm
              key={`new-${formKey}`}
              token={token}
              subjectId={activeSubject.id}
              onDone={() => afterCreate("Dars")}
            />
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
                <div className="flex items-start justify-between gap-2">
                  <p className="text-sm font-semibold text-slate-800">
                    {l.level_order}. {l.title}{" "}
                    {!l.is_published && (
                      <span className="ml-1 rounded-full bg-slate-200 px-2 py-0.5 text-[10px] font-bold text-slate-600">
                        yashirilgan
                      </span>
                    )}
                  </p>
                  <p className="shrink-0 text-right text-[11px] leading-5 text-slate-400">
                    {l.question_count} savol · {l.material_count} material
                    <br />
                    ⭐ {l.stars_reward} · {l.pass_threshold_percent}%
                  </p>
                </div>
                <div className="mt-1.5 flex flex-wrap gap-x-4 gap-y-1">
                  <button onClick={() => togglePanel(l.id, "edit")} className={miniBtn}>
                    {panel?.lessonId === l.id && panel.kind === "edit" ? "Tahrirni yopish ▲" : "✏️ Tahrirlash"}
                  </button>
                  <button
                    onClick={() => void toggleLesson(l)}
                    disabled={busyKey === `lesson-${l.id}`}
                    className={l.is_published ? miniDanger : miniBtn}
                  >
                    {l.is_published ? "🙈 Yashirish" : "👁 Chiqarish"}
                  </button>
                  <button onClick={() => togglePanel(l.id, "question")} className="text-xs font-bold text-blue-500 underline-offset-2 hover:underline">
                    {panel?.lessonId === l.id && panel.kind === "question" ? "Formani yopish ▲" : "+ Savol qo‘shish"}
                  </button>
                  <button onClick={() => togglePanel(l.id, "material")} className="text-xs font-bold text-emerald-600 underline-offset-2 hover:underline">
                    {panel?.lessonId === l.id && panel.kind === "material" ? "Formani yopish ▲" : "🎞 + Material"}
                  </button>
                  <button onClick={() => togglePanel(l.id, "materials")} className="text-xs font-bold text-emerald-700 underline-offset-2 hover:underline">
                    {panel?.lessonId === l.id && panel.kind === "materials" ? "Ro‘yxatni yopish ▲" : `📋 Materiallar (${l.material_count})`}
                  </button>
                  <button onClick={() => togglePanel(l.id, "questions")} className="text-xs font-bold text-blue-700 underline-offset-2 hover:underline">
                    {panel?.lessonId === l.id && panel.kind === "questions" ? "Ro‘yxatni yopish ▲" : `📝 Savollar (${l.question_count})`}
                  </button>
                </div>

                {panel?.lessonId === l.id && panel.kind === "edit" && (
                  <LessonEditForm
                    key={`edit-${l.id}`}
                    token={token}
                    lesson={l}
                    onDone={(msg) => afterChange(msg)}
                    onCancel={() => setPanel(null)}
                  />
                )}
                {panel?.lessonId === l.id && panel.kind === "question" && (
                  <QuestionForm
                    key={`q-${l.id}-${formKey}`}
                    token={token}
                    lessonId={l.id}
                    onDone={() => afterCreate("Savol")}
                  />
                )}
                {panel?.lessonId === l.id && panel.kind === "material" && (
                  <MaterialForm
                    key={`m-${l.id}-${formKey}`}
                    token={token}
                    lessonId={l.id}
                    onDone={() => afterCreate("Material")}
                  />
                )}
                {panel?.lessonId === l.id && panel.kind === "materials" && (
                  <MaterialList
                    token={token}
                    lessonId={l.id}
                    onChanged={() => afterChange("Material o‘chirildi", false)}
                  />
                )}
                {panel?.lessonId === l.id && panel.kind === "questions" && (
                  <QuestionList
                    token={token}
                    lessonId={l.id}
                    onChanged={() => afterChange("Savol o‘chirildi", false)}
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

/* ---------- create forms ---------- */

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

/* ---------- edit forms ---------- */

function SubjectEditForm({
  token,
  subject,
  onDone,
  onCancel,
}: {
  token: string;
  subject: AdminSubject;
  onDone: (msg: string) => Promise<void> | void;
  onCancel: () => void;
}) {
  const [name, setName] = useState(subject.name);
  const [emoji, setEmoji] = useState(subject.emoji);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  const submit = async () => {
    setBusy(true);
    setErr("");
    try {
      await api.adminUpdateSubject(token, subject.id, {
        name: name.trim(),
        emoji: emoji.trim() || "📘",
      });
      await onDone("Fan yangilandi");
    } catch (e) {
      setErr(errText(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="mt-2 rounded-xl border border-blue-200 bg-white p-3">
      <label className={label}>Fan nomi</label>
      <input className={input} value={name} onChange={(e) => setName(e.target.value)} />
      <label className={label}>Emoji</label>
      <input className={input} value={emoji} onChange={(e) => setEmoji(e.target.value)} maxLength={4} />
      {err && <p className="mt-2 text-xs font-semibold text-rose-600">{err}</p>}
      <div className="mt-3 flex gap-2">
        <button
          onClick={submit}
          disabled={busy || name.trim().length < 2}
          className="flex-1 rounded-xl bg-blue-600 px-3 py-2 text-xs font-bold text-white disabled:opacity-50"
        >
          {busy ? "Saqlanmoqda…" : "Saqlash"}
        </button>
        <button onClick={onCancel} className="rounded-xl border border-slate-200 px-3 py-2 text-xs font-bold text-slate-500">
          Bekor
        </button>
      </div>
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

function LessonEditForm({
  token,
  lesson,
  onDone,
  onCancel,
}: {
  token: string;
  lesson: AdminLesson;
  onDone: (msg: string) => Promise<void> | void;
  onCancel: () => void;
}) {
  const [title, setTitle] = useState(lesson.title);
  const [explanation, setExplanation] = useState(lesson.explanation);
  const [stars, setStars] = useState(lesson.stars_reward);
  const [threshold, setThreshold] = useState(lesson.pass_threshold_percent);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  const submit = async () => {
    setBusy(true);
    setErr("");
    try {
      await api.adminUpdateLesson(token, lesson.id, {
        title: title.trim(),
        explanation: explanation.trim(),
        stars_reward: stars,
        pass_threshold_percent: threshold,
      });
      await onDone("Dars yangilandi");
    } catch (e) {
      setErr(errText(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="mt-2 rounded-xl border border-blue-200 bg-blue-50/40 p-3">
      <label className={label}>Dars nomi</label>
      <input className={input} value={title} onChange={(e) => setTitle(e.target.value)} />
      <label className={label}>Dars matni</label>
      <textarea
        className={`${input} min-h-24`}
        value={explanation}
        onChange={(e) => setExplanation(e.target.value)}
      />
      <div className="mt-3 grid grid-cols-2 gap-3">
        <div>
          <label className={label}>⭐ sovrin</label>
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
          <label className={label}>Chegara %</label>
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
      <div className="mt-3 flex gap-2">
        <button
          onClick={submit}
          disabled={busy || title.trim().length < 2 || explanation.trim().length < 10}
          className="flex-1 rounded-xl bg-blue-600 px-3 py-2 text-xs font-bold text-white disabled:opacity-50"
        >
          {busy ? "Saqlanmoqda…" : "Saqlash"}
        </button>
        <button onClick={onCancel} className="rounded-xl border border-slate-200 px-3 py-2 text-xs font-bold text-slate-500">
          Bekor
        </button>
      </div>
    </div>
  );
}

/* ---------- question form ---------- */

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

/* ---------- material form + lists ---------- */

const MATERIAL_KINDS = [
  { kind: "video", label: "▶️ Video" },
  { kind: "pdf", label: "📄 PDF" },
  { kind: "live", label: "🔴 Jonli dars" },
  { kind: "text", label: "📝 Yozma matn" },
] as const;

const KIND_ICON: Record<string, string> = {
  video: "▶️",
  pdf: "📄",
  live: "🔴",
  text: "📝",
  image: "🖼",
  slide: "🖼",
};

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

function ConfirmDelete({
  busy,
  onConfirm,
  idleLabel = "🗑 O‘chirish",
}: {
  busy: boolean;
  onConfirm: () => void;
  idleLabel?: string;
}) {
  const [confirming, setConfirming] = useState(false);
  return confirming ? (
    <span className="inline-flex items-center gap-2">
      <button
        onClick={() => {
          setConfirming(false);
          onConfirm();
        }}
        disabled={busy}
        className="rounded-lg bg-rose-600 px-2 py-1 text-[11px] font-bold text-white disabled:opacity-50"
      >
        {busy ? "O‘chirilmoqda…" : "Tasdiqlash"}
      </button>
      <button onClick={() => setConfirming(false)} className="text-[11px] font-bold text-slate-500">
        Bekor
      </button>
    </span>
  ) : (
    <button onClick={() => setConfirming(true)} className={miniDanger}>
      {idleLabel}
    </button>
  );
}

function MaterialList({
  token,
  lessonId,
  onChanged,
}: {
  token: string;
  lessonId: number;
  onChanged: () => Promise<void> | void;
}) {
  const [items, setItems] = useState<Material[] | null>(null);
  const [err, setErr] = useState("");
  const [busyId, setBusyId] = useState<number | null>(null);

  const load = useCallback(async () => {
    try {
      setItems(await api.adminMaterials(token, lessonId));
      setErr("");
    } catch (e) {
      setItems([]);
      setErr(errText(e));
    }
  }, [token, lessonId]);

  useEffect(() => {
    void load();
  }, [load]);

  const remove = async (id: number) => {
    setBusyId(id);
    setErr("");
    try {
      await api.adminDeleteMaterial(token, id);
      await load();
      await onChanged();
    } catch (e) {
      setErr(errText(e));
    } finally {
      setBusyId(null);
    }
  };

  return (
    <div className="mt-2 rounded-xl border border-emerald-100 bg-emerald-50/40 p-3">
      {err && <p className="mb-2 text-xs font-semibold text-rose-600">{err}</p>}
      {items === null && <p className="text-xs text-slate-400">Yuklanmoqda…</p>}
      {items !== null && items.length === 0 && (
        <p className="text-center text-xs text-slate-500">Bu darsda material yo‘q.</p>
      )}
      <div className="space-y-2">
        {items?.map((m) => (
          <div key={m.id} className="rounded-lg border border-emerald-100 bg-white px-3 py-2">
            <div className="flex items-start justify-between gap-2">
              <p className="min-w-0 text-xs font-bold text-slate-800">
                {KIND_ICON[m.kind] ?? "📎"} {m.title}
                <span className="ml-1 font-normal text-slate-400">({m.kind})</span>
              </p>
              <ConfirmDelete busy={busyId === m.id} onConfirm={() => void remove(m.id)} />
            </div>
            <p className="mt-1 line-clamp-2 break-all text-[11px] text-slate-500">{m.content}</p>
          </div>
        ))}
      </div>
    </div>
  );
}

function QuestionList({
  token,
  lessonId,
  onChanged,
}: {
  token: string;
  lessonId: number;
  onChanged: () => Promise<void> | void;
}) {
  const [items, setItems] = useState<AdminQuestionDetail[] | null>(null);
  const [err, setErr] = useState("");
  const [busyId, setBusyId] = useState<number | null>(null);

  const load = useCallback(async () => {
    try {
      setItems(await api.adminQuestions(token, lessonId));
      setErr("");
    } catch (e) {
      setItems([]);
      setErr(errText(e));
    }
  }, [token, lessonId]);

  useEffect(() => {
    void load();
  }, [load]);

  const remove = async (id: number) => {
    setBusyId(id);
    setErr("");
    try {
      await api.adminDeleteQuestion(token, id);
      await load();
      await onChanged();
    } catch (e) {
      setErr(errText(e));
    } finally {
      setBusyId(null);
    }
  };

  return (
    <div className="mt-2 rounded-xl border border-blue-100 bg-blue-50/40 p-3">
      {err && <p className="mb-2 text-xs font-semibold text-rose-600">{err}</p>}
      {items === null && <p className="text-xs text-slate-400">Yuklanmoqda…</p>}
      {items !== null && items.length === 0 && (
        <p className="text-center text-xs text-slate-500">Bu darsda savol yo‘q.</p>
      )}
      <div className="space-y-2">
        {items?.map((q, qi) => (
          <div key={q.id} className="rounded-lg border border-blue-100 bg-white px-3 py-2">
            <div className="flex items-start justify-between gap-2">
              <p className="text-xs font-bold text-slate-800">
                {qi + 1}. {q.text}{" "}
                <span className="font-normal text-slate-400">({q.kind})</span>
              </p>
              <ConfirmDelete busy={busyId === q.id} onConfirm={() => void remove(q.id)} />
            </div>
            <ul className="mt-1 space-y-0.5">
              {q.options.map((o) => (
                <li
                  key={o.id}
                  className={
                    o.is_correct
                      ? "text-[11px] font-bold text-emerald-600"
                      : "text-[11px] text-slate-500"
                  }
                >
                  {o.is_correct ? "✓" : "•"} {o.text}
                </li>
              ))}
            </ul>
          </div>
        ))}
      </div>
    </div>
  );
}
