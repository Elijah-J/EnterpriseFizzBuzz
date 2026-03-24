"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { Reveal } from "@/components/ui/reveal";
import { Skeleton } from "@/components/ui/skeleton";
import type {
  FLClient,
  FLModelState,
  FLTrainingRound,
} from "@/lib/data-providers";
import { useDataProvider } from "@/lib/data-providers";

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const REFRESH_INTERVAL_MS = 10_000;

// ---------------------------------------------------------------------------
// SVG Chart: Client Topology (Star Network)
// ---------------------------------------------------------------------------

function ClientTopologyDiagram({
  clients,
  width,
  height,
}: {
  clients: FLClient[];
  width: number;
  height: number;
}) {
  const cx = width / 2;
  const cy = height / 2;
  const radius = Math.min(width, height) * 0.35;

  const statusColor: Record<string, string> = {
    training: "#22c55e",
    idle: "#94a3b8",
    uploading: "#f59e0b",
    offline: "#ef4444",
  };

  return (
    <svg
      width={width}
      height={height}
      viewBox={`0 0 ${width} ${height}`}
      className="min-w-full"
    >
      {/* Central aggregation server */}
      <circle
        cx={cx}
        cy={cy}
        r={22}
        fill="#1e293b"
        stroke="#6366f1"
        strokeWidth={2.5}
      />
      <text
        x={cx}
        y={cy + 1}
        textAnchor="middle"
        dominantBaseline="middle"
        className="fill-indigo-300 text-[10px] font-semibold"
      >
        AGG
      </text>

      {/* Client nodes */}
      {clients.map((client, i) => {
        const angle = (2 * Math.PI * i) / clients.length - Math.PI / 2;
        const nx = cx + radius * Math.cos(angle);
        const ny = cy + radius * Math.sin(angle);
        const color = statusColor[client.status] ?? "#94a3b8";

        return (
          <g key={client.id}>
            {/* Connection line */}
            <line
              x1={cx}
              y1={cy}
              x2={nx}
              y2={ny}
              stroke={client.status === "offline" ? "#334155" : "#475569"}
              strokeWidth={client.status === "offline" ? 1 : 1.5}
              strokeDasharray={client.status === "offline" ? "4,4" : undefined}
            />
            {/* Node circle */}
            <circle
              cx={nx}
              cy={ny}
              r={16}
              fill="#1e293b"
              stroke={color}
              strokeWidth={2}
            />
            {/* Region label */}
            <text
              x={nx}
              y={ny - 1}
              textAnchor="middle"
              dominantBaseline="middle"
              className="fill-panel-200 text-[8px] font-medium"
            >
              {client.region.split("-")[0]}
            </text>
            {/* Status dot */}
            <circle cx={nx + 12} cy={ny - 12} r={4} fill={color} />
          </g>
        );
      })}

      {/* Legend */}
      {Object.entries(statusColor).map(([status, color], i) => (
        <g key={status} transform={`translate(10, ${height - 70 + i * 16})`}>
          <circle cx={5} cy={0} r={4} fill={color} />
          <text
            x={14}
            y={1}
            dominantBaseline="middle"
            className="fill-panel-400 text-[10px]"
          >
            {status}
          </text>
        </g>
      ))}
    </svg>
  );
}

// ---------------------------------------------------------------------------
// SVG Chart: Privacy Budget Meter
// ---------------------------------------------------------------------------

