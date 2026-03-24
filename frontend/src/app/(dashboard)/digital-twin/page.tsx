"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { Reveal } from "@/components/ui/reveal";
import { Skeleton } from "@/components/ui/skeleton";
import type {
  TwinProjection,
  TwinState,
  WhatIfOutcome,
} from "@/lib/data-providers";
import { useDataProvider } from "@/lib/data-providers";

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const TWIN_REFRESH_INTERVAL_MS = 5_000;

/** Metric options for the Monte Carlo projection chart. */
const PROJECTION_METRICS = [
  { id: "latency", label: "Latency" },
  { id: "throughput", label: "Throughput" },
  { id: "cost", label: "Cost" },
  { id: "failure_rate", label: "Failure Rate" },
] as const;

/** Horizon options in seconds with display labels. */
const HORIZON_OPTIONS = [
  { seconds: 300, label: "5m" },
  { seconds: 900, label: "15m" },
  { seconds: 3600, label: "1h" },
  { seconds: 21600, label: "6h" },
] as const;

/** Pre-built what-if scenarios for rapid experimentation. */
const PREBUILT_SCENARIOS = [
  {
    id: "double-cache",
    name: "Double MESI Cache Capacity",
    description:
      "Increases MESI cache capacity from 1024 to 2048 entries, reducing cache miss rate and expected evaluation latency.",
    overrides: { "cache.capacity": 2048 } as Record<
      string,
      string | number | boolean
    >,
  },
  {
    id: "disable-blockchain",
    name: "Disable Blockchain Ledger",
    description:
      "Removes blockchain-backed immutable audit trail, significantly reducing per-evaluation cost at the expense of audit integrity.",
    overrides: { "blockchain.enabled": false } as Record<
      string,
      string | number | boolean
    >,
  },
  {
    id: "quantum-strategy",
    name: "Switch to Quantum Strategy",
    description:
      "Routes all evaluations through the quantum circuit simulator, trading classical determinism for potential quantum advantage.",
    overrides: { "evaluation.strategy": "quantum" } as Record<
      string,
      string | number | boolean
    >,
  },
] as const;

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface ScenarioRow {
  name: string;
  outcome: WhatIfOutcome;
  assessment: "Favorable" | "Trade-off" | "Unfavorable";
}

