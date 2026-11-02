import { useEffect, useRef, useState } from "react";

import { api, ApiError } from "../api";
import type {
  Avatar,
  Certificate,
  EligibleCertificate,
  Leaderboard,
  Profile,
  Progress,
} from "../types";
import Card from "./ui/Card";
import Button from "./ui/Button";
import Badge from "./ui/Badge";
import ProgressBar from "./ui/ProgressBar";
import {
  IconTrophy,
  IconCheck,
  IconDownload,
  IconEye,
  IconEyeOff,
  IconGraduationCap,
  IconImage,
  IconLock,
  IconTrash,
} from "./ui/Icons";

/** "2026-10-26" → "26.10" (optionally shifted by a day). */
function formatDay(iso: string, dayOffset = 0): string {
  const d = new Date(`${iso}T00:00:00`);
  d.setDate(d.getDate() + dayOffset);
  return `${String(d.getDate()).padStart(2, "0")}.${String(d.getMonth() + 1).padStart(2, "0")}`;
}

/** Weekly stars league: Top-10 of the pupil's grade. */
function LeagueCard({ token, gradeId }: { token: string; gradeId: number | null }) {
  const [board, setBoard] = useState<Leaderboard | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    if (!token || gradeId == null) return;
    let alive = true;
    setFailed(false);
    api
      .leaderboard(token)
      .then((b) => {
        if (alive) setBoard(b);
      })
      .catch(() => {
        if (alive) setFailed(true);
      });
    return () => {
      alive = false;
    };
  }, [token, gradeId]);

  if (gradeId == null) return null;

  const medal = (rank: number) =>
    rank === 1 ? "🥇" : rank === 2 ? "🥈" : rank === 3 ? "🥉" : `${rank}`;

  return (
    <Card variant="elevated" className="mb-3.5 sm:mb-6 p-3.5 sm:p-5 bg-white">
      <div className="flex items-center justify-between gap-2">
        <div>
          <h2 className="text-sm sm:text-base font-black text-slate-900">
            🏆 Haftalik reyting
          </h2>
          <p className="text-[10px] sm:text-xs font-semibold text-slate-400 mt-0.5">
            {board
              ? `${board.grade_name} · ${formatDay(board.week_start)} – ${formatDay(board.week_end, -1)}`
              : "Yuklanmoqda…"}
          </p>
        </div>
        {board && (
          <span className="text-[10px] sm:text-[11px] font-bold px-2 py-0.5 rounded-full bg-indigo-50 text-indigo-700 border border-indigo-200 shrink-0">
            {board.participants} ishtirokchi
          </span>
        )}
      </div>

      {failed ? (
        <p className="text-[11px] text-slate-400 mt-3">Reytingni yuklab bo‘lmadi.</p>
      ) : board && board.top.length === 0 ? (
        <p className="text-[11px] sm:text-xs text-slate-500 mt-3">
          Bu hafta hali yulduz yo‘q. Birinchi bo‘lib yulduz to‘plang! ⭐
        </p>
      ) : board ? (
        <>
          <ol className="mt-2.5 divide-y divide-slate-100">
            {board.top.map((row) => (
              <li
                key={row.user_id}
                className={`flex items-center gap-2 py-1.5 ${
                  row.is_me ? "bg-blue-50/60 -mx-2 px-2 rounded-lg" : ""
                }`}
              >
                <span className="w-6 text-center text-xs font-black text-slate-500 shrink-0">
                  {medal(row.rank)}
                </span>
                <span
                  className={`flex-1 truncate text-xs sm:text-sm font-bold ${
                    row.is_me ? "text-blue-700" : "text-slate-800"
                  }`}
                >
                  {row.first_name || "O‘quvchi"}
                  {row.is_me && (
                    <span className="ml-1 text-[10px] font-bold text-blue-500">(siz)</span>
                  )}
                </span>
                <span className="text-xs sm:text-sm font-black text-amber-600 shrink-0">
                  ⭐ {row.stars}
                </span>
              </li>
            ))}
          </ol>
          <div className="mt-2 pt-2 border-t border-slate-100 text-[11px] sm:text-xs font-bold text-slate-500">
            {board.me
              ? `Sizning o‘rningiz: #${board.me.rank} · ⭐ ${board.me.stars}`
              : "Siz bu hafta hali yulduz to‘pladingiz."}
          </div>
        </>
      ) : null}
    </Card>
  );
}

