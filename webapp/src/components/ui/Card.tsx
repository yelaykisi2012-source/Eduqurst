import type { HTMLAttributes } from "react";

interface CardProps extends HTMLAttributes<HTMLDivElement> {
  variant?: "default" | "elevated" | "flat" | "interactive";
  padding?: "none" | "sm" | "md" | "lg";
}

export default function Card({
  children,
  variant = "default",
  padding = "md",
  className = "",
  ...props
}: CardProps) {
  const paddingStyles = {
    none: "",
    sm: "p-3.5",
    md: "p-5",
    lg: "p-6 sm:p-8",
  };

  const variantStyles = {
    default: "bg-white border border-slate-100 shadow-sm rounded-3xl",
    elevated: "bg-white border border-slate-100/80 shadow-md shadow-slate-200/50 rounded-3xl",
    flat: "bg-slate-50/80 border border-slate-100 rounded-2xl",
    interactive:
      "bg-white border border-slate-100 shadow-sm hover:shadow-md hover:border-blue-100 transition-all duration-200 rounded-3xl cursor-pointer active:scale-[0.99]",
  };

  return (
    <div
      className={`${variantStyles[variant]} ${paddingStyles[padding]} ${className}`}
      {...props}
    >
      {children}
    </div>
  );
}
