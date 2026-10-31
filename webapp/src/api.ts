/**
 * api.ts — tiny typed client for the EduQuest FastAPI backend.
 *
 * Security: we send the RAW initData string to /api/auth/telegram and the
 * backend verifies its HMAC signature before trusting anything. The token the
 * backend returns is then used for every other call. We never send secrets and
 * never trust the Telegram user object shown on-screen (initDataUnsafe) as
 * proof of identity.
 *
 * VITE_API_URL is a build-time (public) value, not a secret. If it is missing
 * we fail loudly with an honest message instead of silently misbehaving.
 */
import type {
  AdminLesson,
  AdminQuestionDetail,
  AdminSubject,
  Grade,
  GradeOverview,
  Leaderboard,
  LessonDetail,
  Material,
  MaterialCreate,
  Profile,
  Progress,
  Quiz,
  QuizResult,
  SubjectItem,
  TelegramWebUser,
} from "./types";

// In dev we call same-origin "/api" so Vite's proxy forwards to the backend and
// the browser never sees a cross-origin request (the backend CORS allow-list
// only contains the production site, so localhost would be blocked otherwise).
// In production the build-time VITE_API_URL is baked in as before.
const API_URL = import.meta.env.DEV
  ? ""
  : (import.meta.env.VITE_API_URL ?? "").replace(/\/+$/, "");
const HAS_API = Boolean(API_URL) || import.meta.env.DEV;

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    message: string,
    public readonly code?: string, // backend machine code, e.g. "grade_not_selected"
  ) {
    super(message);
    this.name = "ApiError";
  }
}

async function req<T>(
  path: string,
  opts: { method?: string; token?: string; body?: unknown } = {},
): Promise<T> {
  if (!HAS_API) {
    throw new ApiError(0, "Backend manzili sozlanmagan (VITE_API_URL bo‘sh).", "no_api");
  }
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (opts.token) headers.Authorization = `Bearer ${opts.token}`;

  const res = await fetch(API_URL + path, {
    method: opts.method ?? "GET",
    headers,
    body: opts.body !== undefined ? JSON.stringify(opts.body) : undefined,
  });

  const text = await res.text();
  let data: unknown = null;
  try {
    data = text ? JSON.parse(text) : null;
  } catch {
    data = null;
  }

  if (!res.ok) {
    const detail = (data as { detail?: unknown } | null)?.detail;
    let message = res.statusText || "Noma’lum xatolik";
    let code: string | undefined;
    if (typeof detail === "string") {
      message = detail;
    } else if (detail && typeof detail === "object") {
      const d = detail as { error?: string; message_uz?: string };
      code = d.error;
      message = d.message_uz ?? "Xatolik yuz berdi";
    }
    throw new ApiError(res.status, message, code);
  }
  return data as T;
}

