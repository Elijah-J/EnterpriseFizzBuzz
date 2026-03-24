"use client";

import { useCallback, useState } from "react";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface CopyButtonProps {
  /** The text string to copy to the clipboard. */
  text: string;
  /** Additional class names on the button element. */
  className?: string;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

/**
 * Clipboard copy trigger with visual confirmation feedback. On click,
 * the provided text is written to the system clipboard via the
 * Clipboard API, and the button icon transitions from a copy glyph
 * to a checkmark for 2 seconds before reverting.
 *
 * This two-state visual pattern provides immediate, unambiguous
 * confirmation that the copy operation completed without requiring
 * toast notifications or other overlay feedback mechanisms.
 */
export function CopyButton({ text, className = "" }: CopyButtonProps) {
  const [copied, setCopied] = useState(false);

  const handleCopy = useCallback(async () => {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // Fallback for non-secure contexts — no-op, user can manually select and copy
    }
  }, [text]);

  return (
    <button
      type="button"
      onClick={handleCopy}
      data-cursor="pointer"
      className={`inline-flex items-center justify-center rounded p-1 text-text-muted hover:text-text-secondary hover:bg-surface-overlay transition-colors ${className}`}
      aria-label={copied ? "Copied to clipboard" : "Copy to clipboard"}
      title={copied ? "Copied" : "Copy to clipboard"}
    >
      {copied ? (
        <svg
          width="14"
          height="14"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
          className="text-fizz-400"
        >
          <path d="M20 6L9 17l-5-5" />
        </svg>
      ) : (
        <svg
          width="14"
          height="14"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
        >
          <rect x="9" y="9" width="13" height="13" rx="2" ry="2" />
          <path d="M5 15H4a2 2 0 01-2-2V4a2 2 0 012-2h9a2 2 0 012 2v1" />
        </svg>
      )}
    </button>
  );
}
