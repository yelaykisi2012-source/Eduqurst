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
  AdminExamCoverage,
  AdminLesson,
  AdminQuestionDetail,
  AdminSubject,
  Avatar,
  Certificate,
  ChatFeed,
  ChatMember,
  ChatPendingQueue,
  ChatPeopleResult,
  ChatRoom,
  ChatRoomResult,
  ChatSendResult,
  EligibleCertificate,
  ExamCard,
  ExamPaper,
  ExamResult,
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
    /**
     * Structured detail object from the backend (when it is not a plain string).
     * e.g. an exam lock sends { error, message_uz, locked_until }.
     */
    public readonly payload?: Record<string, unknown>,
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
    let payload: Record<string, unknown> | undefined;
    if (typeof detail === "string") {
      message = detail;
    } else if (detail && typeof detail === "object") {
      const d = detail as { error?: string; message_uz?: string };
      code = d.error;
      message = d.message_uz ?? "Xatolik yuz berdi";
      payload = detail as Record<string, unknown>;
    }
    throw new ApiError(res.status, message, code, payload);
  }
  return data as T;
}

/**
 * Multipart POST (a real file upload). The browser adds the Content-Type
 * boundary itself, so ONLY the Authorization header is sent — same rule as
 * `adminUploadMaterial`. Errors keep the backend's {"error","message_uz"} shape.
 */
async function uploadMultipart<T>(
  path: string,
  token: string,
  form: FormData,
  fallback: string,
): Promise<T> {
  if (!HAS_API) {
    throw new ApiError(0, "Backend manzili sozlanmagan (VITE_API_URL bo‘sh).", "no_api");
  }
  const res = await fetch(API_URL + path, {
    method: "POST",
    headers: { Authorization: `Bearer ${token}` },
    body: form,
  });
  if (!res.ok) {
    const text = await res.text();
    let message = res.statusText || fallback;
    let code: string | undefined;
    try {
      const detail = (JSON.parse(text) as { detail?: unknown } | null)?.detail;
      if (typeof detail === "string") message = detail;
      else if (detail && typeof detail === "object") {
        const d = detail as { error?: string; message_uz?: string };
        code = d.error;
        message = d.message_uz ?? fallback;
      }
    } catch {
      /* non-JSON error body — keep the status text */
    }
    throw new ApiError(res.status, message, code);
  }
  return (await res.json()) as T;
}

