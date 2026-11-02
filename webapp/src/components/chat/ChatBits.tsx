import { useEffect, useState } from "react";
import { createPortal } from "react-dom";

import { api } from "../../api";
import type { ChatMedia } from "../../types";
import { IconClose } from "../ui/Icons";

/** Initials for pupils without a picture — the same fallback everywhere. */
export function initials(name: string): string {
  return (name.trim().charAt(0) || "?").toUpperCase();
}

/** "14:32" for today, "05.11" for an older day — both in the pupils' own timezone. */
export function stamp(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "";
  const zone = "Asia/Tashkent";
  const opts: Intl.DateTimeFormatOptions = { timeZone: zone };
  const now = new Date().toLocaleDateString("en-CA", opts);
  const then = date.toLocaleDateString("en-CA", opts);
  return then === now
    ? new Intl.DateTimeFormat("en-GB", { ...opts, hour: "2-digit", minute: "2-digit" }).format(date)
    : new Intl.DateTimeFormat("en-GB", { ...opts, day: "2-digit", month: "2-digit" }).format(date);
}

/** A face: the picture when there is one, a coloured initial when there is not. */
export function AvatarDot({
  name,
  avatarUrl,
  size = 28,
}: {
  name: string;
  avatarUrl: string | null;
  size?: number;
}) {
  const url = api.publicUrl(avatarUrl);
  if (url) {
    return (
      <img
        src={url}
        alt=""
        width={size}
        height={size}
        loading="lazy"
        className="shrink-0 rounded-full object-cover ring-1 ring-slate-200"
        style={{ width: size, height: size }}
      />
    );
  }
  return (
    <span
      className="flex shrink-0 items-center justify-center rounded-full bg-gradient-to-br from-[#3478F6] to-indigo-600 font-black text-white"
      style={{ width: size, height: size, fontSize: Math.round(size * 0.42) }}
      aria-hidden
    >
      {initials(name)}
    </span>
  );
}

/**
 * A chat's own icon: its picture if the owner uploaded one, otherwise the emoji
 * it was opened with (a group chat always has one — the server defaults to 💬).
 */
export function RoomBadge({
  room,
  size = 40,
}: {
  room: { name: string; emoji: string; avatar_url: string | null };
  size?: number;
}) {
  const url = api.publicUrl(room.avatar_url);
  if (url) {
    return (
      <img
        src={url}
        alt=""
        width={size}
        height={size}
        className="shrink-0 rounded-2xl object-cover ring-1 ring-black/10"
        style={{ width: size, height: size }}
      />
    );
  }
  return (
    <span
      className="flex shrink-0 items-center justify-center rounded-2xl bg-white/20 text-center"
      style={{ width: size, height: size, fontSize: Math.round(size * 0.5) }}
      aria-hidden
    >
      {room.emoji || "💬"}
    </span>
  );
}

/** Emoji a pupil actually types. One row per eight, so it stays a strip. */
export const CHAT_EMOJI = [
  "👍", "😂", "😍", "🎉", "🔥", "💡", "✅", "❤️",
  "😅", "🤔", "😮", "🙏", "👏", "💪", "⭐", "📚",
  "✏️", "🧠", "🎯", "🏆", "⚽", "🎮", "🍕", "🌈",
];

/**
 * The emoji strip above the composer.
 *
 * Deliberately NOT the OS keyboard: in a Telegram Mini App the system emoji
 * panel covers the whole screen and takes a pupil's text with it. A small in-app
 * strip inserts at the caret and keeps the message typed.
 */
export function EmojiStrip({ onPick }: { onPick: (emoji: string) => void }) {
  return (
    <div className="no-scrollbar -mx-1 flex gap-1 overflow-x-auto px-1 pb-1.5">
      {CHAT_EMOJI.map((emoji) => (
        <button
          key={emoji}
          type="button"
          onClick={() => onPick(emoji)}
          className="shrink-0 rounded-lg px-1.5 py-1 text-lg leading-none hover:bg-slate-100 active:scale-95 cursor-pointer"
          aria-label={`${emoji} qo‘shish`}
        >
          {emoji}
        </button>
      ))}
    </div>
  );
}

/** The three icons a room kind deserves (group chats carry their own emoji). */
export function kindLabel(kind: string): string {
  if (kind === "news") return "📣 E'lonxona";
  if (kind === "staff") return "🧑‍🏫 O‘qituvchilar";
  if (kind === "grade") return "🎓 Sinf";
  return "💬 Guruh";
}

/** 2.4 MB → "2.4 MB"; 480 KB → "480 KB" (the size a video bubble is labelled with). */
export function fileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

