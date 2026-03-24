"use client";

import { useMemo } from "react";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface PaginationProps {
  /** Total number of items across all pages. */
  total: number;
  /** Current active page (1-indexed). */
  current: number;
  /** Called when the user navigates to a different page. */
  onPageChange: (page: number) => void;
  /** Items per page. Defaults to 25. */
  pageSize?: number;
  /** Additional class names on the root container. */
  className?: string;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

/**
 * Page navigation control for large result sets. Renders Previous/Next
 * arrows flanking a set of page number buttons with intelligent ellipsis
 * compression for large ranges.
 *
 * The current page button uses an amber background matching the platform
 * accent system. Ellipsis placeholders appear when the page count exceeds
 * 7, compressing the middle range while always showing the first page,
 * last page, and a 3-page window around the current position.
 *
 * All buttons receive appropriate disabled states at range boundaries,
 * communicated both visually (reduced opacity) and semantically
 * (aria-disabled, disabled attribute).
 */
export function Pagination({
  total,
  current,
  onPageChange,
  pageSize = 25,
  className = "",
}: PaginationProps) {
  const totalPages = Math.max(1, Math.ceil(total / pageSize));

  // Build the page number array with ellipsis placeholders
  const pageNumbers = useMemo(() => {
    const items: (number | "ellipsis-start" | "ellipsis-end")[] = [];

    if (totalPages <= 7) {
      for (let i = 1; i <= totalPages; i++) items.push(i);
      return items;
    }

    items.push(1);

    if (current > 3) {
      items.push("ellipsis-start");
    }

    const rangeStart = Math.max(2, current - 1);
    const rangeEnd = Math.min(totalPages - 1, current + 1);

    for (let i = rangeStart; i <= rangeEnd; i++) {
      items.push(i);
    }

    if (current < totalPages - 2) {
      items.push("ellipsis-end");
    }

    items.push(totalPages);

    return items;
  }, [totalPages, current]);

  if (totalPages <= 1) return null;

  return (
    <nav
      role="navigation"
      aria-label="Pagination"
      className={`flex items-center gap-1 ${className}`}
    >
      {/* Previous */}
      <button
        type="button"
        onClick={() => onPageChange(current - 1)}
        disabled={current <= 1}
        aria-label="Go to previous page"
        data-cursor="pointer"
        className="rounded px-2 py-1 text-xs text-text-secondary bg-surface-raised hover:bg-surface-overlay disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
      >
        <svg
          width="14"
          height="14"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
        >
          <path d="M15 18l-6-6 6-6" />
        </svg>
      </button>

      {/* Page numbers */}
      {pageNumbers.map((item) => {
        if (typeof item === "string") {
          return (
            <span
              key={item}
              className="px-1.5 py-1 text-xs text-text-muted select-none"
              aria-hidden="true"
            >
              &hellip;
            </span>
          );
        }

        const isCurrent = item === current;
        return (
          <button
            key={item}
            type="button"
            onClick={() => onPageChange(item)}
            aria-label={`Page ${item}`}
            aria-current={isCurrent ? "page" : undefined}
            data-cursor="pointer"
            className={`min-w-[28px] rounded px-2 py-1 text-xs font-medium transition-colors ${
              isCurrent
                ? "bg-accent text-text-inverse"
                : "bg-surface-raised text-text-secondary hover:bg-surface-overlay"
            }`}
          >
            {item}
          </button>
        );
      })}

      {/* Next */}
      <button
        type="button"
        onClick={() => onPageChange(current + 1)}
        disabled={current >= totalPages}
        aria-label="Go to next page"
        data-cursor="pointer"
        className="rounded px-2 py-1 text-xs text-text-secondary bg-surface-raised hover:bg-surface-overlay disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
      >
        <svg
          width="14"
          height="14"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
        >
          <path d="M9 18l6-6-6-6" />
        </svg>
      </button>
    </nav>
  );
}
