"use client";

import { useCallback, useMemo, useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { Reveal } from "@/components/ui/reveal";
import { Skeleton } from "@/components/ui/skeleton";
import type {
  GAChromosome,
  GAConfig,
  GAEvolutionHistory,
  GAPopulation,
} from "@/lib/data-providers";
import { useDataProvider } from "@/lib/data-providers";

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const DEFAULT_CONFIG: GAConfig = {
  populationSize: 40,
  mutationRate: 0.15,
  crossoverRate: 0.7,
  elitismCount: 2,
  maxGenerations: 50,
};

/** Mass extinction threshold — diversity below this value triggers a warning indicator. */
const DIVERSITY_EXTINCTION_THRESHOLD = 1.0;

// ---------------------------------------------------------------------------
// SVG Chart: Fitness Convergence
// ---------------------------------------------------------------------------

const CHART_LEFT = 50;
const CHART_TOP = 20;
const CHART_RIGHT = 20;
const CHART_BOTTOM = 30;

function FitnessConvergenceChart({
  generations,
  selectedGen,
  width,
  height,
}: {
  generations: GAPopulation[];
  selectedGen: number;
  width: number;
  height: number;
}) {
  const plotW = width - CHART_LEFT - CHART_RIGHT;
  const plotH = height - CHART_TOP - CHART_BOTTOM;

  if (generations.length === 0) {
    return (
      <svg width={width} height={height} className="min-w-full">
        <text
          x={width / 2}
          y={height / 2}
          textAnchor="middle"
          className="fill-text-muted text-sm"
        >
          No evolution data. Configure parameters and press Evolve.
        </text>
      </svg>
    );
  }

  const maxGen = generations.length - 1;
  const xScale = maxGen > 0 ? plotW / maxGen : plotW;
  const toX = (gen: number) => CHART_LEFT + gen * xScale;
  const toY = (val: number) => CHART_TOP + plotH * (1 - val);

  // Build polyline strings
  const bestLine = generations
    .map((g, i) => `${toX(i)},${toY(g.bestFitness)}`)
    .join(" ");
  const avgLine = generations
    .map((g, i) => `${toX(i)},${toY(g.averageFitness)}`)
    .join(" ");
  const worstLine = generations
    .map((g, i) => `${toX(i)},${toY(g.worstFitness)}`)
    .join(" ");

  // Cursor position
  const cursorX = toX(selectedGen);

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
            x1={CHART_LEFT}
            y1={toY(v)}
            x2={width - CHART_RIGHT}
            y2={toY(v)}
            stroke="#334155"
            strokeWidth={0.5}
            strokeDasharray={v === 0 || v === 1 ? undefined : "4,4"}
          />
          <text
            x={CHART_LEFT - 6}
            y={toY(v) + 4}
            textAnchor="end"
            className="fill-text-muted"
            fontSize={10}
          >
            {v.toFixed(2)}
          </text>
        </g>
      ))}

      {/* X-axis labels */}
      {generations
        .filter(
          (_, i) =>
            i % Math.max(1, Math.floor(generations.length / 8)) === 0 ||
            i === maxGen,
        )
        .map((g) => (
          <text
            key={g.generation}
            x={toX(g.generation)}
            y={height - 6}
            textAnchor="middle"
            className="fill-text-muted"
            fontSize={10}
          >
            {g.generation}
          </text>
        ))}

      {/* Data lines */}
      <polyline
        points={worstLine}
        fill="none"
        stroke="#f87171"
        strokeWidth={1.5}
        opacity={0.7}
      />
      <polyline
        points={avgLine}
        fill="none"
        stroke="#fbbf24"
        strokeWidth={1.5}
        opacity={0.8}
      />
      <polyline
        points={bestLine}
        fill="none"
        stroke="#4ade80"
        strokeWidth={2}
      />

      {/* Cursor */}
      <line
        x1={cursorX}
        y1={CHART_TOP}
        x2={cursorX}
        y2={CHART_TOP + plotH}
        stroke="#94a3b8"
        strokeWidth={1}
        strokeDasharray="4,2"
      />
    </svg>
  );
}