/** Course certificates: a finished course earns a QR-verified PDF. */
function CertificatesCard({ token }: { token: string }) {
  const [eligible, setEligible] = useState<EligibleCertificate[] | null>(null);
  const [issued, setIssued] = useState<Certificate[]>([]);
  const [failed, setFailed] = useState(false);
  const [failure, setFailure] = useState("");
  const [attempt, setAttempt] = useState(0);
  const [busy, setBusy] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!token) return;
    let alive = true;
    setFailed(false);
    setFailure("");
    setEligible(null);

    const fetchAll = () =>
      Promise.all([api.eligibleCertificates(token), api.certificates(token)]);

    (async () => {
      for (let tries = 0; tries < 3; tries += 1) {
        try {
          const [courses, certs] = await fetchAll();
          if (!alive) return;
          setEligible(courses);
          setIssued(certs);
          return;
        } catch (err) {
          const retryable =
            !(err instanceof ApiError) || err.status === 0 || err.status >= 500;
          if (!retryable || tries === 2) {
            if (!alive) return;
            console.warn("Sertifikatlar yuklanmadi:", err);
            setFailed(true);
            setFailure(
              err instanceof ApiError
                ? err.status === 409
                  ? "Avval sinfingizni tanlang."
                  : err.status
                    ? `Server xatosi (HTTP ${err.status}).`
                    : "Server bilan aloqa uzildi."
                : "Server bilan aloqa uzildi.",
            );
            return;
          }
          // Render free tier can answer 502 while waking up — retry briefly.
          await new Promise((resolve) => window.setTimeout(resolve, tries === 0 ? 2000 : 5000));
          if (!alive) return;
        }
      }
    })();

    return () => {
      alive = false;
    };
  }, [token, attempt]);

  const refresh = () => {
    api.eligibleCertificates(token).then(setEligible).catch(() => {});
    api.certificates(token).then(setIssued).catch(() => {});
  };

  const download = async (subjectId: number) => {
    setBusy(subjectId);
    setError(null);
    try {
      const { blob, fileName } = await api.downloadCertificate(token, subjectId);
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = fileName;
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.setTimeout(() => URL.revokeObjectURL(url), 5000);
      refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Sertifikatni yuklab bo‘lmadi");
    } finally {
      setBusy(null);
    }
  };

  const older = issued.filter(
    (cert) => !(eligible ?? []).some((course) => course.subject_id === cert.subject_id),
  );
  const empty = eligible !== null && eligible.length === 0 && older.length === 0;

  return (
    <Card variant="elevated" className="mb-3.5 sm:mb-6 p-3.5 sm:p-5 bg-white">
      <div className="flex items-center justify-between gap-2">
        <div>
          <h2 className="text-sm sm:text-base font-black text-slate-900">
            📜 Sertifikatlar
          </h2>
          <p className="text-[10px] sm:text-xs font-semibold text-slate-400 mt-0.5">
            Kursni to‘liq tugatib yoki majburiy imtihondan o‘tib QR-kodli sertifikat olinadi
          </p>
        </div>
        {issued.length > 0 && (
          <span className="text-[10px] sm:text-[11px] font-bold px-2 py-0.5 rounded-full bg-amber-50 text-amber-700 border border-amber-200 shrink-0">
            {issued.length} ta
          </span>
        )}
      </div>

      {failed ? (
        <div className="mt-3">
          <p className="text-[11px] text-slate-400">
            Sertifikatlarni yuklab bo‘lmadi.
          </p>
          {failure && (
            <p className="text-[10px] text-slate-400 mt-0.5">{failure}</p>
          )}
          <Button
            variant="secondary"
            size="sm"
            className="mt-2"
            onClick={() => setAttempt((value) => value + 1)}
          >
            Qayta urinish
          </Button>
        </div>
      ) : eligible === null ? (
        <p className="text-[11px] text-slate-400 mt-3">Yuklanmoqda…</p>
      ) : empty ? (
        <p className="text-[11px] sm:text-xs text-slate-500 mt-3">
          Hali sertifikat yo‘q. Biror fanda barcha darslarni tugating yoki «Imtihon»
          bo‘limidagi majburiy imtihondan 90% va undan yuqori natija bilan o‘ting —
          sertifikat shu yerda paydo bo‘ladi. 📈
        </p>
      ) : (
        <ul className="mt-2.5 divide-y divide-slate-100">
          {eligible.map((course) => {
            const cert = course.certificate;
            return (
              <li key={course.subject_id} className="flex items-center gap-2 py-2">
                <span className="text-xl shrink-0" aria-hidden>
                  {course.emoji}
                </span>
                <div className="flex-1 min-w-0">
                  <p className="text-xs sm:text-sm font-bold text-slate-800 truncate">
                    {course.subject_name}
                  </p>
                  <p className="text-[10px] sm:text-[11px] font-semibold text-slate-400 truncate">
                    {course.total_lessons} ta dars · {course.score_percent}% ·{" "}
                    {cert
                      ? cert.issued_via === "exam"
                        ? `Imtihon · baho ${cert.mark ?? "—"} · kod ${cert.code}`
                        : `Kurs · kod ${cert.code}`
                      : "kurs tugallandi"}
                  </p>
                </div>
                {cert && (
                  <Badge variant="emerald" size="sm" className="hidden sm:inline-flex">
                    Tayyor
                  </Badge>
                )}
                <Button
                  variant={cert ? "secondary" : "accent"}
                  size="sm"
                  loading={busy === course.subject_id}
                  onClick={() => download(course.subject_id)}
                  icon={
                    busy === course.subject_id ? undefined : <IconDownload size={14} />
                  }
                >
                  {cert ? "Yuklash" : "Olish"}
                </Button>
              </li>
            );
          })}
          {older.map((cert) => (
            <li key={`old-${cert.subject_id}`} className="flex items-center gap-2 py-2">
              <span className="text-xl shrink-0" aria-hidden>
                📜
              </span>
              <div className="flex-1 min-w-0">
                <p className="text-xs sm:text-sm font-bold text-slate-800 truncate">
                  {cert.subject_name}
                </p>
                <p className="text-[10px] sm:text-[11px] font-semibold text-slate-400 truncate">
                  {cert.grade_name} · {cert.score_percent}% ·{" "}
                  {cert.issued_via === "exam"
                    ? `Majburiy imtihon · baho ${cert.mark ?? "—"} · kod ${cert.code}`
                    : `Kurs · kod ${cert.code}`}
                </p>
              </div>
              {cert.issued_via === "exam" && (
                <Badge variant="purple" size="sm" className="hidden sm:inline-flex">
                  Imtihon
                </Badge>
              )}
              <Button
                variant="secondary"
                size="sm"
                loading={busy === cert.subject_id}
                onClick={() => download(cert.subject_id)}
                icon={busy === cert.subject_id ? undefined : <IconDownload size={14} />}
              >
                Yuklash
              </Button>
            </li>
          ))}
        </ul>
      )}

      {error && <p className="mt-2 text-[11px] font-semibold text-rose-600">{error}</p>}
    </Card>
  );
}

