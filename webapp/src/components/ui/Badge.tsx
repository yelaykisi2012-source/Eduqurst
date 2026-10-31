import type { HTMLAttributes, ReactNode } from "react";

type BadgeVariant = "blue" | "amber" | "emerald" | "purple" | "slate" | "rose";
type BadgeSize = "sm" | "md";

interface BadgeProps extends HTMLAttributes<HTMLSpanElement> {
  variant?: BadgeVariant;
  size?: BadgeSize;
  icon?: ReactNode;
}

export default function Badge({
  children,
  variant = "blue",
  size = "md",
  icon,
  className = "",
  ...props
}: BadgeProps) {
  const variantStyles: Record<BadgeVariant, string> = {
    blue: "bg-blue-50 text-blue-700 border border-blue-200/60",
    amber: "bg-amber-50 text-amber-700 border border-amber-200/60",
    emerald: "bg-emerald-50 text-emerald-700 border border-emerald-200/60",
    purple: "bg-purple-50 text-purple-700 border border-purple-200/60",
    slate: "bg-slate-100 text-slate-700 border border-slate-200/60",
    rose: "bg-rose-50 text-rose-700 border border-rose-200/60",
  };

  const sizeStyles: Record<BadgeSize, string> = {
    sm: "px-2 py-0.5 text-[11px] font-semibold gap-1",
    md: "px-3 py-1 text-xs font-bold gap-1.5",
  };

  return (
    <span
      className={`inline-flex items-center rounded-full ${variantStyles[variant]} ${sizeStyles[size]} ${className}`}
      {...props}
    >
      {icon && <span className="shrink-0">{icon}</span>}
      <span>{children}</span>
    </span>
  );
}
