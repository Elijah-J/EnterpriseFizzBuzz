"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { useDataProvider } from "@/lib/data-providers";
import type {
  QuantumCircuit,
  QuantumState,
  QuantumSimulationResult,
} from "@/lib/data-providers";

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const SHOT_PRESETS = [128, 256, 512, 1024, 4096, 8192] as const;

/** Gate color assignments following the platform's quantum visualization palette. */
const GATE_COLORS: Record<string, string> = {
  H: "#38bdf8",    // sky-400
  X: "#fb7185",    // rose-400
  Z: "#a78bfa",    // violet-400
  S: "#a78bfa",    // violet-400
  T: "#a78bfa",    // violet-400
  CNOT: "#34d399",  // emerald-400
  CZ: "#34d399",   // emerald-400
  SWAP: "#34d399",  // emerald-400
  M: "#fbbf24",    // amber-400
};

const GATE_TEXT_CLASSES: Record<string, string> = {
  H: "text-sky-400",
  X: "text-rose-400",
  Z: "text-violet-400",
  S: "text-violet-400",
  T: "text-violet-400",
  CNOT: "text-emerald-400",
  CZ: "text-emerald-400",
  SWAP: "text-emerald-400",
  M: "text-amber-400",
};

// ---------------------------------------------------------------------------
// SVG Circuit Diagram renderer
// ---------------------------------------------------------------------------

const WIRE_Y_SPACING = 48;
const STEP_X_SPACING = 64;
const GATE_SIZE = 32;
const LEFT_MARGIN = 60;
const TOP_MARGIN = 30;
const RIGHT_MARGIN = 40;
const BOTTOM_MARGIN = 40;

