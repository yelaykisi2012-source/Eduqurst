import {
  IconHome,
  IconBook,
  IconTrophy,
  IconUser,
  IconSettings,
  IconStar,
  IconGraduationCap,
  IconExam,
} from "./ui/Icons";

export type NavTab = "home" | "lessons" | "exams" | "achievements" | "profile" | "admin";

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
  const tabs = [
    { key: "home" as NavTab, label: "Bosh sahifa", icon: IconHome },
    { key: "lessons" as NavTab, label: "Fanlar", icon: IconBook },
    { key: "exams" as NavTab, label: "Imtihon", icon: IconExam },
    { key: "achievements" as NavTab, label: "Yutuqlar", icon: IconTrophy },
    { key: "profile" as NavTab, label: "Profil", icon: IconUser },
    ...(isAdmin ? [{ key: "admin" as NavTab, label: "Admin", icon: IconSettings }] : []),
  ];

  const handleTabClick = (key: NavTab) => {
    window.Telegram?.WebApp?.HapticFeedback?.selectionChanged();
    onTabChange(key);
  };

  return (
    <>
      {/* ================= DESKTOP / TABLET TOP NAVBAR ================= */}
      <header className="sticky top-0 z-40 hidden md:block border-b border-slate-200/80 bg-white/90 backdrop-blur-md">
        <div className="mx-auto flex max-w-6xl items-center justify-between px-6 py-3">
          {/* Logo & Slogan */}
          <div
            onClick={() => handleTabClick("home")}
            className="flex items-center gap-3 cursor-pointer select-none group"
          >
            <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-gradient-to-br from-[#3478F6] to-blue-700 text-white shadow-md shadow-blue-500/20 group-hover:scale-105 transition-transform">
              <span className="text-lg font-black">E</span>
            </div>
            <div>
              <span className="text-lg font-extrabold tracking-tight text-slate-900 group-hover:text-blue-600 transition-colors">
                EduQuest
              </span>
              <span className="hidden lg:inline-block ml-2 text-xs font-semibold text-slate-400">
                · O‘rganish — endi o‘yin!
              </span>
            </div>
          </div>

          {/* Nav Links */}
          <nav className="flex items-center gap-1 bg-slate-100/80 p-1 rounded-2xl">
            {tabs.map((tab) => {
              const active = currentTab === tab.key;
              const Icon = tab.icon;
              return (
                <button
                  key={tab.key}
                  onClick={() => handleTabClick(tab.key)}
                  className={`flex items-center gap-1.5 px-3.5 py-1.5 rounded-xl text-xs sm:text-sm font-bold transition-all cursor-pointer ${
                    active
                      ? "bg-white text-blue-600 shadow-xs"
                      : "text-slate-600 hover:text-slate-900 hover:bg-white/50"
                  }`}
                >
                  <Icon size={16} className={active ? "text-blue-600" : "text-slate-400"} />
                  <span>{tab.label}</span>
                </button>
              );
            })}
          </nav>

          {/* Right badges: Grade + Stars */}
          <div className="flex items-center gap-2.5">
            {gradeLabel && (
              <button
                onClick={onChangeGrade}
                className="flex items-center gap-1 px-2.5 py-1.5 rounded-xl bg-blue-50 text-blue-700 hover:bg-blue-100/70 border border-blue-200/60 text-xs font-bold transition-colors cursor-pointer"
                title="Sinfni almashtirish"
              >
                <IconGraduationCap size={15} />
                <span>{gradeLabel}</span>
              </button>
            )}

            {streak > 0 && (
              <div
                className="flex items-center gap-1 px-3 py-1.5 rounded-xl bg-orange-50 text-orange-700 border border-orange-200/70 font-extrabold text-xs sm:text-sm shadow-xs"
                title={`Kunlik seriya: ${streak} kun`}
              >
                <span aria-hidden="true">🔥</span>
                <span>{streak}</span>
              </div>
            )}

            <div className="flex items-center gap-1 px-3 py-1.5 rounded-xl bg-amber-50 text-amber-700 border border-amber-200/60 font-extrabold text-xs sm:text-sm shadow-xs">
              <IconStar size={15} filled className="text-amber-500" />
              <span>{stars}</span>
            </div>
          </div>
        </div>
      </header>

      {/* ================= MOBILE BOTTOM NAVIGATION BAR ================= */}
      <nav className="fixed inset-x-0 bottom-0 z-40 md:hidden border-t border-slate-200/80 bg-white/95 backdrop-blur-md pb-[env(safe-area-inset-bottom,0px)] shadow-lg">
        <div className="grid grid-flow-col auto-cols-fr px-1 py-1">
          {tabs.map((tab) => {
            const active = currentTab === tab.key;
            const Icon = tab.icon;
            return (
              <button
                key={tab.key}
                onClick={() => handleTabClick(tab.key)}
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
                <span className="text-[9.5px] tracking-tight mt-0.5 leading-none">{tab.label}</span>
              </button>
            );
          })}
        </div>
      </nav>
    </>
  );
}
