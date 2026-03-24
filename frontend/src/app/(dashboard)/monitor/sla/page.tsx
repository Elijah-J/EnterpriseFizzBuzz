"use client";

import { useCallback, useEffect, useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { Reveal } from "@/components/ui/reveal";
import { Skeleton } from "@/components/ui/skeleton";
import type {
  Incident,
  SLAHistoryPoint,
  SLAStatus,
} from "@/lib/data-providers";
import { useDataProvider } from "@/lib/data-providers";

// ---------------------------------------------------------------------------
// On-call roster for escalation chain display
// ---------------------------------------------------------------------------

const ESCALATION_CHAIN = [
  { role: "Primary On-Call", index: 0 },
  { role: "Backup", index: 1 },
  { role: "Escalation L1", index: 2 },
  { role: "Escalation L2 (VP Eng)", index: 3 },
] as const;

const ON_CALL_ROSTER = [
  "Dr. Elara Modulus",
  "Prof. Byron Divisor",
  "Eng. Cassandra Remainder",
  "Arch. Dmitri Quotient",
  "SRE Jenkins McFizzface",
  "Dir. Priya Evaluator",
] as const;

// ---------------------------------------------------------------------------
// Severity badge mapping
// ---------------------------------------------------------------------------

const SEVERITY_VARIANT: Record<
  Incident["severity"],
  "error" | "warning" | "info" | "success"
> = {
  P1: "error",
  P2: "warning",
  P3: "info",
  P4: "success",
};

// ---------------------------------------------------------------------------
// Error Budget Burn-Down Line Chart
// ---------------------------------------------------------------------------

function BurnDownChart({ data }: { data: SLAHistoryPoint[] }) {
  if (data.length < 2) return null;

  const width = 800;
  const height = 200;
  const paddingX = 50;
  const paddingY = 20;
  const chartWidth = width - paddingX * 2;
  const chartHeight = height - paddingY * 2;

  const minBudget = Math.min(...data.map((d) => d.budgetRemaining));
  const maxBudget = 100;
  const budgetRange = maxBudget - Math.max(0, minBudget - 5) || 1;
  const yMin = Math.max(0, minBudget - 5);

  // Generate line points
  const points = data
    .map((point, index) => {
      const x = paddingX + (index / (data.length - 1)) * chartWidth;
      const y =
        paddingY +
        chartHeight -
        ((point.budgetRemaining - yMin) / budgetRange) * chartHeight;
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");

  // Area fill beneath the line
  const firstX = paddingX;
  const lastX = paddingX + chartWidth;
  const bottomY = paddingY + chartHeight;
  const areaPoints = `${firstX},${bottomY} ${points} ${lastX},${bottomY}`;

  // Time axis labels (first, middle, last)
  const timeLabels = [
    data[0],
    data[Math.floor(data.length / 2)],
    data[data.length - 1],
  ].map((p) => {
    const d = new Date(p.timestamp);
    return `${d.getHours().toString().padStart(2, "0")}:${d.getMinutes().toString().padStart(2, "0")}`;
  });

  // Y-axis grid lines
  const yGridLines = [100, 75, 50, 25, 0].filter(
    (v) => v >= yMin && v <= maxBudget,
  );

  // Current budget color
  const currentBudget = data[data.length - 1].budgetRemaining;
  let lineColor = "var(--fizz-400)";
  if (currentBudget < 20) lineColor = "#ef4444";
  else if (currentBudget < 50) lineColor = "#f59e0b";

  return (
    <svg
      width="100%"
      height={height}
      viewBox={`0 0 ${width} ${height}`}
      preserveAspectRatio="xMidYMid meet"
      className="overflow-visible"
      aria-label="Error budget burn-down chart"
    >
      <defs>
        <linearGradient id="burndown-fill" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={lineColor} stopOpacity="0.2" />
          <stop offset="100%" stopColor={lineColor} stopOpacity="0.02" />
        </linearGradient>
      </defs>

      {/* Y-axis grid lines */}
      {yGridLines.map((value) => {
        const y =
          paddingY + chartHeight - ((value - yMin) / budgetRange) * chartHeight;
        return (
          <g key={value}>
            <line
              x1={paddingX}
              y1={y}
              x2={paddingX + chartWidth}
              y2={y}
              stroke="var(--surface-overlay)"
              strokeWidth="1"
              strokeDasharray="4,4"
            />
            <text
              x={paddingX - 8}
              y={y + 3}
              textAnchor="end"
              className="text-[10px]"
              fill="var(--text-muted)"
            >
              {value}%
            </text>
          </g>
        );
      })}

      {/* Time axis labels */}
      {timeLabels.map((label, i) => {
        const x = paddingX + (i / (timeLabels.length - 1)) * chartWidth;
        return (
          <text
            key={`time-${i}`}
            x={x}
            y={height - 2}
            textAnchor="middle"
            className="text-[10px]"
            fill="var(--text-muted)"
          >
            {label}
          </text>
        );
      })}

      {/* Area fill */}
      <polygon points={areaPoints} fill="url(#burndown-fill)" />

      {/* Line */}
      <polyline
        points={points}
        fill="none"
        stroke={lineColor}
        strokeWidth="2"
        strokeLinejoin="round"
        strokeLinecap="round"
      />

      {/* Current value dot */}
      {data.length > 0 && (
        <circle
          cx={paddingX + chartWidth}
          cy={
            paddingY +
            chartHeight -
            ((currentBudget - yMin) / budgetRange) * chartHeight
          }
          r="4"
          fill={lineColor}
          stroke="var(--panel-800)"
          strokeWidth="2"
        />
      )}
    </svg>
  );
}

// ---------------------------------------------------------------------------
// Circular SLO Gauge
// ---------------------------------------------------------------------------

function SLOGauge({
  value,
  target,
  label,
  unit,
  inverse,
  size = 120,
}: {
  value: number;
  target: number;
  label: string;
  unit: string;
  /** If true, lower is better (e.g., latency). */
  inverse?: boolean;
  size?: number;
}) {
  const strokeWidth = 8;
  const radius = (size - strokeWidth) / 2;
  const circumference = 2 * Math.PI * radius;

  // Normalize value to 0..1 range for the gauge
  let normalizedFill: number;
  if (inverse) {
    // For latency: full if at 0, empty if at 2x target
    normalizedFill = Math.max(0, Math.min(1, 1 - value / (target * 2)));
  } else {
    // For percentage metrics: show percentage directly
    normalizedFill = Math.max(0, Math.min(1, value / 100));
  }

  const offset = circumference * (1 - normalizedFill);

  // Color based on target compliance
  const meetsTarget = inverse ? value <= target : value >= target;
  const strokeColor = meetsTarget ? "var(--fizz-400)" : "#ef4444";

  // Display value formatting
  const displayValue = inverse
    ? `${value.toFixed(1)}`
    : `${value.toFixed(value >= 99.9 ? 3 : 2)}`;

  return (
    <div className="flex flex-col items-center gap-2">
      <svg
        width={size}
        height={size}
        viewBox={`0 0 ${size} ${size}`}
        aria-label={`${label} gauge: ${displayValue}${unit}`}
      >
        {/* Background track */}
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke="var(--surface-overlay)"
          strokeWidth={strokeWidth}
        />
        {/* Filled arc */}
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke={strokeColor}
          strokeWidth={strokeWidth}
          strokeDasharray={circumference}
          strokeDashoffset={offset}
          strokeLinecap="round"
          transform={`rotate(-90 ${size / 2} ${size / 2})`}
          className="transition-all duration-700"
        />
        {/* Center value */}
        <text
          x={size / 2}
          y={size / 2 - 4}
          textAnchor="middle"
          dominantBaseline="middle"
          className="text-lg font-mono font-bold"
          fill="var(--text-primary)"
        >
          {displayValue}
          <tspan className="text-[10px]" fill="var(--text-secondary)">
            {unit}
          </tspan>
        </text>
        {/* Target line label */}
        <text
          x={size / 2}
          y={size / 2 + 14}
          textAnchor="middle"
          dominantBaseline="middle"
          className="text-[9px]"
          fill="var(--text-muted)"
        >
          target: {inverse ? "<" : ">"}
          {target}
          {unit}
        </text>
      </svg>
      <span className="text-xs font-medium text-text-secondary">{label}</span>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Duration formatter
// ---------------------------------------------------------------------------

function formatDuration(ms: number): string {
  const seconds = Math.floor(ms / 1000);
  if (seconds < 60) return `${seconds}s`;
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ${seconds % 60}s`;
  const hours = Math.floor(minutes / 60);
  return `${hours}h ${minutes % 60}m`;
}

function formatTimestamp(iso: string): string {
  const d = new Date(iso);
  return d.toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

// ---------------------------------------------------------------------------
// Page component
// ---------------------------------------------------------------------------

export default function SLADashboardPage() {
  const provider = useDataProvider();
  const [sla, setSLA] = useState<SLAStatus | null>(null);
  const [slaHistory, setSLAHistory] = useState<SLAHistoryPoint[]>([]);
  const [incidents, setIncidents] = useState<Incident[]>([]);

  const refresh = useCallback(async () => {
    const [slaData, historyData, incidentData] = await Promise.all([
      provider.getSLAStatus(),
      provider.getSLAHistory(),
      provider.getIncidents(),
    ]);
    setSLA(slaData);
    setSLAHistory(historyData);
    setIncidents(incidentData);
  }, [provider]);

  useEffect(() => {
    refresh();
    const interval = setInterval(refresh, 5_000);
    return () => clearInterval(interval);
  }, [refresh]);

  // -------------------------------------------------------------------------
  // Loading state
  // -------------------------------------------------------------------------

  if (!sla) {
    return (
      <div className="flex h-64 items-center justify-center">
        <div className="text-center">
          <div className="inline-block h-6 w-6 animate-spin rounded-full border-2 border-border-default border-t-fizzbuzz-400 mb-3" />
          <p className="text-sm text-text-muted">
            Loading SLA compliance data...
          </p>
        </div>
      </div>
    );
  }

  // -------------------------------------------------------------------------
  // On-call rotation (deterministic by day)
  // -------------------------------------------------------------------------

  const dayIndex = Math.floor(Date.now() / 86_400_000);
  const onCallRoster = ESCALATION_CHAIN.map((entry) => ({
    role: entry.role,
    name: ON_CALL_ROSTER[(dayIndex + entry.index) % ON_CALL_ROSTER.length],
  }));

  // -------------------------------------------------------------------------
  // Render
  // -------------------------------------------------------------------------

  return (
    <div className="space-y-6">
      {/* Page header */}
      <Reveal>
        <div>
          <h1 className="heading-page">SLA Compliance Dashboard</h1>
          <p className="mt-1 text-sm text-text-secondary">
            Service Level Agreement monitoring with error budget tracking,
            availability metrics, and incident correlation.
          </p>
        </div>
      </Reveal>

      {/* Error Budget Burn-Down */}
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <h2 className="heading-section">Error Budget Burn-Down</h2>
            <div className="flex items-center gap-2 text-xs">
              <span className="text-text-muted">Remaining:</span>
              <span
                className={`font-mono font-semibold ${
                  sla.errorBudgetRemaining > 0.5
                    ? "text-fizz-400"
                    : sla.errorBudgetRemaining > 0.2
                      ? "text-amber-400"
                      : "text-red-400"
                }`}
              >
                {(sla.errorBudgetRemaining * 100).toFixed(1)}%
              </span>
            </div>
          </div>
        </CardHeader>
        <CardContent>
          {slaHistory.length > 0 ? (
            <BurnDownChart data={slaHistory} />
          ) : (
            <div className="flex h-48 items-center justify-center">
              <span className="text-xs text-text-muted">
                Collecting burn-down telemetry...
              </span>
            </div>
          )}
        </CardContent>
      </Card>

      {/* SLO Status Cards */}
      <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
        <Card>
          <CardContent className="flex items-center justify-center py-6">
            <SLOGauge
              value={sla.availabilityPercent}
              target={99.95}
              label="Availability"
              unit="%"
            />
          </CardContent>
        </Card>

        <Card>
          <CardContent className="flex items-center justify-center py-6">
            <SLOGauge
              value={sla.latencyP99Ms}
              target={100}
              label="Latency P99"
              unit="ms"
              inverse
            />
          </CardContent>
        </Card>

        <Card>
          <CardContent className="flex items-center justify-center py-6">
            <SLOGauge
              value={sla.correctnessPercent}
              target={100}
              label="Correctness"
              unit="%"
            />
          </CardContent>
        </Card>
      </div>

      {/* Bottom row: Incident Timeline + On-Call Roster */}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        {/* Incident Timeline — 2/3 width */}
        <Card className="lg:col-span-2">
          <CardHeader>
            <div className="flex items-center justify-between">
              <h2 className="heading-section">Incident Timeline</h2>
              <Badge variant={incidents.length > 0 ? "warning" : "success"}>
                {incidents.length} incident{incidents.length !== 1 ? "s" : ""}
              </Badge>
            </div>
          </CardHeader>
          <CardContent>
            {incidents.length === 0 ? (
              <div className="flex h-32 items-center justify-center">
                <span className="text-xs text-text-muted">
                  No incidents in the current reporting window.
                </span>
              </div>
            ) : (
              <div className="relative space-y-0">
                {/* Vertical timeline line */}
                <div className="absolute left-[7px] top-2 bottom-2 w-px bg-surface-overlay" />

                {incidents.map((incident) => (
                  <div key={incident.id} className="relative flex gap-4 py-3">
                    {/* Timeline dot */}
                    <div
                      className={`relative z-10 mt-1 h-3.5 w-3.5 shrink-0 rounded-full border-2 border-panel-800 ${
                        incident.severity === "P1"
                          ? "bg-red-500"
                          : incident.severity === "P2"
                            ? "bg-amber-400"
                            : incident.severity === "P3"
                              ? "bg-buzz-400"
                              : "bg-panel-500"
                      }`}
                    />

                    {/* Content */}
                    <div className="flex-1 min-w-0">
                      <div className="flex items-start justify-between gap-2">
                        <div className="flex items-center gap-2 flex-wrap">
                          <Badge variant={SEVERITY_VARIANT[incident.severity]}>
                            {incident.severity}
                          </Badge>
                          <span className="text-xs text-text-secondary">
                            {incident.id}
                          </span>
                        </div>
                        <span className="shrink-0 text-[10px] text-text-muted font-mono">
                          {formatDuration(incident.durationMs)}
                        </span>
                      </div>

                      <p className="mt-1 text-sm text-text-secondary leading-snug">
                        {incident.title}
                      </p>

                      <div className="mt-1.5 flex items-center gap-3 text-[10px] text-text-muted">
                        <span>{formatTimestamp(incident.startedAt)}</span>
                        {incident.resolvedAt ? (
                          <span className="text-fizz-600">Resolved</span>
                        ) : (
                          <span className="text-red-400 font-medium">
                            Ongoing
                          </span>
                        )}
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>

        {/* On-Call Roster — 1/3 width */}
        <Card>
          <CardHeader>
            <h2 className="heading-section">On-Call Roster</h2>
          </CardHeader>
          <CardContent>
            <div className="space-y-4">
              {onCallRoster.map((entry, i) => (
                <div key={entry.role} className="flex items-center gap-3">
                  {/* Avatar */}
                  <div
                    className={`h-9 w-9 shrink-0 rounded-full flex items-center justify-center ${
                      i === 0
                        ? "bg-fizzbuzz-900 border border-fizzbuzz-700"
                        : "bg-surface-overlay"
                    }`}
                  >
                    <span
                      className={`text-xs font-medium ${
                        i === 0 ? "text-fizzbuzz-300" : "text-text-secondary"
                      }`}
                    >
                      {entry.name
                        .split(" ")
                        .map((w) => w[0])
                        .join("")
                        .slice(0, 2)}
                    </span>
                  </div>

                  {/* Name and role */}
                  <div className="min-w-0">
                    <p
                      className={`text-sm truncate ${
                        i === 0
                          ? "text-text-primary font-medium"
                          : "text-text-secondary"
                      }`}
                    >
                      {entry.name}
                    </p>
                    <p className="text-[10px] text-text-muted">{entry.role}</p>
                  </div>
                </div>
              ))}
            </div>

            {/* Rotation note */}
            <div className="mt-6 rounded border border-border-subtle bg-surface-base px-3 py-2">
              <p className="text-[10px] text-text-muted">
                Rotation schedule follows a 24-hour cycle aligned to UTC
                midnight. Escalation SLA: P1 = 5 min, P2 = 15 min, P3 = 1 hour,
                P4 = next business day.
              </p>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Refresh indicator */}
      <p className="text-[10px] text-panel-600 text-right">
        Auto-refreshing every 5 seconds &middot; SLA window: 30-day rolling
      </p>
    </div>
  );
}
