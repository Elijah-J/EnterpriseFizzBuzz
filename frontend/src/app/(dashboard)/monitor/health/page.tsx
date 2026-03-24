"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Accordion } from "@/components/ui/accordion";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { Reveal } from "@/components/ui/reveal";
import { Skeleton } from "@/components/ui/skeleton";
import { StatGroup } from "@/components/ui/stat-group";
import type { HealthCheckPoint, SubsystemHealth } from "@/lib/data-providers";
import { useDataProvider } from "@/lib/data-providers";

// ---------------------------------------------------------------------------
// Status taxonomy
// ---------------------------------------------------------------------------

const STATUS_DOT: Record<SubsystemHealth["status"], string> = {
  up: "bg-fizz-400",
  degraded: "bg-amber-400",
  down: "bg-red-500",
  unknown: "bg-text-muted",
};

const STATUS_TEXT: Record<SubsystemHealth["status"], string> = {
  up: "text-fizz-400",
  degraded: "text-amber-400",
  down: "text-red-400",
  unknown: "text-text-muted",
};

const STATUS_PRIORITY: Record<SubsystemHealth["status"], number> = {
  down: 0,
  degraded: 1,
  unknown: 2,
  up: 3,
};

const STATUS_LABEL: Record<SubsystemHealth["status"], string> = {
  up: "UP",
  degraded: "DEGRADED",
  down: "DOWN",
  unknown: "UNKNOWN",
};

type SortKey = "status" | "name" | "responseTime";
type FilterMode = "all" | "up" | "issues";

// ---------------------------------------------------------------------------
// Mini sparkline for health trend
// ---------------------------------------------------------------------------

