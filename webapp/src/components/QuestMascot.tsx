/**
 * Quest — the friendly blue-and-white robot mascot.
 * Drawn as inline SVG so it needs no image files or network access.
 */
export default function QuestMascot({ size = 96 }: { size?: number }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 120 120"
      role="img"
      aria-label="Quest robot"
      className="animate-float"
    >
      {/* antenna */}
      <line x1="60" y1="18" x2="60" y2="8" stroke="#1D4ED8" strokeWidth="4" strokeLinecap="round" />
      <circle cx="60" cy="8" r="5" fill="#3B82F6" />
      {/* head */}
      <rect x="28" y="18" width="64" height="52" rx="16" fill="#FFFFFF" stroke="#1D4ED8" strokeWidth="4" />
      {/* eyes */}
      <circle cx="46" cy="42" r="7" fill="#1D4ED8" />
      <circle cx="74" cy="42" r="7" fill="#1D4ED8" />
      <circle cx="48" cy="40" r="2.5" fill="#BFDBFE" />
      <circle cx="76" cy="40" r="2.5" fill="#BFDBFE" />
      {/* smile */}
      <path d="M48 56 Q60 64 72 56" fill="none" stroke="#1D4ED8" strokeWidth="4" strokeLinecap="round" />
      {/* body */}
      <rect x="38" y="76" width="44" height="32" rx="10" fill="#3B82F6" stroke="#1D4ED8" strokeWidth="4" />
      {/* star badge on chest */}
      <path
        d="M60 82 l3.2 6.6 7.2 1 -5.2 5.1 1.2 7.2 -6.4 -3.4 -6.4 3.4 1.2 -7.2 -5.2 -5.1 7.2 -1 z"
        fill="#FDE047"
        stroke="#F59E0B"
        strokeWidth="1.5"
      />
      {/* arms */}
      <rect x="20" y="80" width="12" height="8" rx="4" fill="#FFFFFF" stroke="#1D4ED8" strokeWidth="3" />
      <rect x="88" y="80" width="12" height="8" rx="4" fill="#FFFFFF" stroke="#1D4ED8" strokeWidth="3" />
    </svg>
  );
}
