import { useCallback, useEffect, useRef, useState } from "react";
import QuestMascot from "./components/QuestMascot";
import SubjectCard from "./components/SubjectCard";
import SubjectLessons from "./components/SubjectLessons";
import GradePicker from "./components/GradePicker";
import LessonPage from "./components/LessonPage";
import QuizPage from "./components/QuizPage";
import ResultScreen from "./components/ResultScreen";
import AdminPage from "./components/AdminPage";
import WebLogin from "./components/WebLogin";
import { AchievementsPage, ProfilePage } from "./components/Pages";
import { api, ApiError } from "./api";
import type { Grade, Profile, Progress, QuizResult, SubjectItem, TelegramWebUser } from "./types";

type Phase =
  | "boot"
  | "no_backend"
  | "web_login"
  | "busy"
  | "onboarding"
  | "home"
  | "error";

/** In-app navigation after the pupil reaches "home". */
type View =
  | { kind: "home" }
  | { kind: "subject"; subjectId: number }
  | { kind: "lesson"; lessonId: number; subjectId: number }
  | { kind: "quiz"; lessonId: number; subjectId: number }
  | { kind: "result"; lessonId: number; subjectId: number; result: QuizResult }
  | { kind: "achievements" }
  | { kind: "profile" }
  | { kind: "admin" };

const GRADIENTS = [
  "from-blue-500 to-blue-700",
  "from-sky-400 to-blue-600",
  "from-indigo-500 to-blue-700",
];

// Browser sessions only (inside Telegram we always re-login with initData).
const TOKEN_KEY = "eduquest_token";

function readStoredToken(): string {
  try {
    return window.localStorage.getItem(TOKEN_KEY) ?? "";
  } catch {
    return ""; // private mode / storage disabled
  }
}
function storeToken(value: string) {
  try {
    window.localStorage.setItem(TOKEN_KEY, value);
  } catch {
    /* the in-memory token still works for this tab */
  }
}
function clearStoredToken() {
  try {
    window.localStorage.removeItem(TOKEN_KEY);
  } catch {
    /* ignore */
  }
}

function describe(e: unknown): string {
  if (e instanceof ApiError) return `${e.status ? `(${e.status}) ` : ""}${e.message}`;
  return "Aloqa xatosi: serverga bog‘lanib bo‘lmadi.";
}