function CircuitDiagram({ circuit }: { circuit: QuantumCircuit }) {
  const maxStep = Math.max(...circuit.gates.map((g) => g.step), 0);
  const svgWidth = LEFT_MARGIN + (maxStep + 1) * STEP_X_SPACING + RIGHT_MARGIN;
  const svgHeight =
    TOP_MARGIN +
    circuit.numQubits * WIRE_Y_SPACING +
    BOTTOM_MARGIN;

  const wireY = (qubit: number) => TOP_MARGIN + qubit * WIRE_Y_SPACING + WIRE_Y_SPACING / 2;
  const stepX = (step: number) => LEFT_MARGIN + step * STEP_X_SPACING + STEP_X_SPACING / 2;

  return (
    <div className="overflow-x-auto">
      <svg
        width={svgWidth}
        height={svgHeight}
        viewBox={`0 0 ${svgWidth} ${svgHeight}`}
        className="min-w-full"
      >
        {/* Qubit wire labels */}
        {Array.from({ length: circuit.numQubits }, (_, q) => (
          <text
            key={`label-${q}`}
            x={LEFT_MARGIN - 12}
            y={wireY(q) + 4}
            textAnchor="end"
            className="fill-panel-400 text-xs font-mono"
            fontSize={11}
          >
            q{q}
          </text>
        ))}

        {/* Qubit wires */}
        {Array.from({ length: circuit.numQubits }, (_, q) => (
          <line
            key={`wire-${q}`}
            x1={LEFT_MARGIN}
            y1={wireY(q)}
            x2={svgWidth - RIGHT_MARGIN}
            y2={wireY(q)}
            stroke="#475569"
            strokeWidth={1}
          />
        ))}

        {/* Classical register lines (dashed, below qubit wires) */}
        {Array.from({ length: circuit.numClassicalBits }, (_, c) => {
          const y = TOP_MARGIN + circuit.numQubits * WIRE_Y_SPACING + 8 + c * 4;
          return (
            <line
              key={`classical-${c}`}
              x1={LEFT_MARGIN}
              y1={y}
              x2={svgWidth - RIGHT_MARGIN}
              y2={y}
              stroke="#334155"
              strokeWidth={0.5}
              strokeDasharray="4 3"
            />
          );
        })}

        {/* Gate rendering */}
        {circuit.gates.map((gate, i) => {
          const x = stepX(gate.step);
          const y = wireY(gate.qubit);
          const color = GATE_COLORS[gate.type] ?? "#94a3b8";

          if (gate.type === "CNOT" && gate.controlQubit !== undefined) {
            // Two-qubit CNOT: control dot + target circle-plus + connecting line
            const cy = wireY(gate.controlQubit);
            return (
              <g key={`gate-${i}`}>
                {/* Vertical connection line */}
                <line
                  x1={x}
                  y1={Math.min(y, cy)}
                  x2={x}
                  y2={Math.max(y, cy)}
                  stroke={color}
                  strokeWidth={1.5}
                />
                {/* Control qubit: filled circle */}
                <circle cx={x} cy={cy} r={4} fill={color} />
                {/* Target qubit: circle with plus */}
                <circle
                  cx={x}
                  cy={y}
                  r={10}
                  fill="none"
                  stroke={color}
                  strokeWidth={1.5}
                />
                <line
                  x1={x - 7}
                  y1={y}
                  x2={x + 7}
                  y2={y}
                  stroke={color}
                  strokeWidth={1.5}
                />
                <line
                  x1={x}
                  y1={y - 7}
                  x2={x}
                  y2={y + 7}
                  stroke={color}
                  strokeWidth={1.5}
                />
              </g>
            );
          }

          if (gate.type === "M") {
            // Measurement: meter icon (arc with arrow)
            return (
              <g key={`gate-${i}`}>
                <rect
                  x={x - GATE_SIZE / 2}
                  y={y - GATE_SIZE / 2}
                  width={GATE_SIZE}
                  height={GATE_SIZE}
                  rx={3}
                  fill="#1e293b"
                  stroke={color}
                  strokeWidth={1.2}
                />
                {/* Arc */}
                <path
                  d={`M ${x - 8} ${y + 4} A 10 10 0 0 1 ${x + 8} ${y + 4}`}
                  fill="none"
                  stroke={color}
                  strokeWidth={1.2}
                />
                {/* Arrow from center pointing up-right */}
                <line
                  x1={x}
                  y1={y + 4}
                  x2={x + 6}
                  y2={y - 8}
                  stroke={color}
                  strokeWidth={1.2}
                />
              </g>
            );
          }

          // Single-qubit gate: colored rectangle with label
          return (
            <g key={`gate-${i}`}>
              <rect
                x={x - GATE_SIZE / 2}
                y={y - GATE_SIZE / 2}
                width={GATE_SIZE}
                height={GATE_SIZE}
                rx={3}
                fill="#1e293b"
                stroke={color}
                strokeWidth={1.2}
              />
              <text
                x={x}
                y={y + 4}
                textAnchor="middle"
                fill={color}
                fontSize={12}
                fontWeight={600}
                fontFamily="monospace"
              >
                {gate.type}
              </text>
            </g>
          );
        })}
      </svg>
    </div>
  );
}

// ---------------------------------------------------------------------------
// State Vector Bar Chart
// ---------------------------------------------------------------------------