function PrivacyBudgetMeter({
  remaining,
  total,
  width,
  height,
}: {
  remaining: number;
  total: number;
  width: number;
  height: number;
}) {
  const fraction = Math.max(0, Math.min(1, remaining / total));
  const barWidth = width - 80;
  const barHeight = 24;
  const barX = 50;
  const barY = height / 2 - barHeight / 2;

  // Color transitions: green > 60%, amber 30-60%, red < 30%
  const fillColor =
    fraction > 0.6 ? "#22c55e" : fraction > 0.3 ? "#f59e0b" : "#ef4444";

  return (
    <svg
      width={width}
      height={height}
      viewBox={`0 0 ${width} ${height}`}
      className="min-w-full"
    >
      {/* Label */}
      <text
        x={barX - 4}
        y={barY - 6}
        textAnchor="end"
        className="fill-panel-400 text-[10px]"
      >
        Budget
      </text>
      {/* Background track */}
      <rect
        x={barX}
        y={barY}
        width={barWidth}
        height={barHeight}
        rx={4}
        fill="#1e293b"
      />
      {/* Filled portion */}
      <rect
        x={barX}
        y={barY}
        width={barWidth * fraction}
        height={barHeight}
        rx={4}
        fill={fillColor}
        opacity={0.8}
      />
      {/* Epsilon labels */}
      <text
        x={barX + barWidth + 6}
        y={barY + barHeight / 2 + 1}
        dominantBaseline="middle"
        className="fill-panel-300 text-[11px] font-mono"
      >
        {remaining.toFixed(1)} / {total.toFixed(1)}
      </text>
      {/* Unit label */}
      <text
        x={barX + barWidth / 2}
        y={barY + barHeight / 2 + 1}
        textAnchor="middle"
        dominantBaseline="middle"
        className="fill-panel-950 text-[10px] font-semibold"
      >
        {(fraction * 100).toFixed(1)}% remaining
      </text>
    </svg>
  );
}

// ---------------------------------------------------------------------------
// SVG Chart: Training Convergence
// ---------------------------------------------------------------------------

const CONV_LEFT = 50;
const CONV_TOP = 15;
const CONV_RIGHT = 15;
const CONV_BOTTOM = 30;

function ConvergenceChart({
  rounds,
  width,
  height,
}: {
  rounds: FLTrainingRound[];
  width: number;
  height: number;
}) {
  const plotW = width - CONV_LEFT - CONV_RIGHT;
  const plotH = height - CONV_TOP - CONV_BOTTOM;

  if (rounds.length === 0) {
    return (
      <svg width={width} height={height} className="min-w-full">
        <text
          x={width / 2}
          y={height / 2}
          textAnchor="middle"
          className="fill-text-muted text-sm"
        >
          No training data. Start a training round to begin.
        </text>
      </svg>
    );
  }

  const maxRound = rounds[rounds.length - 1].roundNumber;
  const xScale = maxRound > 1 ? plotW / (maxRound - 1) : plotW;
  const toX = (r: number) => CONV_LEFT + (r - 1) * xScale;
  const toY = (val: number) => CONV_TOP + plotH * (1 - val);

  // Accuracy line
  const accLine = rounds
    .map((r) => `${toX(r.roundNumber)},${toY(r.globalAccuracy)}`)
    .join(" ");

  return (
    <svg
      width={width}
      height={height}
      viewBox={`0 0 ${width} ${height}`}
      className="min-w-full"
    >
      {/* Grid lines at 0.25 increments */}
      {[0, 0.25, 0.5, 0.75, 1.0].map((v) => (
        <g key={v}>
          <line
            x1={CONV_LEFT}
            y1={toY(v)}
            x2={CONV_LEFT + plotW}
            y2={toY(v)}
            stroke="#334155"
            strokeWidth={0.5}
          />
          <text
            x={CONV_LEFT - 6}
            y={toY(v)}
            textAnchor="end"
            dominantBaseline="middle"
            className="fill-text-muted text-[10px]"
          >
            {v.toFixed(2)}
          </text>
        </g>
      ))}

      {/* X-axis labels (every 5 rounds) */}
      {rounds
        .filter((r) => r.roundNumber % 5 === 0 || r.roundNumber === 1)
        .map((r) => (
          <text
            key={r.roundNumber}
            x={toX(r.roundNumber)}
            y={CONV_TOP + plotH + 16}
            textAnchor="middle"
            className="fill-text-muted text-[10px]"
          >
            R{r.roundNumber}
          </text>
        ))}

      {/* Accuracy area fill */}
      <polygon
        points={`${toX(rounds[0].roundNumber)},${toY(0)} ${accLine} ${toX(rounds[rounds.length - 1].roundNumber)},${toY(0)}`}
        fill="#22c55e"
        opacity={0.1}
      />

      {/* Accuracy polyline */}
      <polyline points={accLine} fill="none" stroke="#22c55e" strokeWidth={2} />

      {/* Data point markers */}
      {rounds.map((r) => (
        <circle
          key={r.roundNumber}
          cx={toX(r.roundNumber)}
          cy={toY(r.globalAccuracy)}
          r={3}
          fill="#22c55e"
        />
      ))}

      {/* Y-axis label */}
      <text
        x={12}
        y={CONV_TOP + plotH / 2}
        textAnchor="middle"
        dominantBaseline="middle"
        transform={`rotate(-90, 12, ${CONV_TOP + plotH / 2})`}
        className="fill-panel-400 text-[10px]"
      >
        Global Accuracy
      </text>
    </svg>
  );
}

