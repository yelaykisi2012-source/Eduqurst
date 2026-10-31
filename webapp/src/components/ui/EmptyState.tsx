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
      className={`flex flex-col items-center justify-center p-8 sm:p-10 text-center rounded-3xl border-2 border-dashed border-slate-200 bg-white/70 shadow-xs ${className}`}
    >
      {icon ? (
        <div className="mb-4 flex h-14 w-14 items-center justify-center rounded-2xl bg-blue-50 text-blue-600 shadow-xs">
          {icon}
        </div>
      ) : (
        <span className="text-4xl mb-4" aria-hidden>
          📚
        </span>
      )}
      <h3 className="text-base sm:text-lg font-bold text-slate-800">{title}</h3>
      <p className="mt-1.5 max-w-sm text-xs sm:text-sm text-slate-500 leading-relaxed">
        {description}
      </p>
      {actionText && onAction && (
        <div className="mt-5">
          <Button variant="secondary" size="sm" onClick={onAction}>
            {actionText}
          </Button>
        </div>
      )}
    </div>
  );
}
