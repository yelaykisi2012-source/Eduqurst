import type { ReactNode } from "react";
import Button from "./Button";

interface EmptyStateProps {
  icon?: ReactNode;
  title: string;
  description: string;
  actionText?: string;
  onAction?: () => void;
  className?: string;
}

export default function EmptyState({
  icon,
  title,
  description,
  actionText,
  onAction,
  className = "",
}: EmptyStateProps) {
  return (
    <div
      className={`flex flex-col items-center justify-center p-5 sm:p-8 text-center rounded-2xl sm:rounded-3xl border-2 border-dashed border-slate-200 bg-white/70 shadow-2xs ${className}`}
    >
      {icon ? (
        <div className="mb-2.5 flex h-11 w-11 sm:h-13 sm:w-13 items-center justify-center rounded-2xl bg-blue-50 text-blue-600 shadow-2xs">
          {icon}
        </div>
      ) : (
        <span className="text-3xl sm:text-4xl mb-2.5" aria-hidden>
          📚
        </span>
      )}
      <h3 className="text-sm sm:text-base font-bold text-slate-800">{title}</h3>
      <p className="mt-1 max-w-sm text-xs sm:text-sm text-slate-500 leading-relaxed">
        {description}
      </p>
      {actionText && onAction && (
        <div className="mt-3.5">
          <Button variant="secondary" size="sm" onClick={onAction}>
            {actionText}
          </Button>
        </div>
      )}
    </div>
  );
}
