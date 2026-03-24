import type { ReactNode } from "react";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

type TimelineStatus = "default" | "active" | "success" | "error";

interface TimelineItem {
  /** ISO-8601 timestamp or display string for the left column. */
  timestamp: string;
  /** Primary heading for this timeline event. */
  title: string;
  /** Optional body content rendered below the title. */
  content?: ReactNode;
  /** Dot color mapping. Defaults to "default". */
  status?: TimelineStatus;
  /** Optional unique key. */
  key?: string;
}

interface TimelineProps {
  /** Ordered list of timeline events, earliest first. */
  items: TimelineItem[];
  /** Additional class names on the root container. */
  className?: string;
}

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const STATUS_DOT_COLORS: Record<TimelineStatus, string> = {
  default: "bg-surface-overlay",
  active: "bg-accent",
  success: "bg-fizz-500",
  error: "bg-red-500",
};

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

/**
 * Vertical timeline for displaying chronologically ordered events.
 *
 * Layout follows a two-column structure: timestamps on the left, event
 * content on the right, separated by a vertical track with status-colored
 * dot indicators. The connecting line uses the border-subtle token, and
 * dots are color-mapped via the status prop: amber for active/in-progress,
 * green for success, red for error, and surface-overlay as the neutral
 * default.
 *
 * Each event card is a minimal content block — title and optional body —
 * that integrates with the platform's text-secondary color for consistent
 * information density across monitoring and audit interfaces.
 */
export function Timeline({ items, className = "" }: TimelineProps) {
  if (items.length === 0) return null;

  return (
    <div className={`relative ${className}`}>
      {items.map((item, i) => {
        const isLast = i === items.length - 1;
        const status = item.status ?? "default";
        return (
          <div
            key={item.key ?? i}
            className="relative flex gap-4 pb-4 last:pb-0"
          >
            {/* Left column — timestamp */}
            <div className="w-20 shrink-0 pt-0.5 text-right">
              <span className="text-[10px] font-mono text-text-muted leading-tight">
                {item.timestamp}
              </span>
            </div>

            {/* Center column — dot + connecting line */}
            <div className="relative flex flex-col items-center">
              <div
                className={`z-10 h-2.5 w-2.5 rounded-full shrink-0 mt-1 ${STATUS_DOT_COLORS[status]}`}
              />
              {!isLast && (
                <div className="w-px flex-1 bg-border-subtle mt-1" />
              )}
            </div>

            {/* Right column — content */}
            <div className="flex-1 min-w-0 pb-2">
              <p className="text-xs font-medium text-text-primary leading-tight">
                {item.title}
              </p>
              {item.content && (
                <div className="mt-1 text-xs text-text-secondary">
                  {item.content}
                </div>
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
}
