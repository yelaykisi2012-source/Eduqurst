import type { HTMLAttributes } from "react";

interface ProgressBarProps extends HTMLAttributes<HTMLDivElement> {
  value: number; // 0 to 100
  label?: string;
  showPercent?: boolean;
  size?: "sm" | "md" | "lg";
  gradient?: "blue" | "emerald" | "amber" | "purple";
}

export default function ProgressBar({
  value,
  label,
  showPercent = false,
  size = "md",
  gradient = "blue",
  className = "",
  ...props
}: ProgressBarProps) {
  const clamped = Math.max(0, Math.min(100, Math.round(value)));

  const sizeStyles = {
    sm: "h-1.5",
    md: "h-2.5",
    lg: "h-3.5",
  };

  const gradientStyles = {
    blue: "bg-gradient-to-r from-blue-500 to-indigo-600",
    emerald: "bg-gradient-to-r from-emerald-400 to-teal-500",
    amber: "bg-gradient-to-r from-amber-400 to-orange-500",
    purple: "bg-gradient-to-r from-purple-500 to-indigo-500",
  };

  return (
    <div className={`w-full ${className}`} {...props}>
      {(label || showPercent) && (
        <div className="flex items-center justify-between text-xs font-semibold text-slate-500 mb-1.5">
          {label && <span>{label}</span>}
          {showPercent && <span className="font-bold text-slate-700">{clamped}%</span>}
        </div>
      )}
      <div className={`w-full bg-slate-100 rounded-full overflow-hidden ${sizeStyles[size]}`}>
        <div
          className={`h-full rounded-full transition-all duration-500 ease-out ${gradientStyles[gradient]}`}
          style={{ width: `${clamped}%` }}
        />
      </div>
    </div>
  );
}
