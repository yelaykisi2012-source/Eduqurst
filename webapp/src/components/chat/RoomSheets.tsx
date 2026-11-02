import { useCallback, useEffect, useRef, useState } from "react";

import { api, ApiError } from "../../api";
import type { ChatMember, ChatPerson, ChatRoom } from "../../types";
import Button from "../ui/Button";
import Sheet from "../ui/Sheet";
import { AvatarDot } from "./ChatBits";

/** Icons a chat may be opened with (a pupil picks one, not a keyboard of 40). */
const ROOM_ICONS = ["💬", "📚", "🧠", "⚽", "🎨", "🎵", "🧪", "📐", "🎮", "🏆", "🌟", "🤝"];

/** The same bounds app/chat.py enforces, so a pupil is stopped before the server is. */
const NAME_MAX = 48;
const BIO_MAX = 200;

function errorLine(e: unknown, fallback: string): string {
  return e instanceof ApiError ? e.message : fallback;
}

// ---------------------------------------------------------------------------
// Create / edit a chat: name, description, icon, picture
// ---------------------------------------------------------------------------

interface RoomFormSheetProps {
  open: boolean;
  /** null = the "+" button (create); a room = rename / describe / re-picture. */
  room: ChatRoom | null;
  token: string;
  onClose: () => void;
  /** The saved room, so the page can switch to it and refresh the list. */
  onSaved: (room: ChatRoom) => void;
}

/**
 * One sheet for both "open a chat" and "change this chat".
 *
 * Creating needs only a name (the server defaults the icon to 💬), but the
 * picture needs a room id — so a picked photo is uploaded right AFTER the room
 * exists, in the same press of the button. The pupil sees one honest progress
 * line ("Chat ochilmoqda…", "Rasm yuklanmoqda…") instead of two surprises.
 */
