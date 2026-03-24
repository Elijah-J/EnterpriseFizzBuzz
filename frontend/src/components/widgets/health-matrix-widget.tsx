"use client";

import { useCallback, useEffect, useState } from "react";
import { Reveal } from "@/components/ui/reveal";
import { Skeleton } from "@/components/ui/skeleton";
import type { SubsystemHealth } from "@/lib/data-providers";
import { useDataProvider } from "@/lib/data-providers";

/**
 * Status-to-color mapping for health indicator dots. Colors correspond
 * to the platform's severity taxonomy using desaturated domain tones:
 * green for nominal, amber for degraded, red for outage, stone for unknown.
 */
const STATUS_DOT: Record<SubsystemHealth["status"], string> = {
  up: "bg-fizz-400",
  degraded: "bg-[var(--accent)]",
  down: "bg-[var(--status-error)]",
  unknown: "bg-text-muted",
};

const STATUS_TEXT: Record<SubsystemHealth["status"], string> = {
  up: "text-fizz-400",
  degraded: "text-[var(--accent)]",
  down: "text-[var(--status-error)]",
  unknown: "text-text-muted",
};

/**
 * Sort priority for health statuses. Critical statuses surface first
 * to ensure operators see degradations immediately without scrolling.
 */
const STATUS_PRIORITY: Record<SubsystemHealth["status"], number> = {
  down: 0,
  degraded: 1,
  unknown: 2,
  up: 3,
};

/**
 * Health Matrix Widget — Grid display of all infrastructure subsystem
 * health indicators. Subsystems with degraded or down status are sorted
 * to the top for immediate operator awareness. Auto-refreshes every
 * 5 seconds.
 *
 * Loading state uses a skeleton grid that matches the final layout
 * dimensions, preventing content shift on data arrival.
 */
export function HealthMatrixWidget() {
  const provider = useDataProvider();
  const [health, setHealth] = useState<SubsystemHealth[]>([]);

  const refresh = useCallback(async () => {
    const data = await provider.getSystemHealth();
    data.sort((a, b) => {
      const priorityDiff =
        STATUS_PRIORITY[a.status] - STATUS_PRIORITY[b.status];
      if (priorityDiff !== 0) return priorityDiff;
      return a.name.localeCompare(b.name);
    });
    setHealth(data);
  }, [provider]);

  useEffect(() => {
    refresh();
    const interval = setInterval(refresh, 5_000);
    return () => clearInterval(interval);
  }, [refresh]);

  if (health.length === 0) {
    return (
      <div className="space-y-3">
        <div className="flex gap-3">
          <Skeleton variant="text" width="4rem" />
          <Skeleton variant="text" width="6rem" />
        </div>
        <div className="grid grid-cols-2 gap-1.5">
          {Array.from({ length: 8 }, (_, i) => (
            // biome-ignore lint/suspicious/noArrayIndexKey: static skeleton placeholders with fixed count
            <Skeleton key={i} variant="rect" height="2rem" />
          ))}
        </div>
      </div>
    );
  }

  const upCount = health.filter((h) => h.status === "up").length;
  const degradedCount = health.filter((h) => h.status === "degraded").length;
  const downCount = health.filter((h) => h.status === "down").length;

  return (
    <div className="space-y-3">
      {/* Summary */}
      <div className="flex items-center gap-3 text-xs">
        <span className="text-fizz-400">{upCount} up</span>
        {degradedCount > 0 && (
          <span className="text-[var(--accent)]">{degradedCount} degraded</span>
        )}
        {downCount > 0 && (
          <span className="text-[var(--status-error)]">{downCount} down</span>
        )}
        <span className="ml-auto text-text-muted">
          {health.length} subsystems
        </span>
      </div>

      {/* Grid */}
      <div className="grid grid-cols-2 gap-1.5">
        {health.map((subsystem, index) => (
          <Reveal key={subsystem.name} delay={index * 20}>
            <div
              className="flex items-center gap-2 rounded px-2 py-1.5 bg-surface-base border border-border-subtle"
              title={`${subsystem.name}: ${subsystem.status} (${subsystem.responseTimeMs}ms)`}
            >
              <span
                className={`h-2 w-2 shrink-0 rounded-full transition-colors duration-300 ${STATUS_DOT[subsystem.status]}`}
              />
              <span className="text-[11px] text-text-secondary truncate">
                {subsystem.name}
              </span>
              {subsystem.status !== "down" && (
                <span
                  className={`ml-auto text-[10px] font-mono ${STATUS_TEXT[subsystem.status]}`}
                >
                  {subsystem.responseTimeMs.toFixed(1)}ms
                </span>
              )}
            </div>
          </Reveal>
        ))}
      </div>
    </div>
  );
}