/** Achievements / Yutuqlar Page */
export function AchievementsPage({
  progress,
  token,
}: {
  progress: Progress | null;
  token: string;
}) {
  const earnedCount = progress?.achievements.filter((a) => a.earned).length ?? 0;
  const totalCount = progress?.achievements.length ?? 0;
  const percent = totalCount > 0 ? Math.round((earnedCount / totalCount) * 100) : 0;

  return (
    <div className="mx-auto max-w-2xl animate-fade-in py-1 pb-32 sm:pb-12">
      {/* Header Banner */}
      <Card variant="elevated" className="mb-3.5 sm:mb-6 p-3.5 sm:p-6 bg-gradient-to-br from-indigo-600 to-purple-700 text-white border-0 shadow-sm">
        <div className="flex items-center gap-3">
          <div className="flex h-11 w-11 sm:h-13 sm:w-13 items-center justify-center rounded-xl sm:rounded-2xl bg-white/20 backdrop-blur-md text-2xl sm:text-3xl shadow-inner shrink-0">
            <IconTrophy size={24} />
          </div>
          <div className="flex-1 min-w-0">
            <span className="text-[10px] sm:text-xs font-bold uppercase tracking-wider text-indigo-200">
              Yutuqlar kolleksiyasi
            </span>
            <h1 className="text-base sm:text-xl font-black text-white leading-tight truncate">
              Mukofotlar va Medallar
            </h1>
            <p className="text-[11px] sm:text-xs font-medium text-indigo-100 mt-0.5 truncate">
              {earnedCount} / {totalCount} ta yutuq · ⭐ {progress?.stars_total ?? 0} yulduz
            </p>
          </div>
        </div>

        <div className="mt-3.5">
          <div className="flex justify-between text-[11px] sm:text-xs font-bold text-indigo-100 mb-1">
            <span>To‘plangan yutuqlar</span>
            <span>{percent}%</span>
          </div>
          <div className="h-1.5 sm:h-2 w-full rounded-full bg-white/20 overflow-hidden">
            <div
              className="h-full bg-amber-400 rounded-full transition-all duration-500"
              style={{ width: `${percent}%` }}
            />
          </div>
        </div>
      </Card>

      {/* Weekly league */}
      <LeagueCard token={token} gradeId={progress?.grade_id ?? null} />

      {/* Course certificates */}
      <CertificatesCard token={token} />

      {/* Achievements List */}
      <div className="space-y-2 sm:space-y-3">
        {(progress?.achievements ?? []).map((item) => (
          <Card
            key={item.code}
            variant="default"
            className={`p-2.5 sm:p-4 flex items-center gap-3 transition-all ${
              item.earned
                ? "bg-white border-amber-200/70 shadow-2xs hover:border-amber-300"
                : "bg-slate-50/70 border-slate-200/60 opacity-60"
            }`}
          >
            <div
              className={`flex h-10 w-10 sm:h-12 sm:w-12 shrink-0 items-center justify-center rounded-xl text-2xl shadow-2xs ${
                item.earned
                  ? "bg-amber-50 text-amber-500 border border-amber-200/80"
                  : "bg-slate-100 text-slate-400 border border-slate-200 grayscale"
              }`}
            >
              <span aria-hidden>{item.icon}</span>
            </div>

            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-1.5 flex-wrap">
                <h3 className="text-xs sm:text-sm font-bold text-slate-900 truncate">
                  {item.title}
                </h3>
                {item.earned ? (
                  <Badge variant="amber" size="sm">
                    Egallandi
                  </Badge>
                ) : (
                  <Badge variant="slate" size="sm">
                    Qulflangan
                  </Badge>
                )}
              </div>
              <p className="text-[11px] sm:text-xs text-slate-500 mt-0.5 leading-snug">
                {item.description}
              </p>
            </div>

            <div className="shrink-0">
              {item.earned ? (
                <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-emerald-50 text-emerald-600 border border-emerald-200">
                  <IconCheck size={14} />
                </div>
              ) : (
                <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-slate-100 text-slate-400">
                  <IconLock size={14} />
                </div>
              )}
            </div>
          </Card>
        ))}
      </div>
    </div>
  );
}