export const api = {
  hasBackend: () => HAS_API,

  /**
   * Absolute URL for a server-relative path that the browser loads WITHOUT a
   * token — profile pictures (`/api/avatars/{id}/{slug}`) are fetched by an
   * <img> tag, which cannot send an Authorization header. In dev API_URL is ""
   * so the path stays same-origin and Vite's proxy forwards it.
   */
  publicUrl: (path: string | null | undefined): string => {
    if (!path) return "";
    return /^https?:\/\//i.test(path) ? path : `${API_URL}${path}`;
  },

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

  // ---------- profile picture (avatar) ----------

  /** Replace the caller's own picture (≤5 MB; the server crops to a 256px square). */
  uploadAvatar: (token: string, file: File) => {
    const form = new FormData();
    form.append("file", file);
    return uploadMultipart<Avatar>("/api/me/avatar", token, form, "Rasmni yuklab bo‘lmadi");
  },

  /** Remove the picture — the previously shared capability URL stops working. */
  removeAvatar: (token: string) =>
    req<{ ok: boolean; removed: boolean }>("/api/me/avatar", { method: "DELETE", token }),

  subjects: (token: string) => req<SubjectItem[]>("/api/subjects", { token }),

  progress: (token: string) => req<Progress>("/api/me/progress", { token }),

  /** Weekly star league: Top-10 of the pupil's grade (server picks the grade). */
  leaderboard: (token: string) => req<Leaderboard>("/api/leaderboard", { token }),

  /** Certificates already issued to this pupil. */
  certificates: (token: string) => req<Certificate[]>("/api/certificates", { token }),

  /** Finished courses of the pupil's grade; `certificate` appears once issued. */
  eligibleCertificates: (token: string) =>
    req<EligibleCertificate[]>("/api/certificates/eligible", { token }),

  /**
   * Download the course certificate PDF (issued once on the first call). The
   * token travels in the Authorization header, never in the URL.
   */
  downloadCertificate: async (
    token: string,
    subjectId: number,
  ): Promise<{ blob: Blob; fileName: string }> => {
    if (!HAS_API) {
      throw new ApiError(0, "Backend manzili sozlanmagan (VITE_API_URL bo‘sh).", "no_api");
    }
    const res = await fetch(`${API_URL}/api/certificates/${subjectId}/pdf`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    if (!res.ok) {
      let message = res.statusText || "Sertifikatni yuklab bo‘lmadi";
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
    const fileName = match ? match[1] : `EduQuest-sertifikat-${subjectId}.pdf`;
    return { blob: await res.blob(), fileName };
  },

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

  // ---------- mandatory exam (majburiy sertifikat) ----------

  /** Every exam of the pupil's grade: readiness, 30-day lock, best mark, certificate. */
  exams: (token: string) => req<ExamCard[]>("/api/exams", { token }),

  /**
   * Open (or resume) the frozen paper. 409 "exam_locked" carries `locked_until`,
   * 409 "exam_not_configured" carries `available` / `required` — the caller reads
   * them from ApiError.payload to explain WHY the exam cannot start yet.
   */
  examPaper: (token: string, subjectId: number) =>
    req<ExamPaper>(`/api/exams/${subjectId}/paper`, { token }),

  /** The attempt id is the idempotency key: submitting twice returns the same result. */
  submitExam: (token: string, subjectId: number, body: { attempt_id: number; answers: unknown[] }) =>
    req<ExamResult>(`/api/exams/${subjectId}/submit`, { method: "POST", token, body }),

  /** Admin: mark a question in/out of the exam paper. */
  adminSetQuestionExam: (token: string, questionId: number, isExam: boolean) =>
    req<AdminQuestionDetail>(`/api/admin/questions/${questionId}/exam`, {
      method: "PATCH",
      token,
      body: { is_exam: isExam },
    }),

  /** Admin: how close each subject is to a ready 20-question paper. */
  adminExamCoverage: (token: string, gradeId?: number) =>
    req<AdminExamCoverage[]>(
      `/api/admin/exams${gradeId ? `?grade_id=${gradeId}` : ""}`,
      { token },
    ),

  // ---------- community chat ----------

  /**
   * Every room this person may open, already in the order the app shows them:
   * e'lonxona, the teachers' room (adults only), their own class, then the group
   * chats the "+" button created.
   */
  chatRooms: (token: string) => req<ChatRoom[]>("/api/chat/rooms", { token }),

  /** Open a chat: name is enough, bio and an icon are optional (3–48 / 200 chars). */
  chatCreateRoom: (
    token: string,
    body: { name: string; bio?: string | null; emoji?: string | null },
  ) => req<ChatRoomResult>("/api/chat/rooms", { method: "POST", token, body }),

  /** Rename / describe / change the icon / close a chat (owner or an adult). */
  chatUpdateRoom: (
    token: string,
    roomId: number,
    body: { name?: string; bio?: string | null; emoji?: string; is_closed?: boolean },
  ) =>
    req<ChatRoomResult>(`/api/chat/rooms/${roomId}`, {
      method: "PATCH",
      token,
      body,
    }),

  /** The chat's picture: the server crops it to a 256px square, EXIF stripped. */
  chatRoomPicture: (token: string, roomId: number, file: File) => {
    const form = new FormData();
    form.append("file", file);
    return uploadMultipart<ChatRoomResult>(
      `/api/chat/rooms/${roomId}/picture`,
      token,
      form,
      "Rasmni yuklab bo‘lmadi",
    );
  },

  chatRoomPictureRemove: (token: string, roomId: number) =>
    req<ChatRoomResult>(`/api/chat/rooms/${roomId}/picture`, {
      method: "DELETE",
      token,
    }),

  /**
   * One page of a room, oldest first. First open: omit `afterId` and the newest
   * 40 arrive. Later polls send back the `latest_id` you rendered and only what
   * is newer comes through — that is how polling stays cheap.
   */
  chatMessages: (token: string, roomId: number, afterId?: number | null) => {
    const params = new URLSearchParams({ room_id: String(roomId) });
    if (afterId != null) params.set("after_id", String(afterId));
    return req<ChatFeed>(`/api/chat/messages?${params.toString()}`, { token });
  },

  chatSend: (token: string, body: { text: string; roomId: number }) =>
    req<ChatSendResult>("/api/chat/messages", {
      method: "POST",
      token,
      body: { text: body.text, room_id: body.roomId },
    }),

  /**
   * A message WITH a file (picture ≤2 MB, GIF ≤2 MB, video ≤10 MB — the server
   * answers with an Uzbek line the composer shows as-is). `file_too_big` (413),
   * `file_rejected`/`bad_file_type` (422) and `media_quota` (429) all arrive
   * through ApiError.code, so the bubble never appears half-sent.
   */
  chatAttach: (token: string, roomId: number, file: File, text: string) => {
    const form = new FormData();
    form.append("room_id", String(roomId));
    if (text.trim()) form.append("text", text.trim());
    form.append("file", file);
    return uploadMultipart<ChatSendResult>(
      "/api/chat/messages/attach",
      token,
      form,
      "Faylni yuborib bo‘lmadi",
    );
  },

  /** The "add people" list: a name, a class and a picture — nothing else. */
  chatPeople: (token: string, q: string) =>
    req<ChatPeopleResult>(`/api/chat/people?q=${encodeURIComponent(q)}`, { token }),

  chatMembers: (token: string, roomId: number) =>
    req<ChatMember[]>(`/api/chat/rooms/${roomId}/members`, { token }),

  /** Put yourself in the room's people list (group chats only). */
  chatJoin: (token: string, roomId: number) =>
    req<ChatMember[]>(`/api/chat/rooms/${roomId}/join`, { method: "POST", token }),

  chatAddMember: (token: string, roomId: number, userId: number) =>
    req<ChatMember[]>(`/api/chat/rooms/${roomId}/members`, {
      method: "POST",
      token,
      body: { user_id: userId },
    }),

  /** A person leaves; an owner/staff takes somebody else out. */
  chatRemoveMember: (token: string, roomId: number, personId: number) =>
    req<{ ok: boolean }>(`/api/chat/rooms/${roomId}/members/${personId}`, {
      method: "DELETE",
      token,
    }),

  /**
   * The school's secret, typed once (POST /api/me/teacher-code). 403 means the
   * code was wrong, 429 "too_many_attempts" means wait — retry-after is in
   * ApiError.status and the message is already Uzbek.
   */
  claimTeacher: (token: string, code: string) =>
    req<Profile>("/api/me/teacher-code", { method: "POST", token, body: { code } }),

  /** Admin: the approval queue plus the global count that drives the badge. */
  chatPending: (token: string, gradeId?: number | null) =>
    req<ChatPendingQueue>(
      `/api/chat/admin/pending${gradeId ? `?grade_id=${gradeId}` : ""}`,
      { token },
    ),

  chatApprove: (token: string, messageId: number) =>
    req<{ ok: boolean; id: number; status: string }>(
      `/api/chat/admin/${messageId}/approve`,
      { method: "POST", token },
    ),

  /** A refusal needs a short reason; the author sees it on their own copy. */
  chatReject: (token: string, messageId: number, reason: string) =>
    req<{ ok: boolean; id: number; status: string }>(
      `/api/chat/admin/${messageId}/reject`,
      { method: "POST", token, body: { reason } },
    ),

  /** Take a message out of a room that is already live (the no-filter mode's control). */
  chatDelete: (token: string, messageId: number) =>
    req<{ ok: boolean; id: number; status: string }>(`/api/chat/admin/${messageId}`, {
      method: "DELETE",
      token,
    }),

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
    body: {
      text: string;
      kind: string;
      options?: { text: string; is_correct: boolean }[];
      pairs?: { left: string; right: string }[];
    },
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