export default function App() {
  const [phase, setPhase] = useState<Phase>("boot");
  const [token, setToken] = useState("");
  const [profile, setProfile] = useState<Profile | null>(null);
  const [grades, setGrades] = useState<Grade[]>([]);
  const [subjects, setSubjects] = useState<SubjectItem[]>([]);
  const [progress, setProgress] = useState<Progress | null>(null);
  const [view, setView] = useState<View>({ kind: "home" });
  const [quizNonce, setQuizNonce] = useState(0); // force fresh QuizPage on retry
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [toast, setToast] = useState<string | null>(null);
  const [webSession, setWebSession] = useState(false);
  const started = useRef(false);

  const showToast = (msg: string) => {
    setToast(msg);
    window.Telegram?.WebApp?.HapticFeedback?.impactOccurred("light");
    window.setTimeout(() => setToast(null), 2400);
  };

  const loadHome = useCallback(async (tk: string) => {
    const [subs, prog] = await Promise.all([api.subjects(tk), api.progress(tk)]);
    setSubjects(subs);
    setProgress(prog);
  }, []);

  const bootstrap = useCallback(async (tk: string) => {
    const me = await api.me(tk);
    setProfile(me);
    if (me.needs_grade_selection) {
      setGrades(await api.grades(tk));
      setPhase("onboarding");
    } else {
      await loadHome(tk);
      setPhase("home");
    }
  }, [loadHome]);

  // Boot: inside Telegram verify initData; in a browser use the Telegram
  // Login Widget session (stored JWT) or show the widget.
  useEffect(() => {
    if (started.current) return;
    started.current = true;

    if (!api.hasBackend()) {
      setPhase("no_backend");
      return;
    }

    const tg = window.Telegram?.WebApp;
    if (tg?.initData) {
      (async () => {
        try {
          setPhase("busy");
          const { access_token } = await api.login(tg.initData);
          clearStoredToken(); // inside Telegram, identity always comes fresh
          setToken(access_token);
          setWebSession(false);
          await bootstrap(access_token);
        } catch (e) {
          setError(describe(e));
          setPhase("error");
        }
      })();
      return;
    }

    const saved = readStoredToken();
    if (!saved) {
      setPhase("web_login");
      return;
    }
    (async () => {
      try {
        setPhase("busy");
        setToken(saved);
        setWebSession(true);
        await bootstrap(saved);
      } catch (e) {
        if (e instanceof ApiError && (e.status === 401 || e.status === 403)) {
          clearStoredToken();
          setWebSession(false);
          setPhase("web_login");
        } else {
          setError(describe(e));
          setPhase("error");
        }
      }
    })();
  }, [bootstrap]);

  const pickGrade = async (grade: Grade) => {
    setBusy(true);
    try {
      const me = await api.setGrade(token, grade.id);
      setProfile(me);
      await loadHome(token);
      setView({ kind: "home" });
      setPhase("home");
    } catch (e) {
      setError(describe(e));
      setPhase("error");
    } finally {
      setBusy(false);
    }
  };

  const changeGrade = async () => {
    if (grades.length === 0) {
      try {
        setGrades(await api.grades(token));
      } catch (e) {
        setError(describe(e));
        setPhase("error");
        return;
      }
    }
    setPhase("onboarding");
  };

  const handleWebLogin = useCallback(
    async (user: TelegramWebUser) => {
      try {
        setError("");
        setPhase("busy");
        const { access_token } = await api.webLogin(user);
        storeToken(access_token);
        setToken(access_token);
        setWebSession(true);
        await bootstrap(access_token);
      } catch (e) {
        setError(describe(e));
        setPhase("web_login");
      }
    },
    [bootstrap],
  );

  const logout = () => {
    clearStoredToken();
    setWebSession(false);
    setToken("");
    setProfile(null);
    setProgress(null);
    setSubjects([]);
    setGrades([]);
    setView({ kind: "home" });
    setError("");
    setPhase("web_login");
  };

  /** After a quiz result: refresh counts and return to the lesson ladder. */
  const finishQuiz = async (subjectId: number) => {
    try {
      await loadHome(token);
    } catch {
      /* counts refresh is best-effort; the pupil still sees fresh data next open */
    }
    setView({ kind: "subject", subjectId });
  };

  const name = profile?.first_name || progress?.first_name || "Qahramon";
  const gradeLabel = profile?.grade_name ?? progress?.grade_name;
  const activeSubject =
    view.kind !== "home" && "subjectId" in view
      ? subjects.find((s) => s.id === view.subjectId)
      : undefined;

  const navTo = (v: View) => {
    setView(v);
    window.scrollTo({ top: 0 });
  };

  return (
    <div className="mx-auto flex min-h-full max-w-md flex-col px-4 pb-24 pt-6">
      {/* Header */}
      <header className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-extrabold text-blue-800">EduQuest</h1>
          <p className="text-sm text-blue-500">
            {phase === "home" && gradeLabel ? `${gradeLabel} · ` : ""}
            {phase === "web_login"
              ? "Telegram orqali kiring"
              : `Xush kelibsiz, ${name}!`}
          </p>
        </div>
        <div className="rounded-full bg-amber-100 px-4 py-2 text-lg font-bold text-amber-600 shadow-sm">
          ⭐ {phase === "home" ? progress?.stars_total ?? 0 : 0}
        </div>
      </header>

      {/* Mascot + greeting (home only, to keep lesson screens focused) */}
      {phase === "home" && view.kind === "home" && (
        <section className="mt-6 flex flex-col items-center rounded-3xl bg-white p-6 shadow-md">
          <QuestMascot size={110} />
          <p className="mt-3 text-center text-base font-semibold text-blue-900">
            Salom! Men Quest 🤖
          </p>
          <p className="mt-1 text-center text-sm text-slate-500">
            Birga bilimlar olamiga sayohat qilamiz!
          </p>
        </section>
      )}

      {/* Main content */}
      {phase === "boot" || phase === "busy" ? (
        <p className="mt-8 text-center text-sm font-medium text-blue-500">Yuklanmoqda… ⏳</p>
      ) : phase === "no_backend" ? (
        <Notice
          title="Backend sozlanmagan"
          body="Mini App server manzilini topa olmadi. webapp/.env fayliga VITE_API_URL qiymatini kiriting (masalan http://127.0.0.1:8000)."
        />
      ) : phase === "web_login" ? (
        <WebLogin onAuth={handleWebLogin} error={error} />
      ) : phase === "error" ? (
        <Notice title="Xatolik yuz berdi" body={error} tone="error" />
      ) : phase === "onboarding" ? (
        <GradePicker
          grades={grades}
          busy={busy}
          onPick={pickGrade}
          onCancel={
            // Changing grade must be cancellable; first-run onboarding is not
            // (a pupil cannot use the app without picking a grade).
            profile?.grade_id != null ? () => setPhase("home") : undefined
          }
        />
      ) : view.kind === "home" ? (
        /* ---------- HOME: subject cards ---------- */
        <section className="mt-6 space-y-3">
          <div className="flex items-center justify-between px-1">
            <h2 className="text-sm font-bold uppercase tracking-wide text-blue-400">
              {gradeLabel ? `${gradeLabel} fanlari` : "Fanlar"}
            </h2>
            <button
              onClick={changeGrade}
              className="text-xs font-semibold text-blue-500 underline-offset-2 hover:underline"
            >
              Sinfni o‘zgartirish
            </button>
          </div>

          {subjects.length === 0 ? (
            <div className="rounded-2xl border-2 border-dashed border-blue-200 bg-blue-50 p-5 text-center">
              <p className="text-sm font-semibold text-blue-700">
                Bu sinf uchun darslar hozircha tayyorlanmoqda 🚧
              </p>
              <p className="mt-1 text-xs text-blue-400">
                1–4-sinflarda namuna darslar bor; qolgan sinflar admin panel
                orqali to‘ldiriladi.
              </p>
            </div>
          ) : (
            subjects.map((s, i) => {
              const total = s.lessons.length;
              const done = s.lessons.filter((l) => l.passed).length;
              return (
                <SubjectCard
                  key={s.id}
                  title={s.name}
                  emoji={s.emoji}
                  gradient={GRADIENTS[i % GRADIENTS.length]}
                  subtitle={total ? `${done}/${total} bosqich tugatilgan →` : "Tez orada 🚧"}
                  onClick={() =>
                    total ? navTo({ kind: "subject", subjectId: s.id }) : showToast("Bu fanda darslar hozircha yo‘q 🚧")
                  }
                />
              );
            })
          )}
        </section>
      ) : view.kind === "subject" && activeSubject ? (
        /* ---------- SUBJECT: lesson ladder ---------- */
        <SubjectLessons
          subject={activeSubject}
          onOpenLesson={(lessonId) =>
            navTo({ kind: "lesson", lessonId, subjectId: activeSubject.id })
          }
          onBack={() => navTo({ kind: "home" })}
        />
      ) : view.kind === "lesson" ? (
        /* ---------- LESSON: explanation + mark viewed ---------- */
        <LessonPage
          token={token}
          lessonId={view.lessonId}
          onBack={() => navTo({ kind: "subject", subjectId: view.subjectId })}
          onViewed={() => loadHome(token).catch(() => undefined)}
          onStartQuiz={() =>
            navTo({ kind: "quiz", lessonId: view.lessonId, subjectId: view.subjectId })
          }
        />
      ) : view.kind === "quiz" ? (
        /* ---------- QUIZ: questions ---------- */
        <QuizPage
          key={quizNonce}
          token={token}
          lessonId={view.lessonId}
          onBack={() => navTo({ kind: "lesson", lessonId: view.lessonId, subjectId: view.subjectId })}
          onResult={(r) =>
            navTo({ kind: "result", lessonId: view.lessonId, subjectId: view.subjectId, result: r })
          }
        />
      ) : view.kind === "result" ? (
        /* ---------- RESULT: server verdict ---------- */
        <ResultScreen
          result={view.result}
          onRetry={() => {
            setQuizNonce((n) => n + 1);
            navTo({ kind: "quiz", lessonId: view.lessonId, subjectId: view.subjectId });
          }}
          onContinue={() => finishQuiz(view.subjectId)}
        />
      ) : view.kind === "achievements" ? (
        <AchievementsPage progress={progress} />
      ) : view.kind === "admin" ? (
        <AdminPage token={token} notify={showToast} />
      ) : (
        <ProfilePage
          profile={profile}
          progress={progress}
          onChangeGrade={changeGrade}
          onLogout={webSession ? logout : undefined}
        />
      )}

      {/* Toast */}
      {toast && (
        <div className="fixed bottom-24 left-1/2 z-50 w-[90%] max-w-md -translate-x-1/2 rounded-xl bg-blue-900 px-4 py-3 text-center text-sm font-medium text-white shadow-lg">
          {toast}
        </div>
      )}

      {/* Bottom nav — only on the home phase, so no dead buttons elsewhere */}
      {phase === "home" && (
      <nav className="fixed inset-x-0 bottom-0 mx-auto flex max-w-md justify-around border-t border-blue-100 bg-white py-3">
        {[
          { key: "home", label: "Bosh sahifa", emoji: "🏠" },
          { key: "lessons", label: "Darslar", emoji: "📚" },
          { key: "achievements", label: "Yutuqlar", emoji: "🏆" },
          { key: "profile", label: "Profil", emoji: "👤" },
          ...(profile?.is_admin ? [{ key: "admin", label: "Admin", emoji: "🛠" }] : []),
        ].map((item) => {
          const active =
            item.key === "home"
              ? view.kind === "home"
              : item.key === "lessons"
                ? view.kind === "subject" || view.kind === "lesson" || view.kind === "quiz" || view.kind === "result"
                : view.kind === item.key;
          const go = () => {
            if (phase !== "home") return;
            if (item.key === "home" || item.key === "lessons") navTo({ kind: "home" });
            else navTo({ kind: item.key as "achievements" | "profile" | "admin" });
          };
          return active ? (
            <span key={item.key} className="flex flex-col items-center text-xs font-bold text-blue-700">
              <span className="text-xl">{item.emoji}</span>
              {item.label}
            </span>
          ) : (
            <button
              key={item.key}
              onClick={go}
              className="flex flex-col items-center text-xs text-slate-400"
            >
              <span className="text-xl">{item.emoji}</span>
              {item.label}
            </button>
          );
        })}
      </nav>
      )}
    </div>
  );
}

function Notice({
  title,
  body,
  tone = "info",
}: {
  title: string;
  body: string;
  tone?: "info" | "error";
}) {
  const styles =
    tone === "error"
      ? "border-rose-200 bg-rose-50 text-rose-700"
      : "border-blue-200 bg-blue-50 text-blue-700";
  return (
    <section className={`mt-6 rounded-2xl border-2 border-dashed p-5 text-center ${styles}`}>
      <p className="text-sm font-bold">{title}</p>
      <p className="mt-1 text-xs opacity-80">{body}</p>
    </section>
  );
}
