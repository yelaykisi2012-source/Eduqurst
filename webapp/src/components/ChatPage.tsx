import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { api, ApiError } from "../api";
import type {
  ChatFeed,
  ChatMedia,
  ChatMember,
  ChatMessage,
  ChatPendingQueue,
  ChatRoom,
  ChatSendResult,
} from "../types";
import Card from "./ui/Card";
import Button from "./ui/Button";
import Badge from "./ui/Badge";
import EmptyState from "./ui/EmptyState";
import {
  IconChat,
  IconEdit,
  IconPaperclip,
  IconPlus,
  IconRefresh,
  IconSend,
  IconTrash,
  IconUsers,
  IconCheck,
} from "./ui/Icons";
import {
  AvatarDot,
  EmojiStrip,
  Lightbox,
  MediaBubble,
  RoomBadge,
  StagedFile,
  fileSize,
  kindLabel,
  stamp,
} from "./chat/ChatBits";
import { PeopleSheet, RoomFormSheet } from "./chat/RoomSheets";

interface ChatPageProps {
  token: string;
  /** An admin gets the moderation queue and the delete button on every message. */
  isAdmin: boolean;
  /** The pupil's own grade room opens by default; without it the app nudges onboarding. */
  gradeName: string | null;
  notify: (msg: string) => void;
  onChangeGrade: () => void;
}

/** How often the Mini App asks the server "anything newer than what I show?". */
const POLL_MS = 7000;

/** A feed longer than this is trimmed from the top (nobody scrolls 500 back). */
const KEEP_MESSAGES = 200;

/**
 * The section order the school asked for: the admin's e'lonxona first, then the
 * teachers, then the pupils' own class, then whatever chats pupils opened.
 * app/chat.py already returns rooms in this order — sorting again here is what
 * keeps the layout honest if the server ever returns them differently.
 */
const SECTION_ORDER = ["news", "staff", "grade", "group"];

/** What the browser may claim for a chat file (the server re-checks the bytes). */
const PICKER_ACCEPT = "image/jpeg,image/png,image/webp,image/gif,video/*";

/** Same caps as Settings.CHAT_IMAGE_MAX_BYTES / CHAT_VIDEO_MAX_BYTES. */
const MAX_IMAGE_BYTES = 2 * 1024 * 1024;
const MAX_VIDEO_BYTES = 10 * 1024 * 1024;

/**
 * Merge a poll delta into what is already rendered.
 *
 * Deduping by id (instead of trusting the order of two async sources) is what
 * keeps the feed correct when our own just-sent message and a poll response
 * arrive at the same moment.
 */
function mergeById(current: ChatMessage[], incoming: ChatMessage[]): ChatMessage[] {
  if (incoming.length === 0) return current;
  const byId = new Map<number, ChatMessage>();
  for (const msg of current) byId.set(msg.id, msg);
  for (const msg of incoming) byId.set(msg.id, msg);
  return [...byId.values()].sort((a, b) => a.id - b.id).slice(-KEEP_MESSAGES);
}

/** Rooms in section order, group chats newest-first inside their own section. */
function groupRooms(rooms: ChatRoom[]): ChatRoom[] {
  return [...rooms].sort((a, b) => {
    const byKind = SECTION_ORDER.indexOf(a.kind) - SECTION_ORDER.indexOf(b.kind);
    if (byKind !== 0) return byKind;
    return (b.latest_id ?? 0) - (a.latest_id ?? 0) || b.id - a.id;
  });
}

// ---------------------------------------------------------------------------
// Admin moderation queue
// ---------------------------------------------------------------------------