export const api = {
  hasBackend: () => HAS_API,

  login: (initData: string) =>
    req<{ access_token: string; first_name: string }>("/api/auth/telegram", {
      method: "POST",
      body: { init_data: initData },
    }),

  /** Browser login via the Telegram Login Widget (outside Telegram). */
  webLogin: (user: TelegramWebUser) =>
    req<{ access_token: string; first_name: string }>("/api/auth/telegram-web", {
      method: "POST",
      body: user,
    }),

  register: (body: { login: string; password: string; first_name: string }) =>
    req<{ access_token: string; first_name: string }>("/api/auth/register", {
      method: "POST",
      body,
    }),

  passwordLogin: (body: { login: string; password: string }) =>
    req<{ access_token: string; first_name: string }>("/api/auth/login", {
      method: "POST",
      body,
    }),

  me: (token: string) => req<Profile>("/api/me", { token }),

  grades: (token: string) => req<Grade[]>("/api/grades", { token }),

  setGrade: (token: string, grade_id: number) =>
    req<Profile>("/api/me/grade", { method: "POST", token, body: { grade_id } }),

  subjects: (token: string) => req<SubjectItem[]>("/api/subjects", { token }),

  progress: (token: string) => req<Progress>("/api/me/progress", { token }),

  /** Weekly star league: Top-10 of the pupil's grade (server picks the grade). */
  leaderboard: (token: string) => req<Leaderboard>("/api/leaderboard", { token }),

  lesson: (token: string, id: number) => req<LessonDetail>(`/api/lessons/${id}`, { token }),

  /**
   * An uploaded material (pdf/video) is fetched as raw bytes with the token in
   * the Authorization header — never in the URL. Returns { blob, fileName } so
   * the page can open it via an object URL (PDF preview / video player).
   */
  downloadMaterialFile: async (
    token: string,
    materialId: number,
  ): Promise<{ blob: Blob; fileName: string }> => {
    if (!HAS_API) {
      throw new ApiError(0, "Backend manzili sozlanmagan (VITE_API_URL bo‘sh).", "no_api");
    }
    const res = await fetch(`${API_URL}/api/materials/${materialId}/file`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    if (!res.ok) {
      let message = res.statusText || "Faylni yuklab bo‘lmadi";
      try {
        const data = JSON.parse(await res.text());
        const detail = data?.detail;
        if (typeof detail === "string") message = detail;
        else if (detail && typeof detail === "object") {
          message = detail.message_uz ?? message;
        }
      } catch {
        // non-JSON error body — keep the status text
      }
      throw new ApiError(res.status, message);
    }
    const disposition = res.headers.get("Content-Disposition") ?? "";
    const match = disposition.match(/filename="?([^";]+)"?/i);
    const fileName = match ? match[1] : `material-${materialId}`;
    return { blob: await res.blob(), fileName };
  },

  markViewed: (token: string, id: number) =>
    req<{
      ok: boolean;
      stars_granted: boolean;
      new_achievements: string[];
      new_achievement_titles: string[];
    }>(`/api/lessons/${id}/viewed`, { method: "POST", token }),

  quiz: (token: string, id: number) => req<Quiz>(`/api/lessons/${id}/quiz`, { token }),

  submitQuiz: (token: string, id: number, body: unknown) =>
    req<QuizResult>(`/api/lessons/${id}/quiz/submit`, { method: "POST", token, body }),

  // ---------- admin ----------
  adminOverview: (token: string) => req<GradeOverview[]>("/api/admin/overview", { token }),

  adminCreateSubject: (token: string, body: { grade_id: number; name: string; emoji: string }) =>
    req<AdminSubject>("/api/admin/subjects", { method: "POST", token, body }),

  adminCreateLesson: (
    token: string,
    subjectId: number,
    body: { title: string; explanation: string; stars_reward: number; pass_threshold_percent: number },
  ) => req<AdminLesson>(`/api/admin/subjects/${subjectId}/lessons`, { method: "POST", token, body }),

  adminLessons: (token: string, subjectId: number) =>
    req<AdminLesson[]>(`/api/admin/subjects/${subjectId}/lessons`, { token }),

  adminUpdateSubject: (
    token: string,
    subjectId: number,
    body: { name?: string; emoji?: string; is_published?: boolean },
  ) => req<AdminSubject>(`/api/admin/subjects/${subjectId}`, { method: "PATCH", token, body }),

  adminUpdateLesson: (
    token: string,
    lessonId: number,
    body: {
      title?: string;
      explanation?: string;
      stars_reward?: number;
      pass_threshold_percent?: number;
      is_published?: boolean;
    },
  ) => req<AdminLesson>(`/api/admin/lessons/${lessonId}`, { method: "PATCH", token, body }),

  adminLesson: (token: string, lessonId: number) =>
    req<AdminLesson>(`/api/admin/lessons/${lessonId}`, { token }),

  adminCreateQuestion: (
    token: string,
    lessonId: number,
    body: { text: string; kind: string; options: { text: string; is_correct: boolean }[] },
  ) => req<{ id: number }>(`/api/admin/lessons/${lessonId}/questions`, { method: "POST", token, body }),

  adminQuestions: (token: string, lessonId: number) =>
    req<AdminQuestionDetail[]>(`/api/admin/lessons/${lessonId}/questions`, { token }),

  adminDeleteQuestion: (token: string, questionId: number) =>
    req<null>(`/api/admin/questions/${questionId}`, { method: "DELETE", token }),

  adminMaterials: (token: string, lessonId: number) =>
    req<Material[]>(`/api/admin/lessons/${lessonId}/materials`, { token }),

  adminCreateMaterial: (token: string, lessonId: number, body: MaterialCreate) =>
    req<Material>(`/api/admin/lessons/${lessonId}/materials`, { method: "POST", token, body }),

  adminUploadMaterial: async (
    token: string,
    lessonId: number,
    file: File,
    kind: "video" | "pdf",
    title: string,
  ): Promise<Material> => {
    if (!HAS_API) {
      throw new ApiError(0, "Backend manzili sozlanmagan (VITE_API_URL bo‘sh).", "no_api");
    }
    const formData = new FormData();
    formData.append("file", file);
    formData.append("kind", kind);
    formData.append("title", title);

    const res = await fetch(`${API_URL}/api/admin/lessons/${lessonId}/materials/upload`, {
      method: "POST",
      headers: { Authorization: `Bearer ${token}` },
      body: formData,
    });
    if (!res.ok) {
      let message = res.statusText || "Faylni yuklab bo‘lmadi";
      try {
        const data = await res.json();
        message = data?.detail?.message_uz ?? data?.detail ?? message;
      } catch {
        // ignore
      }
      throw new ApiError(res.status, message);
    }
    return (await res.json()) as Material;
  },

  adminDeleteMaterial: (token: string, materialId: number) =>
    req<null>(`/api/admin/materials/${materialId}`, { method: "DELETE", token }),
};
