"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useDataProvider } from "@/lib/data-providers";
import type {
  ChaosExperiment,
  ChaosMetrics,
  GameDayScenario,
  FaultType,
} from "@/lib/data-providers";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const REFRESH_INTERVAL_MS = 15_000;

/** Color mapping for fault type badges. */
const FAULT_TYPE_COLORS: Record<FaultType, { bg: string; text: string; border: string; label: string }> = {
  latency_injection: { bg: "bg-amber-950", text: "text-amber-400", border: "border-amber-800", label: "Latency Injection" },
  error_injection: { bg: "bg-red-950", text: "text-red-400", border: "border-red-800", label: "Error Injection" },
  resource_exhaustion: { bg: "bg-purple-950", text: "text-purple-400", border: "border-purple-800", label: "Resource Exhaustion" },
  network_partition: { bg: "bg-blue-950", text: "text-blue-400", border: "border-blue-800", label: "Network Partition" },
  cache_corruption: { bg: "bg-orange-950", text: "text-orange-400", border: "border-orange-800", label: "Cache Corruption" },
  circuit_breaker_trip: { bg: "bg-rose-950", text: "text-rose-400", border: "border-rose-800", label: "Circuit Breaker Trip" },
};

const STATUS_VARIANT: Record<string, "success" | "warning" | "error" | "info"> = {
  pending: "info",
  running: "warning",
  completed: "success",
  failed: "error",
  aborted: "error",
};

const GAME_DAY_STATUS_VARIANT: Record<string, "success" | "warning" | "error" | "info"> = {
  scheduled: "info",
  "in-progress": "warning",
  completed: "success",
  failed: "error",
};

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/** Format milliseconds as a human-readable duration string. */
function formatMs(ms: number): string {
  if (ms >= 1000) return `${(ms / 1000).toFixed(1)}s`;
  return `${Math.round(ms)}ms`;
}

