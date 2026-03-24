"use client";

import {
  useCallback,
  useEffect,
  useRef,
  type KeyboardEvent,
  type MouseEvent,
  type ReactNode,
} from "react";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

type DialogSize = "sm" | "md" | "lg";

interface DialogProps {
  /** Controls visibility. When false, the dialog is removed from the visual flow. */
  open: boolean;
  /** Callback invoked when the user requests dismissal (Escape, backdrop click). */
  onClose: () => void;
  /** Optional heading rendered in the dialog header bar. */
  title?: string;
  /** Dialog content. */
  children: ReactNode;
  /** Width preset. sm=400px, md=560px, lg=720px. */
  size?: DialogSize;
  /** Additional class names on the content panel. */
  className?: string;
}

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const SIZE_CLASSES: Record<DialogSize, string> = {
  sm: "max-w-[400px]",
  md: "max-w-[560px]",
  lg: "max-w-[720px]",
};

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

/**
 * Modal dialog with focus trap, backdrop dismiss, and keyboard support.
 *
 * Focus management follows WAI-ARIA dialog pattern: on open, focus moves
 * to the first focusable element inside the panel. Tab and Shift+Tab cycle
 * between the first and last focusable descendants, preventing focus from
 * escaping to the page behind the backdrop. Pressing Escape closes the
 * dialog via the onClose callback.
 *
 * The entrance animation is a combined fade + 8px translateY slide,
 * matching the platform's enter motion vocabulary. The backdrop uses
 * surface-ground at 80% opacity, maintaining the warm stone palette
 * continuity even in overlay contexts.
 */
export function Dialog({
  open,
  onClose,
  title,
  children,
  size = "md",
  className = "",
}: DialogProps) {
  const panelRef = useRef<HTMLDivElement>(null);
  const previousFocusRef = useRef<HTMLElement | null>(null);

  // -----------------------------------------------------------------------
  // Focus management
  // -----------------------------------------------------------------------

  const getFocusableElements = useCallback((): HTMLElement[] => {
    if (!panelRef.current) return [];
    return Array.from(
      panelRef.current.querySelectorAll<HTMLElement>(
        'a[href], button:not([disabled]), textarea:not([disabled]), input:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex="-1"])',
      ),
    );
  }, []);

  // Trap focus on open
  useEffect(() => {
    if (!open) return;

    // Store the element that opened the dialog so we can restore focus on close
    previousFocusRef.current = document.activeElement as HTMLElement;

    // Defer focus to the next frame so the panel is rendered
    const raf = requestAnimationFrame(() => {
      const focusable = getFocusableElements();
      if (focusable.length > 0) {
        focusable[0].focus();
      } else {
        panelRef.current?.focus();
      }
    });

    return () => cancelAnimationFrame(raf);
  }, [open, getFocusableElements]);

  // Restore focus on close
  useEffect(() => {
    if (!open && previousFocusRef.current) {
      previousFocusRef.current.focus();
      previousFocusRef.current = null;
    }
  }, [open]);

  // Lock body scroll while open
  useEffect(() => {
    if (!open) return;
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = prev;
    };
  }, [open]);

  // -----------------------------------------------------------------------
  // Keyboard handling
  // -----------------------------------------------------------------------

  const handleKeyDown = useCallback(
    (e: KeyboardEvent<HTMLDivElement>) => {
      if (e.key === "Escape") {
        e.stopPropagation();
        onClose();
        return;
      }

      if (e.key === "Tab") {
        const focusable = getFocusableElements();
        if (focusable.length === 0) {
          e.preventDefault();
          return;
        }

        const first = focusable[0];
        const last = focusable[focusable.length - 1];

        if (e.shiftKey && document.activeElement === first) {
          e.preventDefault();
          last.focus();
        } else if (!e.shiftKey && document.activeElement === last) {
          e.preventDefault();
          first.focus();
        }
      }
    },
    [onClose, getFocusableElements],
  );

  // -----------------------------------------------------------------------
  // Backdrop click
  // -----------------------------------------------------------------------

  const handleBackdropClick = useCallback(
    (e: MouseEvent<HTMLDivElement>) => {
      if (e.target === e.currentTarget) {
        onClose();
      }
    },
    [onClose],
  );

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center"
      role="presentation"
      onKeyDown={handleKeyDown}
    >
      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-surface-ground/80 animate-[dialog-backdrop_150ms_ease-out_forwards]"
        aria-hidden="true"
        onClick={handleBackdropClick}
      />

      {/* Panel */}
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-label={title}
        tabIndex={-1}
        className={`relative z-10 w-full ${SIZE_CLASSES[size]} rounded-lg border border-border-subtle bg-surface-raised shadow-2xl animate-[dialog-enter_200ms_ease-out_forwards] focus-visible:outline-none ${className}`}
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        {title && (
          <div className="flex items-center justify-between border-b border-border-subtle px-5 py-3.5">
            <h2 className="text-sm font-semibold text-text-primary">
              {title}
            </h2>
            <button
              type="button"
              onClick={onClose}
              data-cursor="pointer"
              className="rounded p-1 text-text-muted hover:text-text-secondary hover:bg-surface-overlay transition-colors"
              aria-label="Close dialog"
            >
              <svg
                width="16"
                height="16"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
              >
                <path d="M18 6L6 18M6 6l12 12" />
              </svg>
            </button>
          </div>
        )}

        {/* Body */}
        <div className="px-5 py-4">{children}</div>
      </div>
    </div>
  );
}
