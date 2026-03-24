"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { HistogramChart } from "@/components/charts/histogram-chart";
import { LineChart } from "@/components/charts/line-chart";
import { MetricGauge } from "@/components/charts/metric-gauge";
import { Sparkline } from "@/components/charts/sparkline";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { Reveal } from "@/components/ui/reveal";
import { Skeleton } from "@/components/ui/skeleton";
import type { MetricDefinition, TimeSeriesData } from "@/lib/data-providers";
import { useDataProvider } from "@/lib/data-providers";

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const TIME_RANGES = [
  { label: "1m", seconds: 60 },
  { label: "5m", seconds: 300 },
  { label: "15m", seconds: 900 },
  { label: "1h", seconds: 3600 },
] as const;

const REFRESH_OPTIONS = [
  { label: "1s", interval: 1_000 },
  { label: "5s", interval: 5_000 },
  { label: "30s", interval: 30_000 },
  { label: "Off", interval: 0 },
] as const;

/** Color assignments per metric type for visual differentiation. */
const TYPE_COLORS: Record<string, string> = {
  counter: "var(--fizz-400)",
  gauge: "var(--buzz-400)",
  histogram: "var(--fizzbuzz-400)",
};

/** Metrics that represent percentage values suitable for gauge rendering. */
const GAUGE_METRICS = new Set([
  "cache_hit_ratio",
  "ml_inference_confidence",
  "sla_error_budget_remaining",
  "compliance_audit_score",
]);

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export default function MetricsPage() {
  const provider = useDataProvider();

  // Metric registry
  const [metrics, setMetrics] = useState<MetricDefinition[]>([]);
  const [selectedMetric, setSelectedMetric] = useState<string>("");
  const [searchQuery, setSearchQuery] = useState("");

  // Time controls
  const [timeRange, setTimeRange] = useState<(typeof TIME_RANGES)[number]>(
    TIME_RANGES[1],
  ); // default 5m
  const [refreshInterval, setRefreshInterval] = useState<
    (typeof REFRESH_OPTIONS)[number]
  >(REFRESH_OPTIONS[1]); // default 5s
  const [autoRefresh, setAutoRefresh] = useState(true);

  // Data
  const [mainTimeSeries, setMainTimeSeries] = useState<TimeSeriesData | null>(
    null,
  );
  const [sparklineCache, setSparklineCache] = useState<
    Record<string, number[]>
  >({});

  // Dropdown state
  const [dropdownOpen, setDropdownOpen] = useState(false);
  const dropdownRef = useRef<HTMLDivElement>(null);

  // -----------------------------------------------------------------------
  // Load metric definitions on mount
  // -----------------------------------------------------------------------

  useEffect(() => {
    let cancelled = false;
    provider.listMetrics().then((defs) => {
      if (cancelled) return;
      setMetrics(defs);
      if (defs.length > 0 && !selectedMetric) {
        setSelectedMetric(defs[0].name);
      }
    });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [provider]);

  // -----------------------------------------------------------------------
  // Fetch main chart data when selection or time range changes
  // -----------------------------------------------------------------------

  const fetchMainData = useCallback(async () => {
    if (!selectedMetric) return;
    const data = await provider.getMetricTimeSeries(
      selectedMetric,
      timeRange.seconds,
    );
    setMainTimeSeries(data);
  }, [provider, selectedMetric, timeRange]);

  useEffect(() => {
    fetchMainData();
  }, [fetchMainData]);

  // -----------------------------------------------------------------------
  // Fetch sparkline data for all metrics (compact view)
  // -----------------------------------------------------------------------

  const fetchSparklines = useCallback(async () => {
    const results: Record<string, number[]> = {};
    // Fetch 60s of data for each metric sparkline
    const promises = metrics.map(async (m) => {
      const ts = await provider.getMetricTimeSeries(m.name, 60);
      results[m.name] = ts.dataPoints.map((dp) => dp.value);
    });
    await Promise.all(promises);
    setSparklineCache(results);
  }, [provider, metrics]);

  useEffect(() => {
    if (metrics.length > 0) {
      fetchSparklines();
    }
  }, [metrics, fetchSparklines]);

  // -----------------------------------------------------------------------
  // Auto-refresh
  // -----------------------------------------------------------------------

  useEffect(() => {
    if (!autoRefresh || refreshInterval.interval === 0) return;
    const timer = setInterval(() => {
      fetchMainData();
      fetchSparklines();
    }, refreshInterval.interval);
    return () => clearInterval(timer);
  }, [autoRefresh, refreshInterval, fetchMainData, fetchSparklines]);

  // -----------------------------------------------------------------------
  // Close dropdown on outside click
  // -----------------------------------------------------------------------

  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (
        dropdownRef.current &&
        !dropdownRef.current.contains(e.target as Node)
      ) {
        setDropdownOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, []);

  // -----------------------------------------------------------------------
  // Derived state
  // -----------------------------------------------------------------------

  const selectedDef = useMemo(
    () => metrics.find((m) => m.name === selectedMetric),
    [metrics, selectedMetric],
  );

  const filteredMetrics = useMemo(() => {
    if (!searchQuery) return metrics;
    const q = searchQuery.toLowerCase();
    return metrics.filter(
      (m) =>
        m.name.toLowerCase().includes(q) ||
        m.description.toLowerCase().includes(q),
    );
  }, [metrics, searchQuery]);

  const stats = useMemo(() => {
    if (!mainTimeSeries || mainTimeSeries.dataPoints.length === 0) {
      return { current: 0, min: 0, max: 0, avg: 0 };
    }
    const values = mainTimeSeries.dataPoints.map((dp) => dp.value);
    const sum = values.reduce((a, b) => a + b, 0);
    return {
      current: values[values.length - 1],
      min: Math.min(...values),
      max: Math.max(...values),
      avg: sum / values.length,
    };
  }, [mainTimeSeries]);

  // -----------------------------------------------------------------------
  // Render
  // -----------------------------------------------------------------------

  return (
    <div className="space-y-6">
      {/* Page header */}
      <div>
        <h1 className="text-xl font-bold tracking-tight text-text-primary">
          Real-Time Metrics Dashboard
        </h1>
        <p className="mt-1 text-xs text-text-secondary">
          Platform-wide telemetry signals for the Enterprise FizzBuzz evaluation
          infrastructure. All metrics are collected at 1-second resolution and
          retained for the configured scrape window.
        </p>
      </div>

      {/* Controls bar */}
      <div className="flex flex-wrap items-center gap-3">
        {/* Metric selector dropdown */}
        <div className="relative" ref={dropdownRef}>
          <button
            type="button"
            onClick={() => setDropdownOpen(!dropdownOpen)}
            className="flex items-center gap-2 rounded border border-border-default bg-surface-raised px-3 py-1.5 text-xs text-text-primary hover:border-panel-500 transition-colors min-w-[280px]"
          >
            <span className="flex-1 text-left truncate font-mono">
              {selectedMetric || "Select metric..."}
            </span>
            <svg
              width="12"
              height="12"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              className={`transition-transform ${dropdownOpen ? "rotate-180" : ""}`}
            >
              <path d="M6 9l6 6 6-6" />
            </svg>
          </button>

          {dropdownOpen && (
            <div className="absolute z-50 mt-1 w-[360px] rounded border border-border-default bg-surface-raised shadow-xl">
              <div className="border-b border-border-subtle p-2">
                <input
                  type="text"
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  placeholder="Search metrics..."
                  className="w-full rounded bg-surface-base px-2 py-1 text-xs text-text-primary placeholder-panel-500 outline-none border border-border-subtle focus:border-panel-500"
                  autoFocus
                />
              </div>
              <ul className="max-h-64 overflow-y-auto py-1">
                {filteredMetrics.map((m) => (
                  <li key={m.name}>
                    <button
                      type="button"
                      onClick={() => {
                        setSelectedMetric(m.name);
                        setDropdownOpen(false);
                        setSearchQuery("");
                      }}
                      className={`w-full px-3 py-1.5 text-left hover:bg-surface-overlay transition-colors ${
                        m.name === selectedMetric
                          ? "bg-surface-overlay text-text-primary"
                          : "text-text-secondary"
                      }`}
                    >
                      <span className="block text-xs font-mono truncate">
                        {m.name}
                      </span>
                      <span className="block text-[10px] text-text-muted truncate mt-0.5">
                        {m.type} &middot; {m.unit}
                      </span>
                    </button>
                  </li>
                ))}
                {filteredMetrics.length === 0 && (
                  <li className="px-3 py-2 text-xs text-text-muted">
                    No metrics match the current filter
                  </li>
                )}
              </ul>
            </div>
          )}
        </div>

        {/* Time range selector */}
        <div className="flex rounded border border-border-subtle overflow-hidden">
          {TIME_RANGES.map((tr) => (
            <button
              key={tr.label}
              type="button"
              onClick={() => setTimeRange(tr)}
              className={`px-2.5 py-1 text-xs transition-colors ${
                tr.label === timeRange.label
                  ? "bg-surface-overlay text-text-primary"
                  : "bg-surface-raised text-text-secondary hover:bg-surface-overlay hover:text-text-secondary"
              }`}
            >
              {tr.label}
            </button>
          ))}
        </div>

        {/* Auto-refresh controls */}
        <div className="flex items-center gap-2 ml-auto">
          <span className="text-[10px] text-text-muted uppercase tracking-wider">
            Refresh
          </span>
          <div className="flex rounded border border-border-subtle overflow-hidden">
            {REFRESH_OPTIONS.map((opt) => (
              <button
                key={opt.label}
                type="button"
                onClick={() => {
                  setRefreshInterval(opt);
                  setAutoRefresh(opt.interval > 0);
                }}
                className={`px-2 py-1 text-xs transition-colors ${
                  opt.label === refreshInterval.label && autoRefresh
                    ? "bg-surface-overlay text-text-primary"
                    : opt.label === "Off" && !autoRefresh
                      ? "bg-surface-overlay text-text-primary"
                      : "bg-surface-raised text-text-secondary hover:bg-surface-overlay hover:text-text-secondary"
                }`}
              >
                {opt.label}
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* Main chart area */}
      <div className="grid grid-cols-1 xl:grid-cols-4 gap-4">
        <Card className="xl:col-span-3">
          <CardHeader>
            <div className="flex items-center justify-between">
              <div>
                <h2 className="text-sm font-semibold text-text-primary font-mono">
                  {selectedMetric}
                </h2>
                {selectedDef && (
                  <p className="text-[10px] text-text-muted mt-0.5">
                    {selectedDef.description}
                  </p>
                )}
              </div>
              {selectedDef && (
                <span
                  className="rounded px-1.5 py-0.5 text-[10px] font-mono uppercase"
                  style={{
                    color: TYPE_COLORS[selectedDef.type] ?? "var(--panel-400)",
                    borderWidth: 1,
                    borderColor:
                      TYPE_COLORS[selectedDef.type] ?? "var(--panel-600)",
                  }}
                >
                  {selectedDef.type}
                </span>
              )}
            </div>
          </CardHeader>
          <CardContent>
            {mainTimeSeries ? (
              selectedDef?.type === "histogram" ? (
                <HistogramChart
                  data={mainTimeSeries.dataPoints}
                  color={TYPE_COLORS.histogram}
                  unit={mainTimeSeries.unit}
                />
              ) : (
                <LineChart
                  data={mainTimeSeries.dataPoints}
                  color={TYPE_COLORS[selectedDef?.type ?? "gauge"]}
                  unit={mainTimeSeries.unit}
                  label={selectedMetric}
                />
              )
            ) : (
              <div className="flex h-[300px] items-center justify-center">
                <span className="text-xs text-text-muted">
                  Initializing metric telemetry stream...
                </span>
              </div>
            )}
          </CardContent>
        </Card>

        {/* Details panel */}
        <Card>
          <CardHeader>
            <h2 className="text-xs font-semibold text-text-secondary uppercase tracking-wider">
              Metric Details
            </h2>
          </CardHeader>
          <CardContent>
            <div className="space-y-4">
              {/* Gauge for percentage metrics */}
              {selectedDef && GAUGE_METRICS.has(selectedMetric) && (
                <div className="flex justify-center py-2">
                  <MetricGauge
                    value={stats.current}
                    label={selectedDef.unit}
                    size={112}
                    invertColor={
                      selectedMetric === "quantum_qubit_decoherence_rate"
                    }
                  />
                </div>
              )}

              <div className="space-y-2.5">
                <DetailRow label="Name" value={selectedMetric} mono />
                <DetailRow label="Type" value={selectedDef?.type ?? "-"} />
                <DetailRow label="Unit" value={selectedDef?.unit ?? "-"} />
                <div className="border-t border-border-subtle pt-2.5">
                  <DetailRow
                    label="Current"
                    value={formatMetricValue(stats.current)}
                    mono
                  />
                  <DetailRow
                    label="Min"
                    value={formatMetricValue(stats.min)}
                    mono
                  />
                  <DetailRow
                    label="Max"
                    value={formatMetricValue(stats.max)}
                    mono
                  />
                  <DetailRow
                    label="Average"
                    value={formatMetricValue(stats.avg)}
                    mono
                  />
                </div>
              </div>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Metric grid — all metrics as sparkline cards */}
      <div>
        <h2 className="text-xs font-semibold text-text-secondary uppercase tracking-wider mb-3">
          All Platform Metrics
        </h2>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-3">
          {metrics.map((m) => {
            const sparkData = sparklineCache[m.name] ?? [];
            const lastValue =
              sparkData.length > 0 ? sparkData[sparkData.length - 1] : null;
            const isSelected = m.name === selectedMetric;

            return (
              <button
                key={m.name}
                type="button"
                onClick={() => setSelectedMetric(m.name)}
                className={`rounded-lg border text-left p-3 transition-all ${
                  isSelected
                    ? "border-fizzbuzz-400/50 bg-surface-raised ring-1 ring-fizzbuzz-400/20"
                    : "border-border-subtle bg-surface-raised hover:border-border-default"
                }`}
              >
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0 flex-1">
                    <p className="text-[10px] text-text-muted truncate">
                      {m.name}
                    </p>
                    <p className="text-sm font-mono font-semibold text-text-primary mt-0.5">
                      {lastValue !== null ? formatMetricValue(lastValue) : "-"}
                      <span className="text-[10px] text-text-secondary font-normal ml-1">
                        {m.unit}
                      </span>
                    </p>
                  </div>
                  <span
                    className="shrink-0 rounded px-1 py-0.5 text-[9px] font-mono uppercase"
                    style={{
                      color: TYPE_COLORS[m.type] ?? "var(--panel-400)",
                    }}
                  >
                    {m.type}
                  </span>
                </div>
                <div className="mt-2">
                  <Sparkline
                    data={sparkData}
                    width={200}
                    height={28}
                    color={TYPE_COLORS[m.type]}
                    showArea
                  />
                </div>
              </button>
            );
          })}
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Helper components
// ---------------------------------------------------------------------------

function DetailRow({
  label,
  value,
  mono = false,
}: {
  label: string;
  value: string;
  mono?: boolean;
}) {
  return (
    <div className="flex items-baseline justify-between gap-2 text-xs">
      <span className="text-text-muted shrink-0">{label}</span>
      <span
        className={`text-text-secondary truncate text-right ${mono ? "font-mono" : ""}`}
      >
        {value}
      </span>
    </div>
  );
}

function formatMetricValue(value: number): string {
  if (value >= 1_000_000_000) return `${(value / 1_000_000_000).toFixed(2)}G`;
  if (value >= 1_000_000) return `${(value / 1_000_000).toFixed(2)}M`;
  if (value >= 10_000) return `${(value / 1_000).toFixed(1)}K`;
  if (value >= 1) return value.toFixed(2);
  if (value >= 0.001) return value.toFixed(4);
  if (value === 0) return "0";
  return value.toExponential(3);
}