/**
 * A picture, GIF or video inside a bubble.
 *
 * The URL is a capability link (…/media/{slug}) that needs no token, so an
 * ordinary <img>/<video> tag can load it. `preload="metadata"` matters on a
 * school phone with a small data plan: a video downloads nothing until the
 * pupil presses play.
 */
export function MediaBubble({
  media,
  onOpen,
}: {
  media: ChatMedia;
  onOpen: (media: ChatMedia) => void;
}) {
  const url = api.publicUrl(media.url);
  if (!url) return null;

  if (media.kind === "video") {
    return (
      <video
        src={url}
        controls
        playsInline
        preload="metadata"
        className="mt-1.5 max-h-[46vh] w-full rounded-xl bg-black"
      />
    );
  }

  return (
    <figure
      className="relative mt-1.5 overflow-hidden rounded-xl border border-black/10"
      onClick={() => onOpen(media)}
      role="button"
      tabIndex={0}
      aria-label={
        media.kind === "gif" ? "GIFni kattalashtirish" : "Rasmni kattalashtirish"
      }
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          onOpen(media);
        }
      }}
      title="Rasmni kattalashtirish"
    >
      <img
        src={url}
        alt=""
        loading="lazy"
        className="max-h-[42vh] w-full cursor-zoom-in object-cover active:opacity-90"
      />
      {media.kind === "gif" && (
        <figcaption className="pointer-events-none absolute left-1.5 top-1.5 rounded-md bg-black/60 px-1.5 py-0.5 text-[10px] font-black uppercase tracking-wide text-white">
          GIF
        </figcaption>
      )}
    </figure>
  );
}

/**
 * Full-screen picture (a GIF included — it is still an <img>, so it animates).
 * Closing on Escape and on a tap anywhere is what makes it feel like a photo
 * viewer rather than a broken page.
 */
export function Lightbox({
  media,
  onClose,
}: {
  media: ChatMedia | null;
  onClose: () => void;
}) {
  useEffect(() => {
    if (!media) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [media, onClose]);

  if (!media) return null;
  const url = api.publicUrl(media.url);
  // Same reason as Sheet: portalled to <body>, or the page's leftover transform
  // would keep this "full screen" inside the page box and under the tab bar.
  return createPortal(
    <div
      className="fixed inset-0 z-[60] flex flex-col items-center justify-center bg-black/85 p-3 animate-fade-in"
      onClick={onClose}
      role="dialog"
      aria-modal="true"
      aria-label="Rasm"
    >
      <img
        src={url}
        alt=""
        className="max-h-[86dvh] w-auto max-w-full rounded-2xl object-contain"
        onClick={(e) => e.stopPropagation()}
      />
      <button
        type="button"
        onClick={onClose}
        aria-label="Yopish"
        className="mt-3 flex h-10 w-10 items-center justify-center rounded-full bg-white/15 text-white hover:bg-white/25 cursor-pointer"
      >
        <IconClose size={18} />
      </button>
    </div>,
    document.body,
  );
}

/**
 * A file the pupil picked but has not sent yet: a thumbnail (or a name for a
 * video) plus a cancel button. It lives in object-URL land, so the URL is
 * revoked on unmount — otherwise every picked photo leaks memory until reload.
 */
export function StagedFile({
  file,
  onDrop,
}: {
  file: File;
  onDrop: () => void;
}) {
  const [preview, setPreview] = useState<string | null>(null);

  useEffect(() => {
    const isPicture = file.type.startsWith("image/");
    const url = isPicture ? URL.createObjectURL(file) : null;
    setPreview(url);
    return () => {
      if (url) URL.revokeObjectURL(url);
    };
  }, [file]);

  const isVideo = file.type.startsWith("video/");

  return (
    <div className="mb-2 flex items-center gap-2 rounded-xl border border-blue-200 bg-blue-50/70 p-1.5">
      {preview ? (
        <img src={preview} alt="" className="h-12 w-12 rounded-lg object-cover" />
      ) : (
        <span className="flex h-12 w-12 items-center justify-center rounded-lg bg-slate-800 text-lg">
          {isVideo ? "🎬" : "🖼"}
        </span>
      )}
      <div className="min-w-0 flex-1">
        <p className="truncate text-[11px] font-bold text-slate-800">
          {file.name || (isVideo ? "video" : "rasm")}
        </p>
        <p className="text-[10px] font-semibold text-slate-500">
          {fileSize(file.size)} · yuborilganda kichraytiriladi
        </p>
      </div>
      <button
        type="button"
        onClick={onDrop}
        aria-label="Faylni olish"
        className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-white text-slate-500 hover:text-rose-600 cursor-pointer"
      >
        <IconClose size={15} />
      </button>
    </div>
  );
}