/**
 * The 256px face used on the profile card: the uploaded picture when there is
 * one, the initial when there is not (a pupil who never set a picture is not
 * left with an empty grey hole).
 */
function AvatarFace({
  name,
  avatarUrl,
  className = "",
}: {
  name: string;
  avatarUrl?: string | null;
  className?: string;
}) {
  const url = api.publicUrl(avatarUrl);
  if (url) {
    return (
      <img
        src={url}
        alt={`${name} profili`}
        className={`shrink-0 rounded-2xl object-cover ring-1 ring-slate-200 ${className}`}
      />
    );
  }
  return (
    <div
      className={`flex shrink-0 items-center justify-center rounded-2xl bg-gradient-to-br from-[#3478F6] to-indigo-600 font-black text-white shadow-xs ${className}`}
      aria-hidden
    >
      {(name.trim().charAt(0) || "?").toUpperCase()}
    </div>
  );
}

/**
 * AvatarSection — "profiliga rasm qoya olsin".
 *
 * The file is sent as-is; the server centre-crops it to a 256px square,
 * re-encodes it (which drops the phone's EXIF block, so no GPS coordinates or
 * camera serial leave the device) and returns a brand new capability URL.
 * Removing the picture rotates that URL too, so a link already shared dies.
 *
 * A Telegram profile photo can also be pushed by the bot ("🖼 Rasmim" tugmasi) —
 * both sources land in the same row, so the Mini App never has to know which.
 */