export function RoomFormSheet({ open, room, token, onClose, onSaved }: RoomFormSheetProps) {
  const editing = room !== null;
  const [name, setName] = useState("");
  const [bio, setBio] = useState("");
  const [emoji, setEmoji] = useState("💬");
  const [closed, setClosed] = useState(false);
  const [picture, setPicture] = useState<File | null>(null);
  const [dropPicture, setDropPicture] = useState(false);
  const [preview, setPreview] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [progress, setProgress] = useState("");
  const [error, setError] = useState("");
  const fileInput = useRef<HTMLInputElement | null>(null);

  // A fresh sheet every time it opens (or switches between rooms).
  useEffect(() => {
    if (!open) return;
    setName(room?.name ?? "");
    setBio(room?.bio ?? "");
    setEmoji(room?.emoji ?? "💬");
    setClosed(room?.is_closed ?? false);
    setPicture(null);
    setDropPicture(false);
    setError("");
    setProgress("");
  }, [open, room]);

  // The picked file is previewed through an object URL that must be revoked.
  useEffect(() => {
    if (!picture) {
      setPreview(null);
      return;
    }
    const url = URL.createObjectURL(picture);
    setPreview(url);
    return () => URL.revokeObjectURL(url);
  }, [picture]);

  const trimmed = name.trim();
  const canSubmit = trimmed.length >= 3 && !busy;

  const submit = async () => {
    if (!canSubmit) return;
    setBusy(true);
    setError("");
    try {
      let saved: ChatRoom;
      if (editing && room) {
        const changed: Record<string, string | boolean | null> = {};
        if (trimmed !== room.name) changed.name = trimmed;
        if (bio.trim() !== (room.bio ?? "")) changed.bio = bio.trim() || null;
        if (emoji !== room.emoji) changed.emoji = emoji;
        if (closed !== room.is_closed) changed.is_closed = closed;
        if (Object.keys(changed).length > 0) {
          setProgress("Saqlanmoqda…");
          const res = await api.chatUpdateRoom(token, room.id, changed);
          saved = res.room;
        } else {
          saved = room;
        }
        if (dropPicture && room.avatar_url) {
          setProgress("Rasm o‘chirilmoqda…");
          saved = (await api.chatRoomPictureRemove(token, room.id)).room;
        }
      } else {
        setProgress("Chat ochilmoqda…");
        const created = await api.chatCreateRoom(token, {
          name: trimmed,
          bio: bio.trim() || null,
          emoji,
        });
        saved = created.room;
      }
      if (picture) {
        setProgress("Rasm yuklanmoqda…");
        saved = (await api.chatRoomPicture(token, saved.id, picture)).room;
      }
      onSaved(saved);
    } catch (e) {
      // Nothing was half-saved that the pupil cannot see: the name stays typed.
      setError(errorLine(e, "Chatni saqlab bo‘lmadi. Internetni tekshiring."));
    } finally {
      setBusy(false);
      setProgress("");
    }
  };

  return (
    <Sheet
      open={open}
      title={editing ? "Chatni sozlash" : "Yangi chat ochish"}
      subtitle={
        editing
          ? "Nom, tavsif, ikonka va rasmni shu yerdan boshqarasiz."
          : "Nom, tavsif va ikonka — hammasi shu tugmadan. Chat butun maktabga ochiq."
      }
      onClose={onClose}
      footer={
        <div className="flex items-center gap-2">
          <Button
            variant="primary"
            size="md"
            fullWidth
            loading={busy}
            disabled={!canSubmit}
            onClick={() => void submit()}
          >
            {busy && progress ? progress : editing ? "Saqlash" : "Chat ochish"}
          </Button>
          <Button variant="ghost" size="md" disabled={busy} onClick={onClose}>
            Bekor
          </Button>
        </div>
      }
    >
      <div className="space-y-3.5">
        <label className="block">
          <span className="text-[11px] font-black uppercase tracking-wide text-slate-500">
            Chat nomi *
          </span>
          <input
            value={name}
            onChange={(e) => {
              setName(e.target.value);
              if (error) setError("");
            }}
            maxLength={NAME_MAX}
            placeholder="Masalan: Matematika klubi"
            className="mt-1 w-full rounded-xl border border-slate-200 bg-slate-50/80 px-3 py-2.5 text-sm font-semibold text-slate-900 outline-none focus:border-blue-400 focus:bg-white"
          />
          <span className="mt-1 block text-[10.5px] font-semibold text-slate-400">
            {trimmed.length}/{NAME_MAX} · kamida 3 belgi
          </span>
        </label>

        <label className="block">
          <span className="text-[11px] font-black uppercase tracking-wide text-slate-500">
            Tavsif (ixtiyoriy)
          </span>
          <textarea
            value={bio}
            onChange={(e) => setBio(e.target.value)}
            maxLength={BIO_MAX}
            rows={2}
            placeholder="Bu chat nimaga? Kimlar uchun?"
            className="mt-1 w-full resize-none rounded-xl border border-slate-200 bg-slate-50/80 px-3 py-2.5 text-[13px] font-medium text-slate-900 outline-none focus:border-blue-400 focus:bg-white"
          />
          <span className="mt-1 block text-[10.5px] font-semibold text-slate-400">
            {bio.length}/{BIO_MAX}
          </span>
        </label>

        <div>
          <span className="text-[11px] font-black uppercase tracking-wide text-slate-500">
            Ikonka
          </span>
          <div className="mt-1.5 flex flex-wrap gap-1.5">
            {ROOM_ICONS.map((option) => (
              <button
                key={option}
                type="button"
                onClick={() => setEmoji(option)}
                aria-label={`Ikonka ${option}`}
                className={`flex h-10 w-10 items-center justify-center rounded-xl border text-xl transition-colors cursor-pointer ${
                  emoji === option
                    ? "border-blue-500 bg-blue-50 shadow-xs"
                    : "border-slate-200 bg-white hover:border-blue-200"
                }`}
              >
                {option}
              </button>
            ))}
          </div>
        </div>

        <div>
          <span className="text-[11px] font-black uppercase tracking-wide text-slate-500">
            Chat rasmi (ixtiyoriy)
          </span>
          <div className="mt-1.5 flex items-center gap-2.5">
            {preview ? (
              <img
                src={preview}
                alt=""
                className="h-14 w-14 rounded-2xl object-cover ring-1 ring-slate-200"
              />
            ) : (
              <AvatarDot name={trimmed || "Chat"} avatarUrl={room?.avatar_url ?? null} size={56} />
            )}
            <div className="min-w-0 flex-1">
              <input
                ref={fileInput}
                type="file"
                accept="image/*"
                className="hidden"
                onChange={(e) => {
                  const picked = e.target.files?.[0] ?? null;
                  setPicture(picked);
                  setDropPicture(false);
                  e.target.value = "";
                }}
              />
              <Button
                variant="secondary"
                size="sm"
                onClick={() => fileInput.current?.click()}
              >
                {preview || picture ? "Boshqa rasm" : "Rasm tanlash"}
              </Button>
              {editing && room?.avatar_url && !picture && (
                <Button
                  variant="ghost"
                  size="sm"
                  className={`ml-1.5 ${dropPicture ? "text-rose-600" : "text-slate-500"}`}
                  onClick={() => setDropPicture((v) => !v)}
                >
                  {dropPicture ? "Qaytarish" : "Rasmni o‘chirish"}
                </Button>
              )}
              <p className="mt-1 text-[10.5px] font-semibold text-slate-400">
                Kvadrat qilib kesiladi, telefon ma’lumotlari (Joy, model) o‘chiriladi.
              </p>
            </div>
          </div>
        </div>

        {editing && (
          <label className="flex items-start gap-2.5 rounded-xl border border-slate-200 bg-slate-50/70 p-3 cursor-pointer">
            <input
              type="checkbox"
              checked={closed}
              onChange={(e) => setClosed(e.target.checked)}
              className="mt-0.5 h-4 w-4 accent-blue-600"
            />
            <span className="min-w-0">
              <span className="block text-[12px] font-black text-slate-800">
                Chatni yopish
              </span>
              <span className="block text-[10.5px] font-semibold text-slate-500">
                Hozircha hech kim yza olmaydi — lekin hamma o‘qiy oladi. Tarix
                o‘chmaydi, xohlasangiz qayta ochasiz.
              </span>
            </span>
          </label>
        )}

        {error && (
          <p className="rounded-xl bg-rose-50 px-3 py-2 text-[11.5px] font-bold text-rose-700">
            {error}
          </p>
        )}
      </div>
    </Sheet>
  );
}

