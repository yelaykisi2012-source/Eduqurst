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
import type { Grade, Profile, Progress, SubjectItem } from "./types";

const API_URL = (import.meta.env.VITE_API_URL ?? "").replace(/\/+$/, "");

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
  if (!API_URL) {
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
  hasBackend: () => Boolean(API_URL),

  login: (initData: string) =>
    req<{ access_token: string; first_name: string }>("/api/auth/telegram", {
      method: "POST",
      body: { init_data: initData },
    }),

  me: (token: string) => req<Profile>("/api/me", { token }),

  grades: (token: string) => req<Grade[]>("/api/grades", { token }),

  setGrade: (token: string, grade_id: number) =>
    req<Profile>("/api/me/grade", { method: "POST", token, body: { grade_id } }),

  subjects: (token: string) => req<SubjectItem[]>("/api/subjects", { token }),

  progress: (token: string) => req<Progress>("/api/me/progress", { token }),
};