function AvatarSection({
  token,
  profile,
  onSaved,
  notify,
}: {
  token: string;
  profile: Profile | null;
  onSaved: () => void | Promise<void>;
  notify: (msg: string) => void;
}) {
  const picker = useRef<HTMLInputElement | null>(null);
  const [busy, setBusy] = useState(false);
  const [removing, setRemoving] = useState(false);
  const [error, setError] = useState("");
  const [saved, setSaved] = useState<Avatar | null>(null);

  const name = profile?.first_name || "O‘quvchi";
  const hasPicture = Boolean(profile?.avatar_url);

  const upload = async (file: File | undefined) => {
    if (!file) return;
    setError("");
    // Cheap checks first so the pupil sees the reason instantly; the server
    // re-validates everything (a renamed .exe is still not an image).
    if (!file.type.startsWith("image/")) {
      setError("Rasm fayli tanlang — JPG, PNG yoki WEBP.");
      return;
    }
    if (file.size > 5 * 1024 * 1024) {
      setError("Rasm juda katta — 5 MB dan kichikroq fayl tanlang.");
      return;
    }
    setBusy(true);
    try {
      setSaved(await api.uploadAvatar(token, file));
      await onSaved();
      notify("Profilingiz rasmi qo‘yildi 🖼️");
    } catch (e) {
      setError(
        e instanceof ApiError ? e.message : "Rasmni yuklab bo‘lmadi. Aloqani tekshiring.",
      );
    } finally {
      setBusy(false);
      // Allow picking the same file twice (browsers would otherwise not fire change).
      if (picker.current) picker.current.value = "";
    }
  };

  const remove = async () => {
    setRemoving(true);
    setError("");
    try {
      await api.removeAvatar(token);
      setSaved(null);
      await onSaved();
      notify("Rasm o‘chirildi — profil yana ism bilan ko‘rinadi.");
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "O‘chirib bo‘lmadi.");
    } finally {
      setRemoving(false);
    }
  };

  return (
    <Card className="mb-3.5 sm:mb-6 p-3.5 sm:p-5">
      <div className="flex items-start gap-3">
        <AvatarFace
          name={name}
          avatarUrl={saved?.avatar_url ?? profile?.avatar_url}
          className="h-16 w-16 text-2xl sm:h-20 sm:w-20"
        />
        <div className="min-w-0 flex-1">
          <h2 className="text-xs sm:text-sm font-black text-slate-900">Profil rasmi</h2>
          <p className="mt-0.5 text-[10px] sm:text-[11px] font-semibold text-slate-500 leading-snug">
            {hasPicture || saved
              ? "Rasm 256px kvadrat qilib qisqartiriladi. Telefon ma’lumotlari (Joy/EXIF) saqlanmaydi."
              : "Hali rasm qo‘ymagansiz — harf ko‘rinadi. Rasm 256px kvadratga o‘giriladi, telefon ma’lumotlari tashlanadi."}
          </p>
          {saved && (
            <p className="mt-1 text-[10px] font-bold text-slate-400">
              {saved.source === "telegram" ? "Telegram profil rasmi" : "Yuklangan rasm"} ·{" "}
              {saved.width}×{saved.width} · {Math.max(1, Math.round(saved.size_bytes / 1024))} KB
            </p>
          )}

          <div className="mt-2 flex flex-wrap items-center gap-1.5">
            <input
              ref={picker}
              type="file"
              accept="image/*"
              className="hidden"
              onChange={(e) => void upload(e.target.files?.[0])}
            />
            <Button
              variant="primary"
              size="sm"
              loading={busy}
              icon={busy ? undefined : <IconImage size={14} />}
              onClick={() => picker.current?.click()}
            >
              {hasPicture || saved ? "Rasmni almashtirish" : "Rasm yuklash"}
            </Button>
            {(hasPicture || saved) && (
              <Button
                variant="ghost"
                size="sm"
                className="text-rose-600 hover:bg-rose-50"
                loading={removing}
                icon={removing ? undefined : <IconTrash size={14} />}
                onClick={() => void remove()}
              >
                O‘chirish
              </Button>
            )}
          </div>

          {error && (
            <p className="mt-1.5 text-[11px] font-bold text-rose-600">{error}</p>
          )}
          <p className="mt-1.5 text-[10px] font-semibold text-slate-400">
            Telegram’dagi rasmingizni botdagi «🖼 Rasmimni qo‘yish» tugmasi orqali
            ham shu yerga qo‘yishingiz mumkin.
          </p>
        </div>
      </div>
    </Card>
  );
}

