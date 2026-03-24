"use client";

import { useEffect, useState } from "react";

interface LiveIndicatorProps {
  /** Timestamp (ms since epoch) of the last data update. */
  lastUpdated: number | null;
  /** Whether the data source is considered stale. */
  isStale?: boolean;
}

/**
 * Formats elapsed seconds into a human-readable relative timestamp.
 * Uses the most appropriate unit to maintain spatial compactness
 * in the top bar layout.
 */
function formatRelativeTime(seconds: number): string {
  if (seconds < 5) return "just now";
  if (seconds < 60) return `${seconds}s ago`;
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  return `${hours}h ago`;
}

/**
 * Real-time data freshness indicator for the Enterprise FizzBuzz Platform.
 *
 * Replaces the static "All Systems Operational" text in the top bar with
 * a temporal context indicator that communicates when the most recent
 * telemetry data was received. The amber dot pulses gently to signal
 * live connectivity; when data becomes stale, the indicator transitions
 * to a muted state with explicit temporal distance.
 *
 * The relative timestamp auto-updates every second to maintain accuracy
 * without requiring parent re-renders.
 */
export function LiveIndicator({
  lastUpdated,
  isStale = false,
}: LiveIndicatorProps) {
  const [elapsed, setElapsed] = useState(0);

  useEffect(() => {
    if (!lastUpdated) return;

    const update = () => {
      setElapsed(Math.floor((Date.now() - lastUpdated) / 1000));
    };

    update();
    const id = setInterval(update, 1000);
    return () => clearInterval(id);
  }, [lastUpdated]);

  if (!lastUpdated) {
    return (
      <span className="inline-flex items-center gap-1.5 text-xs text-text-muted">
        <span className="h-2 w-2 rounded-full bg-text-muted" />
        Connecting...
      </span>
    );
  }

  return (
    <span
      className={`inline-flex items-center gap-1.5 text-xs ${
        isStale ? "text-text-muted" : "text-text-secondary"
      }`}
    >
      <span
        className={`h-2 w-2 rounded-full transition-colors duration-300 ${
          isStale ? "bg-text-muted" : "bg-accent"
        }`}
      />
      {isStale ? (
        <>Data stale &mdash; {formatRelativeTime(elapsed)}</>
      ) : (
        <>Live &mdash; {formatRelativeTime(elapsed)}</>
      )}
    </span>
  );
}
