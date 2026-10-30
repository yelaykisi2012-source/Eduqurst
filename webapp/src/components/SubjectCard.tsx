/**
 * One tappable subject card on the home screen.
 * The subtitle tells the pupil how many levels exist / are done, so a card
 * with no content yet can honestly say "Tez orada" instead of pretending.
 */
export default function SubjectCard({
  title,
  emoji,
  gradient,
  subtitle,
  onClick,
}: {
  title: string;
  emoji: string;
  gradient: string; // tailwind classes
  subtitle: string;
  onClick: () => void;
}) {
  return (
    <button
      onClick={onClick}
      className={`w-full rounded-2xl bg-gradient-to-br ${gradient} p-4 text-left shadow-md transition-transform active:scale-95`}
    >
      <div className="flex items-center gap-3">
        <span className="text-4xl" aria-hidden>
          {emoji}
        </span>
        <div>
          <p className="text-lg font-bold text-white">{title}</p>
          <p className="text-sm text-blue-100">{subtitle}</p>
        </div>
      </div>
    </button>
  );
}
