import type { HTMLAttributes, MouseEvent } from "react";

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
    sm: "p-2.5 sm:p-3.5",
    md: "p-3.5 sm:p-5",
    lg: "p-4 sm:p-7",
  };

  const variantStyles = {
    default: "bg-white border border-slate-100/90 shadow-xs sm:shadow-sm rounded-2xl sm:rounded-3xl",
    elevated: "bg-white border border-slate-100/80 shadow-sm sm:shadow-md shadow-slate-200/50 rounded-2xl sm:rounded-3xl",
    flat: "bg-slate-50/80 border border-slate-100 rounded-xl sm:rounded-2xl",
    interactive:
      "bg-white border border-slate-100/90 shadow-xs sm:shadow-sm hover:shadow-md hover:border-blue-100 transition-all duration-200 rounded-2xl sm:rounded-3xl cursor-pointer active:scale-[0.99]",
  };

  return (
    <div
      className={`${variantStyles[variant]} ${paddingStyles[padding]} ${
        props.onClick ? "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-400/70 focus-visible:ring-offset-2 " : ""
      }${className}`}
      // An "interactive" card is a button that happens to look like a card.
      // Without these two attributes a pupil on a keyboard (or a screen reader)
      // can never reach the subject list, because a plain <div> is not focusable.
      role={props.onClick ? "button" : undefined}
      tabIndex={props.onClick ? 0 : undefined}
      onKeyDown={
        props.onClick
          ? (e) => {
              if (e.key === "Enter" || e.key === " ") {
                e.preventDefault();
                props.onClick?.(e as unknown as MouseEvent<HTMLDivElement>);
              }
            }
          : undefined
      }
      {...props}
    >
      {children}
    </div>
  );
}
