"use client";

import { useCallback } from "react";

/**
 * Reusable chart legend component for the Enterprise FizzBuzz
 * data visualization system.
 *
 * Supports horizontal and vertical layouts with interactive toggle
 * and highlight behaviors. Each legend item consists of a colored
 * indicator dot and label. Click-to-toggle removes the corresponding
 * series from the chart. Hover-to-highlight dims non-hovered items,
 * providing rapid visual association between legend entries and
 * chart elements.
 */

export interface ChartLegendItem {
  /** Unique identifier for the series. */
  key: string;
  /** Human-readable label. */
  label: string;
  /** CSS color value for the indicator dot. */
  color: string;
  /** Whether the series is currently visible in the chart. */
  active: boolean;
}

interface ChartLegendProps {
  /** Legend items corresponding to chart series. */
  items: ChartLegendItem[];
  /** Layout direction. Default horizontal. */
  orientation?: "horizontal" | "vertical";
  /** Callback fired when a legend item is toggled. */
  onToggle?: (key: string) => void;
  /** Currently highlighted series key (on hover). */
  highlightedKey?: string | null;
  /** Callback fired when a legend item is hovered. */
  onHighlight?: (key: string | null) => void;
}

export function ChartLegend({
  items,
  orientation = "horizontal",
  onToggle,
  highlightedKey,
  onHighlight,
}: ChartLegendProps) {
  const handleClick = useCallback(
    (key: string) => {
      onToggle?.(key);
    },
    [onToggle],
  );

  return (
    <div
      className={`flex gap-3 ${
        orientation === "vertical" ? "flex-col" : "flex-row flex-wrap"
      }`}
      role="group"
      aria-label="Chart legend"
    >
      {items.map((item) => {
        const dimmed =
          highlightedKey !== null &&
          highlightedKey !== undefined &&
          highlightedKey !== item.key;
        const inactive = !item.active;

        return (
          <button
            key={item.key}
            type="button"
            className="inline-flex items-center gap-1.5 text-xs transition-opacity duration-150 hover:opacity-80"
            style={{
              opacity: dimmed ? 0.4 : inactive ? 0.5 : 1,
            }}
            onClick={() => handleClick(item.key)}
            onMouseEnter={() => onHighlight?.(item.key)}
            onMouseLeave={() => onHighlight?.(null)}
            aria-pressed={item.active}
            aria-label={`Toggle ${item.label} series`}
          >
            <span
              className="inline-block h-2.5 w-2.5 rounded-full shrink-0"
              style={{
                backgroundColor: item.active ? item.color : "var(--text-muted)",
              }}
            />
            <span
              className={`font-sans ${inactive ? "text-text-muted line-through" : "text-text-secondary"}`}
            >
              {item.label}
            </span>
          </button>
        );
      })}
    </div>
  );
}
