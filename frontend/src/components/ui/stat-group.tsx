import type { ReactNode } from "react";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

type TrendDirection = "up" | "down" | "neutral";

interface StatItem {
  /** Descriptive label for the metric. */
  label: string;
  /** Display value (pre-formatted string). */
  value: string;
  /** Optional trend indicator. */
  trend?: {
    direction: TrendDirection;
    /** Display text, e.g. "+12.5%" or "-3 events". */
    label: string;
  };
  /** Optional icon or element rendered beside the value. */
  icon?: ReactNode;
}

interface StatGroupProps {
  /** Stat items to render in a horizontal row. */
  items: StatItem[];
  /** Additional class names on the root container. */
  className?: string;
}

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const TREND_STYLES: Record<TrendDirection, string> = {
  up: "text-fizz-400",
  down: "text-red-400",
  neutral: "text-text-muted",
};

const TREND_ARROWS: Record<TrendDirection, string> = {
  up: "\u2191",
  down: "\u2193",
  neutral: "\u2192",
};

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

/**
 * Horizontal stat row for KPI summary displays. Each stat item presents
 * a label-value pair with an optional trend indicator (direction arrow
 * and percentage/delta label). Items are separated by subtle vertical
 * dividers that collapse on mobile, where the layout switches to a
 * responsive 2-column grid.
 *
 * Trend colors follow the platform's semantic palette: fizz-400 (green)
 * for upward trends, red-400 for downward, and text-muted for neutral.
 * Values use the monospace font with tabular numerals for consistent
 * column alignment across changing data.
 */
export function StatGroup({ items, className = "" }: StatGroupProps) {
  if (items.length === 0) return null;

  return (
    <div
      className={`grid grid-cols-2 gap-4 sm:flex sm:items-start sm:gap-0 sm:divide-x sm:divide-border-subtle ${className}`}
    >
      {items.map((item, i) => (
        <div
          key={i}
          className="flex flex-col gap-0.5 sm:px-4 first:sm:pl-0 last:sm:pr-0"
        >
          <span className="text-[10px] uppercase tracking-wider text-text-muted font-medium">
            {item.label}
          </span>
          <div className="flex items-baseline gap-1.5">
            {item.icon && (
              <span className="shrink-0 text-text-muted">{item.icon}</span>
            )}
            <span className="text-lg font-mono font-semibold text-text-primary tabular-nums">
              {item.value}
            </span>
          </div>
          {item.trend && (
            <span
              className={`text-[10px] font-medium ${TREND_STYLES[item.trend.direction]}`}
            >
              {TREND_ARROWS[item.trend.direction]} {item.trend.label}
            </span>
          )}
        </div>
      ))}
    </div>
  );
}
