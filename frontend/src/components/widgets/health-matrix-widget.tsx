"use client";

import { useCallback, useEffect, useState } from "react";
import { useDataProvider } from "@/lib/data-providers";
import type { SubsystemHealth } from "@/lib/data-providers";

/**
 * Status-to-color mapping for health indicator dots. Colors correspond
 * to the platform's severity taxonomy: green for nominal, amber for
 * degraded, red for outage, gray for unknown/unreachable.
 */
const STATUS_DOT: Record<SubsystemHealth["status"], string> = {
  up: "bg-fizz-400",
  degraded: "bg-amber-400",
  down: "bg-red-500",
  unknown: "bg-panel-500",
};

const STATUS_TEXT: Record<SubsystemHealth["status"], string> = {
  up: "text-fizz-400",
  degraded: "text-amber-400",
  down: "text-red-400",
  unknown: "text-panel-500",
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
 */
export function HealthMatrixWidget() {
  const provider = useDataProvider();
  const [health, setHealth] = useState<SubsystemHealth[]>([]);

  const refresh = useCallback(async () => {
    const data = await provider.getSystemHealth();
    // Sort: critical statuses first, then alphabetical within tier
    data.sort((a, b) => {
      const priorityDiff = STATUS_PRIORITY[a.status] - STATUS_PRIORITY[b.status];
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
      <div className="flex h-40 items-center justify-center">
        <span className="text-xs text-panel-500">Probing subsystem health...</span>
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
          <span className="text-amber-400">{degradedCount} degraded</span>
        )}
        {downCount > 0 && (
          <span className="text-red-400">{downCount} down</span>
        )}
        <span className="ml-auto text-panel-500">{health.length} subsystems</span>
      </div>

      {/* Grid */}
      <div className="grid grid-cols-2 gap-1.5">
        {health.map((subsystem) => (
          <div
            key={subsystem.name}
            className="flex items-center gap-2 rounded px-2 py-1.5 bg-panel-900 border border-panel-700"
            title={`${subsystem.name}: ${subsystem.status} (${subsystem.responseTimeMs}ms)`}
          >
            <span
              className={`h-2 w-2 shrink-0 rounded-full ${STATUS_DOT[subsystem.status]} ${
                subsystem.status === "down" ? "animate-pulse" : ""
              }`}
            />
            <span className="text-[11px] text-panel-300 truncate">
              {subsystem.name}
            </span>
            {subsystem.status !== "down" && (
              <span className={`ml-auto text-[10px] font-mono ${STATUS_TEXT[subsystem.status]}`}>
                {subsystem.responseTimeMs.toFixed(1)}ms
              </span>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
