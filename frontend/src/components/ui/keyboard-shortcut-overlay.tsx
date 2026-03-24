"use client";

import { useCallback, useEffect, useRef } from "react";

interface ShortcutGroup {
  label: string;
  shortcuts: { keys: string; description: string }[];
}

const SHORTCUT_GROUPS: ShortcutGroup[] = [
  {
    label: "Navigation",
    shortcuts: [
      { keys: "j / k", description: "Next / previous card" },
      { keys: "[ / ]", description: "Previous / next page" },
      { keys: "g g", description: "Scroll to top" },
      { keys: "G", description: "Scroll to bottom" },
    ],
  },
  {
    label: "Search & Commands",
    shortcuts: [
      { keys: "\u2318K", description: "Open command palette" },
      { keys: "/", description: "Focus search" },
      { keys: "?", description: "Toggle this overlay" },
    ],
  },
  {
    label: "Actions",
    shortcuts: [
      { keys: "\u2318B", description: "Toggle sidebar" },
      { keys: "Esc", description: "Clear focus / close overlay" },
    ],
  },
];

interface KeyboardShortcutOverlayProps {
  open: boolean;
  onClose: () => void;
}

/**
 * Full-screen keyboard shortcut reference overlay for the Enterprise
 * FizzBuzz Operations Center.
 *
 * Displays all available keyboard shortcuts in a categorized grid layout,
 * enabling operators to quickly reference the platform's navigation vocabulary
 * without consulting external documentation. The overlay uses the standard
 * surface-base background with subtle border treatment, consistent with
 * the Warm Precision design language.
 *
 * Activated via the `?` key and dismissed via Escape or click outside.
 */
export function KeyboardShortcutOverlay({
  open,
  onClose,
}: KeyboardShortcutOverlayProps) {
  const panelRef = useRef<HTMLDivElement>(null);

  const handleKeyDown = useCallback(
    (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.preventDefault();
        onClose();
      }
    },
    [onClose]
  );

  useEffect(() => {
    if (!open) return;
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [open, handleKeyDown]);

  const handleBackdropClick = useCallback(
    (e: React.MouseEvent) => {
      if (panelRef.current && !panelRef.current.contains(e.target as Node)) {
        onClose();
      }
    },
    [onClose]
  );

  if (!open) return null;

  return (
    // biome-ignore lint/a11y/useKeyWithClickEvents: Backdrop dismiss on click is standard overlay UX
    <div
      className="fixed inset-0 z-50 flex items-center justify-center"
      style={{ animation: "enter 150ms ease-out" }}
      onClick={handleBackdropClick}
    >
      {/* Backdrop */}
      <div className="absolute inset-0 bg-surface-ground/80" />

      {/* Panel */}
      <div
        ref={panelRef}
        className="relative w-full max-w-2xl rounded-lg border border-border-subtle bg-surface-base p-6 mx-4"
        role="dialog"
        aria-modal="true"
        aria-label="Keyboard shortcuts"
      >
        <div className="flex items-center justify-between mb-6">
          <h2 className="heading-page text-lg">Keyboard Shortcuts</h2>
          <button
            type="button"
            onClick={onClose}
            className="flex items-center justify-center w-8 h-8 rounded text-text-muted hover:bg-surface-raised hover:text-text-secondary transition-colors duration-150"
            aria-label="Close keyboard shortcuts"
          >
            <svg
              width="16"
              height="16"
              viewBox="0 0 16 16"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.5"
              strokeLinecap="round"
              aria-hidden="true"
            >
              <path d="M4 4l8 8M12 4l-8 8" />
            </svg>
          </button>
        </div>

        <div className="grid grid-cols-1 gap-6 sm:grid-cols-3">
          {SHORTCUT_GROUPS.map((group) => (
            <div key={group.label}>
              <h3 className="heading-section mb-3">{group.label}</h3>
              <ul className="space-y-2">
                {group.shortcuts.map((shortcut) => (
                  <li
                    key={shortcut.keys}
                    className="flex items-center justify-between gap-3"
                  >
                    <span className="text-xs text-text-secondary">
                      {shortcut.description}
                    </span>
                    <kbd className="shrink-0 font-mono text-[11px] text-text-muted border border-border-subtle rounded px-1.5 py-0.5 bg-surface-raised">
                      {shortcut.keys}
                    </kbd>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>

        <p className="mt-6 text-[10px] text-text-muted text-center">
          Shortcuts are disabled when typing in input fields
        </p>
      </div>
    </div>
  );
}
