import type { ButtonHTMLAttributes, ReactNode } from "react";

type ButtonVariant = "primary" | "secondary" | "accent" | "outline" | "ghost" | "danger" | "success";
type ButtonSize = "sm" | "md" | "lg";

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  size?: ButtonSize;
  loading?: boolean;
  icon?: ReactNode;
  iconRight?: ReactNode;
  fullWidth?: boolean;
}

export default function Button({
  children,
  variant = "primary",
  size = "md",
  loading = false,
  icon,
  iconRight,
  fullWidth = false,
  className = "",
  disabled,
  ...props
}: ButtonProps) {
  const baseStyles =
    "inline-flex items-center justify-center font-bold transition-all duration-150 rounded-2xl active:scale-[0.98] disabled:opacity-50 disabled:pointer-events-none disabled:active:scale-100 select-none cursor-pointer";

  const sizeStyles: Record<ButtonSize, string> = {
    sm: "px-3.5 py-2 text-xs gap-1.5",
    md: "px-5 py-3 text-sm gap-2",
    lg: "px-6 py-4 text-base gap-2.5",
  };

  const variantStyles: Record<ButtonVariant, string> = {
    primary:
      "bg-[#3478F6] text-white hover:bg-blue-600 shadow-sm hover:shadow-md hover:shadow-blue-500/20 active:bg-blue-700",
    secondary:
      "bg-white text-slate-800 border border-slate-200 hover:bg-slate-50 hover:border-slate-300 shadow-xs",
    accent:
      "bg-gradient-to-r from-amber-400 to-amber-500 text-amber-950 font-extrabold hover:from-amber-500 hover:to-amber-600 shadow-sm shadow-amber-400/20",
    outline:
      "bg-transparent border-2 border-blue-500 text-blue-600 hover:bg-blue-50/70",
    ghost:
      "bg-transparent text-slate-600 hover:bg-slate-100/80 active:bg-slate-200/60",
    danger:
      "bg-rose-500 text-white hover:bg-rose-600 shadow-sm hover:shadow-rose-500/20",
    success:
      "bg-emerald-600 text-white hover:bg-emerald-700 shadow-sm hover:shadow-emerald-500/20",
  };

  return (
    <button
      className={`${baseStyles} ${sizeStyles[size]} ${variantStyles[variant]} ${
        fullWidth ? "w-full" : ""
      } ${className}`}
      disabled={disabled || loading}
      {...props}
    >
      {loading ? (
        <span className="flex items-center gap-2">
          <svg className="h-4 w-4 animate-spin" viewBox="0 0 24 24" fill="none">
            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v4a4 4 0 00-4 4H4z" />
          </svg>
          <span>Yuklanmoqda…</span>
        </span>
      ) : (
        <>
          {icon && <span className="shrink-0">{icon}</span>}
          <span>{children}</span>
          {iconRight && <span className="shrink-0">{iconRight}</span>}
        </>
      )}
    </button>
  );
}
