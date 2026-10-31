import { useCallback, useEffect, useRef, useState } from "react";
import Navbar from "./components/Navbar";
import type { NavTab } from "./components/Navbar";
import SubjectCard from "./components/SubjectCard";
import SubjectLessons from "./components/SubjectLessons";
import GradePicker from "./components/GradePicker";
import LessonPage from "./components/LessonPage";
import QuizPage from "./components/QuizPage";
import ResultScreen from "./components/ResultScreen";
import AdminPage from "./components/AdminPage";
import WebLogin from "./components/WebLogin";
import { AchievementsPage, ProfilePage } from "./components/Pages";
import Card from "./components/ui/Card";
import Button from "./components/ui/Button";
import Badge from "./components/ui/Badge";
import EmptyState from "./components/ui/EmptyState";
import {
  IconGraduationCap,
  IconStar,
  IconPlay,
  IconSparkles,
  IconArrowRight,
} from "./components/ui/Icons";
import { api, ApiError } from "./api";
import type {
  Grade,
  LessonSummary,
  Profile,
  Progress,
  QuizResult,
  SubjectItem,
  TelegramWebUser,
} from "./types";

type Phase =
  | "boot"
  | "no_backend"
  | "web_login"
  | "busy"
  | "onboarding"
  | "home"
  | "error";

type View =
  | { kind: "home" }
  | { kind: "subject"; subjectId: number }
  | { kind: "lesson"; lessonId: number; subjectId: number }
  | { kind: "quiz"; lessonId: number; subjectId: number }
  | { kind: "result"; lessonId: number; subjectId: number; result: QuizResult }
  | { kind: "achievements" }
  | { kind: "profile" }
  | { kind: "admin" };

const TOKEN_KEY = "eduquest_token";