/**
 * "Men o‘qituvchiman" — the school's secret code, typed once.
 *
 * Three honest states, and nothing in between:
 *   * already staff  → a purple line, no form (there is no un-becoming);
 *   * code configured → the form;
 *   * code NOT set   → the whole section disappears, because a button that can
 *     never succeed is worse than no button (the rule for every unfinished part
 *     of this app).
 * The 429 the server sends after too many guesses is shown as-is: it is already
 * Uzbek and already says how long to wait.
 */
function TeacherSection({
  profile,
  token,
  onSaved,
  notify,
}: {
  profile: Profile | null;
  token: string;
  onSaved: () => void | Promise<void>;
  notify: (msg: string) => void;
}) {
  const [code, setCode] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [reveal, setReveal] = useState(false);

  if (profile?.is_teacher) {
    return (
      <Card className="mb-3.5 sm:mb-6 p-3.5 sm:p-5 border-purple-200/70 bg-purple-50/50">
        <h2 className="text-xs sm:text-sm font-black text-purple-900">
          🧑‍🏫 Siz o‘qituvchisiz
        </h2>
        <p className="mt-1 text-[11px] sm:text-[12px] font-semibold text-purple-800/80">
          Chatlar ro‘yxatida «O‘qituvchilar» xonasi ko‘rinadi va e'lonxonaga yozishingiz
          mumkin. Bu holat orqaga qaytarilmaydi — kerak bo‘lsa administrator bilan
          bog‘laning.
        </p>
      </Card>
    );
  }

  // TEACHER_CODE is not in the server's settings → keep the door invisible.
  if (!profile?.can_claim_teacher) return null;

  const submit = async () => {
    const value = code.trim();
    if (value.length === 0) return;
    setBusy(true);
    setError("");
    try {
      await api.claimTeacher(token, value);
      setCode("");
      await onSaved();
      notify("O‘qituvchi huquqi berildi 🧑‍🏫");
    } catch (e) {
      setError(
        e instanceof ApiError
          ? e.message
          : "Tekshirib bo‘lmadi. Aloqani tekshiring.",
      );
    } finally {
      setBusy(false);
    }
  };

  return (
    <Card className="mb-3.5 sm:mb-6 p-3.5 sm:p-5">
      <h2 className="text-xs sm:text-sm font-black text-slate-900">
        🧑‍🏫 Men o‘qituvchiman
      </h2>
      <p className="mt-0.5 text-[10px] sm:text-[11px] font-semibold text-slate-500 leading-snug">
        Maktab bergan maxfiy kodni bir marta yozing — o‘qituvchilar xonasi va
        e'lonxonani yozish huquqi shu bilan ochiladi. Kod o‘quvchilarga berilmaydi.
      </p>
      <div className="mt-2.5 flex items-center gap-2">
        <div className="relative min-w-0 flex-1">
          <input
            type={reveal ? "text" : "password"}
            value={code}
            onChange={(e) => {
              setCode(e.target.value);
              if (error) setError("");
            }}
            onKeyDown={(e) => {
              if (e.key === "Enter") void submit();
            }}
            maxLength={64}
            autoComplete="off"
            placeholder="Maktab kodi"
            className="w-full rounded-xl border border-slate-200 bg-slate-50/80 px-3 py-2.5 pr-10 text-[13px] font-semibold text-slate-900 outline-none focus:border-purple-400 focus:bg-white"
          />
          <button
            type="button"
            onClick={() => setReveal((v) => !v)}
            aria-label={reveal ? "Kodni yashirish" : "Kodni ko‘rsatish"}
            className="absolute right-2 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600 cursor-pointer"
          >
            {reveal ? <IconEyeOff size={16} /> : <IconEye size={16} />}
          </button>
        </div>
        <Button
          variant="secondary"
          size="sm"
          loading={busy}
          disabled={code.trim().length === 0}
          onClick={() => void submit()}
          icon={busy ? undefined : <IconLock size={14} />}
        >
          {busy ? "" : "Tekshirish"}
        </Button>
      </div>
      {error && <p className="mt-1.5 text-[11px] font-bold text-rose-600">{error}</p>}
    </Card>
  );
}