// ---------------------------------------------------------------------------
// People: who is inside, add somebody, leave
// ---------------------------------------------------------------------------

interface PeopleSheetProps {
  open: boolean;
  room: ChatRoom;
  token: string;
  /** Owner or an adult: they may invite and remove other people. */
  canManage: boolean;
  notify: (msg: string) => void;
  onMembersChanged: (members: ChatMember[]) => void;
  onClose: () => void;
}

/**
 * The room's people panel + the "add people" search.
 *
 * A class room has no member list (it IS the whole grade), so the sheet says so
 * instead of showing an empty box and an "Add" button that could never work —
 * the same honesty rule the rest of the chat follows.
 */
export function PeopleSheet({
  open,
  room,
  token,
  canManage,
  notify,
  onMembersChanged,
  onClose,
}: PeopleSheetProps) {
  const [members, setMembers] = useState<ChatMember[] | null>(null);
  const [loadError, setLoadError] = useState("");
  const [busyId, setBusyId] = useState<number | null>(null);

  const [query, setQuery] = useState("");
  const [found, setFound] = useState<ChatPerson[] | null>(null);
  // Every list change is also pushed up to the page (member count in the header).
  const publish = useCallback(
    (list: ChatMember[]) => {
      setMembers(list);
      onMembersChanged(list);
    },
    [onMembersChanged],
  );

  useEffect(() => {
    if (!open) return;
    let alive = true;
    setMembers(null);
    setLoadError("");
    setQuery("");
    setFound(null);
    api
      .chatMembers(token, room.id)
      .then((list) => {
        if (alive) setMembers(list);
      })
      .catch((e: unknown) => {
        if (alive) setLoadError(errorLine(e, "Odamlarni yuklab bo‘lmadi."));
      });
    return () => {
      alive = false;
    };
  }, [open, room.id, token]);

  // Search only runs when there is something to search for (2+ characters), so
  // the whole school is never pulled down on every keystroke.
  useEffect(() => {
    if (!open || !canManage) return;
    const q = query.trim();
    if (q.length < 2) {
      setFound(null);
      return;
    }
    let alive = true;
    const timer = window.setTimeout(() => {
      api
        .chatPeople(token, q)
        .then((res) => {
          if (alive) setFound(res.people);
        })
        .catch(() => {
          if (alive) setFound([]);
        });
    }, 320);
    return () => {
      alive = false;
      window.clearTimeout(timer);
    };
  }, [canManage, open, query, token]);

  const inside = new Set((members ?? []).map((m) => m.id));
  const meInside = (members ?? []).some((m) => m.is_me);

  const act = async (fn: () => Promise<ChatMember[]>, done: string) => {
    try {
      publish(await fn());
      notify(done);
    } catch (e) {
      notify(errorLine(e, "Amalni bajarsa bo‘lmadi."));
    }
  };

  const add = (person: ChatPerson) => {
    setBusyId(person.id);
    return act(
      () => api.chatAddMember(token, room.id, person.id),
      `${person.name} qo‘shildi ✅`,
    ).finally(() => setBusyId(null));
  };

  // The DELETE returns nothing, so the fresh list is re-read right after it —
  // the panel must not keep showing a person who has already gone.
  const remove = (member: ChatMember) => {
    setBusyId(member.id);
    return act(
      () =>
        api
          .chatRemoveMember(token, room.id, member.id)
          .then(() => api.chatMembers(token, room.id)),
      member.is_me ? "Chatdan chiqdingiz." : `${member.name} chiqarildi.`,
    ).finally(() => setBusyId(null));
  };

  const isGroup = room.kind === "group";

  return (
    <Sheet
      open={open}
      title={isGroup ? "Chatdagi odamlar" : room.name}
      subtitle={
        isGroup
          ? canManage
            ? "Ism bo‘yicha izlab, do‘stingizni qo‘shing."
            : "Bu chatga kimlar yozishini shu yerda ko‘rasiz."
          : "Sinf xonasi — bu yerga butun sinfingiz avtomatik kiradi, ro‘yxat shart emas."
      }
      onClose={onClose}
      footer={
        isGroup && !meInside ? (
          <Button
            variant="primary"
            fullWidth
            loading={busyId === -1}
            onClick={() => {
              setBusyId(-1);
              void act(() => api.chatJoin(token, room.id), "Chatga kirdingiz ✅").finally(
                () => setBusyId(null),
              );
            }}
          >
            Men ham bu chatdaman
          </Button>
        ) : isGroup && canManage ? (
          <Button
            variant="secondary"
            fullWidth
            loading={busyId === -2}
            onClick={() => {
              setBusyId(-2);
              void act(
                () => api.chatMembers(token, room.id),
                "Ro‘yxat yangilandi.",
              ).finally(() => setBusyId(null));
            }}
          >
            Ro‘yxatni yangilash
          </Button>
        ) : undefined
      }
    >
      {loadError ? (
        <p className="rounded-xl bg-rose-50 px-3 py-2 text-[11.5px] font-bold text-rose-700">
          {loadError}
        </p>
      ) : members === null ? (
        <div className="py-8 text-center">
          <div className="inline-block h-7 w-7 animate-spin rounded-full border-4 border-slate-300 border-t-transparent" />
          <p className="mt-2 text-[11px] font-semibold text-slate-400">Yuklanmoqda…</p>
        </div>
      ) : !isGroup ? (
        <div className="space-y-2 py-1">
          <p className="text-[12px] font-semibold text-slate-600">
            🎓 {room.name} — butun sinf. Alohida odam qo‘shish shart emas: sinfingizdagi
            har bir o‘quvchi bu xonani ochadi.
          </p>
          {room.bio && <p className="text-[11px] font-semibold text-slate-500">{room.bio}</p>}
        </div>
      ) : (
        <>
          {canManage && (
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              maxLength={64}
              placeholder="O‘quvchini ismi bilan izlash…"
              className="mb-3 w-full rounded-xl border border-slate-200 bg-slate-50/80 px-3 py-2.5 text-[13px] font-semibold text-slate-900 outline-none focus:border-blue-400 focus:bg-white"
            />
          )}

          {canManage && query.trim().length >= 2 && (
            <div className="mb-3">
              <p className="mb-1.5 text-[10.5px] font-black uppercase tracking-wide text-slate-400">
                Topildi
              </p>
              {found === null ? (
                <p className="text-[11px] font-semibold text-slate-400">Izlanmoqda…</p>
              ) : found.length === 0 ? (
                <p className="text-[11px] font-semibold text-slate-400">
                  Bunday ism topilmadi. Birinchi nomni to‘liq yozib ko‘ring.
                </p>
              ) : (
                <ul className="space-y-1.5">
                  {found.map((person) => (
                    <li key={person.id} className="flex items-center gap-2">
                      <AvatarDot name={person.name} avatarUrl={person.avatar_url} size={30} />
                      <div className="min-w-0 flex-1">
                        <p className="truncate text-[12px] font-bold text-slate-800">
                          {person.name}
                          {person.is_teacher && (
                            <span className="ml-1 text-[10px] font-black text-purple-600">
                              · o‘qituvchi
                            </span>
                          )}
                        </p>
                        <p className="text-[10.5px] font-semibold text-slate-400">
                          {person.grade_name ?? "sinf tanlanmagan"}
                        </p>
                      </div>
                      {person.is_me ? (
                        <span className="text-[10.5px] font-black text-blue-600">siz</span>
                      ) : inside.has(person.id) ? (
                        <span className="text-[10.5px] font-black text-emerald-600">
                          allaqachon
                        </span>
                      ) : (
                        <Button
                          variant="secondary"
                          size="sm"
                          loading={busyId === person.id}
                          disabled={busyId !== null}
                          onClick={() => void add(person)}
                        >
                          Qo‘shish
                        </Button>
                      )}
                    </li>
                  ))}
                </ul>
              )}
            </div>
          )}

          <p className="mb-1.5 text-[10.5px] font-black uppercase tracking-wide text-slate-400">
            Ro‘yxat · {members.length} kishi
          </p>
          {members.length === 0 ? (
            <p className="text-[11px] font-semibold text-slate-400">
              Hozircha hech kim yo‘q. Chatni ochgan odam ham shu ro‘yxatda turadi.
            </p>
          ) : (
            <ul className="space-y-1.5">
              {members.map((member) => (
                <li key={member.id} className="flex items-center gap-2">
                  <AvatarDot name={member.name} avatarUrl={member.avatar_url} size={32} />
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-[12px] font-bold text-slate-800">
                      {member.name}
                      {member.is_me && (
                        <span className="ml-1 text-[10px] font-black text-blue-600">· siz</span>
                      )}
                      {member.role === "owner" && (
                        <span className="ml-1 rounded-md bg-blue-50 px-1.5 py-0.5 text-[10px] font-black uppercase text-blue-700">
                          ochgan
                        </span>
                      )}
                      {member.is_teacher && (
                        <span className="ml-1 text-[10px] font-black text-purple-600">
                          · o‘qituvchi
                        </span>
                      )}
                    </p>
                    <p className="text-[10.5px] font-semibold text-slate-400">
                      {member.grade_name ?? "sinf tanlanmagan"}
                    </p>
                  </div>
                  {/* Own row → leave. Somebody else's → only the owner/adult sees a button,
                      and the person who opened the chat is never removable by a pupil. */}
                  {member.is_me && member.role !== "owner" ? (
                    <Button
                      variant="ghost"
                      size="sm"
                      className="text-slate-500 hover:bg-slate-100"
                      loading={busyId === member.id}
                      disabled={busyId !== null}
                      onClick={() => void remove(member)}
                    >
                      Chiqish
                    </Button>
                  ) : canManage && member.role !== "owner" ? (
                    <Button
                      variant="ghost"
                      size="sm"
                      className="text-rose-600 hover:bg-rose-50"
                      loading={busyId === member.id}
                      disabled={busyId !== null}
                      onClick={() => void remove(member)}
                    >
                      Chiqarish
                    </Button>
                  ) : null}
                </li>
              ))}
            </ul>
          )}
        </>
      )}
    </Sheet>
  );
}