function StateVectorChart({
  state,
  maxDisplay = 16,
}: {
  state: QuantumState;
  maxDisplay?: number;
}) {
  const [hoveredIdx, setHoveredIdx] = useState<number | null>(null);

  // For large state spaces, show only the top states by probability
  const displayData = useMemo(() => {
    if (state.basisLabels.length <= maxDisplay) {
      return state.probabilities.map((p, i) => ({
        label: state.basisLabels[i],
        probability: p,
        amplitude: state.amplitudes[i],
        index: i,
      }));
    }
    // Sort by probability descending, take top entries
    const indexed = state.probabilities
      .map((p, i) => ({ p, i }))
      .sort((a, b) => b.p - a.p)
      .slice(0, 8);
    return indexed.map(({ p, i }) => ({
      label: state.basisLabels[i],
      probability: p,
      amplitude: state.amplitudes[i],
      index: i,
    }));
  }, [state, maxDisplay]);

  const hiddenCount = state.basisLabels.length > maxDisplay
    ? state.basisLabels.length - 8
    : 0;

  const chartWidth = 500;
  const chartHeight = 200;
  const barPadding = 4;
  const leftPad = 40;
  const bottomPad = 50;
  const topPad = 10;
  const plotWidth = chartWidth - leftPad - 10;
  const plotHeight = chartHeight - bottomPad - topPad;
  const barWidth = Math.max(8, (plotWidth - barPadding * displayData.length) / displayData.length);

  return (
    <div className="relative">
      <svg
        width="100%"
        height={chartHeight}
        viewBox={`0 0 ${chartWidth} ${chartHeight}`}
        preserveAspectRatio="xMidYMid meet"
      >
        {/* Y-axis labels */}
        {[0, 0.25, 0.5, 0.75, 1.0].map((v) => {
          const y = topPad + plotHeight - v * plotHeight;
          return (
            <g key={v}>
              <text
                x={leftPad - 6}
                y={y + 3}
                textAnchor="end"
                className="fill-panel-500"
                fontSize={9}
              >
                {v.toFixed(2)}
              </text>
              <line
                x1={leftPad}
                y1={y}
                x2={leftPad + plotWidth}
                y2={y}
                stroke="#334155"
                strokeWidth={0.5}
                strokeDasharray="2 2"
              />
            </g>
          );
        })}

        {/* Bars */}
        {displayData.map((d, i) => {
          const x = leftPad + i * (barWidth + barPadding);
          const barHeight = d.probability * plotHeight;
          const y = topPad + plotHeight - barHeight;
          // Color gradient: low prob = panel-600, high = fizzbuzz-400-ish
          const intensity = Math.min(1, d.probability * 2);
          const r = Math.round(100 + intensity * 155);
          const g = Math.round(116 + intensity * 70);
          const b = Math.round(140 - intensity * 40);
          const fillColor = `rgb(${r}, ${g}, ${b})`;

          return (
            <g
              key={d.label}
              onMouseEnter={() => setHoveredIdx(i)}
              onMouseLeave={() => setHoveredIdx(null)}
            >
              <rect
                x={x}
                y={y}
                width={barWidth}
                height={Math.max(1, barHeight)}
                fill={fillColor}
                rx={2}
                className="cursor-pointer"
              />
              {/* X-axis label */}
              <text
                x={x + barWidth / 2}
                y={topPad + plotHeight + 14}
                textAnchor="middle"
                className="fill-panel-400"
                fontSize={8}
                fontFamily="monospace"
                transform={`rotate(-45, ${x + barWidth / 2}, ${topPad + plotHeight + 14})`}
              >
                {d.label}
              </text>
            </g>
          );
        })}

        {/* Tooltip */}
        {hoveredIdx !== null && displayData[hoveredIdx] && (() => {
          const d = displayData[hoveredIdx];
          const tooltipX = leftPad + hoveredIdx * (barWidth + barPadding) + barWidth / 2;
          const tooltipY = topPad - 2;
          const amp = d.amplitude;
          const text = `${amp.real >= 0 ? "" : "-"}${Math.abs(amp.real).toFixed(3)} ${amp.imag >= 0 ? "+" : "-"} ${Math.abs(amp.imag).toFixed(3)}i  P=${d.probability.toFixed(4)}`;
          return (
            <g>
              <rect
                x={Math.max(5, tooltipX - 90)}
                y={tooltipY - 12}
                width={180}
                height={16}
                rx={3}
                fill="#0f172a"
                stroke="#475569"
                strokeWidth={0.5}
              />
              <text
                x={Math.max(5, tooltipX - 90) + 90}
                y={tooltipY}
                textAnchor="middle"
                className="fill-panel-200"
                fontSize={8}
                fontFamily="monospace"
              >
                {text}
              </text>
            </g>
          );
        })()}
      </svg>
      {hiddenCount > 0 && (
        <p className="text-xs text-panel-500 text-center mt-1">
          ... and {hiddenCount} more basis states
        </p>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Measurement Histogram
// ---------------------------------------------------------------------------

function MeasurementHistogram({ result }: { result: QuantumSimulationResult }) {
  const sortedEntries = useMemo(() => {
    return Object.entries(result.measurementCounts)
      .sort((a, b) => b[1] - a[1]);
  }, [result.measurementCounts]);

  const maxCount = sortedEntries.length > 0 ? sortedEntries[0][1] : 1;

  const chartWidth = 500;
  const chartHeight = 200;
  const leftPad = 50;
  const bottomPad = 50;
  const topPad = 20;
  const plotWidth = chartWidth - leftPad - 10;
  const plotHeight = chartHeight - bottomPad - topPad;
  const barPadding = 3;
  const barWidth = Math.max(
    6,
    (plotWidth - barPadding * sortedEntries.length) / Math.max(1, sortedEntries.length),
  );

  // States encoding divisibility by 3 or 5 (for coloring)
  const isDivisibilityState = (label: string): boolean => {
    // Extract binary digits from ket notation
    const match = label.match(/\|([01]+)>/);
    if (!match) return false;
    const val = parseInt(match[1], 2);
    return val > 0 && (val % 3 === 0 || val % 5 === 0);
  };

  return (
    <div>
      <div className="flex items-center gap-4 mb-2 text-xs text-panel-400">
        <span>Shots: {result.shotsExecuted.toLocaleString()}</span>
        <span>Completed: {new Date(result.simulatedAt).toLocaleTimeString()}</span>
      </div>
      <svg
        width="100%"
        height={chartHeight}
        viewBox={`0 0 ${chartWidth} ${chartHeight}`}
        preserveAspectRatio="xMidYMid meet"
      >
        {/* Y-axis */}
        {[0, 0.25, 0.5, 0.75, 1.0].map((frac) => {
          const val = Math.round(frac * maxCount);
          const y = topPad + plotHeight - frac * plotHeight;
          return (
            <g key={frac}>
              <text
                x={leftPad - 6}
                y={y + 3}
                textAnchor="end"
                className="fill-panel-500"
                fontSize={9}
              >
                {val}
              </text>
              <line
                x1={leftPad}
                y1={y}
                x2={leftPad + plotWidth}
                y2={y}
                stroke="#334155"
                strokeWidth={0.5}
                strokeDasharray="2 2"
              />
            </g>
          );
        })}

        {/* Bars */}
        {sortedEntries.map(([label, count], i) => {
          const x = leftPad + i * (barWidth + barPadding);
          const barHeight = (count / maxCount) * plotHeight;
          const y = topPad + plotHeight - barHeight;
          const fillColor = isDivisibilityState(label)
            ? "#4ade80"   // fizz-400
            : "#64748b";  // panel-500
          const pct = ((count / result.shotsExecuted) * 100).toFixed(1);

          return (
            <g key={label}>
              <rect
                x={x}
                y={y}
                width={barWidth}
                height={Math.max(1, barHeight)}
                fill={fillColor}
                rx={2}
              />
              {/* Percentage label above bar */}
              {barWidth >= 10 && (
                <text
                  x={x + barWidth / 2}
                  y={y - 3}
                  textAnchor="middle"
                  className="fill-panel-300"
                  fontSize={7}
                  fontFamily="monospace"
                >
                  {pct}%
                </text>
              )}
              {/* X-axis label */}
              <text
                x={x + barWidth / 2}
                y={topPad + plotHeight + 14}
                textAnchor="middle"
                className="fill-panel-400"
                fontSize={7}
                fontFamily="monospace"
                transform={`rotate(-45, ${x + barWidth / 2}, ${topPad + plotHeight + 14})`}
              >
                {label}
              </text>
            </g>
          );
        })}
      </svg>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Quantum Advantage Ratio Gauge
// ---------------------------------------------------------------------------

function AdvantageGauge({ result }: { result: QuantumSimulationResult }) {
  const ratio = result.quantumAdvantageRatio;

  // Logarithmic mapping: 0.01x -> 0 degrees, 1x -> 90 degrees, 1000x -> 180 degrees
  const logMin = Math.log10(0.01); // -2
  const logMax = Math.log10(1000);  // 3
  const logVal = Math.log10(Math.max(0.01, Math.min(1000, ratio)));
  const normalizedAngle = ((logVal - logMin) / (logMax - logMin)) * 180;
  const needleAngle = Math.max(0, Math.min(180, normalizedAngle));

  const cx = 200;
  const cy = 170;
  const outerR = 140;
  const innerR = 100;

  // Generate arc path for a segment
  const arcPath = (startDeg: number, endDeg: number, r: number) => {
    const startRad = ((180 + startDeg) * Math.PI) / 180;
    const endRad = ((180 + endDeg) * Math.PI) / 180;
    const x1 = cx + r * Math.cos(startRad);
    const y1 = cy + r * Math.sin(startRad);
    const x2 = cx + r * Math.cos(endRad);
    const y2 = cy + r * Math.sin(endRad);
    const largeArc = endDeg - startDeg > 180 ? 1 : 0;
    return `M ${x1} ${y1} A ${r} ${r} 0 ${largeArc} 1 ${x2} ${y2}`;
  };

  // Color zones on the gauge
  // Green: < 1x (0-90 degrees), Yellow: 1-10x (90-126), Orange: 10-100x (126-162), Red: > 100x (162-180)
  const zones = [
    { start: 0, end: 90, color: "#22c55e" },     // Green: quantum advantage
    { start: 90, end: 126, color: "#eab308" },    // Yellow: 1-10x
    { start: 126, end: 162, color: "#f97316" },    // Orange: 10-100x
    { start: 162, end: 180, color: "#ef4444" },    // Red: > 100x
  ];

  // Needle endpoint
  const needleRad = ((180 + needleAngle) * Math.PI) / 180;
  const needleX = cx + (outerR - 10) * Math.cos(needleRad);
  const needleY = cy + (outerR - 10) * Math.sin(needleRad);

  const label = ratio < 1.0 ? "Quantum Faster" : "Classical Faster";

  return (
    <div className="flex flex-col items-center">
      <svg
        width="100%"
        height={200}
        viewBox="0 0 400 200"
        preserveAspectRatio="xMidYMid meet"
      >
        {/* Color zone arcs */}
        {zones.map((zone) => (
          <path
            key={zone.start}
            d={arcPath(zone.start, zone.end, outerR)}
            fill="none"
            stroke={zone.color}
            strokeWidth={outerR - innerR}
            strokeLinecap="butt"
            opacity={0.3}
          />
        ))}

        {/* Gauge track */}
        <path
          d={arcPath(0, 180, outerR)}
          fill="none"
          stroke="#334155"
          strokeWidth={2}
        />

        {/* Scale labels */}
        {[
          { deg: 0, label: "0.01x" },
          { deg: 45, label: "0.1x" },
          { deg: 90, label: "1x" },
          { deg: 126, label: "10x" },
          { deg: 162, label: "100x" },
          { deg: 180, label: "1000x" },
        ].map(({ deg, label }) => {
          const rad = ((180 + deg) * Math.PI) / 180;
          const lx = cx + (outerR + 16) * Math.cos(rad);
          const ly = cy + (outerR + 16) * Math.sin(rad);
          return (
            <text
              key={deg}
              x={lx}
              y={ly}
              textAnchor="middle"
              className="fill-panel-500"
              fontSize={8}
              fontFamily="monospace"
            >
              {label}
            </text>
          );
        })}

        {/* Needle */}
        <line
          x1={cx}
          y1={cy}
          x2={needleX}
          y2={needleY}
          stroke="#e2e8f0"
          strokeWidth={2}
          strokeLinecap="round"
        />
        <circle cx={cx} cy={cy} r={5} fill="#e2e8f0" />

        {/* Center readout */}
        <text
          x={cx}
          y={cy - 30}
          textAnchor="middle"
          className="fill-panel-50"
          fontSize={28}
          fontWeight={700}
          fontFamily="monospace"
        >
          {ratio.toFixed(1)}x
        </text>
        <text
          x={cx}
          y={cy - 12}
          textAnchor="middle"
          className="fill-panel-400"
          fontSize={11}
        >
          {label}
        </text>
      </svg>
      <p className="text-xs text-panel-500 mt-1">
        Quantum: {result.quantumTimeMs.toFixed(2)}ms | Classical:{" "}
        {result.classicalTimeMs.toFixed(3)}ms
      </p>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Page Component
// ---------------------------------------------------------------------------

export default function QuantumWorkbenchPage() {
  const provider = useDataProvider();

  const [circuits, setCircuits] = useState<QuantumCircuit[]>([]);
  const [selectedCircuitId, setSelectedCircuitId] = useState<string>("");
  const [quantumState, setQuantumState] = useState<QuantumState | null>(null);
  const [simulationResult, setSimulationResult] =
    useState<QuantumSimulationResult | null>(null);
  const [shots, setShots] = useState<number>(1024);
  const [isSimulating, setIsSimulating] = useState(false);
  const [isLoadingState, setIsLoadingState] = useState(false);

  // Load circuits on mount
  useEffect(() => {
    let cancelled = false;
    provider.getQuantumCircuits().then((c) => {
      if (cancelled) return;
      setCircuits(c);
      if (c.length > 0) {
        setSelectedCircuitId(c[0].id);
      }
    });
    return () => {
      cancelled = true;
    };
  }, [provider]);

  // Load state vector when circuit changes
  useEffect(() => {
    if (!selectedCircuitId) return;
    let cancelled = false;
    setIsLoadingState(true);
    setSimulationResult(null);
    provider.getQuantumState(selectedCircuitId).then((s) => {
      if (cancelled) return;
      setQuantumState(s);
      setIsLoadingState(false);
    });
    return () => {
      cancelled = true;
    };
  }, [selectedCircuitId, provider]);

  const selectedCircuit = useMemo(
    () => circuits.find((c) => c.id === selectedCircuitId) ?? null,
    [circuits, selectedCircuitId],
  );

  const handleExecute = useCallback(async () => {
    if (!selectedCircuitId || isSimulating) return;
    setIsSimulating(true);
    try {
      const result = await provider.runQuantumSimulation(
        selectedCircuitId,
        shots,
      );
      setSimulationResult(result);
      setQuantumState(result.finalState);
    } finally {
      setIsSimulating(false);
    }
  }, [selectedCircuitId, shots, isSimulating, provider]);

  return (
    <div className="space-y-6">
      {/* Page header */}
      <div>
        <h1 className="text-2xl font-semibold text-panel-50">
          Quantum Circuit Workbench
        </h1>
        <p className="text-sm text-panel-400 mt-1">
          Interactive simulation interface for the quantum FizzBuzz evaluation
          subsystem. Configure circuits, execute state-vector simulations, and
          analyze measurement statistics.
        </p>
      </div>

      {/* Panel 1: Circuit Selector and Controls */}
      <Card>
        <CardHeader>
          <div className="flex flex-wrap items-center gap-4">
            {/* Circuit dropdown */}
            <div className="flex items-center gap-2">
              <label
                htmlFor="circuit-select"
                className="text-xs text-panel-400 uppercase tracking-wide"
              >
                Circuit
              </label>
              <select
                id="circuit-select"
                value={selectedCircuitId}
                onChange={(e) => setSelectedCircuitId(e.target.value)}
                className="rounded bg-panel-900 border border-panel-600 px-3 py-1.5 text-sm text-panel-100 focus:outline-none focus:ring-1 focus:ring-fizzbuzz-500"
              >
                {circuits.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.name}
                  </option>
                ))}
              </select>
            </div>

            {/* Shot count selector */}
            <div className="flex items-center gap-2">
              <span className="text-xs text-panel-400 uppercase tracking-wide">
                Shots
              </span>
              <div className="flex rounded border border-panel-600 overflow-hidden">
                {SHOT_PRESETS.map((preset) => (
                  <button
                    key={preset}
                    onClick={() => setShots(preset)}
                    className={`px-3 py-1.5 text-xs font-mono transition-colors ${
                      shots === preset
                        ? "bg-fizzbuzz-600 text-white"
                        : "bg-panel-900 text-panel-300 hover:bg-panel-800"
                    }`}
                  >
                    {preset.toLocaleString()}
                  </button>
                ))}
              </div>
            </div>

            {/* Execute button */}
            <Button
              onClick={handleExecute}
              disabled={isSimulating || !selectedCircuitId}
              size="md"
            >
              {isSimulating ? "Simulating..." : "Execute Simulation"}
            </Button>
          </div>
        </CardHeader>
        {selectedCircuit && (
          <CardContent>
            <p className="text-sm text-panel-300 mb-2">
              {selectedCircuit.description}
            </p>
            <div className="flex gap-6 text-xs text-panel-500">
              <span>
                Qubits:{" "}
                <span className="text-panel-200">
                  {selectedCircuit.numQubits}
                </span>
              </span>
              <span>
                Gates:{" "}
                <span className="text-panel-200">
                  {selectedCircuit.gates.length}
                </span>
              </span>
              <span>
                Depth:{" "}
                <span className="text-panel-200">{selectedCircuit.depth}</span>
              </span>
              <span>
                Classical Bits:{" "}
                <span className="text-panel-200">
                  {selectedCircuit.numClassicalBits}
                </span>
              </span>
            </div>
          </CardContent>
        )}
      </Card>

      {/* Panel 2: Circuit Diagram */}
      {selectedCircuit && (
        <Card>
          <CardHeader>
            <h2 className="text-sm font-medium text-panel-200">
              Circuit Diagram
            </h2>
          </CardHeader>
          <CardContent>
            <CircuitDiagram circuit={selectedCircuit} />
          </CardContent>
        </Card>
      )}

      {/* Row 3: State Vector + Measurement Histogram */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Panel 3: State Vector Visualization */}
        <Card>
          <CardHeader>
            <h2 className="text-sm font-medium text-panel-200">
              State Vector Probabilities
            </h2>
          </CardHeader>
          <CardContent>
            {isLoadingState && (
              <p className="text-sm text-panel-500">
                Computing state vector...
              </p>
            )}
            {!isLoadingState && quantumState && (
              <StateVectorChart state={quantumState} />
            )}
            {!isLoadingState && !quantumState && (
              <p className="text-sm text-panel-500">
                Select a circuit to view its state vector.
              </p>
            )}
          </CardContent>
        </Card>

        {/* Panel 4: Measurement Histogram */}
        <Card>
          <CardHeader>
            <h2 className="text-sm font-medium text-panel-200">
              Measurement Histogram
            </h2>
          </CardHeader>
          <CardContent>
            {simulationResult ? (
              <MeasurementHistogram result={simulationResult} />
            ) : (
              <p className="text-sm text-panel-500">
                Execute a simulation to view measurement outcomes.
              </p>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Panel 5: Quantum Advantage Ratio Gauge */}
      {simulationResult && (
        <div className="flex justify-center">
          <Card className="max-w-lg w-full">
            <CardHeader>
              <h2 className="text-sm font-medium text-panel-200 text-center">
                Quantum Advantage Ratio
              </h2>
            </CardHeader>
            <CardContent>
              <AdvantageGauge result={simulationResult} />
            </CardContent>
          </Card>
        </div>
      )}
    </div>
  );
}
