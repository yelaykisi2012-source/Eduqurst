import { useEffect, type ReactNode } from "react";
import { createPortal } from "react-dom";

import { IconClose } from "./Icons";

interface SheetProps {
  open: boolean;
  title: string;
  /** Small grey line under the title — what the sheet is for. */
  subtitle?: string;
  onClose: () => void;
  children: ReactNode;
  /** Pinned under the scroll area: the sheet's own buttons (Save / Add). */
  footer?: ReactNode;
}

/**
 * A bottom sheet — the shape a phone app uses for "do one small thing".
 *
 * It is not a modal centred on the screen: a pupil holds the phone in one hand
 * and the keyboard pushes the page up, so the panel that slides from the bottom
 * keeps its inputs under the thumb. `max-h-[88dvh]` is what stops a long people
 * list from covering the whole screen with no way back.
 */
export default function Sheet({ open, title, subtitle, onClose, children, footer }: SheetProps) {
  // Escape closes it (a keyboard user must always have a way out), and the body
  // behind the sheet stops scrolling while it is open — otherwise dragging the
  // list inside a sheet also scrolls the chat behind it.
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    const previous = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      window.removeEventListener("keydown", onKey);
      document.body.style.overflow = previous;
    };
  }, [open, onClose]);

  if (!open) return null;

  // Portalled to <body> on purpose. The page container keeps a `transform` from
  // its entrance animation, and a transformed ancestor captures position:fixed:
  // rendered in place, this sheet stopped at the page's edge and the bottom nav
  // painted over the pupil's own "Chat ochish" button on a 320px phone.
  return createPortal(
    <div className="fixed inset-0 z-50 flex flex-col justify-end" role="dialog" aria-modal="true" aria-label={title}>
      <button
        type="button"
        aria-label="Yopish"
        onClick={onClose}
        className="absolute inset-0 bg-slate-900/45 backdrop-blur-[2px] animate-fade-in cursor-pointer"
      />
      <div className="relative mx-auto flex w-full max-w-2xl flex-col rounded-t-3xl bg-white shadow-2xl animate-sheet-up pb-[env(safe-area-inset-bottom,0px)]">
        <div className="flex items-start gap-2 border-b border-slate-100 px-4 py-3 sm:px-5">
          <div className="min-w-0 flex-1">
            <h2 className="text-sm sm:text-base font-black text-slate-900 truncate">{title}</h2>
            {subtitle && (
              <p className="mt-0.5 text-[11px] sm:text-xs font-semibold text-slate-500">{subtitle}</p>
            )}
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Yopish"
            className="flex h-8 w-8 shrink-0 items-center justify-center rounded-xl bg-slate-100 text-slate-500 hover:bg-slate-200 hover:text-slate-700 cursor-pointer"
          >
            <IconClose size={16} />
          </button>
        </div>

        <div className="max-h-[68dvh] overflow-y-auto px-4 py-3.5 sm:px-5">{children}</div>

        {footer && (
          <div className="border-t border-slate-100 bg-slate-50/70 px-4 py-3 sm:px-5">{footer}</div>
        )}
      </div>
    </div>,
    document.body,
  );
}