/** Student Profile Page */
export function ProfilePage({
  profile,
  progress,
  token,
  onChangeGrade,
  onLogout,
  onProfileRefresh,
  notify,
}: {
  profile: Profile | null;
  progress: Progress | null;
  token: string;
  onChangeGrade: () => void;
  onLogout?: () => void;
  /** Re-reads /api/me so the new picture URL reaches every screen. */
  onProfileRefresh: () => void | Promise<void>;
  notify: (msg: string) => void;
}) {
  const name = profile?.first_name || progress?.first_name || "O‘quvchi";
  const gradeLabel = profile?.grade_name ?? progress?.grade_name ?? "Belgilanmagan";

  // Calculate learning level based on stars
  const stars = progress?.stars_total ?? 0;
  let levelTitle = "Boshlovchi";
  let levelBadge = "bg-blue-50 text-blue-700 border-blue-200";
  if (stars >= 100) {
    levelTitle = "Olimpiada qatnashchisi";
    levelBadge = "bg-purple-50 text-purple-700 border-purple-200";
  } else if (stars >= 50) {
    levelTitle = "A’lochi bilimdon";
    levelBadge = "bg-amber-50 text-amber-700 border-amber-200";
  } else if (stars >= 20) {
    levelTitle = "Izlanuvchi o‘quvchi";
    levelBadge = "bg-emerald-50 text-emerald-700 border-emerald-200";
  }

  return (
    <div className="mx-auto max-w-2xl animate-fade-in py-1 pb-32 sm:pb-12">
      {/* Profile Info Card */}
      <Card variant="elevated" className="mb-3.5 sm:mb-6 p-3.5 sm:p-6 bg-white shadow-sm">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
          <div className="flex items-center gap-3">
            <AvatarFace
              name={name}
              avatarUrl={profile?.avatar_url}
              className="h-12 w-12 text-xl sm:h-14 sm:w-14 sm:text-2xl"
            />
            <div className="min-w-0">
              <div className="flex items-center gap-2">
                <h1 className="text-base sm:text-xl font-black text-slate-900 truncate">{name}</h1>
                <span className={`inline-flex px-2 py-0.5 rounded-full text-[10px] sm:text-[11px] font-bold border ${levelBadge}`}>
                  {levelTitle}
                </span>
              </div>
              <p className="text-[11px] font-semibold text-slate-400 mt-0.5">
                Ta'lim oluvchi profili
              </p>
              {(profile?.current_streak ?? 0) > 0 && (
                <p className="text-[10px] font-bold text-orange-600 mt-0.5">
                  🔥 {profile?.current_streak} kunlik seriya · rekord{" "}
                  {profile?.max_streak ?? profile?.current_streak} kun
                </p>
              )}
            </div>
          </div>

          <Button
            variant="secondary"
            size="sm"
            onClick={onChangeGrade}
            icon={<IconGraduationCap size={14} />}
          >
            {gradeLabel} · O‘zgartirish
          </Button>
        </div>

        {/* Learning Statistics Bar */}
        <div className="mt-4 grid grid-cols-3 gap-2">
          <div className="p-2.5 sm:p-3 rounded-xl bg-amber-50/70 border border-amber-200/50 text-center">
            <span className="text-base sm:text-xl font-black text-amber-700">
              {stars}
            </span>
            <span className="block text-[10px] font-bold text-amber-600 mt-0.5">
              ⭐ Yulduzlar
            </span>
          </div>

          <div className="p-2.5 sm:p-3 rounded-xl bg-blue-50/70 border border-blue-200/50 text-center">
            <span className="text-base sm:text-xl font-black text-blue-700">
              {progress?.lessons_viewed ?? 0}
            </span>
            <span className="block text-[10px] font-bold text-blue-600 mt-0.5">
              📖 Darslar
            </span>
          </div>

          <div className="p-2.5 sm:p-3 rounded-xl bg-emerald-50/70 border border-emerald-200/50 text-center">
            <span className="text-base sm:text-xl font-black text-emerald-700">
              {progress?.lessons_passed ?? 0}
            </span>
            <span className="block text-[10px] font-bold text-emerald-600 mt-0.5">
              ✅ Yakunlandi
            </span>
          </div>
        </div>
      </Card>

      {/* Profile picture ("profiliga rasm qoya olsin") */}
      <AvatarSection
        token={token}
        profile={profile}
        onSaved={onProfileRefresh}
        notify={notify}
      />

      {/* Teacher code — only rendered when the school actually handed codes out */}
      <TeacherSection
        profile={profile}
        token={token}
        onSaved={onProfileRefresh}
        notify={notify}
      />

      {/* Subject Progress Section */}
      {progress && progress.subjects.length > 0 && (
        <Card className="mb-3.5 sm:mb-6 p-3.5 sm:p-5">
          <h2 className="text-[11px] sm:text-xs font-bold uppercase tracking-wider text-slate-400 mb-3">
            Fanlar bo‘yicha o‘zlashtirish
          </h2>
          <div className="space-y-3">
            {progress.subjects.map((sub) => {
              const subPercent =
                sub.total_lessons > 0
                  ? Math.round((sub.passed_lessons / sub.total_lessons) * 100)
                  : 0;

              return (
                <div key={sub.subject_name} className="flex items-center gap-2.5">
                  <span className="text-xl shrink-0" aria-hidden>
                    {sub.emoji}
                  </span>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center justify-between text-[11px] sm:text-xs font-bold text-slate-800 mb-1">
                      <span className="truncate">{sub.subject_name}</span>
                      <span className="text-slate-400 font-semibold">
                        {sub.passed_lessons}/{sub.total_lessons}
                      </span>
                    </div>
                    <ProgressBar value={subPercent} size="sm" />
                  </div>
                </div>
              );
            })}
          </div>
        </Card>
      )}

      {/* Settings / Actions */}
      <Card className="p-3.5 sm:p-5 space-y-2.5">
        <h3 className="text-[11px] sm:text-xs font-bold uppercase tracking-wider text-slate-400">
          Sozlamalar
        </h3>
        <Button
          variant="secondary"
          size="sm"
          fullWidth
          onClick={onChangeGrade}
          icon={<IconGraduationCap size={16} />}
        >
          Sinfni almashtirish ({gradeLabel})
        </Button>

        <p className="text-[10px] sm:text-[11px] text-slate-400 text-center px-1">
          Sinfni o‘zgartirganingizda to‘plangan yulduzlar va erishilgan natijalar saqlanib qoladi.
        </p>

        {onLogout && (
          <div className="pt-2 border-t border-slate-100">
            <Button
              variant="danger"
              size="sm"
              fullWidth
              onClick={onLogout}
            >
              Hisobdan chiqish
            </Button>
          </div>
        )}
      </Card>
    </div>
  );
}