// ---------------------------------------------------------------------------
// SVG Chart: Diversity Radar (Area Chart)
// ---------------------------------------------------------------------------

function DiversityChart({
  generations,
  selectedGen,
  width,
  height,
}: {
  generations: GAPopulation[];
  selectedGen: number;
  width: number;
  height: number;
}) {
  const plotW = width - CHART_LEFT - CHART_RIGHT;
  const plotH = height - CHART_TOP - CHART_BOTTOM;

  if (generations.length === 0) {
    return (
      <svg width={width} height={height} className="min-w-full">
        <text
          x={width / 2}
          y={height / 2}
          textAnchor="middle"
          className="fill-text-muted text-sm"
        >
          Awaiting evolution data.
        </text>
      </svg>
    );
  }

  const maxDiversity = Math.max(...generations.map((g) => g.diversityIndex), 1);
  const maxGen = generations.length - 1;
  const xScale = maxGen > 0 ? plotW / maxGen : plotW;
  const toX = (gen: number) => CHART_LEFT + gen * xScale;
  const toY = (val: number) => CHART_TOP + plotH * (1 - val / maxDiversity);

  // Build area path
  const linePoints = generations.map(
    (g, i) => `${toX(i)},${toY(g.diversityIndex)}`,
  );
  const areaPath = `M ${CHART_LEFT},${CHART_TOP + plotH} L ${linePoints.join(" L ")} L ${toX(maxGen)},${CHART_TOP + plotH} Z`;

  // Extinction threshold line
  const thresholdY = toY(DIVERSITY_EXTINCTION_THRESHOLD);
  const showThreshold = DIVERSITY_EXTINCTION_THRESHOLD <= maxDiversity;

  const cursorX = toX(selectedGen);

  return (
    <svg
      width={width}
      height={height}
      viewBox={`0 0 ${width} ${height}`}
      className="min-w-full"
    >
      {/* Y-axis labels */}
      {[0, 0.25, 0.5, 0.75, 1.0].map((frac) => {
        const val = frac * maxDiversity;
        return (
          <g key={frac}>
            <line
              x1={CHART_LEFT}
              y1={toY(val)}
              x2={width - CHART_RIGHT}
              y2={toY(val)}
              stroke="#334155"
              strokeWidth={0.5}
              strokeDasharray="4,4"
            />
            <text
              x={CHART_LEFT - 6}
              y={toY(val) + 4}
              textAnchor="end"
              className="fill-text-muted"
              fontSize={10}
            >
              {val.toFixed(1)}
            </text>
          </g>
        );
      })}

      {/* Filled area */}
      <path d={areaPath} fill="#2dd4bf" fillOpacity={0.15} />
      <polyline
        points={linePoints.join(" ")}
        fill="none"
        stroke="#2dd4bf"
        strokeWidth={2}
      />

      {/* Mass extinction threshold */}
      {showThreshold && (
        <>
          <line
            x1={CHART_LEFT}
            y1={thresholdY}
            x2={width - CHART_RIGHT}
            y2={thresholdY}
            stroke="#ef4444"
            strokeWidth={1}
            strokeDasharray="6,3"
            opacity={0.6}
          />
          <text
            x={width - CHART_RIGHT}
            y={thresholdY - 4}
            textAnchor="end"
            className="fill-red-400"
            fontSize={9}
          >
            extinction threshold
          </text>
        </>
      )}

      {/* Cursor */}
      <line
        x1={cursorX}
        y1={CHART_TOP}
        x2={cursorX}
        y2={CHART_TOP + plotH}
        stroke="#94a3b8"
        strokeWidth={1}
        strokeDasharray="4,2"
      />
    </svg>
  );
}

// ---------------------------------------------------------------------------
// Fitness Breakdown horizontal bar chart
// ---------------------------------------------------------------------------

