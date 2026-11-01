import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { api, ApiError } from "../api";
import type {
  ChatFeed,
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
  IconRefresh,
  IconSend,
  IconTrash,
  IconCheck,
} from "./ui/Icons";

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

/** Room address as the API sends it (news has no grade). */
interface RoomRef {
  kind: string;
  gradeId: number | null;
}

/**
 * Either shape: our own `{kind, gradeId}` state or a `ChatRoom` straight from
 * the server (`grade_id`). Comparing them through one helper is what keeps the
 * active-room highlight and the "did the room change?" guards honest.
 */
type RoomLike = { kind: string; gradeId?: number | null; grade_id?: number | null };

const gradeOf = (room: RoomLike): number | null => room.gradeId ?? room.grade_id ?? null;

const sameRoom = (a: RoomLike | null, b: RoomLike | null) =>
  a !== null && b !== null && a.kind === b.kind && gradeOf(a) === gradeOf(b);

const roomKey = (room: RoomLike) => `${room.kind}:${gradeOf(room) ?? "-"}`;

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

/** "14:32" for today, "05.11" for an older day — both in the pupils' own timezone. */
function stamp(iso: string): string {
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

/** Initials for pupils without a picture — the same fallback everywhere. */
function initials(name: string): string {
  return (name.trim().charAt(0) || "?").toUpperCase();
}

function AvatarDot({
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
}: {
  queue: ChatPendingQueue | null;
  busyId: number | null;
  onApprove: (id: number) => void;
  onReject: (id: number, reason: string) => void;
  onDelete: (id: number) => void;
  onRefresh: () => void;
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
                      · {item.kind === "news" ? "E'lonxona" : item.grade_name ?? "sinf"}
                    </span>
                  </p>
                  <p className="text-[10px] font-semibold text-slate-400">
                    {stamp(item.created_at)}
                  </p>
                </div>
              </div>

              <p className="mt-1.5 text-[11px] sm:text-xs font-medium text-slate-700 whitespace-pre-wrap break-words">
                {item.text}
              </p>

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
  const [active, setActive] = useState<RoomRef | null>(null);

  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [latestId, setLatestId] = useState<number | null>(null);
  const [feedError, setFeedError] = useState("");
  const [needGrade, setNeedGrade] = useState(false);
  const [firstLoad, setFirstLoad] = useState(true);

  const [draft, setDraft] = useState("");
  const [sending, setSending] = useState(false);
  const [sendError, setSendError] = useState("");

  const [queue, setQueue] = useState<ChatPendingQueue | null>(null);
  const [busyId, setBusyId] = useState<number | null>(null);

  // The poller reads the room + cursor from refs, so a room switch never leaves a
  // timer polling the previous room with a stale cursor.
  const latestRef = useRef<number | null>(null);
  const roomRef = useRef<RoomRef | null>(null);
  const feedBox = useRef<HTMLDivElement | null>(null);
  const roomStrip = useRef<HTMLDivElement | null>(null);

  // Eleven room chips do not fit on a 360px phone, so the strip scrolls. When a
  // pupil opens their own class room the chip is often the one that is off
  // screen — bring it back into view, otherwise the bar looks like the tap did
  // nothing. block:"nearest" keeps the page from jumping vertically.
  useEffect(() => {
    const strip = roomStrip.current;
    if (!strip) return;
    strip
      .querySelector<HTMLElement>('[data-active="true"]')
      ?.scrollIntoView({ inline: "center", block: "nearest", behavior: "smooth" });
  }, [active, rooms]);

  const activeRoom = useMemo(
    () => (active ? (rooms ?? []).find((r) => sameRoom(r, active)) ?? null : null),
    [active, rooms],
  );

  // ---------------------------------------------------------------- rooms
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
        if (mine) setActive({ kind: mine.kind, gradeId: mine.grade_id });
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
    async (room: RoomRef) => {
      setFirstLoad(true);
      setFeedError("");
      setNeedGrade(false);
      try {
        const feed: ChatFeed = await api.chatMessages(token, room);
        if (!sameRoom(roomRef.current, room)) return;
        setMessages(feed.messages);
        latestRef.current = feed.latest_id;
        setLatestId(feed.latest_id);
      } catch (e) {
        if (!sameRoom(roomRef.current, room)) return;
        setMessages([]);
        if (e instanceof ApiError && e.code === "grade_not_selected") setNeedGrade(true);
        else
          setFeedError(
            e instanceof ApiError ? e.message : "Xabalarni yuklab bo‘lmadi.",
          );
      } finally {
        if (sameRoom(roomRef.current, room)) setFirstLoad(false);
      }
    },
    [token],
  );

  useEffect(() => {
    roomRef.current = active;
    latestRef.current = null;
    setMessages([]);
    setLatestId(null);
    setSendError("");
    if (active) void openRoom(active);
    else setFirstLoad(false);
  }, [active, openRoom]);

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
    if (!active || firstLoad) return;
    let alive = true;

    const tick = async () => {
      // A hidden Mini App should not spend the pupil's data — wait for a focus.
      if (document.hidden || !roomRef.current) return;
      const room = roomRef.current;
      try {
        const feed = await api.chatMessages(token, room, latestRef.current ?? undefined);
        if (!alive || !sameRoom(roomRef.current, room)) return;
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
  }, [active, firstLoad, token]);

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
    async (
      id: number,
      action: "approve" | "reject" | "delete",
      reason?: string,
    ) => {
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
        if (room) void openRoom(room);
      } catch (e) {
        notify(e instanceof ApiError ? e.message : "Amalni bajarsa bo‘lmadi.");
      } finally {
        setBusyId(null);
      }
    },
    [notify, openRoom, refreshQueue, token],
  );

  // ------------------------------------------------------------- sending
  const send = async () => {
    const text = draft.trim();
    if (!activeRoom || text.length === 0 || sending) return;
    setSending(true);
    setSendError("");
    try {
      const result: ChatSendResult = await api.chatSend(
        token,
        {
          text,
          kind: activeRoom.kind,
          grade_id: activeRoom.grade_id,
        },
      );
      // Append right away (the pupil must see their own message immediately),
      // then move the cursor past it — dedupe by id protects the next poll.
      setMessages((prev) => mergeById(prev, [result.message]));
      if (result.message.id > (latestRef.current ?? 0)) {
        latestRef.current = result.message.id;
        setLatestId(result.message.id);
      }
      setDraft("");
      notify(result.message_uz);
      const box = feedBox.current;
      if (box) window.requestAnimationFrame(() => {
        box.scrollTop = box.scrollHeight;
      });
      if (isAdmin) void refreshQueue();
    } catch (e) {
      // Keep the draft: a refused message should never be typed out twice.
      setSendError(
        e instanceof ApiError
          ? e.message
          : "Yuborib bo‘lmadi. Aloqani tekshiring.",
      );
    } finally {
      setSending(false);
    }
  };

  const canPost = activeRoom?.can_post ?? false;

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
        />
      )}

      {/* Rooms strip: E'lonxona + the pupil's class (an admin: every class). */}
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
      ) : rooms === null ? (
        <div className="py-10 text-center">
          <div className="inline-block h-8 w-8 animate-spin rounded-full border-4 border-blue-500 border-t-transparent" />
          <p className="mt-3 text-sm font-semibold text-slate-500">
            Chat xonalari ochilmoqda…
          </p>
        </div>
      ) : (
        <>
          <Card
            variant="elevated"
            padding="none"
            className="p-3 sm:p-4 bg-gradient-to-r from-[#3478F6] via-blue-600 to-indigo-700 text-white border-0 mb-2.5"
          >
            <div className="flex items-center gap-2.5">
              <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-white/20 backdrop-blur-md">
                <IconChat size={20} />
              </div>
              <div className="min-w-0">
                <h1 className="text-sm sm:text-lg font-black leading-tight truncate">
                  Jamoat chati
                </h1>
                <p className="text-[10px] sm:text-[11px] font-semibold text-blue-100 truncate">
                  {gradeName
                    ? `${gradeName} xonasi va butun maktab e'lonxonasi`
                    : "Sinfingiz xonasi va e'lonxona"}
                </p>
              </div>
            </div>
          </Card>

          <div
            ref={roomStrip}
            className="no-scrollbar -mx-0.5 flex snap-x gap-1.5 overflow-x-auto px-0.5 pb-1.5"
          >
            {rooms.map((room) => {
              const on = sameRoom(active, room);
              return (
                <button
                  key={roomKey(room)}
                  data-active={on ? "true" : undefined}
                  onClick={() => setActive({ kind: room.kind, gradeId: room.grade_id })}
                  className={`shrink-0 snap-start inline-flex items-center gap-1.5 rounded-xl px-3 py-1.5 text-[11px] sm:text-xs font-bold border transition-colors cursor-pointer whitespace-nowrap ${
                    on
                      ? "bg-blue-600 text-white border-blue-600 shadow-xs"
                      : "bg-white text-slate-700 border-slate-200 hover:border-blue-300"
                  }`}
                >
                  <span aria-hidden>{room.emoji}</span>
                  <span>{room.name}</span>
                  {room.is_current_grade && !on && (
                    <span className="text-[10px] font-black text-blue-600">· siz</span>
                  )}
                </button>
              );
            })}
          </div>

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
                  {active && (
                    <Button
                      variant="secondary"
                      size="sm"
                      className="mt-3"
                      icon={<IconRefresh size={14} />}
                      onClick={() => void openRoom(active)}
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
                      ? "Birinchi xabarni shu yozish oynasidan yuboring."
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
                        <p className="text-[12px] sm:text-[13px] font-medium leading-snug whitespace-pre-wrap break-words">
                          {msg.text}
                        </p>
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
                  <div className="flex items-end gap-2">
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
                        activeRoom?.kind === "news" ? "E'lon yozing…" : "Xabar yozing…"
                      }
                      className="min-w-0 flex-1 resize-none rounded-2xl border border-slate-200 bg-slate-50/80 px-3 py-2 text-[12px] sm:text-sm font-medium text-slate-900 outline-none focus:border-blue-400 focus:bg-white max-h-32"
                    />
                    <Button
                      variant="primary"
                      size="sm"
                      className="shrink-0"
                      loading={sending}
                      disabled={draft.trim().length === 0}
                      onClick={() => void send()}
                      icon={sending ? undefined : <IconSend size={14} />}
                    >
                      {sending ? "" : "Yuborish"}
                    </Button>
                  </div>
                  <div className="mt-1 flex items-center justify-between gap-2">
                    <p className="text-[10.5px] sm:text-[11px] font-semibold text-slate-400">
                      500 belgi · 4 qatorgacha · juda tez yozsangiz chat biroz to‘xtatadi
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
                  📣 E'lonxonaga faqat o‘qituvchi yozadi. Siz bu xabarlarni o‘qiy olasiz.
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
            Chatda ismingiz, profil rasmingiz va xabarlaringiz ko‘rinadi.
            Qoidalarga rioya qiling — keraksiz xabarni o‘qituvchi o‘chiradi.
          </p>
        </>
      )}
    </div>
  );
}
