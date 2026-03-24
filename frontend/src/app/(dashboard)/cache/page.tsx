"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { Reveal } from "@/components/ui/reveal";
import { Skeleton } from "@/components/ui/skeleton";
import type {
  CacheAccessCell,
  CacheEulogy,
  CacheLine,
  CacheStats,
  MESIState,
  MESITransition,
} from "@/lib/data-providers";
import { useDataProvider } from "@/lib/data-providers";

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const REFRESH_INTERVAL_MS = 5_000;

/** Canonical MESI state color scheme, used consistently across all widgets. */
const MESI_COLORS: Record<
  MESIState,
  { bg: string; text: string; border: string; fill: string; label: string }
> = {
  MODIFIED: {
    bg: "bg-red-950",
    text: "text-red-400",
    border: "border-red-800",
    fill: "#ef4444",
    label: "Modified",
  },
  EXCLUSIVE: {
    bg: "bg-blue-950",
    text: "text-blue-400",
    border: "border-blue-800",
    fill: "#3b82f6",
    label: "Exclusive",
  },
  SHARED: {
    bg: "bg-green-950",
    text: "text-green-400",
    border: "border-green-800",
    fill: "#22c55e",
    label: "Shared",
  },
  INVALID: {
    bg: "bg-gray-950",
    text: "text-gray-400",
    border: "border-gray-800",
    fill: "#6b7280",
    label: "Invalid",
  },
};

/** Sort configuration for the cache line inventory table. */
type SortField =
  | "state"
  | "key"
  | "value"
  | "accessCount"
  | "dignityLevel"
  | "createdAt"
  | "ttlSeconds";
type SortDirection = "asc" | "desc";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/** Format an ISO timestamp as a relative "ago" string. */
function formatRelativeTime(isoString: string): string {
  const delta = Date.now() - new Date(isoString).getTime();
  if (delta < 0) return "just now";
  if (delta < 60_000) return `${Math.floor(delta / 1000)}s ago`;
  if (delta < 3_600_000) return `${Math.floor(delta / 60_000)}m ago`;
  if (delta < 86_400_000) return `${Math.floor(delta / 3_600_000)}h ago`;
  return `${Math.floor(delta / 86_400_000)}d ago`;
}

/** Format seconds as human-readable duration. */
function formatTTL(seconds: number): string {
  if (seconds >= 3600) return `${(seconds / 3600).toFixed(1)}h`;
  if (seconds >= 60) return `${Math.floor(seconds / 60)}m ${seconds % 60}s`;
  return `${seconds}s`;
}

/** Format a number with locale-aware thousand separators. */
function formatNumber(n: number): string {
  return n.toLocaleString("en-US");
}

/** Compute the MESI state ordering for sort comparison. */
function mesiStateOrder(state: MESIState): number {
  const order: Record<MESIState, number> = {
    MODIFIED: 0,
    EXCLUSIVE: 1,
    SHARED: 2,
    INVALID: 3,
  };
  return order[state];
}

// ---------------------------------------------------------------------------
// MESI State Badge
// ---------------------------------------------------------------------------

function MESIBadge({ state }: { state: MESIState }) {
  const c = MESI_COLORS[state];
  return (
    <span
      className={`inline-flex items-center rounded px-1.5 py-0.5 text-xs font-medium ${c.bg} ${c.text} border ${c.border}`}
    >
      {state[0]}
    </span>
  );
}

// ---------------------------------------------------------------------------
// Stats Summary Bar
// ---------------------------------------------------------------------------