function HealthSparkline({ data }: { data: HealthCheckPoint[] }) {
  if (data.length < 2) return null;

  const width = 100;
  const height = 24;
  const values = data.map((d) => d.responseTimeMs);
  const min = Math.min(...values);
  const max = Math.max(...values);
  const range = max - min || 1;

  const points = values
    .map((value, index) => {
      const x = (index / (values.length - 1)) * width;
      const y = height - ((value - min) / range) * (height - 4) - 2;
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");

  // Color segments based on status
  const hasIssues = data.some(
    (d) => d.status === "down" || d.status === "degraded",
  );
  const strokeColor = hasIssues ? "var(--fizzbuzz-gold)" : "var(--fizz-400)";

  return (
    <svg
      width={width}
      height={height}
      viewBox={`0 0 ${width} ${height}`}
      className="overflow-visible shrink-0"
      aria-label="Health trend sparkline"
    >
      <polyline
        points={points}
        fill="none"
        stroke={strokeColor}
        strokeWidth="1.5"
        strokeLinejoin="round"
        strokeLinecap="round"
        opacity={0.8}
      />
    </svg>
  );
}

// ---------------------------------------------------------------------------
// Relative time formatter
// ---------------------------------------------------------------------------

function relativeTime(isoString: string): string {
  const diffMs = Date.now() - new Date(isoString).getTime();
  const diffS = Math.floor(diffMs / 1000);
  if (diffS < 5) return "just now";
  if (diffS < 60) return `${diffS}s ago`;
  const diffM = Math.floor(diffS / 60);
  if (diffM < 60) return `${diffM}m ago`;
  const diffH = Math.floor(diffM / 60);
  return `${diffH}h ago`;
}

// ---------------------------------------------------------------------------
// Overall status derivation
// ---------------------------------------------------------------------------

function deriveOverallStatus(health: SubsystemHealth[]): {
  label: string;
  color: string;
} {
  const hasDown = health.some((h) => h.status === "down");
  const hasDegraded = health.some((h) => h.status === "degraded");

  if (hasDown) return { label: "DOWN", color: "text-red-400" };
  if (hasDegraded) return { label: "DEGRADED", color: "text-amber-400" };
  return { label: "OPERATIONAL", color: "text-fizz-400" };
}

// ---------------------------------------------------------------------------
// Page component
// ---------------------------------------------------------------------------

export default function HealthCheckMatrixPage() {
  const provider = useDataProvider();
  const [health, setHealth] = useState<SubsystemHealth[]>([]);
  const [historyMap, setHistoryMap] = useState<
    Record<string, HealthCheckPoint[]>
  >({});
  const [sortBy, setSortBy] = useState<SortKey>("status");
  const [filter, setFilter] = useState<FilterMode>("all");
  const initialLoadDone = useRef(false);

  // -------------------------------------------------------------------------
  // Data fetching
  // -------------------------------------------------------------------------

  const refresh = useCallback(async () => {
    const data = await provider.getSystemHealth();
    setHealth(data);

    // Fetch history for all subsystems
    const histories: Record<string, HealthCheckPoint[]> = {};
    await Promise.all(
      data.map(async (subsystem) => {
        const history = await provider.getHealthHistory(subsystem.name);
        histories[subsystem.name] = history;
      }),
    );
    setHistoryMap(histories);
    initialLoadDone.current = true;
  }, [provider]);

  useEffect(() => {
    refresh();
    const interval = setInterval(refresh, 5_000);
    return () => clearInterval(interval);
  }, [refresh]);

  // -------------------------------------------------------------------------
  // Sorting
  // -------------------------------------------------------------------------

  const sortedHealth = [...health].sort((a, b) => {
    switch (sortBy) {
      case "status": {
        const diff = STATUS_PRIORITY[a.status] - STATUS_PRIORITY[b.status];
        return diff !== 0 ? diff : a.name.localeCompare(b.name);
      }
      case "name":
        return a.name.localeCompare(b.name);
      case "responseTime":
        return b.responseTimeMs - a.responseTimeMs;
      default:
        return 0;
    }
  });

  // -------------------------------------------------------------------------
  // Filtering
  // -------------------------------------------------------------------------

  const filteredHealth = sortedHealth.filter((h) => {
    if (filter === "up") return h.status === "up";
    if (filter === "issues") return h.status !== "up";
    return true;
  });

  // -------------------------------------------------------------------------
  // Counts
  // -------------------------------------------------------------------------

  const upCount = health.filter((h) => h.status === "up").length;
  const degradedCount = health.filter((h) => h.status === "degraded").length;
  const downCount = health.filter((h) => h.status === "down").length;
  const unknownCount = health.filter((h) => h.status === "unknown").length;
  const overall = deriveOverallStatus(health);

  // -------------------------------------------------------------------------
  // Loading state
  // -------------------------------------------------------------------------

  if (health.length === 0) {
    return (
      <div className="flex h-64 items-center justify-center">
        <div className="text-center">
          <div className="inline-block h-6 w-6 animate-spin rounded-full border-2 border-border-default border-t-fizzbuzz-400 mb-3" />
          <p className="text-sm text-text-muted">
            Probing infrastructure subsystem health...
          </p>
        </div>
      </div>
    );
  }

  // -------------------------------------------------------------------------
  // Render
  // -------------------------------------------------------------------------

  return (
    <div className="space-y-6">
      {/* Page header */}
      <Reveal>
        <div>
          <h1 className="heading-page">Health Check Matrix</h1>
          <p className="mt-1 text-sm text-text-secondary">
            Real-time infrastructure subsystem health monitoring with response
            time tracking and historical sparklines.
          </p>
        </div>
      </Reveal>

      {/* Summary KPI bar */}
      <StatGroup
        items={[
          { label: "Overall", value: overall.label },
          { label: "Healthy", value: String(upCount), trend: { direction: "up", label: `${health.length > 0 ? ((upCount / health.length) * 100).toFixed(0) : 0}%` } },
          { label: "Degraded", value: String(degradedCount) },
          { label: "Down", value: String(downCount) },
          { label: "Unknown", value: String(unknownCount) },
        ]}
        className="rounded-lg border border-border-subtle bg-surface-raised px-4 py-3"
      />

      {/* Controls */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        {/* Sort controls */}
        <div className="flex items-center gap-2">
          <span className="text-xs text-text-muted">Sort by:</span>
          {(
            [
              ["status", "Status"],
              ["name", "Name"],
              ["responseTime", "Response Time"],
            ] as [SortKey, string][]
          ).map(([key, label]) => (
            <button
              key={key}
              type="button"
              onClick={() => setSortBy(key)}
              className={`rounded px-2.5 py-1 text-xs font-medium transition-colors ${
                sortBy === key
                  ? "bg-fizzbuzz-600 text-white"
                  : "bg-surface-overlay text-text-secondary hover:bg-surface-overlay hover:text-text-primary"
              }`}
            >
              {label}
            </button>
          ))}
        </div>

        {/* Filter dropdown */}
        <div className="flex items-center gap-2">
          <span className="text-xs text-text-muted">Show:</span>
          <select
            value={filter}
            onChange={(e) => setFilter(e.target.value as FilterMode)}
            className="rounded border border-border-subtle bg-surface-base px-2.5 py-1 text-xs text-text-secondary focus:outline-none focus:ring-1 focus:ring-fizzbuzz-500"
          >
            <option value="all">All Subsystems</option>
            <option value="up">UP Only</option>
            <option value="issues">Issues Only</option>
          </select>
        </div>
      </div>

      {/* Health grid */}
      <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3">
        {filteredHealth.map((subsystem) => (
          <Card key={subsystem.name}>
            <CardContent className="py-3">
              <div className="flex items-start gap-3">
                {/* Status dot */}
                <span
                  className={`mt-1 h-3 w-3 shrink-0 rounded-full ${STATUS_DOT[subsystem.status]} ${
                    subsystem.status === "down" ? "animate-pulse" : ""
                  }`}
                />

                {/* Info */}
                <div className="flex-1 min-w-0">
                  <div className="flex items-center justify-between gap-2">
                    <h3 className="text-sm font-medium text-text-primary truncate">
                      {subsystem.name}
                    </h3>
                    <span
                      className={`shrink-0 text-[10px] font-mono font-semibold uppercase ${STATUS_TEXT[subsystem.status]}`}
                    >
                      {STATUS_LABEL[subsystem.status]}
                    </span>
                  </div>

                  {/* Metrics row */}
                  <div className="mt-1.5 flex items-center gap-3 text-xs text-text-secondary">
                    <span>
                      Checked{" "}
                      <span className="text-text-secondary">
                        {relativeTime(subsystem.lastChecked)}
                      </span>
                    </span>
                    {subsystem.status !== "down" && (
                      <span>
                        Response{" "}
                        <span className="font-mono text-text-secondary">
                          {subsystem.responseTimeMs.toFixed(1)}ms
                        </span>
                      </span>
                    )}
                  </div>

                  {/* Sparkline */}
                  {historyMap[subsystem.name] && (
                    <div className="mt-2">
                      <HealthSparkline data={historyMap[subsystem.name]} />
                    </div>
                  )}
                </div>
              </div>
            </CardContent>
          </Card>
        ))}
      </div>

      {/* Empty state for filtered view */}
      {filteredHealth.length === 0 && (
        <div className="flex h-32 items-center justify-center">
          <p className="text-sm text-text-muted">
            No subsystems match the current filter.
          </p>
        </div>
      )}

      {/* Refresh indicator */}
      <p className="text-[10px] text-text-muted text-right">
        Auto-refreshing every 5 seconds &middot; {health.length} subsystems
        monitored
      </p>
    </div>
  );
}