interface CustomOverride {
  key: string;
  value: string;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/** Format an ISO timestamp as a relative "ago" string. */
function formatRelativeTime(isoString: string): string {
  const delta = Date.now() - new Date(isoString).getTime();
  if (delta < 5_000) return "just now";
  if (delta < 60_000) return `${Math.floor(delta / 1_000)}s ago`;
  if (delta < 3_600_000) return `${Math.floor(delta / 60_000)}m ago`;
  if (delta < 86_400_000) return `${Math.floor(delta / 3_600_000)}h ago`;
  return `${Math.floor(delta / 86_400_000)}d ago`;
}

/** Return drift magnitude styling based on threshold. */
function driftColor(absDrift: number): string {
  if (absDrift < 2) return "text-fizz-400";
  if (absDrift < 5) return "text-amber-400";
  return "text-red-400";
}

/** Return drift dot color class based on threshold. */
function driftDotColor(absDrift: number): string {
  if (absDrift < 2) return "bg-fizz-400";
  if (absDrift < 5) return "bg-amber-400";
  return "bg-red-400";
}

/** Sync status badge variant mapping. */
function syncBadgeVariant(
  status: TwinState["syncStatus"],
): "success" | "warning" | "error" {
  if (status === "synchronized") return "success";
  if (status === "drifting") return "warning";
  return "error";
}

/** Determine overall scenario assessment heuristic. */
function assessScenario(outcome: WhatIfOutcome): ScenarioRow["assessment"] {
  const improvements = [
    outcome.latencyChangePercent < 0,
    outcome.costChangePercent < 0,
    outcome.failureRateChangePercent < 0,
    outcome.throughputChangePercent > 0,
  ].filter(Boolean).length;

  const degradations = [
    outcome.latencyChangePercent > 5,
    outcome.costChangePercent > 5,
    outcome.failureRateChangePercent > 5,
    outcome.throughputChangePercent < -5,
  ].filter(Boolean).length;

  if (improvements >= 3 && degradations === 0) return "Favorable";
  if (degradations >= 3) return "Unfavorable";
  return "Trade-off";
}

/** Format a change percentage with sign and color class. */
function formatChange(value: number): { text: string; className: string } {
  const sign = value > 0 ? "+" : "";
  const text = `${sign}${value.toFixed(1)}%`;
  // For latency, cost, failure rate: negative is good. For throughput: positive is good.
  // We handle per-metric inversion at the call site.
  return {
    text,
    className:
      value < 0
        ? "text-fizz-400"
        : value > 0
          ? "text-red-400"
          : "text-text-secondary",
  };
}

/** Inverted change format (for throughput where positive is good). */
function formatChangeInverted(value: number): {
  text: string;
  className: string;
} {
  const sign = value > 0 ? "+" : "";
  const text = `${sign}${value.toFixed(1)}%`;
  return {
    text,
    className:
      value > 0
        ? "text-fizz-400"
        : value < 0
          ? "text-red-400"
          : "text-text-secondary",
  };
}

// ---------------------------------------------------------------------------
// Fan Chart Component (SVG)
// ---------------------------------------------------------------------------

const CHART_MARGIN = { top: 20, right: 20, bottom: 36, left: 64 };
const CHART_WIDTH = 700;
const CHART_HEIGHT = 300;

function FanChart({ projection }: { projection: TwinProjection }) {
  const plotWidth = CHART_WIDTH - CHART_MARGIN.left - CHART_MARGIN.right;
  const plotHeight = CHART_HEIGHT - CHART_MARGIN.top - CHART_MARGIN.bottom;

  const { minVal, maxVal, minTime, maxTime } = useMemo(() => {
    if (projection.points.length === 0) {
      return { minVal: 0, maxVal: 1, minTime: 0, maxTime: 1 };
    }
    const allVals = projection.points.flatMap((p) => [
      p.ci90Lower,
      p.ci90Upper,
    ]);
    let lo = Math.min(...allVals);
    let hi = Math.max(...allVals);
    const padding = (hi - lo) * 0.1 || 1;
    lo = Math.max(0, lo - padding);
    hi = hi + padding;
    const times = projection.points.map((p) => p.timestamp);
    return {
      minVal: lo,
      maxVal: hi,
      minTime: Math.min(...times),
      maxTime: Math.max(...times),
    };
  }, [projection.points]);

  const toX = useCallback(
    (timestamp: number) => {
      const range = maxTime - minTime || 1;
      return CHART_MARGIN.left + ((timestamp - minTime) / range) * plotWidth;
    },
    [minTime, maxTime, plotWidth],
  );

  const toY = useCallback(
    (value: number) => {
      const range = maxVal - minVal || 1;
      return (
        CHART_MARGIN.top + plotHeight - ((value - minVal) / range) * plotHeight
      );
    },
    [minVal, maxVal, plotHeight],
  );

  const gradientId90 = useMemo(
    () => `fan-90-${Math.random().toString(36).slice(2, 8)}`,
    [],
  );
  const gradientId50 = useMemo(
    () => `fan-50-${Math.random().toString(36).slice(2, 8)}`,
    [],
  );

  if (projection.points.length === 0) {
    return (
      <div
        className="flex items-center justify-center text-xs text-text-muted"
        style={{ height: CHART_HEIGHT }}
      >
        No projection data available
      </div>
    );
  }

  // Build polygon paths for CI bands
  const ci90Path = useMemo(() => {
    const upper = projection.points
      .map(
        (p) => `${toX(p.timestamp).toFixed(1)},${toY(p.ci90Upper).toFixed(1)}`,
      )
      .join(" ");
    const lower = [...projection.points]
      .reverse()
      .map(
        (p) => `${toX(p.timestamp).toFixed(1)},${toY(p.ci90Lower).toFixed(1)}`,
      )
      .join(" ");
    return `${upper} ${lower}`;
  }, [projection.points, toX, toY]);

  const ci50Path = useMemo(() => {
    const upper = projection.points
      .map(
        (p) => `${toX(p.timestamp).toFixed(1)},${toY(p.ci50Upper).toFixed(1)}`,
      )
      .join(" ");
    const lower = [...projection.points]
      .reverse()
      .map(
        (p) => `${toX(p.timestamp).toFixed(1)},${toY(p.ci50Lower).toFixed(1)}`,
      )
      .join(" ");
    return `${upper} ${lower}`;
  }, [projection.points, toX, toY]);

  const meanLine = useMemo(() => {
    return projection.points
      .map((p) => `${toX(p.timestamp).toFixed(1)},${toY(p.mean).toFixed(1)}`)
      .join(" ");
  }, [projection.points, toX, toY]);

  // Y-axis ticks
  const yTicks = useMemo(() => {
    const step = (maxVal - minVal) / 4;
    return Array.from({ length: 5 }, (_, i) => minVal + step * i);
  }, [minVal, maxVal]);

  // X-axis ticks
  const xTicks = useMemo(() => {
    const step = (maxTime - minTime) / 5;
    return Array.from({ length: 6 }, (_, i) => minTime + step * i);
  }, [minTime, maxTime]);

  function formatYValue(v: number): string {
    if (v >= 1000) return `${(v / 1000).toFixed(1)}K`;
    if (v >= 1) return v.toFixed(1);
    if (v >= 0.001) return v.toFixed(3);
    return v.toExponential(2);
  }

  function formatXTime(ts: number): string {
    const d = new Date(ts);
    return d.toLocaleTimeString([], {
      hour: "2-digit",
      minute: "2-digit",
      hour12: false,
    });
  }

  return (
    <svg
      width="100%"
      height={CHART_HEIGHT}
      viewBox={`0 0 ${CHART_WIDTH} ${CHART_HEIGHT}`}
      preserveAspectRatio="xMidYMid meet"
      className="overflow-visible"
    >
      <defs>
        <linearGradient id={gradientId90} x1="0" y1="0" x2="0" y2="1">
          <stop
            offset="0%"
            stopColor="var(--fizzbuzz-400)"
            stopOpacity="0.10"
          />
          <stop
            offset="100%"
            stopColor="var(--fizzbuzz-400)"
            stopOpacity="0.05"
          />
        </linearGradient>
        <linearGradient id={gradientId50} x1="0" y1="0" x2="0" y2="1">
          <stop
            offset="0%"
            stopColor="var(--fizzbuzz-400)"
            stopOpacity="0.25"
          />
          <stop
            offset="100%"
            stopColor="var(--fizzbuzz-400)"
            stopOpacity="0.15"
          />
        </linearGradient>
      </defs>

      {/* Grid lines */}
      {yTicks.map((tick, i) => (
        <line
          key={`ygrid-${i}`}
          x1={CHART_MARGIN.left}
          x2={CHART_WIDTH - CHART_MARGIN.right}
          y1={toY(tick)}
          y2={toY(tick)}
          stroke="var(--surface-overlay)"
          strokeWidth="0.5"
        />
      ))}

      {/* Y labels */}
      {yTicks.map((tick, i) => (
        <text
          key={`ylabel-${i}`}
          x={CHART_MARGIN.left - 8}
          y={toY(tick)}
          textAnchor="end"
          dominantBaseline="middle"
          className="text-[10px] fill-text-muted"
        >
          {formatYValue(tick)}
        </text>
      ))}

      {/* X labels */}
      {xTicks.map((tick, i) => (
        <text
          key={`xlabel-${i}`}
          x={toX(tick)}
          y={CHART_HEIGHT - 6}
          textAnchor="middle"
          className="text-[10px] fill-text-muted"
        >
          {formatXTime(tick)}
        </text>
      ))}

      {/* 90% CI band */}
      <polygon points={ci90Path} fill={`url(#${gradientId90})`} />

      {/* 50% CI band */}
      <polygon points={ci50Path} fill={`url(#${gradientId50})`} />

      {/* Mean line */}
      <polyline
        points={meanLine}
        fill="none"
        stroke="var(--fizzbuzz-400)"
        strokeWidth="2"
        strokeLinejoin="round"
        strokeLinecap="round"
      />
    </svg>
  );
}

// ---------------------------------------------------------------------------
// Page Component
// ---------------------------------------------------------------------------

export default function DigitalTwinPage() {
  const provider = useDataProvider();

  // Twin state (auto-refreshing)
  const [twinState, setTwinState] = useState<TwinState | null>(null);

  // Projection state
  const [selectedMetric, setSelectedMetric] = useState<string>("latency");
  const [selectedHorizon, setSelectedHorizon] = useState<number>(300);
  const [projection, setProjection] = useState<TwinProjection | null>(null);
  const [projectionLoading, setProjectionLoading] = useState(false);

  // What-if state
  const [customOverrides, setCustomOverrides] = useState<CustomOverride[]>([]);
  const [newKey, setNewKey] = useState("");
  const [newValue, setNewValue] = useState("");
  const [whatIfResult, setWhatIfResult] = useState<WhatIfOutcome | null>(null);
  const [whatIfLoading, setWhatIfLoading] = useState(false);

  // Scenario comparison table
  const [scenarioRows, setScenarioRows] = useState<ScenarioRow[]>([]);

  // -----------------------------------------------------------------------
  // Data fetching
  // -----------------------------------------------------------------------

  const fetchTwinState = useCallback(async () => {
    const state = await provider.getTwinState();
    setTwinState(state);
  }, [provider]);

  const fetchProjection = useCallback(async () => {
    setProjectionLoading(true);
    const result = await provider.runProjection(
      selectedMetric,
      selectedHorizon,
    );
    setProjection(result);
    setProjectionLoading(false);
  }, [provider, selectedMetric, selectedHorizon]);

  // Auto-refresh twin state
  useEffect(() => {
    fetchTwinState();
    const interval = setInterval(fetchTwinState, TWIN_REFRESH_INTERVAL_MS);
    return () => clearInterval(interval);
  }, [fetchTwinState]);

  // Fetch projection when metric or horizon changes
  useEffect(() => {
    fetchProjection();
  }, [fetchProjection]);

  // -----------------------------------------------------------------------
  // What-if handlers
  // -----------------------------------------------------------------------

  const handleRunScenario = useCallback(
    async (
      overrides: Record<string, string | number | boolean>,
      scenarioName: string,
    ) => {
      setWhatIfLoading(true);
      const outcome = await provider.runWhatIfScenario(overrides);
      setWhatIfResult(outcome);
      setScenarioRows((prev) => [
        ...prev,
        { name: scenarioName, outcome, assessment: assessScenario(outcome) },
      ]);
      setWhatIfLoading(false);
    },
    [provider],
  );

  const handleRunCustomScenario = useCallback(async () => {
    const overrides: Record<string, string | number | boolean> = {};
    for (const o of customOverrides) {
      if (!o.key) continue;
      // Attempt numeric conversion
      const numVal = Number(o.value);
      if (!isNaN(numVal) && o.value.trim() !== "") {
        overrides[o.key] = numVal;
      } else if (o.value === "true" || o.value === "false") {
        overrides[o.key] = o.value === "true";
      } else {
        overrides[o.key] = o.value;
      }
    }
    await handleRunScenario(overrides, "Custom Scenario");
  }, [customOverrides, handleRunScenario]);

  const addOverride = useCallback(() => {
    if (!newKey.trim()) return;
    setCustomOverrides((prev) => [
      ...prev,
      { key: newKey.trim(), value: newValue.trim() },
    ]);
    setNewKey("");
    setNewValue("");
  }, [newKey, newValue]);

  const removeOverride = useCallback((index: number) => {
    setCustomOverrides((prev) => prev.filter((_, i) => i !== index));
  }, []);

  // -----------------------------------------------------------------------
  // Render
  // -----------------------------------------------------------------------

  return (
    <div className="space-y-6">
      {/* Page Header */}
      <Reveal>
        <div>
          <h1 className="heading-page">Digital Twin Situation Room</h1>
          <p className="text-sm text-text-secondary mt-1">
            Real-time synchronized simulation model of the Enterprise FizzBuzz
            Platform. Compare live telemetry against predicted state, run Monte
            Carlo projections, and execute what-if scenarios for capacity
            planning.
          </p>
        </div>
      </Reveal>

      {/* 4a. Twin Sync Status Bar */}
      {twinState && (
        <Card>
          <CardContent>
            <div className="flex flex-wrap items-center gap-6 py-2">
              {/* Sync health indicator */}
              <div className="flex items-center gap-2">
                <span
                  className={`h-3 w-3 rounded-full ${
                    twinState.syncStatus === "synchronized"
                      ? "bg-fizz-400"
                      : twinState.syncStatus === "drifting"
                        ? "bg-amber-400"
                        : "bg-red-400"
                  }`}
                />
                <Badge variant={syncBadgeVariant(twinState.syncStatus)}>
                  {twinState.syncStatus.charAt(0).toUpperCase() +
                    twinState.syncStatus.slice(1)}
                </Badge>
              </div>

              {/* Aggregate drift */}
              <div className="flex items-center gap-1.5">
                <span className="text-xs text-text-muted">Drift:</span>
                <span
                  className={`text-sm font-mono font-semibold ${driftColor(twinState.aggregateDriftFBDU / 0.47)}`}
                >
                  {twinState.aggregateDriftFBDU.toFixed(2)} FBDUs
                </span>
              </div>

              {/* Last sync */}
              <div className="flex items-center gap-1.5">
                <span className="text-xs text-text-muted">Last sync:</span>
                <span
                  className="text-sm text-text-secondary"
                  title={twinState.lastSyncAt}
                >
                  {formatRelativeTime(twinState.lastSyncAt)}
                </span>
              </div>

              {/* Simulation count */}
              <div className="flex items-center gap-1.5">
                <Badge variant="info">
                  {twinState.simulationCount.toLocaleString()} simulations
                </Badge>
              </div>

              {/* Model built at */}
              <div className="flex items-center gap-1.5">
                <span className="text-xs text-text-muted">Model built:</span>
                <span
                  className="text-sm text-text-secondary"
                  title={twinState.modelBuiltAt}
                >
                  {formatRelativeTime(twinState.modelBuiltAt)}
                </span>
              </div>
            </div>
          </CardContent>
        </Card>
      )}

      {/* 4b. Live vs Twin Comparison Grid */}
      {twinState && (
        <Card>
          <CardHeader>Live vs Twin Comparison</CardHeader>
          <CardContent>
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 2xl:grid-cols-5 gap-4">
              {twinState.subsystemStates.map((subsystem) => {
                const absDrift = Math.abs(subsystem.driftPercent);
                return (
                  <div
                    key={subsystem.name}
                    className="rounded-lg border border-border-subtle bg-surface-raised/50 p-4"
                  >
                    <div className="flex items-center justify-between mb-3">
                      <span
                        className="text-sm font-medium text-text-secondary truncate"
                        title={subsystem.name}
                      >
                        {subsystem.name}
                      </span>
                      <Badge
                        variant={subsystem.enabled ? "success" : "warning"}
                      >
                        {subsystem.enabled ? "On" : "Off"}
                      </Badge>
                    </div>
                    <div className="flex items-center justify-between gap-2">
                      <div className="text-center flex-1">
                        <div className="text-[10px] uppercase tracking-wider text-text-muted mb-1">
                          Live
                        </div>
                        <div className="text-lg font-mono font-semibold text-text-primary">
                          {subsystem.liveValue.toFixed(2)}
                        </div>
                      </div>
                      <div className="flex flex-col items-center px-2">
                        <span
                          className={`h-2 w-2 rounded-full ${driftDotColor(absDrift)}`}
                        />
                        <span
                          className={`text-xs font-mono mt-0.5 ${driftColor(absDrift)}`}
                        >
                          {subsystem.driftPercent > 0 ? "+" : ""}
                          {subsystem.driftPercent.toFixed(1)}%
                        </span>
                      </div>
                      <div className="text-center flex-1">
                        <div className="text-[10px] uppercase tracking-wider text-text-muted mb-1">
                          Twin
                        </div>
                        <div className="text-lg font-mono font-semibold text-text-primary">
                          {subsystem.twinValue.toFixed(2)}
                        </div>
                      </div>
                    </div>
                    <div className="text-center text-[10px] text-text-muted mt-2">
                      {subsystem.unit}
                    </div>
                  </div>
                );
              })}
            </div>
          </CardContent>
        </Card>
      )}

      {/* 4c. Monte Carlo Projection Chart */}
      <Card>
        <CardHeader>Monte Carlo Projection</CardHeader>
        <CardContent>
          {/* Metric selector */}
          <div className="flex flex-wrap items-center gap-4 mb-4">
            <div className="flex gap-1">
              {PROJECTION_METRICS.map((m) => (
                <Button
                  key={m.id}
                  variant={selectedMetric === m.id ? "primary" : "ghost"}
                  size="sm"
                  onClick={() => setSelectedMetric(m.id)}
                >
                  {m.label}
                </Button>
              ))}
            </div>
            <div className="flex gap-1">
              {HORIZON_OPTIONS.map((h) => (
                <Button
                  key={h.seconds}
                  variant={
                    selectedHorizon === h.seconds ? "secondary" : "ghost"
                  }
                  size="sm"
                  onClick={() => setSelectedHorizon(h.seconds)}
                >
                  {h.label}
                </Button>
              ))}
            </div>
          </div>

          {/* Chart */}
          {projectionLoading ? (
            <div
              className="flex items-center justify-center text-sm text-text-muted"
              style={{ height: CHART_HEIGHT }}
            >
              Running Monte Carlo simulation...
            </div>
          ) : projection ? (
            <>
              <FanChart projection={projection} />
              {/* Legend */}
              <div className="flex items-center gap-6 mt-3 text-xs text-text-secondary">
                <div className="flex items-center gap-1.5">
                  <span className="h-0.5 w-4 bg-fizzbuzz-400 rounded" />
                  <span>Mean</span>
                </div>
                <div className="flex items-center gap-1.5">
                  <span className="h-3 w-4 rounded bg-fizzbuzz-400/25" />
                  <span>50% CI</span>
                </div>
                <div className="flex items-center gap-1.5">
                  <span className="h-3 w-4 rounded bg-fizzbuzz-400/10" />
                  <span>90% CI</span>
                </div>
              </div>
              {/* Summary stats */}
              {projection.points.length > 0 && (
                <div className="mt-4 p-3 rounded border border-border-subtle bg-surface-raised/50">
                  <p className="text-xs text-text-muted mb-1">
                    Projected {projection.metricLabel} at horizon (
                    {
                      HORIZON_OPTIONS.find((h) => h.seconds === selectedHorizon)
                        ?.label
                    }
                    ):
                  </p>
                  <p className="text-sm font-mono text-text-primary">
                    {projection.points[
                      projection.points.length - 1
                    ].mean.toFixed(3)}{" "}
                    {projection.unit}
                    <span className="text-text-muted ml-2">
                      (90% CI:{" "}
                      {projection.points[
                        projection.points.length - 1
                      ].ci90Lower.toFixed(3)}{" "}
                      &ndash;{" "}
                      {projection.points[
                        projection.points.length - 1
                      ].ci90Upper.toFixed(3)}
                      )
                    </span>
                  </p>
                  <p className="text-xs text-text-muted mt-1">
                    Based on {projection.simulationCount.toLocaleString()} Monte
                    Carlo simulations
                  </p>
                </div>
              )}
            </>
          ) : null}
        </CardContent>
      </Card>

      {/* 4d. What-If Console */}
      <Card>
        <CardHeader>What-If Console</CardHeader>
        <CardContent>
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            {/* Left panel: Scenario Builder */}
            <div>
              <p className="text-xs text-text-muted uppercase tracking-wider mb-3">
                Pre-built Scenarios
              </p>
              <div className="space-y-2 mb-4">
                {PREBUILT_SCENARIOS.map((scenario) => (
                  <button
                    key={scenario.id}
                    className="w-full text-left rounded border border-border-subtle bg-surface-raised/50 p-3 hover:bg-panel-700/50 transition-colors"
                    onClick={() =>
                      handleRunScenario(scenario.overrides, scenario.name)
                    }
                    disabled={whatIfLoading}
                  >
                    <div className="heading-section">{scenario.name}</div>
                    <div className="text-xs text-text-muted mt-0.5">
                      {scenario.description}
                    </div>
                  </button>
                ))}
              </div>

              <p className="text-xs text-text-muted uppercase tracking-wider mb-3">
                Custom Overrides
              </p>
              <div className="space-y-2 mb-3">
                {customOverrides.map((override, index) => (
                  <div key={index} className="flex items-center gap-2">
                    <span className="text-xs font-mono text-text-secondary bg-surface-raised rounded px-2 py-1 flex-1 truncate">
                      {override.key} = {override.value}
                    </span>
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => removeOverride(index)}
                    >
                      Remove
                    </Button>
                  </div>
                ))}
              </div>
              <div className="flex items-center gap-2">
                <input
                  type="text"
                  placeholder="Parameter key"
                  value={newKey}
                  onChange={(e) => setNewKey(e.target.value)}
                  className="flex-1 rounded bg-surface-raised border border-border-default px-2 py-1.5 text-sm text-text-primary placeholder:text-panel-600 focus:outline-none focus:ring-1 focus:ring-fizzbuzz-500"
                />
                <input
                  type="text"
                  placeholder="Value"
                  value={newValue}
                  onChange={(e) => setNewValue(e.target.value)}
                  className="flex-1 rounded bg-surface-raised border border-border-default px-2 py-1.5 text-sm text-text-primary placeholder:text-panel-600 focus:outline-none focus:ring-1 focus:ring-fizzbuzz-500"
                />
                <Button variant="secondary" size="sm" onClick={addOverride}>
                  Add
                </Button>
              </div>
              <div className="mt-3">
                <Button
                  variant="primary"
                  size="sm"
                  onClick={handleRunCustomScenario}
                  disabled={whatIfLoading || customOverrides.length === 0}
                >
                  {whatIfLoading ? "Running..." : "Run Scenario"}
                </Button>
              </div>
            </div>

            {/* Right panel: Projected Impact */}
            <div>
              <p className="text-xs text-text-muted uppercase tracking-wider mb-3">
                Projected Impact
              </p>
              {whatIfResult ? (
                <div className="grid grid-cols-2 gap-3">
                  <div className="rounded border border-border-subtle bg-surface-raised/50 p-3">
                    <div className="text-[10px] uppercase tracking-wider text-text-muted mb-1">
                      Latency
                    </div>
                    <div className="text-xl font-mono font-semibold text-text-primary">
                      {whatIfResult.predictedLatencyMs.toFixed(1)}
                      <span className="text-xs font-normal text-text-muted ml-1">
                        ms
                      </span>
                    </div>
                    <div
                      className={`text-xs font-mono mt-1 ${formatChange(whatIfResult.latencyChangePercent).className}`}
                    >
                      {formatChange(whatIfResult.latencyChangePercent).text}
                    </div>
                  </div>
                  <div className="rounded border border-border-subtle bg-surface-raised/50 p-3">
                    <div className="text-[10px] uppercase tracking-wider text-text-muted mb-1">
                      Cost
                    </div>
                    <div className="text-xl font-mono font-semibold text-text-primary">
                      {whatIfResult.predictedCostFB.toFixed(3)}
                      <span className="text-xs font-normal text-text-muted ml-1">
                        FB$
                      </span>
                    </div>
                    <div
                      className={`text-xs font-mono mt-1 ${formatChange(whatIfResult.costChangePercent).className}`}
                    >
                      {formatChange(whatIfResult.costChangePercent).text}
                    </div>
                  </div>
                  <div className="rounded border border-border-subtle bg-surface-raised/50 p-3">
                    <div className="text-[10px] uppercase tracking-wider text-text-muted mb-1">
                      Failure Rate
                    </div>
                    <div className="text-xl font-mono font-semibold text-text-primary">
                      {(whatIfResult.predictedFailureRate * 100).toFixed(2)}
                      <span className="text-xs font-normal text-text-muted ml-1">
                        %
                      </span>
                    </div>
                    <div
                      className={`text-xs font-mono mt-1 ${formatChange(whatIfResult.failureRateChangePercent).className}`}
                    >
                      {formatChange(whatIfResult.failureRateChangePercent).text}
                    </div>
                  </div>
                  <div className="rounded border border-border-subtle bg-surface-raised/50 p-3">
                    <div className="text-[10px] uppercase tracking-wider text-text-muted mb-1">
                      Throughput
                    </div>
                    <div className="text-xl font-mono font-semibold text-text-primary">
                      {whatIfResult.predictedThroughput.toLocaleString()}
                      <span className="text-xs font-normal text-text-muted ml-1">
                        eval/s
                      </span>
                    </div>
                    <div
                      className={`text-xs font-mono mt-1 ${formatChangeInverted(whatIfResult.throughputChangePercent).className}`}
                    >
                      {
                        formatChangeInverted(
                          whatIfResult.throughputChangePercent,
                        ).text
                      }
                    </div>
                  </div>
                </div>
              ) : (
                <div className="flex items-center justify-center h-48 text-sm text-text-muted border border-dashed border-border-subtle rounded">
                  Select or build a scenario to view projected impact
                </div>
              )}
            </div>
          </div>
        </CardContent>
      </Card>

      {/* 4e. Scenario Comparison Table */}
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between w-full">
            <span>Scenario Comparison</span>
            {scenarioRows.length > 0 && (
              <Button
                variant="ghost"
                size="sm"
                onClick={() => setScenarioRows([])}
              >
                Clear
              </Button>
            )}
          </div>
        </CardHeader>
        <CardContent>
          {scenarioRows.length === 0 ? (
            <div className="text-sm text-text-muted text-center py-8">
              Run what-if scenarios to populate the comparison table. Results
              accumulate across the session for side-by-side analysis.
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-border-subtle text-left text-xs text-text-muted uppercase tracking-wider">
                    <th className="py-2 pr-4">Scenario</th>
                    <th className="py-2 pr-4">Latency (ms)</th>
                    <th className="py-2 pr-4">Cost (FB$)</th>
                    <th className="py-2 pr-4">Failure Rate</th>
                    <th className="py-2 pr-4">Throughput</th>
                    <th className="py-2">Overall</th>
                  </tr>
                </thead>
                <tbody>
                  {/* Baseline row */}
                  <tr className="border-b border-panel-800 text-text-secondary">
                    <td className="py-2 pr-4 font-medium text-text-secondary">
                      Baseline
                    </td>
                    <td className="py-2 pr-4 font-mono">12.4</td>
                    <td className="py-2 pr-4 font-mono">0.034</td>
                    <td className="py-2 pr-4 font-mono">0.02%</td>
                    <td className="py-2 pr-4 font-mono">1,247/s</td>
                    <td className="py-2 text-text-muted">&mdash;</td>
                  </tr>
                  {scenarioRows.map((row, index) => {
                    const latencyFmt = formatChange(
                      row.outcome.latencyChangePercent,
                    );
                    const costFmt = formatChange(row.outcome.costChangePercent);
                    const failureFmt = formatChange(
                      row.outcome.failureRateChangePercent,
                    );
                    const throughputFmt = formatChangeInverted(
                      row.outcome.throughputChangePercent,
                    );

                    const assessmentVariant: "success" | "warning" | "error" =
                      row.assessment === "Favorable"
                        ? "success"
                        : row.assessment === "Trade-off"
                          ? "warning"
                          : "error";

                    return (
                      <tr
                        key={index}
                        className="border-b border-panel-800 text-text-secondary"
                      >
                        <td className="py-2 pr-4 font-medium text-text-secondary">
                          {row.name}
                        </td>
                        <td className="py-2 pr-4 font-mono">
                          {row.outcome.predictedLatencyMs.toFixed(1)}{" "}
                          <span className={`text-xs ${latencyFmt.className}`}>
                            ({latencyFmt.text})
                          </span>
                        </td>
                        <td className="py-2 pr-4 font-mono">
                          {row.outcome.predictedCostFB.toFixed(3)}{" "}
                          <span className={`text-xs ${costFmt.className}`}>
                            ({costFmt.text})
                          </span>
                        </td>
                        <td className="py-2 pr-4 font-mono">
                          {(row.outcome.predictedFailureRate * 100).toFixed(2)}%{" "}
                          <span className={`text-xs ${failureFmt.className}`}>
                            ({failureFmt.text})
                          </span>
                        </td>
                        <td className="py-2 pr-4 font-mono">
                          {row.outcome.predictedThroughput.toLocaleString()}/s{" "}
                          <span
                            className={`text-xs ${throughputFmt.className}`}
                          >
                            ({throughputFmt.text})
                          </span>
                        </td>
                        <td className="py-2">
                          <Badge variant={assessmentVariant}>
                            {row.assessment}
                          </Badge>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