function StatsSummary({ stats }: { stats: CacheStats }) {
  const cards = [
    {
      label: "Hit Rate",
      value: `${(stats.hitRate * 100).toFixed(1)}%`,
      color:
        stats.hitRate >= 0.8
          ? "text-green-400"
          : stats.hitRate >= 0.6
            ? "text-amber-400"
            : "text-red-400",
    },
    {
      label: "Miss Rate",
      value: `${(stats.missRate * 100).toFixed(1)}%`,
      color:
        stats.missRate <= 0.2
          ? "text-green-400"
          : stats.missRate <= 0.4
            ? "text-amber-400"
            : "text-red-400",
    },
    {
      label: "Total Requests",
      value: formatNumber(stats.totalRequests),
      color: "text-text-primary",
    },
    {
      label: "Live Entries",
      value: `${stats.entries} / ${stats.capacity}`,
      color: "text-text-primary",
    },
    {
      label: "Evictions",
      value: formatNumber(stats.evictions),
      color: "text-text-primary",
    },
    {
      label: "Total Transitions",
      value: formatNumber(stats.totalTransitions),
      color: "text-text-primary",
    },
  ];

  return (
    <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-4">
      {cards.map((card) => (
        <div
          key={card.label}
          className="rounded-lg border border-border-subtle bg-surface-base p-4"
        >
          <p className="text-xs text-text-secondary mb-1">{card.label}</p>
          <p className={`text-xl font-semibold ${card.color}`}>{card.value}</p>
        </div>
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// MESI State Machine Diagram (inline SVG)
// ---------------------------------------------------------------------------

function MESIStateMachine({
  stateDistribution,
  recentTransitions,
}: {
  stateDistribution: Record<MESIState, number>;
  recentTransitions: MESITransition[];
}) {
  // Diamond layout: M (top), E (right), S (bottom), I (left)
  const states: Array<{ state: MESIState; cx: number; cy: number }> = [
    { state: "MODIFIED", cx: 200, cy: 50 },
    { state: "EXCLUSIVE", cx: 350, cy: 150 },
    { state: "SHARED", cx: 200, cy: 250 },
    { state: "INVALID", cx: 50, cy: 150 },
  ];

  // Valid transitions with curved arrow paths
  const transitions: Array<{
    from: MESIState;
    to: MESIState;
    trigger: string;
    path: string;
    labelX: number;
    labelY: number;
  }> = [
    {
      from: "INVALID",
      to: "EXCLUSIVE",
      trigger: "miss",
      path: "M 80,130 Q 180,80 320,135",
      labelX: 180,
      labelY: 90,
    },
    {
      from: "EXCLUSIVE",
      to: "MODIFIED",
      trigger: "write",
      path: "M 330,130 Q 310,70 225,60",
      labelX: 295,
      labelY: 70,
    },
    {
      from: "EXCLUSIVE",
      to: "SHARED",
      trigger: "share",
      path: "M 340,170 Q 320,230 225,245",
      labelX: 310,
      labelY: 220,
    },
    {
      from: "EXCLUSIVE",
      to: "INVALID",
      trigger: "inval",
      path: "M 320,160 Q 200,180 80,160",
      labelX: 200,
      labelY: 180,
    },
    {
      from: "SHARED",
      to: "MODIFIED",
      trigger: "upgrade",
      path: "M 185,235 Q 140,150 185,65",
      labelX: 135,
      labelY: 150,
    },
    {
      from: "SHARED",
      to: "INVALID",
      trigger: "inval",
      path: "M 175,245 Q 90,230 60,175",
      labelX: 95,
      labelY: 235,
    },
    {
      from: "MODIFIED",
      to: "EXCLUSIVE",
      trigger: "wb",
      path: "M 225,65 Q 310,80 340,130",
      labelX: 300,
      labelY: 85,
    },
    {
      from: "MODIFIED",
      to: "SHARED",
      trigger: "wb+share",
      path: "M 215,65 Q 260,150 215,235",
      labelX: 255,
      labelY: 150,
    },
    {
      from: "MODIFIED",
      to: "INVALID",
      trigger: "inval",
      path: "M 175,55 Q 90,70 55,130",
      labelX: 95,
      labelY: 70,
    },
  ];

  // Determine which transitions were recent (last 2 transitions) for glow effect
  const recentPairs = new Set(
    recentTransitions.slice(0, 2).map((t) => `${t.fromState}->${t.toState}`),
  );

  return (
    <div className="rounded-lg border border-border-subtle bg-surface-base p-4">
      <h3 className="text-sm font-medium text-text-secondary mb-3">
        MESI State Machine
      </h3>
      <svg viewBox="0 0 400 300" className="w-full" style={{ maxHeight: 280 }}>
        <defs>
          <marker
            id="arrowhead"
            markerWidth="8"
            markerHeight="6"
            refX="7"
            refY="3"
            orient="auto"
          >
            <polygon points="0 0, 8 3, 0 6" fill="#64748b" />
          </marker>
          <marker
            id="arrowhead-glow"
            markerWidth="8"
            markerHeight="6"
            refX="7"
            refY="3"
            orient="auto"
          >
            <polygon points="0 0, 8 3, 0 6" fill="#fbbf24" />
          </marker>
          <filter id="glow">
            <feGaussianBlur stdDeviation="2" result="coloredBlur" />
            <feMerge>
              <feMergeNode in="coloredBlur" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>
        </defs>

        {/* Transition arrows */}
        {transitions.map((t) => {
          const isActive = recentPairs.has(`${t.from}->${t.to}`);
          return (
            <g key={`${t.from}-${t.to}`}>
              <path
                d={t.path}
                fill="none"
                stroke={isActive ? "#fbbf24" : "#475569"}
                strokeWidth={isActive ? 2 : 1}
                markerEnd={
                  isActive ? "url(#arrowhead-glow)" : "url(#arrowhead)"
                }
                filter={isActive ? "url(#glow)" : undefined}
                className={isActive ? "animate-pulse" : ""}
              />
              <text
                x={t.labelX}
                y={t.labelY}
                textAnchor="middle"
                className="text-[8px]"
                fill={isActive ? "#fbbf24" : "#64748b"}
              >
                {t.trigger}
              </text>
            </g>
          );
        })}

        {/* State circles */}
        {states.map(({ state, cx, cy }) => {
          const color = MESI_COLORS[state];
          const count = stateDistribution[state] ?? 0;
          return (
            <g key={state}>
              <circle
                cx={cx}
                cy={cy}
                r={30}
                fill={color.fill}
                fillOpacity={0.15}
                stroke={color.fill}
                strokeWidth={2}
              />
              <text
                x={cx}
                y={cy - 5}
                textAnchor="middle"
                fill={color.fill}
                className="text-sm font-bold"
              >
                {state[0]}
              </text>
              <text
                x={cx}
                y={cy + 12}
                textAnchor="middle"
                fill={color.fill}
                className="text-[10px]"
              >
                {count}
              </text>
            </g>
          );
        })}
      </svg>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Cache Line Inventory Table
// ---------------------------------------------------------------------------

function CacheLineTable({ lines }: { lines: CacheLine[] }) {
  const [sortField, setSortField] = useState<SortField>("accessCount");
  const [sortDir, setSortDir] = useState<SortDirection>("desc");

  const handleSort = useCallback(
    (field: SortField) => {
      if (field === sortField) {
        setSortDir((d) => (d === "asc" ? "desc" : "asc"));
      } else {
        setSortField(field);
        setSortDir("desc");
      }
    },
    [sortField],
  );

  const sorted = useMemo(() => {
    const copy = [...lines];
    const dir = sortDir === "asc" ? 1 : -1;
    copy.sort((a, b) => {
      switch (sortField) {
        case "state":
          return dir * (mesiStateOrder(a.state) - mesiStateOrder(b.state));
        case "key":
          return dir * a.key.localeCompare(b.key);
        case "value":
          return dir * a.value.localeCompare(b.value);
        case "accessCount":
          return dir * (a.accessCount - b.accessCount);
        case "dignityLevel":
          return dir * (a.dignityLevel - b.dignityLevel);
        case "createdAt":
          return (
            dir *
            (new Date(a.createdAt).getTime() - new Date(b.createdAt).getTime())
          );
        case "ttlSeconds":
          return dir * (a.ttlSeconds - b.ttlSeconds);
        default:
          return 0;
      }
    });
    return copy;
  }, [lines, sortField, sortDir]);

  const headers: Array<{ field: SortField; label: string }> = [
    { field: "state", label: "State" },
    { field: "key", label: "Key" },
    { field: "value", label: "Value" },
    { field: "accessCount", label: "Accesses" },
    { field: "dignityLevel", label: "Dignity" },
    { field: "createdAt", label: "Age" },
    { field: "ttlSeconds", label: "TTL" },
  ];

  return (
    <div className="rounded-lg border border-border-subtle bg-surface-base p-4">
      <h3 className="text-sm font-medium text-text-secondary mb-3">
        Cache Line Inventory
      </h3>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border-subtle text-left text-xs text-text-secondary">
              {headers.map((h) => (
                <th
                  key={h.field}
                  className="pb-2 pr-3 cursor-pointer hover:text-text-secondary select-none"
                  onClick={() => handleSort(h.field)}
                >
                  {h.label}
                  {sortField === h.field && (
                    <span className="ml-1">
                      {sortDir === "asc" ? "\u25B2" : "\u25BC"}
                    </span>
                  )}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {sorted.map((line) => {
              const isInvalid = line.state === "INVALID";
              const lowDignity = line.dignityLevel < 0.2;
              return (
                <tr
                  key={line.key}
                  className={`border-b border-panel-800 ${
                    isInvalid
                      ? "opacity-40"
                      : lowDignity
                        ? "bg-amber-950/20"
                        : ""
                  }`}
                >
                  <td className="py-1.5 pr-3">
                    <MESIBadge state={line.state} />
                  </td>
                  <td className="py-1.5 pr-3 font-mono text-xs text-text-secondary">
                    {line.key}
                  </td>
                  <td className="py-1.5 pr-3 text-text-secondary">
                    {line.value}
                  </td>
                  <td className="py-1.5 pr-3 text-text-secondary">
                    {formatNumber(line.accessCount)}
                  </td>
                  <td className="py-1.5 pr-3">
                    <div className="flex items-center gap-2">
                      <div className="h-1.5 w-16 rounded-full bg-surface-overlay overflow-hidden">
                        <div
                          className={`h-full rounded-full ${
                            line.dignityLevel >= 0.6
                              ? "bg-green-500"
                              : line.dignityLevel >= 0.3
                                ? "bg-amber-500"
                                : "bg-red-500"
                          }`}
                          style={{ width: `${line.dignityLevel * 100}%` }}
                        />
                      </div>
                      <span className="text-xs text-text-secondary">
                        {(line.dignityLevel * 100).toFixed(0)}%
                      </span>
                    </div>
                  </td>
                  <td className="py-1.5 pr-3 text-xs text-text-secondary">
                    {formatRelativeTime(line.createdAt)}
                  </td>
                  <td className="py-1.5 pr-3 text-xs text-text-secondary">
                    {formatTTL(line.ttlSeconds)}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Hit/Miss Heatmap
// ---------------------------------------------------------------------------

function HitMissHeatmap({ transitions }: { transitions: MESITransition[] }) {
  // Derive hit/miss cells from transitions:
  // INVALID -> EXCLUSIVE = miss (cache miss load)
  // Any other transition involving an existing entry = hit
  const cells: CacheAccessCell[] = [];
  for (const t of transitions) {
    const result: "hit" | "miss" =
      t.fromState === "INVALID" && t.toState === "EXCLUSIVE" ? "miss" : "hit";
    cells.push({
      timestamp: t.timestamp,
      key: t.cacheLineKey,
      result,
    });
  }

  // Fill up to 128 cells, pad with empty if needed
  while (cells.length < 128) {
    cells.push({ timestamp: "", key: "", result: "hit" });
  }
  const display = cells.slice(0, 128);

  return (
    <div className="rounded-lg border border-border-subtle bg-surface-base p-4">
      <h3 className="text-sm font-medium text-text-secondary mb-3">
        Hit/Miss Heatmap
      </h3>
      <div
        className="grid grid-cols-16 gap-0.5"
        style={{ gridTemplateColumns: "repeat(16, 1fr)" }}
      >
        {display.map((cell, i) => (
          <div
            key={i}
            className={`aspect-square rounded-sm ${
              cell.key === ""
                ? "bg-surface-raised"
                : cell.result === "hit"
                  ? "bg-green-600 hover:bg-green-500"
                  : "bg-red-600 hover:bg-red-500"
            }`}
            title={
              cell.key
                ? `${cell.key} — ${cell.result} — ${formatRelativeTime(cell.timestamp)}`
                : ""
            }
          />
        ))}
      </div>
      <div className="flex items-center gap-4 mt-2 text-xs text-text-secondary">
        <span className="flex items-center gap-1">
          <span className="h-2.5 w-2.5 rounded-sm bg-green-600" /> Hit
        </span>
        <span className="flex items-center gap-1">
          <span className="h-2.5 w-2.5 rounded-sm bg-red-600" /> Miss
        </span>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// State Distribution Donut Chart (pure SVG)
// ---------------------------------------------------------------------------

function StateDistributionDonut({
  distribution,
  total,
}: {
  distribution: Record<MESIState, number>;
  total: number;
}) {
  const radius = 60;
  const cx = 80;
  const cy = 80;
  const strokeWidth = 18;
  const circumference = 2 * Math.PI * radius;

  const stateOrder: MESIState[] = [
    "MODIFIED",
    "EXCLUSIVE",
    "SHARED",
    "INVALID",
  ];
  let cumulativeOffset = 0;

  const segments = stateOrder.map((state) => {
    const count = distribution[state] ?? 0;
    const fraction = total > 0 ? count / total : 0;
    const dashLength = fraction * circumference;
    const offset = cumulativeOffset;
    cumulativeOffset += dashLength;
    return { state, count, fraction, dashLength, offset };
  });

  return (
    <div className="rounded-lg border border-border-subtle bg-surface-base p-4">
      <h3 className="text-sm font-medium text-text-secondary mb-3">
        State Distribution
      </h3>
      <div className="flex justify-center">
        <svg width="160" height="160" viewBox="0 0 160 160">
          {/* Background ring */}
          <circle
            cx={cx}
            cy={cy}
            r={radius}
            fill="none"
            stroke="#1e293b"
            strokeWidth={strokeWidth}
          />
          {/* Segments */}
          {segments.map((seg) => (
            <circle
              key={seg.state}
              cx={cx}
              cy={cy}
              r={radius}
              fill="none"
              stroke={MESI_COLORS[seg.state].fill}
              strokeWidth={strokeWidth}
              strokeDasharray={`${seg.dashLength} ${circumference - seg.dashLength}`}
              strokeDashoffset={-seg.offset}
              transform={`rotate(-90 ${cx} ${cy})`}
            />
          ))}
          {/* Center text */}
          <text
            x={cx}
            y={cy - 4}
            textAnchor="middle"
            fill="#e2e8f0"
            className="text-lg font-bold"
          >
            {total}
          </text>
          <text
            x={cx}
            y={cy + 12}
            textAnchor="middle"
            fill="#94a3b8"
            className="text-[9px]"
          >
            entries
          </text>
        </svg>
      </div>
      {/* Legend */}
      <div className="mt-3 space-y-1">
        {segments.map((seg) => (
          <div
            key={seg.state}
            className="flex items-center justify-between text-xs"
          >
            <div className="flex items-center gap-2">
              <span
                className="h-2.5 w-2.5 rounded-sm"
                style={{ backgroundColor: MESI_COLORS[seg.state].fill }}
              />
              <span className="text-text-secondary">
                {MESI_COLORS[seg.state].label}
              </span>
            </div>
            <span className="text-text-secondary">
              {seg.count} ({total > 0 ? (seg.fraction * 100).toFixed(0) : 0}%)
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// MESI Transition Log
// ---------------------------------------------------------------------------

function TransitionLog({ transitions }: { transitions: MESITransition[] }) {
  return (
    <div className="rounded-lg border border-border-subtle bg-surface-base p-4">
      <h3 className="text-sm font-medium text-text-secondary mb-3">
        MESI Transition Log
      </h3>
      <div className="max-h-80 overflow-y-auto space-y-1.5 pr-1">
        {transitions.map((t) => (
          <div
            key={t.id}
            className="flex items-center gap-2 text-xs border-b border-panel-800 pb-1.5"
          >
            <MESIBadge state={t.fromState} />
            <span className="text-text-muted">&rarr;</span>
            <MESIBadge state={t.toState} />
            <span className="rounded bg-surface-raised px-1.5 py-0.5 text-text-secondary">
              {t.trigger}
            </span>
            <span className="font-mono text-text-secondary truncate flex-1">
              {t.cacheLineKey}
            </span>
            <span className="text-text-muted whitespace-nowrap">
              {formatRelativeTime(t.timestamp)}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Eviction Eulogies Memorial Feed
// ---------------------------------------------------------------------------

function EulogyFeed({ eulogies }: { eulogies: CacheEulogy[] }) {
  return (
    <div className="rounded-lg border border-border-subtle bg-surface-base p-4">
      <h3 className="text-sm font-medium text-text-secondary mb-3">
        Eviction Eulogies
      </h3>
      <div className="max-h-96 overflow-y-auto space-y-3 pr-1">
        {eulogies.map((e) => (
          <div
            key={e.id}
            className="rounded-lg border border-border-default bg-surface-ground p-3"
          >
            <div className="flex items-center justify-between mb-2">
              <span className="font-mono text-sm text-text-secondary">
                {e.key}
              </span>
              <span className="text-[10px] text-text-muted italic">
                In Memoriam
              </span>
            </div>
            <div className="text-xs text-text-secondary space-y-1 mb-2">
              <p>Born: {new Date(e.bornAt).toLocaleString()}</p>
              <p>Died: {new Date(e.diedAt).toLocaleString()}</p>
            </div>
            <div className="flex items-center gap-3 text-xs text-text-secondary mb-2">
              <span>{formatNumber(e.accessCount)} accesses</span>
              <span>Dignity: {(e.finalDignity * 100).toFixed(0)}%</span>
              <span className="rounded bg-surface-raised px-1.5 py-0.5 text-text-muted border border-border-subtle">
                {e.causeOfDeath}
              </span>
            </div>
            <p className="text-xs text-text-secondary italic leading-relaxed">
              {e.eulogy}
            </p>
          </div>
        ))}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Page Component
// ---------------------------------------------------------------------------

export default function CacheCoherencePage() {
  const provider = useDataProvider();
  const [cacheLines, setCacheLines] = useState<CacheLine[]>([]);
  const [stats, setStats] = useState<CacheStats | null>(null);
  const [transitions, setTransitions] = useState<MESITransition[]>([]);
  const [eulogies, setEulogies] = useState<CacheEulogy[]>([]);
  const [loading, setLoading] = useState(true);

  const fetchData = useCallback(async () => {
    try {
      const [lines, s, t, e] = await Promise.all([
        provider.getCacheState(),
        provider.getCacheStats(),
        provider.getMESITransitions(50),
        provider.getCacheEulogies(20),
      ]);
      setCacheLines(lines);
      setStats(s);
      setTransitions(t);
      setEulogies(e);
    } catch {
      // Telemetry subsystem will capture the failure; UI continues with stale data
    } finally {
      setLoading(false);
    }
  }, [provider]);

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, REFRESH_INTERVAL_MS);
    return () => clearInterval(interval);
  }, [fetchData]);

  if (loading || !stats) {
    return (
      <div className="flex items-center justify-center h-64">
        <p className="text-text-secondary text-sm">
          Initializing MESI cache coherence telemetry...
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <Reveal>
        <div>
          <h1 className="heading-page">MESI Cache Coherence Visualizer</h1>
          <p className="text-sm text-text-secondary mt-1">
            Real-time coherence protocol monitoring and cache line lifecycle
            management
          </p>
        </div>
      </Reveal>

      {/* Stats Summary Bar */}
      <StatsSummary stats={stats} />

      {/* Two-Column Layout */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Left Column (2/3 width) */}
        <div className="lg:col-span-2 space-y-6">
          <MESIStateMachine
            stateDistribution={stats.stateDistribution}
            recentTransitions={transitions}
          />
          <CacheLineTable lines={cacheLines} />
          <HitMissHeatmap transitions={transitions} />
        </div>

        {/* Right Column (1/3 width) */}
        <div className="space-y-6">
          <StateDistributionDonut
            distribution={stats.stateDistribution}
            total={stats.entries}
          />
          <TransitionLog transitions={transitions} />
          <EulogyFeed eulogies={eulogies} />
        </div>
      </div>
    </div>
  );
}