function FitnessBreakdown({ chromosome }: { chromosome: GAChromosome }) {
  const components: { label: string; value: number; color: string }[] = [
    { label: "Accuracy", value: chromosome.fitness.accuracy, color: "#4ade80" },
    { label: "Coverage", value: chromosome.fitness.coverage, color: "#38bdf8" },
    {
      label: "Distinctness",
      value: chromosome.fitness.distinctness,
      color: "#a78bfa",
    },
    {
      label: "Phonetic Harmony",
      value: chromosome.fitness.phoneticHarmony,
      color: "#fbbf24",
    },
    {
      label: "Math Elegance",
      value: chromosome.fitness.mathematicalElegance,
      color: "#fb7185",
    },
  ];

  return (
    <div className="space-y-2">
      {components.map((c) => (
        <div key={c.label} className="flex items-center gap-3">
          <span className="text-xs text-text-secondary w-32 text-right shrink-0">
            {c.label}
          </span>
          <div className="flex-1 h-4 bg-surface-base rounded overflow-hidden">
            <div
              className="h-full rounded transition-all"
              style={{
                width: `${(c.value * 100).toFixed(1)}%`,
                backgroundColor: c.color,
              }}
            />
          </div>
          <span className="text-xs text-text-secondary w-12 text-right font-mono">
            {c.value.toFixed(3)}
          </span>
        </div>
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Correctness Grid (10x10)
// ---------------------------------------------------------------------------

function CorrectnessGrid({ chromosome }: { chromosome: GAChromosome }) {
  const [hoveredCell, setHoveredCell] = useState<number | null>(null);

  // Compute the chromosome's output for each number (for tooltip)
  const outputs = useMemo(() => {
    const results: string[] = [];
    for (let n = 1; n <= 100; n++) {
      const matching = chromosome.genes
        .filter((g) => n % g.divisor === 0)
        .sort((a, b) => a.priority - b.priority);
      results.push(
        matching.length > 0 ? matching.map((g) => g.label).join("") : String(n),
      );
    }
    return results;
  }, [chromosome]);

  const canonicalOutput = useCallback((n: number): string => {
    if (n % 15 === 0) return "FizzBuzz";
    if (n % 3 === 0) return "Fizz";
    if (n % 5 === 0) return "Buzz";
    return String(n);
  }, []);

  return (
    <div className="relative">
      <div className="grid grid-cols-10 gap-0.5">
        {Array.from({ length: 100 }, (_, i) => {
          const n = i + 1;
          const correct = chromosome.correctnessMap[i] ?? false;
          return (
            <div
              key={n}
              className={`w-full aspect-square flex items-center justify-center text-[9px] font-mono rounded-sm cursor-default transition-colors ${
                correct
                  ? "bg-fizz-900/60 text-fizz-300 border border-fizz-800/40"
                  : "bg-red-900/60 text-red-300 border border-red-800/40"
              }`}
              onMouseEnter={() => setHoveredCell(n)}
              onMouseLeave={() => setHoveredCell(null)}
            >
              {n}
            </div>
          );
        })}
      </div>
      {hoveredCell !== null && (
        <div className="absolute -top-16 left-1/2 -translate-x-1/2 bg-surface-overlay border border-border-default rounded px-3 py-2 text-xs z-10 whitespace-nowrap shadow-lg">
          <div className="text-text-secondary">
            <span className="font-mono font-bold">{hoveredCell}</span>
          </div>
          <div className="text-text-secondary">
            Expected:{" "}
            <span className="text-fizz-400 font-mono">
              {canonicalOutput(hoveredCell)}
            </span>
          </div>
          <div className="text-text-secondary">
            Got:{" "}
            <span
              className={`font-mono ${
                chromosome.correctnessMap[hoveredCell - 1]
                  ? "text-fizz-400"
                  : "text-red-400"
              }`}
            >
              {outputs[hoveredCell - 1]}
            </span>
          </div>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Chromosome Tile
// ---------------------------------------------------------------------------

function chromosomeFitnessColor(fitness: number): string {
  // Interpolate from red (0) through yellow (0.5) to green (1.0)
  if (fitness <= 0.5) {
    const t = fitness / 0.5;
    const r = Math.round(239 + (234 - 239) * t);
    const g = Math.round(68 + (179 - 68) * t);
    const b = Math.round(68 + (8 - 68) * t);
    return `rgb(${r},${g},${b})`;
  }
  const t = (fitness - 0.5) / 0.5;
  const r = Math.round(234 + (74 - 234) * t);
  const g = Math.round(179 + (222 - 179) * t);
  const b = Math.round(8 + (128 - 8) * t);
  return `rgb(${r},${g},${b})`;
}

// ---------------------------------------------------------------------------
// Main Page Component
// ---------------------------------------------------------------------------

export default function EvolutionObservatoryPage() {
  const provider = useDataProvider();

  // Configuration state
  const [config, setConfig] = useState<GAConfig>({ ...DEFAULT_CONFIG });

  // Run state
  const [runState, setRunState] = useState<"idle" | "evolving" | "converged">(
    "idle",
  );
  const [history, setHistory] = useState<GAEvolutionHistory | null>(null);

  // UI state
  const [selectedGen, setSelectedGen] = useState(0);
  const [selectedChromosome, setSelectedChromosome] =
    useState<GAChromosome | null>(null);

  // Launch evolution run
  const handleEvolve = useCallback(async () => {
    setRunState("evolving");
    setSelectedChromosome(null);
    setSelectedGen(0);
    try {
      const result = await provider.runEvolution(config);
      setHistory(result);
      setRunState("converged");
      setSelectedGen(result.generations.length - 1);
    } catch {
      setRunState("idle");
    }
  }, [provider, config]);

  // Current generation population
  const currentPopulation = useMemo<GAPopulation | null>(() => {
    if (!history || history.generations.length === 0) return null;
    return history.generations[selectedGen] ?? null;
  }, [history, selectedGen]);

  // Status badge
  const statusBadge = useMemo(() => {
    switch (runState) {
      case "idle":
        return <Badge variant="info">Idle</Badge>;
      case "evolving":
        return <Badge variant="warning">Evolving</Badge>;
      case "converged":
        return <Badge variant="success">Converged</Badge>;
    }
  }, [runState]);

  return (
    <div className="space-y-6">
      {/* Page Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="heading-page">Genetic Algorithm Observatory</h1>
          <p className="text-sm text-text-secondary mt-1">
            Evolutionary Rule Discovery Engine
          </p>
        </div>
        {statusBadge}
      </div>

      {/* GA Configuration Panel */}
      <Card>
        <CardContent className="py-4">
          <div className="flex flex-wrap items-end gap-4">
            <div className="flex flex-col gap-1">
              <label className="text-xs text-text-secondary">
                Population Size
              </label>
              <input
                type="number"
                min={10}
                max={200}
                value={config.populationSize}
                onChange={(e) =>
                  setConfig((c) => ({
                    ...c,
                    populationSize: Math.max(
                      10,
                      Math.min(200, Number(e.target.value) || 10),
                    ),
                  }))
                }
                className="w-24 rounded bg-surface-base border border-border-default px-2 py-1.5 text-sm text-text-primary focus:outline-none focus:ring-1 focus:ring-fizzbuzz-500"
              />
            </div>
            <div className="flex flex-col gap-1">
              <label className="text-xs text-text-secondary">
                Mutation Rate
              </label>
              <input
                type="number"
                min={0.01}
                max={0.5}
                step={0.01}
                value={config.mutationRate}
                onChange={(e) =>
                  setConfig((c) => ({
                    ...c,
                    mutationRate: Math.max(
                      0.01,
                      Math.min(0.5, Number(e.target.value) || 0.01),
                    ),
                  }))
                }
                className="w-24 rounded bg-surface-base border border-border-default px-2 py-1.5 text-sm text-text-primary focus:outline-none focus:ring-1 focus:ring-fizzbuzz-500"
              />
            </div>
            <div className="flex flex-col gap-1">
              <label className="text-xs text-text-secondary">
                Crossover Rate
              </label>
              <input
                type="number"
                min={0.1}
                max={1.0}
                step={0.05}
                value={config.crossoverRate}
                onChange={(e) =>
                  setConfig((c) => ({
                    ...c,
                    crossoverRate: Math.max(
                      0.1,
                      Math.min(1.0, Number(e.target.value) || 0.1),
                    ),
                  }))
                }
                className="w-24 rounded bg-surface-base border border-border-default px-2 py-1.5 text-sm text-text-primary focus:outline-none focus:ring-1 focus:ring-fizzbuzz-500"
              />
            </div>
            <div className="flex flex-col gap-1">
              <label className="text-xs text-text-secondary">
                Elitism Count
              </label>
              <input
                type="number"
                min={0}
                max={10}
                value={config.elitismCount}
                onChange={(e) =>
                  setConfig((c) => ({
                    ...c,
                    elitismCount: Math.max(
                      0,
                      Math.min(10, Number(e.target.value) || 0),
                    ),
                  }))
                }
                className="w-24 rounded bg-surface-base border border-border-default px-2 py-1.5 text-sm text-text-primary focus:outline-none focus:ring-1 focus:ring-fizzbuzz-500"
              />
            </div>
            <div className="flex flex-col gap-1">
              <label className="text-xs text-text-secondary">
                Max Generations
              </label>
              <input
                type="number"
                min={10}
                max={200}
                value={config.maxGenerations}
                onChange={(e) =>
                  setConfig((c) => ({
                    ...c,
                    maxGenerations: Math.max(
                      10,
                      Math.min(200, Number(e.target.value) || 10),
                    ),
                  }))
                }
                className="w-24 rounded bg-surface-base border border-border-default px-2 py-1.5 text-sm text-text-primary focus:outline-none focus:ring-1 focus:ring-fizzbuzz-500"
              />
            </div>
            <Button
              onClick={handleEvolve}
              disabled={runState === "evolving"}
              size="md"
            >
              {runState === "evolving" ? "Evolving..." : "Evolve"}
            </Button>
          </div>
        </CardContent>
      </Card>

      {/* Charts: Fitness Convergence + Diversity Radar */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <Card>
          <CardHeader>
            <div className="flex items-center justify-between">
              <h2 className="text-sm font-semibold text-text-secondary">
                Fitness Convergence
              </h2>
              <div className="flex items-center gap-4 text-xs">
                <span className="flex items-center gap-1.5">
                  <span className="inline-block w-3 h-0.5 bg-green-400 rounded" />
                  Best
                </span>
                <span className="flex items-center gap-1.5">
                  <span className="inline-block w-3 h-0.5 bg-amber-400 rounded" />
                  Average
                </span>
                <span className="flex items-center gap-1.5">
                  <span className="inline-block w-3 h-0.5 bg-red-400 rounded" />
                  Worst
                </span>
              </div>
            </div>
          </CardHeader>
          <CardContent>
            <div className="overflow-x-auto">
              <FitnessConvergenceChart
                generations={history?.generations ?? []}
                selectedGen={selectedGen}
                width={560}
                height={280}
              />
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <h2 className="text-sm font-semibold text-text-secondary">
              Genetic Diversity Index
            </h2>
          </CardHeader>
          <CardContent>
            <div className="overflow-x-auto">
              <DiversityChart
                generations={history?.generations ?? []}
                selectedGen={selectedGen}
                width={560}
                height={280}
              />
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Generation Slider */}
      {history && history.generations.length > 0 && (
        <Card>
          <CardContent className="py-4">
            <div className="flex items-center gap-4">
              <label className="text-sm text-text-secondary shrink-0">
                Generation
              </label>
              <input
                type="range"
                min={0}
                max={history.generations.length - 1}
                value={selectedGen}
                onChange={(e) => {
                  setSelectedGen(Number(e.target.value));
                  setSelectedChromosome(null);
                }}
                className="flex-1 accent-fizzbuzz-500"
              />
              <span className="text-sm font-mono text-text-secondary w-16 text-right">
                {selectedGen} / {history.generations.length - 1}
              </span>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Population Inspector */}
      {currentPopulation && (
        <Card>
          <CardHeader>
            <div className="flex items-center justify-between">
              <h2 className="text-sm font-semibold text-text-secondary">
                Population Inspector — Generation {currentPopulation.generation}
              </h2>
              <span className="text-xs text-text-muted">
                {currentPopulation.chromosomes.length} chromosomes | Best:{" "}
                <span className="text-fizz-400 font-mono">
                  {currentPopulation.bestFitness.toFixed(4)}
                </span>{" "}
                | Avg:{" "}
                <span className="text-amber-400 font-mono">
                  {currentPopulation.averageFitness.toFixed(4)}
                </span>
              </span>
            </div>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-4 sm:grid-cols-6 md:grid-cols-8 lg:grid-cols-10 gap-1.5">
              {[...currentPopulation.chromosomes]
                .sort((a, b) => b.fitness.overall - a.fitness.overall)
                .map((chromo) => {
                  const isSelected =
                    selectedChromosome?.chromosomeId === chromo.chromosomeId;
                  return (
                    <button
                      key={chromo.chromosomeId}
                      onClick={() => setSelectedChromosome(chromo)}
                      className={`rounded p-1.5 text-center transition-all border ${
                        isSelected
                          ? "border-fizzbuzz-400 ring-1 ring-fizzbuzz-500"
                          : "border-border-subtle hover:border-panel-500"
                      }`}
                      style={{
                        backgroundColor:
                          chromosomeFitnessColor(chromo.fitness.overall) + "20",
                      }}
                    >
                      <div
                        className="text-[9px] font-mono truncate"
                        style={{
                          color: chromosomeFitnessColor(chromo.fitness.overall),
                        }}
                      >
                        {chromo.chromosomeId.slice(0, 6)}
                      </div>
                      <div className="text-[10px] text-text-secondary">
                        {chromo.genes.length}g
                      </div>
                      <div
                        className="text-xs font-mono font-bold"
                        style={{
                          color: chromosomeFitnessColor(chromo.fitness.overall),
                        }}
                      >
                        {chromo.fitness.overall.toFixed(3)}
                      </div>
                    </button>
                  );
                })}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Chromosome Detail Panel */}
      {selectedChromosome && (
        <Card>
          <CardHeader>
            <div className="flex items-center justify-between">
              <h2 className="text-sm font-semibold text-text-secondary">
                Chromosome Detail —{" "}
                <span className="font-mono text-fizzbuzz-400">
                  {selectedChromosome.chromosomeId.slice(0, 12)}
                </span>
              </h2>
              <span className="text-xs text-text-muted">
                Generation {selectedChromosome.generation} | Overall Fitness:{" "}
                <span className="text-fizz-400 font-mono">
                  {selectedChromosome.fitness.overall.toFixed(4)}
                </span>
              </span>
            </div>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
              {/* Gene Table */}
              <div>
                <h3 className="heading-section">Gene Table</h3>
                <div className="overflow-hidden rounded border border-border-subtle">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="bg-surface-base text-text-secondary text-xs">
                        <th className="px-3 py-1.5 text-left font-medium">
                          Divisor
                        </th>
                        <th className="px-3 py-1.5 text-left font-medium">
                          Label
                        </th>
                        <th className="px-3 py-1.5 text-right font-medium">
                          Priority
                        </th>
                      </tr>
                    </thead>
                    <tbody>
                      {selectedChromosome.genes.map((gene, i) => (
                        <tr
                          key={i}
                          className="border-t border-border-subtle text-text-secondary"
                        >
                          <td className="px-3 py-1.5 font-mono">
                            {gene.divisor}
                          </td>
                          <td className="px-3 py-1.5 font-mono">
                            {gene.label}
                          </td>
                          <td className="px-3 py-1.5 font-mono text-right">
                            {gene.priority}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>

                {/* Lineage */}
                {selectedChromosome.parentIds.length > 0 && (
                  <div className="mt-4">
                    <h3 className="heading-section">Lineage</h3>
                    <div className="text-xs text-text-muted space-y-0.5">
                      {selectedChromosome.parentIds.map((pid) => (
                        <div key={pid} className="font-mono">
                          Parent: {pid.slice(0, 12)}...
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>

              {/* Fitness Breakdown */}
              <div>
                <h3 className="heading-section">Fitness Breakdown</h3>
                <FitnessBreakdown chromosome={selectedChromosome} />
              </div>

              {/* Correctness Grid */}
              <div>
                <h3 className="heading-section">Correctness Grid (1-100)</h3>
                <CorrectnessGrid chromosome={selectedChromosome} />
              </div>
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
