import {
  IconHome,
  IconBook,
  IconTrophy,
  IconUser,
  IconSettings,
  IconStar,
  IconGraduationCap,
  IconExam,
  IconChat,
} from "./ui/Icons";

export type NavTab =
  | "home"
  | "lessons"
  | "exams"
  | "chat"
  | "achievements"
  | "profile"
  | "admin";

interface NavbarProps {
  currentTab: NavTab;
  onTabChange: (tab: NavTab) => void;
  stars: number;
  streak?: number;
  gradeLabel?: string | null;
  onChangeGrade?: () => void;
  isAdmin?: boolean;
}

export default function Navbar({
  currentTab,
  onTabChange,
  stars,
  streak = 0,
  gradeLabel,
  onChangeGrade,
  isAdmin = false,
}: NavbarProps) {
  // `short` is what the 7-column mobile bar can actually fit; desktop shows the
  // full word. Without it "Bosh sahifa" wraps and the bar jumps in height.
  const tabs: {
    key: NavTab;
    label: string;
    short: string;
    icon: typeof IconHome;
  }[] = [
    { key: "home", label: "Bosh sahifa", short: "Bosh", icon: IconHome },
    { key: "lessons", label: "Fanlar", short: "Fanlar", icon: IconBook },
    { key: "exams", label: "Imtihon", short: "Imtihon", icon: IconExam },
    { key: "chat", label: "Chat", short: "Chat", icon: IconChat },
    { key: "achievements", label: "Yutuqlar", short: "Yutuqlar", icon: IconTrophy },
    { key: "profile", label: "Profil", short: "Profil", icon: IconUser },
    ...(isAdmin
      ? [{ key: "admin" as NavTab, label: "Admin", short: "Admin", icon: IconSettings }]
      : []),
  ];

  const handleTabClick = (key: NavTab) => {
    window.Telegram?.WebApp?.HapticFeedback?.selectionChanged();
    onTabChange(key);
  };

  return (
    <>
      {/* ================= DESKTOP / TABLET TOP NAVBAR =================
          Seven tabs plus three badges do not fit between 768px and ~1100px.
          They used to push the whole page sideways (the document became 1034px
          wide inside a 768px window, so the Admin tab and the star counter were
          cut off and the page scrolled horizontally). Two rules fix that for
          every width: the strip itself scrolls (`min-w-0 overflow-x-auto` +
          `shrink-0` items), and the words only appear once there is room for
          them (`hidden xl:inline`) — below that the icons carry `title`/
          `aria-label`, so a tablet user still knows what each button is. */}
      <header className="sticky top-0 z-40 hidden md:block border-b border-slate-200/80 bg-white/90 backdrop-blur-md">
        <div className="mx-auto flex w-full max-w-6xl items-center gap-3 px-4 sm:px-6 py-2.5">
          {/* Logo & Slogan */}
          <div
            onClick={() => handleTabClick("home")}
            className="flex shrink-0 items-center gap-3 cursor-pointer select-none group"
          >
            <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-gradient-to-br from-[#3478F6] to-blue-700 text-white shadow-md shadow-blue-500/20 group-hover:scale-105 transition-transform">
              <span className="text-lg font-black">E</span>
            </div>
            <div className="min-w-0">
              <span className="text-lg font-extrabold tracking-tight text-slate-900 group-hover:text-blue-600 transition-colors">
                EduQuest
              </span>
              <span className="hidden 2xl:inline-block ml-2 text-xs font-semibold text-slate-400">
                · O‘rganish — endi o‘yin!
              </span>
            </div>
          </div>

          {/* Nav Links */}
          <nav className="no-scrollbar flex min-w-0 flex-1 items-center gap-1 overflow-x-auto rounded-2xl bg-slate-100/80 p-1">
            {tabs.map((tab) => {
              const active = currentTab === tab.key;
              const Icon = tab.icon;
              return (
                <button
                  key={tab.key}
                  onClick={() => handleTabClick(tab.key)}
                  title={tab.label}
                  aria-label={tab.label}
                  aria-current={active ? "page" : undefined}
                  className={`flex shrink-0 items-center gap-1.5 whitespace-nowrap rounded-xl px-3 py-1.5 text-sm font-bold transition-all cursor-pointer ${
                    active
                      ? "bg-white text-blue-600 shadow-xs"
                      : "text-slate-600 hover:text-slate-900 hover:bg-white/50"
                  }`}
                >
                  <Icon size={16} className={active ? "text-blue-600" : "text-slate-400"} />
                  <span className="hidden xl:inline">{tab.label}</span>
                </button>
              );
            })}
          </nav>

          {/* Right badges: Grade + Streak + Stars */}
          <div className="flex shrink-0 items-center gap-2">
            {gradeLabel && (
              <button
                onClick={onChangeGrade}
                className="flex items-center gap-1 px-2.5 py-1.5 rounded-xl bg-blue-50 text-blue-700 hover:bg-blue-100/70 border border-blue-200/60 text-xs font-bold transition-colors cursor-pointer whitespace-nowrap"
                title="Sinfni almashtirish"
              >
                <IconGraduationCap size={15} />
                <span>{gradeLabel}</span>
              </button>
            )}

            {streak > 0 && (
              <div
                className="flex items-center gap-1 px-2.5 py-1.5 rounded-xl bg-orange-50 text-orange-700 border border-orange-200/70 font-extrabold text-xs shadow-xs"
                title={`Kunlik seriya: ${streak} kun`}
              >
                <span aria-hidden="true">🔥</span>
                <span>{streak}</span>
              </div>
            )}

            <div
              className="flex items-center gap-1 px-2.5 py-1.5 rounded-xl bg-amber-50 text-amber-700 border border-amber-200/60 font-extrabold text-xs shadow-xs"
              title={`Yulduzcha: ${stars}`}
            >
              <IconStar size={15} filled className="text-amber-500" />
              <span>{stars}</span>
            </div>
          </div>
        </div>
      </header>

      {/* ================= MOBILE BOTTOM NAVIGATION BAR ================= */}
      <nav className="fixed inset-x-0 bottom-0 z-40 md:hidden border-t border-slate-200/80 bg-white/95 backdrop-blur-md pb-[env(safe-area-inset-bottom,0px)] shadow-lg">
        <div className="grid grid-flow-col auto-cols-fr px-0.5 py-1">
          {tabs.map((tab) => {
            const active = currentTab === tab.key;
            const Icon = tab.icon;
            return (
              <button
                key={tab.key}
                onClick={() => handleTabClick(tab.key)}
                aria-current={active ? "page" : undefined}
                className={`flex flex-col items-center justify-center py-1 px-0.5 transition-all cursor-pointer ${
                  active ? "text-blue-600 font-bold" : "text-slate-400 hover:text-slate-600 font-medium"
                }`}
              >
                <div
                  className={`relative flex h-7 w-11 items-center justify-center rounded-xl transition-all ${
                    active ? "bg-blue-50 text-blue-600 shadow-2xs" : ""
                  }`}
                >
                  <Icon size={18} className={active ? "text-blue-600" : "text-slate-400"} />
                </div>
                {/* 9.5px is the smallest type a 10-year-old can read at arm's
                    length; it is only kept that small so "Yutuqlar" still fits
                    in one of seven columns on a 320–360px phone. */}
                <span className="text-[9.5px] min-[380px]:text-[10.5px] tracking-tight mt-0.5 leading-none whitespace-nowrap">
                  {tab.short}
                </span>
              </button>
            );
          })}
        </div>
      </nav>
    </>
  );
}