function ModerationQueue({
  queue,
  busyId,
  onApprove,
  onReject,
  onDelete,
  onRefresh,
  onOpenMedia,
}: {
  queue: ChatPendingQueue | null;
  busyId: number | null;
  onApprove: (id: number) => void;
  onReject: (id: number, reason: string) => void;
  onDelete: (id: number) => void;
  onRefresh: () => void;
  onOpenMedia: (media: ChatMedia) => void;
}) {
  // Which message is currently being refused, and the reason typed for it.
  const [refusing, setRefusing] = useState<number | null>(null);
  const [reason, setReason] = useState("");

  // A queue entry can disappear under our fingers (another admin acted) — reset.
  useEffect(() => {
    if (refusing !== null && !(queue?.items ?? []).some((item) => item.id === refusing)) {
      setRefusing(null);
      setReason("");
    }
  }, [queue, refusing]);

  const submitRefusal = (id: number) => {
    onReject(id, reason.trim());
    setRefusing(null);
    setReason("");
  };

  return (
    <Card className="mb-3 sm:mb-4 p-3 sm:p-4 border-purple-200/80 bg-purple-50/40">
      <div className="flex items-center justify-between gap-2">
        <div className="min-w-0">
          <h2 className="text-xs sm:text-sm font-black text-slate-900">
            🛡️ Tasdiq navbati
          </h2>
          <p className="text-[10px] sm:text-[11px] font-semibold text-slate-500 mt-0.5">
            {queue === null
              ? "Yuklanmoqda…"
              : queue.premoderation
                ? "Bu rejimda har bir xabar avval tekshiriladi."
                : "Filtsiz rejim: xabarlar darhol chiqadi — keraksizini o‘chiring."}
          </p>
        </div>
        <div className="flex items-center gap-1.5 shrink-0">
          {queue && queue.count > 0 && (
            <Badge variant="purple" size="sm">
              {queue.count} ta kutilmoqda
            </Badge>
          )}
          <button
            onClick={onRefresh}
            title="Qayta yangilash"
            className="flex h-8 w-8 items-center justify-center rounded-xl bg-white text-slate-500 border border-slate-200 hover:text-purple-600 cursor-pointer"
          >
            <IconRefresh size={15} />
          </button>
        </div>
      </div>

      {queue !== null && queue.items.length === 0 && (
        <p className="mt-2 text-[11px] font-semibold text-slate-500">
          Navbat bo‘sh. Xabar yuborilganda shu yerda ko‘rinadi.
        </p>
      )}

      {queue !== null && queue.items.length > 0 && (
        <ul className="mt-2 space-y-2">
          {queue.items.map((item) => (
            <li
              key={item.id}
              className="rounded-xl bg-white border border-slate-200/80 p-2.5"
            >
              <div className="flex items-center gap-2">
                <AvatarDot name={item.author_name} avatarUrl={item.avatar_url} size={26} />
                <div className="min-w-0 flex-1">
                  <p className="text-[11px] sm:text-xs font-bold text-slate-800 truncate">
                    {item.author_name}
                    <span className="ml-1 font-semibold text-slate-400">
                      · {kindLabel(item.kind)}
                    </span>
                  </p>
                  <p className="text-[10px] font-semibold text-slate-400">
                    {stamp(item.created_at)}
                  </p>
                </div>
              </div>

              {item.text && (
                <p className="mt-1.5 text-[11px] sm:text-xs font-medium text-slate-700 whitespace-pre-wrap break-words">
                  {item.text}
                </p>
              )}

              {/* A queued picture must be judged as a picture, not as text: this
                  is the only place an adult sees it before pupils do. */}
              {item.media && (
                <div className="mt-1.5 max-w-[220px]">
                  <MediaBubble media={item.media} onOpen={onOpenMedia} />
                </div>
              )}

              {refusing === item.id ? (
                <div className="mt-2 space-y-1.5">
                  <input
                    value={reason}
                    onChange={(e) => setReason(e.target.value)}
                    maxLength={160}
                    placeholder="Qisqa sabab (muallif ko‘radi)"
                    className="w-full rounded-xl border border-rose-200 bg-rose-50/50 px-2.5 py-1.5 text-[11px] font-semibold text-slate-800 outline-none focus:border-rose-400"
                  />
                  <div className="flex items-center gap-1.5">
                    <Button
                      variant="danger"
                      size="sm"
                      disabled={reason.trim().length === 0 || busyId === item.id}
                      onClick={() => submitRefusal(item.id)}
                    >
                      Sababni yuborish
                    </Button>
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => {
                        setRefusing(null);
                        setReason("");
                      }}
                    >
                      Bekor
                    </Button>
                  </div>
                </div>
              ) : (
                <div className="mt-2 flex items-center gap-1.5 flex-wrap">
                  <Button
                    variant="success"
                    size="sm"
                    loading={busyId === item.id}
                    icon={busyId === item.id ? undefined : <IconCheck size={13} />}
                    onClick={() => onApprove(item.id)}
                  >
                    Tasdiqlash
                  </Button>
                  <Button
                    variant="secondary"
                    size="sm"
                    onClick={() => {
                      setRefusing(item.id);
                      setReason("");
                    }}
                  >
                    Rad etish
                  </Button>
                  <Button
                    variant="ghost"
                    size="sm"
                    className="text-rose-600 hover:bg-rose-50"
                    icon={<IconTrash size={13} />}
                    onClick={() => onDelete(item.id)}
                  >
                    O‘chirish
                  </Button>
                </div>
              )}
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}

// ---------------------------------------------------------------------------
// The page
// ---------------------------------------------------------------------------

export default function ChatPage({
  token,
  isAdmin,
  gradeName,
  notify,
  onChangeGrade,
}: ChatPageProps) {
  const [rooms, setRooms] = useState<ChatRoom[] | null>(null);
  const [roomsError, setRoomsError] = useState("");
  const [roomsRetry, setRoomsRetry] = useState(0);
  const [activeId, setActiveId] = useState<number | null>(null);

  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [latestId, setLatestId] = useState<number | null>(null);
  const [feedError, setFeedError] = useState("");
  const [needGrade, setNeedGrade] = useState(false);
  const [firstLoad, setFirstLoad] = useState(true);

  const [draft, setDraft] = useState("");
  const [staged, setStaged] = useState<File | null>(null);
  const [sending, setSending] = useState(false);
  const [sendError, setSendError] = useState("");
  const [showEmoji, setShowEmoji] = useState(false);

  const [queue, setQueue] = useState<ChatPendingQueue | null>(null);
  const [busyId, setBusyId] = useState<number | null>(null);

  // Sheets: "+" (create), the gear on the active room (edit), the people panel.
  const [createOpen, setCreateOpen] = useState(false);
  const [editRoom, setEditRoom] = useState<ChatRoom | null>(null);
  const [peopleFor, setPeopleFor] = useState<ChatRoom | null>(null);
  const [lightbox, setLightbox] = useState<ChatMedia | null>(null);

  // Newest id the pupil has actually seen per room — drives the unread dot.
  const [seen, setSeen] = useState<Record<number, number>>({});

  // The poller reads the room + cursor from refs, so a room switch never leaves a
  // timer polling the previous room with a stale cursor.
  const latestRef = useRef<number | null>(null);
  const roomRef = useRef<number | null>(null);
  const feedBox = useRef<HTMLDivElement | null>(null);
  const roomStrip = useRef<HTMLDivElement | null>(null);
  const fileInput = useRef<HTMLInputElement | null>(null);

  const ordered = useMemo(() => (rooms ? groupRooms(rooms) : null), [rooms]);
  const activeRoom = useMemo(
    () => (rooms ?? []).find((r) => r.id === activeId) ?? null,
    [activeId, rooms],
  );

  // Who may change this room: the pupil who opened it, or an adult.
  const canManageRoom = !!activeRoom && (activeRoom.is_mine || isAdmin);

  // A group chat counts its members; a class/e'lonxona does not (member_count 0).
  const memberCount = (activeRoom?.member_count ?? 0) > 0 ? activeRoom?.member_count : null;

  // ---------------------------------------------------------------- rooms
  /**
   * Refresh the room list, keeping the open chat.
   *
   * `keep` is the id the pupil is looking at: after a create/rename we pass the
   * saved room so the app lands on it, otherwise the current one is preserved.
   */
  const loadRooms = useCallback(
    async (keep?: number | null) => {
      try {
        const list = await api.chatRooms(token);
        setRooms(list);
        setRoomsError("");
        setActiveId((current) => {
          const wanted = keep ?? current;
          if (wanted != null && list.some((r) => r.id === wanted)) return wanted;
          // Prefer the pupil's own class; the e'lonxona is the fallback reading room.
          const mine =
            list.find((r) => r.is_current_grade) ??
            list.find((r) => r.kind === "grade") ??
            list[0] ??
            null;
          return mine?.id ?? null;
        });
      } catch (e) {
        setRoomsError(
          e instanceof ApiError
            ? e.message
            : "Xonalarni yuklab bo‘lmadi. Internetni tekshiring.",
        );
      }
    },
    [token],
  );

  useEffect(() => {
    let alive = true;
    setRooms(null);
    setRoomsError("");
    api
      .chatRooms(token)
      .then((list) => {
        if (!alive) return;
        setRooms(list);
        // Prefer the pupil's own class; the e'lonxona is the fallback reading room.
        const mine =
          list.find((r) => r.is_current_grade) ??
          list.find((r) => r.kind === "grade") ??
          list[0] ??
          null;
        if (mine) setActiveId(mine.id);
      })
      .catch((e: unknown) => {
        if (!alive) return;
        setRoomsError(
          e instanceof ApiError
            ? e.message
            : "Xonalarni yuklab bo‘lmadi. Internetni tekshiring.",
        );
      });
    return () => {
      alive = false;
    };
  }, [token, roomsRetry]);

  // ------------------------------------------------------------- feed load
  const openRoom = useCallback(
    async (roomId: number) => {
      setFirstLoad(true);
      setFeedError("");
      setNeedGrade(false);
      try {
        const feed: ChatFeed = await api.chatMessages(token, roomId);
        if (roomRef.current !== roomId) return;
        setMessages(feed.messages);
        latestRef.current = feed.latest_id;
        setLatestId(feed.latest_id);
        if (feed.latest_id != null) {
          setSeen((prev) => ({ ...prev, [roomId]: feed.latest_id as number }));
        }
      } catch (e) {
        if (roomRef.current !== roomId) return;
        setMessages([]);
        if (e instanceof ApiError && e.code === "grade_not_selected") setNeedGrade(true);
        else setFeedError(e instanceof ApiError ? e.message : "Xabalarni yuklab bo‘lmadi.");
      } finally {
        if (roomRef.current === roomId) setFirstLoad(false);
      }
    },
    [token],
  );

  useEffect(() => {
    roomRef.current = activeId;
    latestRef.current = null;
    setMessages([]);
    setLatestId(null);
    setSendError("");
    setStaged(null);
    setDraft("");
    if (activeId != null) void openRoom(activeId);
    else setFirstLoad(false);
  }, [activeId, openRoom]);

  // Jump to the newest message when a room opens.
  useEffect(() => {
    if (firstLoad || messages.length === 0) return;
    const box = feedBox.current;
    if (box) box.scrollTop = box.scrollHeight;
    // Only on the first render of a freshly opened room.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [firstLoad]);

  // ------------------------------------------------------------- polling
  useEffect(() => {
    if (activeId === null || firstLoad) return;
    let alive = true;

    const tick = async () => {
      // A hidden Mini App should not spend the pupil's data — wait for a focus.
      if (document.hidden || roomRef.current === null) return;
      const roomId = roomRef.current;
      try {
        const feed = await api.chatMessages(token, roomId, latestRef.current ?? undefined);
        if (!alive || roomRef.current !== roomId) return;
        if (feed.messages.length > 0) {
          const box = feedBox.current;
          const nearBottom =
            !box || box.scrollHeight - box.scrollTop - box.clientHeight < 140;
          setMessages((prev) => mergeById(prev, feed.messages));
          if (nearBottom && box)
            window.requestAnimationFrame(() => {
              box.scrollTop = box.scrollHeight;
            });
        }
        if (feed.latest_id != null && feed.latest_id > (latestRef.current ?? 0)) {
          latestRef.current = feed.latest_id;
          setLatestId(feed.latest_id);
          setSeen((prev) => ({ ...prev, [roomId]: feed.latest_id as number }));
        }
        setFeedError("");
      } catch {
        /* a dropped poll is retried on the next tick — never shown as an error */
      }
    };

    const timer = window.setInterval(() => void tick(), POLL_MS);
    const onFocus = () => void tick();
    window.addEventListener("focus", onFocus);
    document.addEventListener("visibilitychange", onFocus);
    return () => {
      alive = false;
      window.clearInterval(timer);
      window.removeEventListener("focus", onFocus);
      document.removeEventListener("visibilitychange", onFocus);
    };
  }, [activeId, firstLoad, token]);

  // The room list itself is refreshed occasionally, so a chat somebody else
  // opened shows up without the pupil reloading the page.
  useEffect(() => {
    if (rooms === null) return;
    const timer = window.setInterval(() => {
      if (!document.hidden) void loadRooms(activeId);
    }, POLL_MS * 9);
    return () => window.clearInterval(timer);
  }, [activeId, loadRooms, rooms === null]); // eslint-disable-line react-hooks/exhaustive-deps

  // ------------------------------------------------------- admin queue
  const refreshQueue = useCallback(async () => {
    if (!isAdmin) return;
    try {
      setQueue(await api.chatPending(token));
    } catch {
      /* the badge is not worth an error screen — it retries with the poll */
    }
  }, [isAdmin, token]);

  useEffect(() => {
    if (!isAdmin) {
      setQueue(null);
      return;
    }
    void refreshQueue();
    const timer = window.setInterval(() => void refreshQueue(), POLL_MS);
    return () => window.clearInterval(timer);
  }, [isAdmin, refreshQueue]);

  const decide = useCallback(
    async (id: number, action: "approve" | "reject" | "delete", reason?: string) => {
      setBusyId(id);
      try {
        if (action === "approve") await api.chatApprove(token, id);
        else if (action === "reject") await api.chatReject(token, id, reason ?? "");
        else await api.chatDelete(token, id);
        notify(
          action === "approve"
            ? "Xabar tasdiqlandi ✅"
            : action === "reject"
              ? "Rad qilindi — muallif sababini ko‘radi."
              : "Xabar o‘chirildi 🗑️",
        );
        // The room the message lives in may be the one on screen — refetch the delta.
        await refreshQueue();
        const room = roomRef.current;
        if (room !== null) void openRoom(room);
      } catch (e) {
        notify(e instanceof ApiError ? e.message : "Amalni bajarsa bo‘lmadi.");
      } finally {
        setBusyId(null);
      }
    },
    [notify, openRoom, refreshQueue, token],
  );

  // ------------------------------------------------------------- sending

  /** A pick that cannot pass the server's check is stopped here, in Uzbek. */
  const pickFile = (file: File | null) => {
    if (!file) return;
    const isVideo = file.type.startsWith("video/");
    const cap = isVideo ? MAX_VIDEO_BYTES : MAX_IMAGE_BYTES;
    if (file.size > cap) {
      setSendError(
        `${isVideo ? "Video" : "Rasm"} juda katta (${fileSize(file.size)}). ` +
          `Kamida ${fileSize(cap)} kichikroq fayl tanlang.`,
      );
      return;
    }
    if (!file.type.startsWith("image/") && !isVideo) {
      setSendError("Faqat rasm, GIF yoki video yuborish mumkin.");
      return;
    }
    setStaged(file);
    setSendError("");
  };

  const send = async () => {
    if (!activeRoom || sending) return;
    const text = draft.trim();
    if (text.length === 0 && !staged) return;
    setSending(true);
    setSendError("");
    try {
      const result: ChatSendResult = staged
        ? await api.chatAttach(token, activeRoom.id, staged, text)
        : await api.chatSend(token, { text, roomId: activeRoom.id });
      // Append right away (the pupil must see their own message immediately),
      // then move the cursor past it — dedupe by id protects the next poll.
      setMessages((prev) => mergeById(prev, [result.message]));
      if (result.message.id > (latestRef.current ?? 0)) {
        latestRef.current = result.message.id;
        setLatestId(result.message.id);
        setSeen((prev) => ({ ...prev, [activeRoom.id]: result.message.id }));
      }
      setDraft("");
      setStaged(null);
      setShowEmoji(false);
      notify(result.message_uz);
      const box = feedBox.current;
      if (box)
        window.requestAnimationFrame(() => {
          box.scrollTop = box.scrollHeight;
        });
      if (isAdmin) void refreshQueue();
      // A brand-new chat only exists in the list after the server says so.
      void loadRooms(activeRoom.id);
    } catch (e) {
      // Keep the draft AND the file: a refused upload should never be picked twice.
      setSendError(
        e instanceof ApiError ? e.message : "Yuborib bo‘lmadi. Aloqani tekshiring.",
      );
    } finally {
      setSending(false);
    }
  };

  /** A sheet saved a room: merge it into the list and open it. */
  const roomSaved = (saved: ChatRoom, created: boolean) => {
    setRooms((prev) => {
      const list = prev ?? [];
      const without = list.filter((r) => r.id !== saved.id);
      return [...without, saved];
    });
    setActiveId(saved.id);
    setSeen((prev) => ({ ...prev, [saved.id]: saved.latest_id ?? 0 }));
    notify(created ? `«${saved.name}» ochildi ✅` : "Saqlandi ✅");
    if (created) void loadRooms(saved.id);
  };

  const onMembersChanged = (list: ChatMember[]) => {
    if (!peopleFor) return;
    setRooms((prev) =>
      (prev ?? []).map((r) => (r.id === peopleFor.id ? { ...r, member_count: list.length } : r)),
    );
  };

  const canPost = activeRoom?.can_post ?? false;
  const canRead = activeRoom?.can_read ?? true;

  return (
    <div className="mx-auto max-w-2xl animate-fade-in py-1 pb-32 sm:pb-12">
      {isAdmin && (
        <ModerationQueue
          queue={queue}
          busyId={busyId}
          onApprove={(id) => void decide(id, "approve")}
          onReject={(id, reason) => void decide(id, "reject", reason)}
          onDelete={(id) => void decide(id, "delete")}
          onRefresh={() => void refreshQueue()}
          onOpenMedia={(media) => setLightbox(media)}
        />
      )}

      {roomsError ? (
        <Card className="p-4 border-rose-200 bg-rose-50/50 text-center">
          <p className="text-xs font-bold text-rose-700">{roomsError}</p>
          <Button
            variant="secondary"
            size="sm"
            className="mt-3"
            icon={<IconRefresh size={14} />}
            onClick={() => setRoomsRetry((v) => v + 1)}
          >
            Qayta urinish
          </Button>
        </Card>
      ) : ordered === null ? (
        <div className="py-10 text-center">
          <div className="inline-block h-8 w-8 animate-spin rounded-full border-4 border-blue-500 border-t-transparent" />
          <p className="mt-3 text-sm font-semibold text-slate-500">
            Chat xonalari ochilmoqda…
          </p>
        </div>
      ) : (
        <>
          {/* ------------------------------------------------- rooms strip */}
          <div
            ref={roomStrip}
            className="no-scrollbar -mx-0.5 flex items-center gap-1.5 overflow-x-auto px-0.5 pb-2"
          >
            {ordered.map((room) => {
              const on = room.id === activeId;
              const unread = (room.latest_id ?? 0) > (seen[room.id] ?? 0) && !on;
              return (
                <button
                  key={room.id}
                  data-active={on ? "true" : undefined}
                  onClick={() => setActiveId(room.id)}
                  className={`shrink-0 snap-start inline-flex items-center gap-1.5 rounded-xl px-3 py-1.5 text-[11px] sm:text-xs font-bold border transition-colors cursor-pointer whitespace-nowrap ${
                    on
                      ? "bg-blue-600 text-white border-blue-600 shadow-xs"
                      : "bg-white text-slate-700 border-slate-200 hover:border-blue-300"
                  }`}
                >
                  {room.avatar_url ? (
                    <img
                      src={api.publicUrl(room.avatar_url)}
                      alt=""
                      className="h-4 w-4 rounded-full object-cover"
                    />
                  ) : (
                    <span aria-hidden>{room.emoji}</span>
                  )}
                  <span>{room.name}</span>
                  {room.is_current_grade && !on && (
                    <span className={`text-[10px] font-black ${on ? "text-blue-100" : "text-blue-600"}`}>
                      · siz
                    </span>
                  )}
                  {unread && <span className="h-1.5 w-1.5 rounded-full bg-rose-500" aria-hidden />}
                </button>
              );
            })}
            {/* The "+" button: any pupil may open a chat — the school chose that. */}
            <button
              onClick={() => setCreateOpen(true)}
              className="shrink-0 inline-flex items-center gap-1.5 rounded-xl border border-dashed border-blue-300 bg-blue-50/70 px-3 py-1.5 text-[11px] sm:text-xs font-black text-blue-700 hover:bg-blue-100 cursor-pointer whitespace-nowrap"
            >
              <IconPlus size={14} />
              Chat ochish
            </button>
          </div>

          {/* ------------------------------------------------- room header */}
          {activeRoom && (
            <Card
              variant="elevated"
              padding="none"
              className="mb-2.5 p-3 sm:p-4 bg-gradient-to-r from-[#3478F6] via-blue-600 to-indigo-700 text-white border-0"
            >
              <div className="flex items-start gap-2.5">
                <RoomBadge room={activeRoom} size={44} />
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-1.5">
                    <h1 className="text-sm sm:text-lg font-black leading-tight truncate">
                      {activeRoom.name}
                    </h1>
                    {activeRoom.is_closed && (
                      <span className="shrink-0 rounded-md bg-white/20 px-1.5 py-0.5 text-[10px] font-black uppercase">
                        yopiq
                      </span>
                    )}
                  </div>
                  <p className="text-[10px] sm:text-[11px] font-semibold text-blue-100 truncate">
                    {activeRoom.bio ??
                      (activeRoom.kind === "group"
                        ? `${kindLabel(activeRoom.kind)} · ${activeRoom.owner_name ?? "o‘quvchi"} ochgan`
                        : gradeName
                          ? `${gradeName} va butun maktab`
                          : "Sinfingiz va e'lonxona")}
                  </p>
                </div>
                <div className="flex shrink-0 items-center gap-1.5">
                  <button
                    onClick={() => setPeopleFor(activeRoom)}
                    title="Odamlar"
                    aria-label="Chatdagi odamlar"
                    className="flex h-9 items-center gap-1 rounded-xl bg-white/15 px-2 text-[10px] font-black hover:bg-white/25 cursor-pointer"
                  >
                    <IconUsers size={15} />
                    {memberCount !== null && <span>{memberCount}</span>}
                  </button>
                  {canManageRoom && (
                    <button
                      onClick={() => setEditRoom(activeRoom)}
                      title="Chatni sozlash"
                      aria-label="Chatni sozlash"
                      className="flex h-9 w-9 items-center justify-center rounded-xl bg-white/15 hover:bg-white/25 cursor-pointer"
                    >
                      <IconEdit size={15} />
                    </button>
                  )}
                </div>
              </div>
            </Card>
          )}

          {/* ---------------------------------------------------- the feed */}
          <Card className="mt-2 p-0 overflow-hidden">
            <div
              ref={feedBox}
              className="max-h-[52dvh] min-h-[220px] overflow-y-auto px-2.5 py-3 sm:px-4 bg-slate-50/60"
            >
              {needGrade ? (
                <div className="py-8 text-center">
                  <span className="text-3xl block mb-1.5">🎓</span>
                  <p className="text-xs sm:text-sm font-bold text-slate-700">
                    Chatni ochish uchun avval sinfini tanlang
                  </p>
                  <Button
                    variant="primary"
                    size="sm"
                    className="mt-3"
                    onClick={onChangeGrade}
                  >
                    Sinfni tanlash
                  </Button>
                </div>
              ) : !canRead ? (
                <div className="py-8 text-center">
                  <span className="text-3xl block mb-1.5">🔒</span>
                  <p className="text-xs sm:text-sm font-bold text-slate-700">
                    Bu xona yopiq
                  </p>
                  <p className="mt-1 text-[11px] font-semibold text-slate-500">
                    Faqat o‘qituvchilar va administrator yozadi.
                  </p>
                </div>
              ) : firstLoad ? (
                <div className="py-10 text-center">
                  <div className="inline-block h-7 w-7 animate-spin rounded-full border-4 border-slate-300 border-t-transparent" />
                  <p className="mt-2.5 text-[11px] font-semibold text-slate-400">
                    Xabarlar yuklanmoqda…
                  </p>
                </div>
              ) : feedError ? (
                <div className="py-8 text-center">
                  <p className="text-xs font-bold text-rose-600">{feedError}</p>
                  {activeId !== null && (
                    <Button
                      variant="secondary"
                      size="sm"
                      className="mt-3"
                      icon={<IconRefresh size={14} />}
                      onClick={() => void openRoom(activeId)}
                    >
                      Qayta urinish
                    </Button>
                  )}
                </div>
              ) : messages.length === 0 ? (
                <EmptyState
                  icon={<IconChat size={26} />}
                  title={
                    activeRoom?.kind === "news" ? "E'lonxona hozircha bo‘sh" : "Hali xabar yo‘q"
                  }
                  description={
                    canPost
                      ? "Birinchi xabarni shu yozish oynasidan yuboring — rasm, GIF yoki video ham bo‘ladi."
                      : "Bu yerga faqat o‘qituvchi yozadi — siz esa o‘qib borishingiz mumkin."
                  }
                />
              ) : (
                <ul className="space-y-2">
                  {messages.map((msg) => (
                    <li
                      key={msg.id}
                      className={`flex items-end gap-1.5 ${
                        msg.is_me ? "flex-row-reverse" : ""
                      }`}
                    >
                      <AvatarDot name={msg.author_name} avatarUrl={msg.avatar_url} size={28} />
                      <div
                        className={`max-w-[82%] min-w-0 rounded-2xl px-3 py-2 shadow-2xs border ${
                          msg.is_me
                            ? "bg-blue-600 border-blue-600 text-white rounded-br-md"
                            : msg.status === "rejected"
                              ? "bg-rose-50 border-rose-200 text-rose-900 rounded-bl-md"
                              : msg.status === "pending"
                                ? "bg-amber-50 border-amber-200 text-amber-950 rounded-bl-md"
                                : "bg-white border-slate-200/80 text-slate-800 rounded-bl-md"
                        }`}
                      >
                        {!msg.is_me && (
                          <p className="text-[10px] font-black text-slate-500 mb-0.5 truncate">
                            {msg.author_name}
                            {msg.kind === "news" && (
                              <span className="ml-1 font-bold text-indigo-500">· e'lon</span>
                            )}
                          </p>
                        )}
                        {msg.media && (
                          <MediaBubble media={msg.media} onOpen={(m) => setLightbox(m)} />
                        )}
                        {msg.text && (
                          <p className="text-[12px] sm:text-[13px] font-medium leading-snug whitespace-pre-wrap break-words">
                            {msg.text}
                          </p>
                        )}
                        <div className="mt-1 flex items-center gap-1.5 justify-end">
                          <span
                            className={`text-[10px] font-bold ${
                              msg.is_me ? "text-blue-200" : "text-slate-400"
                            }`}
                          >
                            {stamp(msg.created_at)}
                          </span>
                          {msg.status === "pending" && (
                            <span className="text-[10px] font-black text-amber-600">
                              ⏳ tekshiruvda
                            </span>
                          )}
                          {msg.status === "rejected" && (
                            <span className="text-[10px] font-black text-rose-600">
                              ⛔ rad etildi
                            </span>
                          )}
                          {isAdmin && (
                            <button
                              onClick={() => void decide(msg.id, "delete")}
                              title="Bu xabarni o‘chirish"
                              className="ml-0.5 flex h-5 w-5 items-center justify-center rounded-md text-slate-400 hover:bg-rose-50 hover:text-rose-600 cursor-pointer"
                            >
                              <IconTrash size={12} />
                            </button>
                          )}
                        </div>
                        {msg.status === "rejected" && msg.reject_reason && (
                          <p className="mt-1 border-t border-rose-200/70 pt-1 text-[10px] font-bold text-rose-700">
                            Sabab: {msg.reject_reason}
                          </p>
                        )}
                      </div>
                    </li>
                  ))}
                </ul>
              )}
            </div>

            {/* ------------------------------------------------- composer */}
            <div className="border-t border-slate-200/80 bg-white px-2.5 py-2 sm:px-4 sm:py-3">
              {canPost ? (
                <>
                  {staged && <StagedFile file={staged} onDrop={() => setStaged(null)} />}
                  {showEmoji && (
                    <EmojiStrip
                      onPick={(emoji) => setDraft((prev) => (prev + emoji).slice(0, 500))}
                    />
                  )}
                  <div className="flex items-end gap-1.5">
                    <input
                      ref={fileInput}
                      type="file"
                      accept={PICKER_ACCEPT}
                      className="hidden"
                      onChange={(e) => {
                        pickFile(e.target.files?.[0] ?? null);
                        e.target.value = "";
                      }}
                    />
                    <button
                      onClick={() => fileInput.current?.click()}
                      title="Rasm, GIF yoki video biriktirish"
                      aria-label="Fayl biriktirish"
                      className="flex h-10 w-10 shrink-0 items-center justify-center rounded-2xl border border-slate-200 bg-slate-50 text-slate-500 hover:border-blue-300 hover:text-blue-600 cursor-pointer"
                    >
                      <IconPaperclip size={17} />
                    </button>
                    <button
                      onClick={() => setShowEmoji((v) => !v)}
                      title="Emoji"
                      aria-label="Emoji tanlash"
                      className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-2xl border text-lg cursor-pointer ${
                        showEmoji
                          ? "border-blue-400 bg-blue-50"
                          : "border-slate-200 bg-slate-50 hover:border-blue-300"
                      }`}
                    >
                      🙂
                    </button>
                    <textarea
                      value={draft}
                      onChange={(e) => {
                        setDraft(e.target.value);
                        if (sendError) setSendError("");
                      }}
                      onKeyDown={(e) => {
                        if (e.key === "Enter" && !e.shiftKey) {
                          e.preventDefault();
                          void send();
                        }
                      }}
                      rows={1}
                      maxLength={500}
                      // The room is already highlighted in the strip above, and a
                      // long placeholder wrapped to a second line inside a
                      // one-row box — so on a 320px phone the pupil saw
                      // "3-sinf xonasiga / yozin…" with the word cut in half.
                      placeholder={
                        activeRoom?.kind === "news"
                          ? "E'lon yozing…"
                          : staged
                            ? "Rasmga qisqa izoh (ixtiyoriy)…"
                            : "Xabar yozing…"
                      }
                      className="min-w-0 flex-1 resize-none rounded-2xl border border-slate-200 bg-slate-50/80 px-3 py-2 text-[12px] sm:text-sm font-medium text-slate-900 outline-none focus:border-blue-400 focus:bg-white max-h-32"
                    />
                    <Button
                      variant="primary"
                      size="sm"
                      className="h-10 shrink-0"
                      aria-label="Xabar yuborish"
                      loading={sending}
                      disabled={draft.trim().length === 0 && !staged}
                      onClick={() => void send()}
                      icon={sending ? undefined : <IconSend size={14} />}
                    >
                      {/* On a 320px phone the word "Yuborish" ate the room the
                          pupil needs to read what they typed: below 360px the
                          button is the paper plane alone. */}
                      {sending ? "" : <span className="hidden min-[360px]:inline">Yuborish</span>}
                    </Button>
                  </div>
                  <div className="mt-1 flex items-center justify-between gap-2">
                    <p className="text-[10.5px] sm:text-[11px] font-semibold text-slate-400">
                      Rasm/GIF 2 MB · video 10 MB · 500 belgi · juda tez yozsangiz chat
                      biroz to‘xtatadi
                    </p>
                    {draft.length > 400 && (
                      <span className="text-[10px] font-black text-amber-600">
                        {draft.length}/500
                      </span>
                    )}
                  </div>
                </>
              ) : (
                <p className="text-[11px] sm:text-xs font-semibold text-slate-500 text-center py-1.5">
                  {activeRoom?.kind === "group" && activeRoom.is_closed
                    ? "🔒 Bu chatni ochgan odam uni yopgan — yozib bo‘lmaydi, o‘qish mumkin."
                    : "📣 Bu yerga faqat o‘qituvchi yozadi. Siz bu xabarlarni o‘qiy olasiz."}
                </p>
              )}
              {sendError && (
                <p className="mt-1.5 text-[11px] font-bold text-rose-600">{sendError}</p>
              )}
              {latestId !== null && messages.length > 0 && !firstLoad && (
                <p className="mt-1 text-[10.5px] font-semibold text-slate-400">
                  💬 {messages.length} xabar ko‘rsatilmoqda · yangilanish avtomatik
                </p>
              )}
            </div>
          </Card>

          <p className="mt-2.5 text-[10px] sm:text-[11px] font-semibold text-slate-400 text-center px-2">
            Chatda ismingiz, profil rasmingiz va xabarlaringiz ko‘rinadi. Qoidalarga rioya
            qiling — keraksiz xabarni o‘qituvchi o‘chiradi.
          </p>
        </>
      )}

      <RoomFormSheet
        open={createOpen}
        room={null}
        token={token}
        onClose={() => setCreateOpen(false)}
        onSaved={(saved) => {
          setCreateOpen(false);
          roomSaved(saved, true);
        }}
      />
      <RoomFormSheet
        open={editRoom !== null}
        room={editRoom}
        token={token}
        onClose={() => setEditRoom(null)}
        onSaved={(saved) => {
          setEditRoom(null);
          roomSaved(saved, false);
        }}
      />
      {peopleFor && (
        <PeopleSheet
          open={peopleFor !== null}
          room={peopleFor}
          token={token}
          canManage={peopleFor.is_mine || isAdmin}
          notify={notify}
          onMembersChanged={onMembersChanged}
          onClose={() => setPeopleFor(null)}
        />
      )}
      <Lightbox media={lightbox} onClose={() => setLightbox(null)} />
    </div>
  );
}