// ---------------------------------------------------------------------------
// SVG Chart: Weight Aggregation Visualization
// ---------------------------------------------------------------------------

function WeightAggregationChart({
  round,
  clients,
  width,
  height,
}: {
  round: FLTrainingRound | null;
  clients: FLClient[];
  width: number;
  height: number;
}) {
  if (!round) {
    return (
      <svg width={width} height={height} className="min-w-full">
        <text
          x={width / 2}
          y={height / 2}
          textAnchor="middle"
          className="fill-text-muted text-sm"
        >
          Select a training round to view weight contributions.
        </text>
      </svg>
    );
  }

  const entries = Object.entries(round.clientWeights);
  const barHeight = 20;
  const gap = 8;
  const labelWidth = 120;
  const rightPad = 50;
  const maxBarWidth = width - labelWidth - rightPad;
  const totalHeight = entries.length * (barHeight + gap);
  const offsetY = Math.max(0, (height - totalHeight) / 2);

  const colors = ["#6366f1", "#22c55e", "#f59e0b", "#ef4444", "#06b6d4"];

  return (
    <svg
      width={width}
      height={height}
      viewBox={`0 0 ${width} ${height}`}
      className="min-w-full"
    >
      {entries.map(([clientId, weight], i) => {
        const client = clients.find((c) => c.id === clientId);
        const y = offsetY + i * (barHeight + gap);
        const barW = maxBarWidth * weight;

        return (
          <g key={clientId}>
            {/* Client label */}
            <text
              x={labelWidth - 6}
              y={y + barHeight / 2}
              textAnchor="end"
              dominantBaseline="middle"
              className="fill-panel-300 text-[10px]"
            >
              {client?.name ?? clientId}
            </text>
            {/* Background track */}
            <rect
              x={labelWidth}
              y={y}
              width={maxBarWidth}
              height={barHeight}
              rx={3}
              fill="#1e293b"
            />
            {/* Weight bar */}
            <rect
              x={labelWidth}
              y={y}
              width={barW}
              height={barHeight}
              rx={3}
              fill={colors[i % colors.length]}
              opacity={0.8}
            />
            {/* Weight value */}
            <text
              x={labelWidth + barW + 6}
              y={y + barHeight / 2}
              dominantBaseline="middle"
              className="fill-panel-400 text-[10px] font-mono"
            >
              {(weight * 100).toFixed(1)}%
            </text>
          </g>
        );
      })}
    </svg>
  );
}

// ---------------------------------------------------------------------------
// Page Component
// ---------------------------------------------------------------------------