/** Format an ISO timestamp as a relative "ago" string. */
function formatRelativeTime(isoString: string): string {
  const delta = Date.now() - new Date(isoString).getTime();
  if (delta < 60_000) return "just now";
  if (delta < 3_600_000) return `${Math.floor(delta / 60_000)}m ago`;
  if (delta < 86_400_000) return `${Math.floor(delta / 3_600_000)}h ago`;
  return `${Math.floor(delta / 86_400_000)}d ago`;
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

/** Renders a row of intensity dots (1-5) with filled/empty states. */
function IntensityMeter({ intensity }: { intensity: number }) {
  return (
    <div className="flex items-center gap-1" title={`Intensity: ${intensity}/5`}>
      {Array.from({ length: 5 }, (_, i) => (
        <span
          key={i}
          className={`h-2 w-2 rounded-full ${
            i < intensity ? "bg-red-400" : "bg-panel-600"
          }`}
        />
      ))}
    </div>
  );
}

/** Fault type badge with color coding. */
function FaultTypeBadge({ faultType }: { faultType: FaultType }) {
  const config = FAULT_TYPE_COLORS[faultType];
  return (
    <span
      className={`inline-flex items-center rounded-full border px-2 py-0.5 text-xs font-medium ${config.bg} ${config.text} ${config.border}`}
    >
      {config.label}
    </span>
  );
}

/** Single experiment card in the catalog grid. */
function ExperimentCard({
  experiment,
  onInject,
  isAnyRunning,
}: {
  experiment: ChaosExperiment;
  onInject: (id: string) => void;
  isAnyRunning: boolean;
}) {
  const isRunning = experiment.status === "running";
  const isCompleted = experiment.status === "completed";

  return (
    <Card>
      <CardContent className="space-y-3">
        <div className="flex items-start justify-between gap-2">
          <div className="min-w-0 flex-1">
            <h3 className="text-sm font-semibold text-panel-50 truncate">
              {experiment.name}
            </h3>
            <p className="mt-0.5 text-xs text-panel-400">{experiment.targetSubsystem}</p>
          </div>
          <Badge variant={STATUS_VARIANT[experiment.status] ?? "info"}>
            {experiment.status}
          </Badge>
        </div>

        <div className="flex items-center gap-3">
          <FaultTypeBadge faultType={experiment.faultType} />
          <IntensityMeter intensity={experiment.intensity} />
        </div>

        <p className="text-xs text-panel-400 line-clamp-2">{experiment.description}</p>

        {experiment.results && isCompleted && (
          <div className="flex items-center gap-4 text-xs text-panel-400 border-t border-panel-700 pt-2">
            <span>Recovery: {formatMs(experiment.results.recoveryTimeMs)}</span>
            <span>Error rate: {(experiment.results.peakErrorRate * 100).toFixed(1)}%</span>
          </div>
        )}

        <button
          onClick={() => onInject(experiment.id)}
          disabled={isRunning || isAnyRunning}
          className="w-full rounded px-3 py-1.5 text-xs font-medium bg-red-900 text-red-200 border border-red-700 hover:bg-red-800 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
        >
          Inject Fault
        </button>
      </CardContent>
    </Card>
  );
}

/** Active experiment panel showing live fault injection status. */
function ActiveExperimentPanel({
  experiment,
  elapsedSec,
}: {
  experiment: ChaosExperiment | null;
  elapsedSec: number;
}) {
  if (!experiment) {
    return (
      <Card className="h-full">
        <CardHeader>
          <h2 className="text-sm font-semibold text-panel-50">Active Experiment</h2>
        </CardHeader>
        <CardContent>
          <p className="text-xs text-panel-500 text-center py-8">
            No active experiments. Select an experiment from the catalog to begin fault injection.
          </p>
        </CardContent>
      </Card>
    );
  }

  const progress = Math.min(
    100,
    (elapsedSec / experiment.estimatedDurationSec) * 100
  );
  const remaining = Math.max(0, experiment.estimatedDurationSec - elapsedSec);

  // Simulated event timeline entries
  const eventTimeline = useMemo(() => {
    const events = [
      { offset: 0, label: "Fault injection initiated" },
      { offset: Math.floor(experiment.estimatedDurationSec * 0.15), label: `${experiment.faultType.replace(/_/g, " ")} activated on ${experiment.targetSubsystem}` },
      { offset: Math.floor(experiment.estimatedDurationSec * 0.35), label: "First error detected in evaluation pipeline" },
      { offset: Math.floor(experiment.estimatedDurationSec * 0.6), label: "Circuit breaker state transition observed" },
      { offset: Math.floor(experiment.estimatedDurationSec * 0.85), label: "Recovery procedures initiated" },
    ];
    return events.filter((e) => e.offset <= elapsedSec);
  }, [experiment, elapsedSec]);

  const affectedCount = experiment.results
    ? Math.floor(experiment.results.evaluationsAffected * (progress / 100))
    : 0;
  const errorCount = experiment.results
    ? Math.floor(experiment.results.corruptedResults * (progress / 100))
    : 0;

  return (
    <Card className="h-full">
      <CardHeader>
        <div className="flex items-center justify-between">
          <h2 className="text-sm font-semibold text-panel-50">Active Experiment</h2>
          <Badge variant="warning">Running</Badge>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        <div>
          <h3 className="text-sm font-semibold text-panel-50">{experiment.name}</h3>
          <p className="text-xs text-panel-400">{experiment.targetSubsystem}</p>
        </div>

        {/* Progress bar */}
        <div className="space-y-1">
          <div className="flex items-center justify-between text-xs text-panel-400">
            <span>Progress</span>
            <span>{Math.round(progress)}%</span>
          </div>
          <div className="h-2 rounded-full bg-panel-700 overflow-hidden">
            <div
              className="h-full rounded-full bg-amber-500 transition-all duration-1000"
              style={{ width: `${progress}%` }}
            />
          </div>
          <p className="text-xs text-panel-500">~{Math.ceil(remaining)}s remaining</p>
        </div>

        {/* Live counters */}
        <div className="grid grid-cols-2 gap-3">
          <div className="rounded bg-panel-900 p-2 text-center">
            <p className="text-lg font-mono font-semibold text-panel-50">{affectedCount}</p>
            <p className="text-xs text-panel-400">Affected</p>
          </div>
          <div className="rounded bg-panel-900 p-2 text-center">
            <p className="text-lg font-mono font-semibold text-red-400">{errorCount}</p>
            <p className="text-xs text-panel-400">Errors</p>
          </div>
        </div>

        {/* Event timeline */}
        <div className="space-y-2">
          <p className="text-xs font-medium text-panel-300">Event Timeline</p>
          <div className="space-y-1.5">
            {eventTimeline.map((event, i) => (
              <div key={i} className="flex items-start gap-2 text-xs">
                <span className="mt-0.5 h-1.5 w-1.5 rounded-full bg-amber-400 shrink-0" />
                <span className="text-panel-400">
                  <span className="font-mono text-panel-500">+{event.offset}s</span>{" "}
                  {event.label}
                </span>
              </div>
            ))}
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

/** Game Day scenario accordion panel. */
function GameDayPanel({
  scenario,
  experiments,
  isAnyRunning,
  onStart,
}: {
  scenario: GameDayScenario;
  experiments: ChaosExperiment[];
  isAnyRunning: boolean;
  onStart: (id: string) => void;
}) {
  const [expanded, setExpanded] = useState(false);

  const scenarioExperiments = scenario.experiments
    .map((eid) => experiments.find((e) => e.id === eid))
    .filter((e): e is ChaosExperiment => e !== undefined);

  return (
    <Card>
      <CardHeader
        className="cursor-pointer select-none"
        onClick={() => setExpanded(!expanded)}
      >
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <span className="text-xs text-panel-500">{expanded ? "\u25BC" : "\u25B6"}</span>
            <div>
              <h3 className="text-sm font-semibold text-panel-50">{scenario.name}</h3>
              <p className="text-xs text-panel-400 mt-0.5">{scenario.description}</p>
            </div>
          </div>
          <div className="flex items-center gap-2 shrink-0">
            <Badge variant={GAME_DAY_STATUS_VARIANT[scenario.status] ?? "info"}>
              {scenario.status}
            </Badge>
          </div>
        </div>
      </CardHeader>
      {expanded && (
        <CardContent className="space-y-4">
          {/* Phase stepper */}
          <div className="flex items-center gap-1 overflow-x-auto py-2">
            {scenarioExperiments.map((exp, idx) => {
              const isCurrentPhase = scenario.currentPhase === idx;
              const isCompletedPhase =
                scenario.currentPhase !== undefined && idx < scenario.currentPhase;

              return (
                <div key={exp.id} className="flex items-center gap-1 shrink-0">
                  {idx > 0 && (
                    <div
                      className={`h-px w-6 ${
                        isCompletedPhase ? "bg-fizz-400" : "bg-panel-600"
                      }`}
                    />
                  )}
                  <div
                    className={`rounded px-2 py-1 text-xs border ${
                      isCurrentPhase
                        ? "border-amber-700 bg-amber-950 text-amber-400"
                        : isCompletedPhase
                          ? "border-fizz-700 bg-fizz-950 text-fizz-400"
                          : "border-panel-600 bg-panel-900 text-panel-400"
                    }`}
                  >
                    <span className="font-mono mr-1">P{idx + 1}</span>
                    {exp.name}
                  </div>
                </div>
              );
            })}
          </div>

          {/* Completed summary */}
          {scenario.status === "completed" && scenario.startedAt && scenario.completedAt && (
            <div className="flex items-center gap-4 text-xs text-panel-400 border-t border-panel-700 pt-3">
              <span>
                Duration:{" "}
                {formatMs(
                  new Date(scenario.completedAt).getTime() -
                    new Date(scenario.startedAt).getTime()
                )}
              </span>
              <span>Phases: {scenario.totalPhases}/{scenario.totalPhases} passed</span>
              <Badge variant="success">Recovery Grade: A</Badge>
            </div>
          )}

          <button
            onClick={() => onStart(scenario.id)}
            disabled={isAnyRunning || scenario.status === "in-progress"}
            className="rounded px-3 py-1.5 text-xs font-medium bg-red-900 text-red-200 border border-red-700 hover:bg-red-800 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
          >
            Start Game Day
          </button>
        </CardContent>
      )}
    </Card>
  );
}

/** MTTR trend chart rendered as inline SVG. */
function MttrChart({
  data,
}: {
  data: { timestamp: number; mttrMs: number }[];
}) {
  const width = 700;
  const height = 220;
  const margin = { top: 16, right: 16, bottom: 32, left: 64 };
  const plotWidth = width - margin.left - margin.right;
  const plotHeight = height - margin.top - margin.bottom;
  const slaTarget = 5000;

  if (data.length === 0) {
    return (
      <div
        className="flex items-center justify-center text-xs text-panel-500"
        style={{ width, height }}
      >
        No MTTR data available
      </div>
    );
  }

  const values = data.map((d) => d.mttrMs);
  const times = data.map((d) => d.timestamp);
  const minVal = 0;
  const maxVal = Math.max(slaTarget * 1.2, ...values) * 1.1;
  const minTime = Math.min(...times);
  const maxTime = Math.max(...times);

  const toX = (t: number) => {
    const range = maxTime - minTime || 1;
    return margin.left + ((t - minTime) / range) * plotWidth;
  };
  const toY = (v: number) => {
    const range = maxVal - minVal || 1;
    return margin.top + plotHeight - ((v - minVal) / range) * plotHeight;
  };

  const polylinePoints = data
    .map((d) => `${toX(d.timestamp).toFixed(1)},${toY(d.mttrMs).toFixed(1)}`)
    .join(" ");

  const areaPoints = `${toX(data[0].timestamp).toFixed(1)},${(margin.top + plotHeight).toFixed(1)} ${polylinePoints} ${toX(data[data.length - 1].timestamp).toFixed(1)},${(margin.top + plotHeight).toFixed(1)}`;

  // Y-axis ticks
  const yTicks = Array.from({ length: 5 }, (_, i) => (maxVal / 4) * i);

  // X-axis ticks
  const xTicks = data.filter((_, i) => i % 3 === 0).map((d) => d.timestamp);

  const gradientId = "mttr-chart-fill";

  return (
    <svg
      width="100%"
      height={height}
      viewBox={`0 0 ${width} ${height}`}
      preserveAspectRatio="xMidYMid meet"
      className="overflow-visible"
    >
      <defs>
        <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="var(--fizzbuzz-400)" stopOpacity="0.15" />
          <stop offset="100%" stopColor="var(--fizzbuzz-400)" stopOpacity="0.01" />
        </linearGradient>
      </defs>

      {/* Grid lines */}
      {yTicks.map((tick, i) => (
        <line
          key={`y-grid-${i}`}
          x1={margin.left}
          x2={width - margin.right}
          y1={toY(tick)}
          y2={toY(tick)}
          stroke="var(--panel-700)"
          strokeWidth="0.5"
        />
      ))}

      {/* Y-axis labels */}
      {yTicks.map((tick, i) => (
        <text
          key={`y-label-${i}`}
          x={margin.left - 8}
          y={toY(tick)}
          textAnchor="end"
          dominantBaseline="middle"
          className="text-[10px] fill-panel-500"
        >
          {tick >= 1000 ? `${(tick / 1000).toFixed(1)}s` : `${Math.round(tick)}ms`}
        </text>
      ))}

      {/* X-axis labels */}
      {xTicks.map((tick, i) => (
        <text
          key={`x-label-${i}`}
          x={toX(tick)}
          y={height - 6}
          textAnchor="middle"
          className="text-[10px] fill-panel-500"
        >
          {new Date(tick).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", hour12: false })}
        </text>
      ))}

      {/* SLA target line */}
      <line
        x1={margin.left}
        x2={width - margin.right}
        y1={toY(slaTarget)}
        y2={toY(slaTarget)}
        stroke="var(--red-400, #f87171)"
        strokeWidth="1"
        strokeDasharray="6,4"
      />
      <text
        x={width - margin.right + 4}
        y={toY(slaTarget)}
        dominantBaseline="middle"
        className="text-[9px] fill-red-400"
      >
        SLA
      </text>

      {/* Area fill */}
      <polygon points={areaPoints} fill={`url(#${gradientId})`} />

      {/* Data line */}
      <polyline
        points={polylinePoints}
        fill="none"
        stroke="var(--fizzbuzz-400)"
        strokeWidth="1.5"
        strokeLinejoin="round"
        strokeLinecap="round"
      />

      {/* Data points */}
      {data.map((d, i) => (
        <circle
          key={i}
          cx={toX(d.timestamp)}
          cy={toY(d.mttrMs)}
          r={3}
          fill="var(--fizzbuzz-400)"
          stroke="var(--panel-900)"
          strokeWidth="1.5"
        />
      ))}
    </svg>
  );
}

// ---------------------------------------------------------------------------
// Page Component
// ---------------------------------------------------------------------------

export default function ChaosEngineeringPage() {
  const provider = useDataProvider();

  const [experiments, setExperiments] = useState<ChaosExperiment[]>([]);
  const [metrics, setMetrics] = useState<ChaosMetrics | null>(null);
  const [scenarios, setScenarios] = useState<GameDayScenario[]>([]);
  const [activeExperiment, setActiveExperiment] = useState<ChaosExperiment | null>(null);
  const [elapsedSec, setElapsedSec] = useState(0);
  const [loading, setLoading] = useState(true);

  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const completionRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Initial load and periodic refresh
  const loadData = useCallback(async () => {
    try {
      const [exps, met, scens] = await Promise.all([
        provider.getChaosExperiments(),
        provider.getChaosMetrics(),
        provider.getGameDayScenarios(),
      ]);
      setExperiments(exps);
      setMetrics(met);
      setScenarios(scens);
    } catch {
      // Telemetry subsystem handles error reporting
    } finally {
      setLoading(false);
    }
  }, [provider]);

  useEffect(() => {
    loadData();
    const interval = setInterval(loadData, REFRESH_INTERVAL_MS);
    return () => clearInterval(interval);
  }, [loadData]);

  // Handle fault injection
  const handleInjectFault = useCallback(
    async (experimentId: string) => {
      try {
        const running = await provider.runChaosExperiment(experimentId);
        setActiveExperiment(running);
        setElapsedSec(0);

        // Update the experiment status in the catalog
        setExperiments((prev) =>
          prev.map((e) => (e.id === experimentId ? { ...e, status: "running" as const } : e))
        );

        // Progress timer — increments elapsed seconds
        if (timerRef.current) clearInterval(timerRef.current);
        timerRef.current = setInterval(() => {
          setElapsedSec((prev) => prev + 1);
        }, 1000);

        // Completion timer — marks experiment as completed after estimated duration
        if (completionRef.current) clearTimeout(completionRef.current);
        completionRef.current = setTimeout(() => {
          if (timerRef.current) clearInterval(timerRef.current);

          setExperiments((prev) =>
            prev.map((e) =>
              e.id === experimentId
                ? {
                    ...e,
                    status: "completed" as const,
                    results: running.results,
                    lastRunAt: running.lastRunAt,
                  }
                : e
            )
          );
          setActiveExperiment(null);
          setElapsedSec(0);
        }, running.estimatedDurationSec * 1000);
      } catch {
        // Fault injection failure is itself a form of chaos
      }
    },
    [provider]
  );

  // Handle Game Day start (runs first experiment in the scenario)
  const handleStartGameDay = useCallback(
    async (scenarioId: string) => {
      const scenario = scenarios.find((s) => s.id === scenarioId);
      if (!scenario || scenario.experiments.length === 0) return;

      setScenarios((prev) =>
        prev.map((s) =>
          s.id === scenarioId
            ? { ...s, status: "in-progress" as const, currentPhase: 0, startedAt: new Date().toISOString() }
            : s
        )
      );

      // Execute the first experiment in the scenario
      await handleInjectFault(scenario.experiments[0]);
    },
    [scenarios, handleInjectFault]
  );

  // Cleanup timers on unmount
  useEffect(() => {
    return () => {
      if (timerRef.current) clearInterval(timerRef.current);
      if (completionRef.current) clearTimeout(completionRef.current);
    };
  }, []);

  const isAnyRunning = activeExperiment !== null;

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64 text-sm text-panel-400">
        Initializing chaos engineering control plane...
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Page Header */}
      <div>
        <h1 className="text-lg font-semibold text-panel-50">
          Chaos Engineering Control Plane
        </h1>
        <p className="mt-1 text-sm text-panel-400">
          Fault injection experiments, Game Day scenarios, and resilience metrics
          for the Enterprise FizzBuzz evaluation pipeline.
        </p>
      </div>

      {/* Section A: Metrics Summary Bar */}
      {metrics && (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          <Card>
            <CardContent>
              <p className="text-xs text-panel-400 mb-1">Resilience Score</p>
              <p
                className={`text-2xl font-mono font-bold ${
                  metrics.resilienceScore >= 80
                    ? "text-fizz-400"
                    : metrics.resilienceScore >= 60
                      ? "text-amber-400"
                      : "text-red-400"
                }`}
              >
                {metrics.resilienceScore}
              </p>
              <p className="text-xs text-panel-500 mt-1">out of 100</p>
            </CardContent>
          </Card>
          <Card>
            <CardContent>
              <p className="text-xs text-panel-400 mb-1">Experiments Run</p>
              <p className="text-2xl font-mono font-bold text-panel-50">
                {metrics.experimentsRun}
              </p>
              {metrics.lastExperimentAt && (
                <p className="text-xs text-panel-500 mt-1">
                  Last run: {formatRelativeTime(metrics.lastExperimentAt)}
                </p>
              )}
            </CardContent>
          </Card>
          <Card>
            <CardContent>
              <p className="text-xs text-panel-400 mb-1">Mean Time to Recovery</p>
              <p className="text-2xl font-mono font-bold text-panel-50">
                {(metrics.meanTimeToRecovery / 1000).toFixed(1)}s
              </p>
              <p className="text-xs text-panel-500 mt-1">
                {metrics.meanTimeToRecovery < 5000 ? "\u2193 within SLA" : "\u2191 exceeds SLA target"}
              </p>
            </CardContent>
          </Card>
          <Card>
            <CardContent>
              <p className="text-xs text-panel-400 mb-1">Active Faults</p>
              <p
                className={`text-2xl font-mono font-bold ${
                  metrics.activeExperiments > 0 ? "text-amber-400" : "text-panel-50"
                }`}
              >
                {metrics.activeExperiments}
              </p>
              <p className="text-xs text-panel-500 mt-1">
                {metrics.faultsInjected} total faults injected
              </p>
            </CardContent>
          </Card>
        </div>
      )}

      {/* Section B + C: Experiment Catalog and Active Experiment Panel */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Experiment Catalog (left 2/3) */}
        <div className="lg:col-span-2 space-y-4">
          <h2 className="text-sm font-semibold text-panel-300 uppercase tracking-wider">
            Experiment Catalog
          </h2>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {experiments.map((exp) => (
              <ExperimentCard
                key={exp.id}
                experiment={exp}
                onInject={handleInjectFault}
                isAnyRunning={isAnyRunning}
              />
            ))}
          </div>
        </div>

        {/* Active Experiment Panel (right 1/3) */}
        <div className="lg:col-span-1">
          <h2 className="text-sm font-semibold text-panel-300 uppercase tracking-wider mb-4">
            Live Injection Monitor
          </h2>
          <ActiveExperimentPanel
            experiment={activeExperiment}
            elapsedSec={elapsedSec}
          />
        </div>
      </div>

      {/* Section D: Game Day Scenarios */}
      <div className="space-y-4">
        <h2 className="text-sm font-semibold text-panel-300 uppercase tracking-wider">
          Game Day Scenarios
        </h2>
        <div className="space-y-3">
          {scenarios.map((scenario) => (
            <GameDayPanel
              key={scenario.id}
              scenario={scenario}
              experiments={experiments}
              isAnyRunning={isAnyRunning}
              onStart={handleStartGameDay}
            />
          ))}
        </div>
      </div>

      {/* Section E: Recovery Metrics Chart */}
      {metrics && metrics.mttrHistory.length > 0 && (
        <div className="space-y-4">
          <h2 className="text-sm font-semibold text-panel-300 uppercase tracking-wider">
            Recovery Metrics — MTTR Trend (24h)
          </h2>
          <Card>
            <CardContent>
              <MttrChart data={metrics.mttrHistory} />
            </CardContent>
          </Card>
        </div>
      )}
    </div>
  );
}