function readStoredToken(): string {
  try {
    return window.localStorage.getItem(TOKEN_KEY) ?? "";
  } catch {
    return "";
  }
}
function storeToken(value: string) {
  try {
    window.localStorage.setItem(TOKEN_KEY, value);
  } catch {
    /* session in memory fallback */
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
  const [quizNonce, setQuizNonce] = useState(0);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [toast, setToast] = useState<string | null>(null);
  const [webSession, setWebSession] = useState(false);
  const started = useRef(false);

  const showToast = (msg: string) => {
    setToast(msg);
    window.Telegram?.WebApp?.HapticFeedback?.impactOccurred("light");
    window.setTimeout(() => setToast(null), 2500);
  };

  const loadHome = useCallback(async (tk: string) => {
    const [subs, prog] = await Promise.all([api.subjects(tk), api.progress(tk)]);
    setSubjects(subs);
    setProgress(prog);
  }, []);

  const bootstrap = useCallback(
    async (tk: string) => {
      const me = await api.me(tk);
      setProfile(me);
      if (me.needs_grade_selection) {
        setGrades(await api.grades(tk));
        setPhase("onboarding");
      } else {
        await loadHome(tk);
        setPhase("home");
      }
    },
    [loadHome],
  );

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
          clearStoredToken();
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
      showToast(`${grade.name} muvaffaqiyatli tanlandi!`);
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

  const finishQuiz = async (subjectId: number) => {
    try {
      await loadHome(token);
    } catch {
      /* non-fatal */
    }
    setView({ kind: "subject", subjectId });
  };

  const name = profile?.first_name || progress?.first_name || "O‘quvchi";
  const gradeLabel = profile?.grade_name ?? progress?.grade_name;
  const starsTotal = progress?.stars_total ?? 0;

  const activeSubject =
    view.kind !== "home" && "subjectId" in view
      ? subjects.find((s) => s.id === view.subjectId)
      : undefined;

  const navTo = (v: View) => {
    setView(v);
    window.scrollTo({ top: 0, behavior: "smooth" });
  };

  const currentTab: NavTab =
    view.kind === "home"
      ? "home"
      : view.kind === "subject" || view.kind === "lesson" || view.kind === "quiz" || view.kind === "result"
        ? "lessons"
        : view.kind === "achievements"
          ? "achievements"
          : view.kind === "profile"
            ? "profile"
            : view.kind === "admin"
              ? "admin"
              : "home";

  const handleTabChange = (tab: NavTab) => {
    if (tab === "home") navTo({ kind: "home" });
    else if (tab === "lessons") {
      if (view.kind === "home") {
        const el = document.getElementById("subjects-section");
        if (el) el.scrollIntoView({ behavior: "smooth" });
      } else {
        navTo({ kind: "home" });
      }
    } else if (tab === "achievements") navTo({ kind: "achievements" });
    else if (tab === "profile") navTo({ kind: "profile" });
    else if (tab === "admin") navTo({ kind: "admin" });
  };

  // Find next lesson to continue learning
  let continueItem: { subject: SubjectItem; lesson: LessonSummary } | null = null;
  for (const s of subjects) {
    const nextL = s.lessons.find((l) => l.unlocked && !l.passed);
    if (nextL) {
      continueItem = { subject: s, lesson: nextL };
      break;
    }
  }

  // Calculate overall metrics
  const totalLessonsCount = subjects.reduce((acc, s) => acc + s.lessons.length, 0);
  const passedLessonsCount = subjects.reduce(
    (acc, s) => acc + s.lessons.filter((l) => l.passed).length,
    0,
  );

  return (
    <div className="flex min-h-screen flex-col bg-[#F7F9FC] text-slate-900 antialiased selection:bg-blue-100 selection:text-blue-900">
      {/* Top Navigation */}
      {phase === "home" && (
        <Navbar
          currentTab={currentTab}
          onTabChange={handleTabChange}
          stars={starsTotal}
          gradeLabel={gradeLabel}
          onChangeGrade={changeGrade}
          isAdmin={profile?.is_admin}
        />
      )}

      {/* Main Content Area */}
      <main className="mx-auto w-full max-w-6xl flex-1 px-4 sm:px-6 py-4 sm:py-6 safe-pb">
        {/* Loading / Boot states */}
        {phase === "boot" || phase === "busy" ? (
          <div className="mx-auto max-w-md py-20 text-center animate-fade-in">
            <div className="inline-block h-10 w-10 animate-spin rounded-full border-4 border-blue-500 border-t-transparent" />
            <p className="mt-4 text-sm font-bold text-slate-600">EduQuest yuklanmoqda…</p>
            <p className="text-xs text-slate-400 mt-1">O‘rganish — endi o‘yin!</p>
          </div>
        ) : phase === "no_backend" ? (
          <div className="mx-auto max-w-md py-12">
            <Card className="p-8 text-center border-amber-200 bg-amber-50/50">
              <span className="text-4xl mb-3 block">⚙️</span>
              <h2 className="text-lg font-bold text-slate-800">Server sozlanmagan</h2>
              <p className="mt-2 text-xs text-slate-600">
                Frontend backend manzilini topa olmadi. Iltimos, VITE_API_URL qiymatini tekshiring.
              </p>
            </Card>
          </div>
        ) : phase === "web_login" ? (
          <WebLogin onAuth={handleWebLogin} error={error} />
        ) : phase === "error" ? (
          <div className="mx-auto max-w-md py-12">
            <Card className="p-8 text-center border-rose-200 bg-rose-50/50">
              <span className="text-4xl mb-3 block">⚠️</span>
              <h2 className="text-lg font-bold text-rose-800">Xatolik yuz berdi</h2>
              <p className="mt-2 text-xs text-rose-600">{error}</p>
              <div className="mt-6">
                <Button variant="secondary" size="sm" onClick={() => window.location.reload()}>
                  Qayta yuklash
                </Button>
              </div>
            </Card>
          </div>
        ) : phase === "onboarding" ? (
          <GradePicker
            grades={grades}
            busy={busy}
            currentGradeId={profile?.grade_id}
            onPick={pickGrade}
            onCancel={profile?.grade_id != null ? () => setPhase("home") : undefined}
          />
        ) : view.kind === "home" ? (
          /* ===================== HOMEPAGE ===================== */
          <div className="space-y-6 sm:space-y-8 animate-fade-in">
            {/* Mobile Header (Shows only on small screens where top navbar is hidden) */}
            <div className="flex md:hidden items-center justify-between py-1">
              <div>
                <span className="text-xs font-bold uppercase tracking-wider text-blue-600">
                  EduQuest
                </span>
                <h1 className="text-xl font-black text-slate-900">
                  Salom, {name}! 👋
                </h1>
              </div>
              <div className="flex items-center gap-2">
                {gradeLabel && (
                  <button
                    onClick={changeGrade}
                    className="flex items-center gap-1 px-2.5 py-1 rounded-xl bg-blue-50 text-blue-700 border border-blue-200 text-xs font-bold"
                  >
                    <IconGraduationCap size={14} />
                    <span>{gradeLabel}</span>
                  </button>
                )}
                <div className="flex items-center gap-1 px-3 py-1 rounded-xl bg-amber-50 text-amber-700 border border-amber-200 text-xs font-black shadow-xs">
                  <IconStar size={14} filled className="text-amber-500" />
                  <span>{starsTotal}</span>
                </div>
              </div>
            </div>

            {/* Hero Banner Section */}
            <Card
              variant="elevated"
              className="relative overflow-hidden p-6 sm:p-8 bg-gradient-to-br from-[#3478F6] via-blue-600 to-indigo-700 text-white border-0 shadow-lg shadow-blue-500/15"
            >
              <div className="flex flex-col md:flex-row md:items-center justify-between gap-6 relative z-10">
                <div className="space-y-2 max-w-xl">
                  <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-white/20 backdrop-blur-md text-xs font-extrabold text-blue-100">
                    <IconSparkles size={14} />
                    <span>O‘rganish — endi o‘yin!</span>
                  </div>

                  <h2 className="text-2xl sm:text-3xl font-black tracking-tight text-white">
                    Bugun qaysi yangi bilimni egallaymiz?
                  </h2>

                  <p className="text-sm text-blue-100 leading-relaxed">
                    Har bir o‘rganilgan dars va topshirilgan test uchun yulduzlarni to‘plang hamda yangi bosqichlarni oching!
                  </p>
                </div>

                {/* Overall Stats pill */}
                <div className="flex items-center gap-3 bg-white/10 backdrop-blur-md p-4 rounded-3xl border border-white/20">
                  <div className="text-center px-3 border-r border-white/20">
                    <span className="block text-2xl font-black text-amber-300">
                      ⭐ {starsTotal}
                    </span>
                    <span className="text-[11px] font-bold text-blue-100">
                      Yulduzlar
                    </span>
                  </div>
                  <div className="text-center px-3">
                    <span className="block text-2xl font-black text-white">
                      {passedLessonsCount}/{totalLessonsCount}
                    </span>
                    <span className="text-[11px] font-bold text-blue-100">
                      Darslar
                    </span>
                  </div>
                </div>
              </div>
            </Card>

            {/* "Davom etish" (Continue Learning) Card if there's an active unlocked lesson */}
            {continueItem && (
              <Card
                variant="interactive"
                onClick={() =>
                  navTo({
                    kind: "lesson",
                    lessonId: continueItem!.lesson.id,
                    subjectId: continueItem!.subject.id,
                  })
                }
                className="p-5 sm:p-6 border-2 border-blue-200 bg-gradient-to-r from-blue-50/70 via-indigo-50/40 to-white hover:border-blue-400"
              >
                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
                  <div className="flex items-center gap-4">
                    <div className="flex h-14 w-14 shrink-0 items-center justify-center rounded-2xl bg-blue-600 text-white shadow-md shadow-blue-500/30">
                      <IconPlay size={24} />
                    </div>
                    <div>
                      <div className="flex items-center gap-2">
                        <Badge variant="blue" size="sm">
                          {continueItem.subject.name}
                        </Badge>
                        <span className="text-xs font-bold text-slate-400">
                          {continueItem.lesson.level_order}-bosqich
                        </span>
                      </div>
                      <h3 className="text-base sm:text-lg font-black text-slate-900 mt-0.5">
                        {continueItem.lesson.title}
                      </h3>
                      <p className="text-xs text-slate-500 mt-0.5">
                        O‘qishni to‘xtagan joyingizdan davom ettiring
                      </p>
                    </div>
                  </div>

                  <div className="sm:self-center">
                    <Button
                      variant="primary"
                      size="md"
                      iconRight={<IconArrowRight size={16} />}
                      onClick={(e) => {
                        e.stopPropagation();
                        navTo({
                          kind: "lesson",
                          lessonId: continueItem!.lesson.id,
                          subjectId: continueItem!.subject.id,
                        });
                      }}
                    >
                      Darsni boshlash
                    </Button>
                  </div>
                </div>
              </Card>
            )}

            {/* Subjects Section */}
            <div id="subjects-section" className="space-y-4">
              <div className="flex items-center justify-between px-1">
                <div>
                  <h2 className="text-lg sm:text-xl font-black text-slate-900">
                    {gradeLabel ? `${gradeLabel} fanlari` : "Fanlar"}
                  </h2>
                  <p className="text-xs text-slate-500">
                    O‘zingiz qiziqqan fanni tanlang va sayohatni boshlang
                  </p>
                </div>
                <button
                  onClick={changeGrade}
                  className="flex items-center gap-1.5 text-xs font-extrabold text-blue-600 hover:text-blue-700 hover:underline cursor-pointer"
                >
                  <IconGraduationCap size={16} />
                  <span>Sinfni o‘zgartirish</span>
                </button>
              </div>

              {subjects.length === 0 ? (
                <EmptyState
                  title="Darslar tayyorlanmoqda"
                  description="Ushbu sinf uchun o‘quv dasturi tez kunda joylanadi. Hozircha 1–4-sinflarning namunaviy darslarini sinab ko‘rishingiz mumkin."
                  actionText="Boshqa sinfni tanlash"
                  onAction={changeGrade}
                />
              ) : (
                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
                  {subjects.map((sub) => {
                    const total = sub.lessons.length;
                    const done = sub.lessons.filter((l) => l.passed).length;

                    return (
                      <SubjectCard
                        key={sub.id}
                        title={sub.name}
                        emoji={sub.emoji}
                        totalLessons={total}
                        passedLessons={done}
                        onClick={() => {
                          if (total > 0) {
                            navTo({ kind: "subject", subjectId: sub.id });
                          } else {
                            showToast("Bu fanda darslar hozircha tayyorlanmoqda 🚧");
                          }
                        }}
                      />
                    );
                  })}
                </div>
              )}
            </div>

            {/* Learning Inspiration Card */}
            <Card variant="flat" className="p-5 sm:p-6 border border-slate-200">
              <div className="flex items-center gap-4">
                <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-2xl bg-amber-100 text-amber-700 text-2xl">
                  💡
                </div>
                <div>
                  <h3 className="text-sm font-bold text-slate-800">
                    O‘quvchilar uchun tavsiya
                  </h3>
                  <p className="text-xs text-slate-500 mt-0.5 leading-relaxed">
                    Har kuni muntazam 15 daqiqa dars o‘qish bilimlarni mustahkamlaydi va keyingi bosqichlarni tezroq ochishga yordam beradi.
                  </p>
                </div>
              </div>
            </Card>
          </div>
        ) : view.kind === "subject" && activeSubject ? (
          /* ===================== SUBJECT LESSONS ===================== */
          <SubjectLessons
            subject={activeSubject}
            onOpenLesson={(lessonId) =>
              navTo({ kind: "lesson", lessonId, subjectId: activeSubject.id })
            }
            onBack={() => navTo({ kind: "home" })}
          />
        ) : view.kind === "lesson" ? (
          /* ===================== LESSON PAGE ===================== */
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
          /* ===================== QUIZ PAGE ===================== */
          <QuizPage
            key={quizNonce}
            token={token}
            lessonId={view.lessonId}
            onBack={() =>
              navTo({ kind: "lesson", lessonId: view.lessonId, subjectId: view.subjectId })
            }
            onResult={(r) =>
              navTo({
                kind: "result",
                lessonId: view.lessonId,
                subjectId: view.subjectId,
                result: r,
              })
            }
          />
        ) : view.kind === "result" ? (
          /* ===================== RESULT SCREEN ===================== */
          <ResultScreen
            result={view.result}
            onRetry={() => {
              setQuizNonce((n) => n + 1);
              navTo({ kind: "quiz", lessonId: view.lessonId, subjectId: view.subjectId });
            }}
            onContinue={() => finishQuiz(view.subjectId)}
          />
        ) : view.kind === "achievements" ? (
          /* ===================== ACHIEVEMENTS ===================== */
          <AchievementsPage progress={progress} />
        ) : view.kind === "admin" ? (
          /* ===================== ADMIN PAGE ===================== */
          <AdminPage token={token} notify={showToast} />
        ) : (
          /* ===================== PROFILE PAGE ===================== */
          <ProfilePage
            profile={profile}
            progress={progress}
            onChangeGrade={changeGrade}
            onLogout={webSession ? logout : undefined}
          />
        )}
      </main>

      {/* Toast Notification */}
      {toast && (
        <div className="fixed bottom-24 md:bottom-8 left-1/2 z-50 -translate-x-1/2 animate-scale-in">
          <div className="flex items-center gap-2 rounded-2xl bg-slate-900/90 backdrop-blur-md px-5 py-3 text-xs sm:text-sm font-bold text-white shadow-xl shadow-slate-900/20">
            <IconSparkles size={16} className="text-amber-400" />
            <span>{toast}</span>
          </div>
        </div>
      )}
    </div>
  );
}