export default function FederatedLearningPage() {
  const provider = useDataProvider();
  const [clients, setClients] = useState<FLClient[]>([]);
  const [history, setHistory] = useState<FLTrainingRound[]>([]);
  const [modelState, setModelState] = useState<FLModelState | null>(null);
  const [selectedRoundIdx, setSelectedRoundIdx] = useState<number | null>(null);
  const [isTraining, setIsTraining] = useState(false);
  const [budgetExhausted, setBudgetExhausted] = useState(false);

  // -----------------------------------------------------------------------
  // Data fetching
  // -----------------------------------------------------------------------

  const refresh = useCallback(async () => {
    const [c, h, m] = await Promise.all([
      provider.getFLClients(),
      provider.getFLTrainingHistory(),
      provider.getFLModelState(),
    ]);
    setClients(c);
    setHistory(h);
    setModelState(m);
  }, [provider]);

  useEffect(() => {
    refresh();
    const timer = setInterval(refresh, REFRESH_INTERVAL_MS);
    return () => clearInterval(timer);
  }, [refresh]);

  // -----------------------------------------------------------------------
  // Training action
  // -----------------------------------------------------------------------

  const handleStartRound = useCallback(async () => {
    setIsTraining(true);
    try {
      const result = await provider.startFLTrainingRound();
      if (result === null) {
        setBudgetExhausted(true);
      } else {
        setSelectedRoundIdx(null);
        await refresh();
      }
    } finally {
      setIsTraining(false);
    }
  }, [provider, refresh]);

  // -----------------------------------------------------------------------
  // Derived state
  // -----------------------------------------------------------------------

  const selectedRound = useMemo(() => {
    if (selectedRoundIdx === null && history.length > 0) {
      return history[history.length - 1];
    }
    if (selectedRoundIdx !== null && selectedRoundIdx < history.length) {
      return history[selectedRoundIdx];
    }
    return null;
  }, [history, selectedRoundIdx]);

  return (
    <div className="space-y-6">
      {/* Page header */}
      <div className="flex items-start justify-between">
        <div>
          <h1 className="heading-page">Federated Learning Training Center</h1>
          <p className="mt-1 text-sm text-text-secondary">
            Privacy-preserving distributed model training across geographically
            dispersed FizzBuzz evaluation nodes. Each client trains on its local
            dataset without sharing raw data, contributing only encrypted model
            deltas to the central aggregation server.
          </p>
        </div>
        <Button
          onClick={handleStartRound}
          disabled={isTraining || budgetExhausted}
        >
          {isTraining
            ? "Training..."
            : budgetExhausted
              ? "Budget Exhausted"
              : "Start Training Round"}
        </Button>
      </div>

      {/* KPI Summary */}
      {modelState && (
        <div className="grid grid-cols-2 gap-4 md:grid-cols-4 xl:grid-cols-6">
          <Card>
            <CardContent className="p-4">
              <p className="text-xs text-text-secondary">Global Accuracy</p>
              <p className="mt-1 text-xl font-bold text-fizz-400">
                {(modelState.globalAccuracy * 100).toFixed(2)}%
              </p>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="p-4">
              <p className="text-xs text-text-secondary">Training Rounds</p>
              <p className="mt-1 text-xl font-bold text-text-primary">
                {modelState.totalRounds}
              </p>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="p-4">
              <p className="text-xs text-text-secondary">Convergence Rate</p>
              <p className="mt-1 text-xl font-bold text-text-primary">
                {modelState.convergenceRate > 0 ? "+" : ""}
                {(modelState.convergenceRate * 100).toFixed(3)}%/rd
              </p>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="p-4">
              <p className="text-xs text-text-secondary">Weight Divergence</p>
              <p className="mt-1 text-xl font-bold text-amber-400">
                {(modelState.weightDivergence * 100).toFixed(1)}%
              </p>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="p-4">
              <p className="text-xs text-text-secondary">Active Clients</p>
              <p className="mt-1 text-xl font-bold text-text-primary">
                {clients.filter((c) => c.status !== "offline").length} /{" "}
                {clients.length}
              </p>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="p-4">
              <p className="text-xs text-text-secondary">Privacy Budget</p>
              <p
                className={`mt-1 text-xl font-bold ${
                  modelState.privacyBudgetRemaining /
                    modelState.totalPrivacyBudget >
                  0.3
                    ? "text-fizz-400"
                    : "text-red-400"
                }`}
              >
                {modelState.privacyBudgetRemaining.toFixed(1)} /{" "}
                {modelState.totalPrivacyBudget.toFixed(1)}
              </p>
            </CardContent>
          </Card>
        </div>
      )}

      {/* Topology and Privacy Budget */}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <h2 className="heading-section">Client Topology</h2>
          </CardHeader>
          <CardContent>
            <ClientTopologyDiagram clients={clients} width={400} height={300} />
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <h2 className="heading-section">Differential Privacy Budget</h2>
          </CardHeader>
          <CardContent>
            {modelState && (
              <PrivacyBudgetMeter
                remaining={modelState.privacyBudgetRemaining}
                total={modelState.totalPrivacyBudget}
                width={460}
                height={60}
              />
            )}
            <p className="mt-3 text-xs text-text-muted">
              The privacy budget tracks cumulative epsilon expenditure across
              all training rounds. Once exhausted, no further training rounds
              may be initiated without violating the differential privacy
              guarantee for modulo operations.
            </p>
            {budgetExhausted && (
              <Badge variant="error" className="mt-2">
                Privacy budget exhausted — training suspended
              </Badge>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Convergence Chart and Weight Aggregation */}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <h2 className="heading-section">Training Convergence</h2>
          </CardHeader>
          <CardContent>
            <ConvergenceChart rounds={history} width={500} height={280} />
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <div className="flex items-center justify-between">
              <h2 className="heading-section">Weight Aggregation</h2>
              {selectedRound && (
                <Badge variant="info">
                  Round {selectedRound.roundNumber} &middot;{" "}
                  {selectedRound.aggregationMethod}
                </Badge>
              )}
            </div>
          </CardHeader>
          <CardContent>
            <WeightAggregationChart
              round={selectedRound}
              clients={clients}
              width={500}
              height={200}
            />
          </CardContent>
        </Card>
      </div>

      {/* Client Table */}
      <Card>
        <CardHeader>
          <h2 className="heading-section">Client Nodes</h2>
        </CardHeader>
        <CardContent>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border-subtle text-left text-xs text-text-secondary">
                  <th className="pb-2 pr-4">Name</th>
                  <th className="pb-2 pr-4">Region</th>
                  <th className="pb-2 pr-4">Status</th>
                  <th className="pb-2 pr-4 text-right">Local Accuracy</th>
                  <th className="pb-2 pr-4 text-right">Dataset Size</th>
                  <th className="pb-2 pr-4 text-right">Rounds</th>
                  <th className="pb-2 text-right">Privacy Budget Used</th>
                </tr>
              </thead>
              <tbody>
                {clients.map((client) => (
                  <tr
                    key={client.id}
                    className="border-b border-panel-800 text-text-secondary"
                  >
                    <td className="py-2 pr-4 font-mono text-xs">
                      {client.name}
                    </td>
                    <td className="py-2 pr-4">{client.region}</td>
                    <td className="py-2 pr-4">
                      <Badge
                        variant={
                          client.status === "training"
                            ? "success"
                            : client.status === "offline"
                              ? "error"
                              : client.status === "uploading"
                                ? "warning"
                                : "info"
                        }
                      >
                        {client.status}
                      </Badge>
                    </td>
                    <td className="py-2 pr-4 text-right font-mono">
                      {(client.localAccuracy * 100).toFixed(2)}%
                    </td>
                    <td className="py-2 pr-4 text-right font-mono">
                      {client.dataSize.toLocaleString()}
                    </td>
                    <td className="py-2 pr-4 text-right font-mono">
                      {client.roundsParticipated}
                    </td>
                    <td className="py-2 text-right font-mono">
                      {client.privacyBudgetUsed.toFixed(2)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>

      {/* Training Round History */}
      <Card>
        <CardHeader>
          <h2 className="heading-section">Training Round History</h2>
        </CardHeader>
        <CardContent>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border-subtle text-left text-xs text-text-secondary">
                  <th className="pb-2 pr-4">Round</th>
                  <th className="pb-2 pr-4">Participants</th>
                  <th className="pb-2 pr-4">Method</th>
                  <th className="pb-2 pr-4 text-right">Accuracy</th>
                  <th className="pb-2 pr-4 text-right">Privacy Cost</th>
                  <th className="pb-2 text-right">Duration</th>
                </tr>
              </thead>
              <tbody>
                {[...history].reverse().map((round, displayIdx) => {
                  const actualIdx = history.length - 1 - displayIdx;
                  const isSelected =
                    selectedRoundIdx === actualIdx ||
                    (selectedRoundIdx === null &&
                      actualIdx === history.length - 1);

                  return (
                    <tr
                      key={round.roundNumber}
                      onClick={() => setSelectedRoundIdx(actualIdx)}
                      className={`cursor-pointer border-b border-panel-800 transition-colors ${
                        isSelected
                          ? "bg-surface-raised text-text-primary"
                          : "text-text-secondary hover:bg-surface-raised/50"
                      }`}
                    >
                      <td className="py-2 pr-4 font-mono">
                        {round.roundNumber}
                      </td>
                      <td className="py-2 pr-4">
                        {round.participants.length} clients
                      </td>
                      <td className="py-2 pr-4">
                        <Badge variant="info">{round.aggregationMethod}</Badge>
                      </td>
                      <td className="py-2 pr-4 text-right font-mono text-fizz-400">
                        {(round.globalAccuracy * 100).toFixed(2)}%
                      </td>
                      <td className="py-2 pr-4 text-right font-mono">
                        {round.privacyBudgetSpent.toFixed(3)}
                      </td>
                      <td className="py-2 text-right font-mono">
                        {round.durationMs.toLocaleString()}ms
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
