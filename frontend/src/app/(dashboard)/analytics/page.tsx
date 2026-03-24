"use client";

import { useCallback, useEffect, useState } from "react";
import { DonutChart, HeatmapGrid, LineChart } from "@/components/charts";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { Reveal } from "@/components/ui/reveal";
import { Skeleton } from "@/components/ui/skeleton";
import type {
  ClassificationDistribution,
  EvaluationTrend,
  HeatmapData,
} from "@/lib/data-providers";
import { useDataProvider } from "@/lib/data-providers";

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const TREND_PERIODS = ["1h", "6h", "24h", "7d"] as const;
type TrendPeriod = (typeof TREND_PERIODS)[number];

const PERIOD_LABELS: Record<TrendPeriod, string> = {
  "1h": "1h",
  "6h": "6h",
  "24h": "24h",
  "7d": "7d",
};

/** Classification color dots for the statistics panel. */
const CLASSIFICATION_COLORS: Record<string, string> = {
  fizz: "bg-fizz-400",
  buzz: "bg-buzz-400",
  fizzbuzz: "bg-fizzbuzz-400",
  number: "bg-number-400",
};

const CLASSIFICATION_LABELS: Record<string, string> = {
  fizz: "Fizz",
  buzz: "Buzz",
  fizzbuzz: "FizzBuzz",
  number: "Number",
};

/** Auto-refresh interval for evaluation trend data (milliseconds). */
const TREND_REFRESH_INTERVAL = 15_000;

// ---------------------------------------------------------------------------
// Page component
// ---------------------------------------------------------------------------

export default function AnalyticsPage() {
  const provider = useDataProvider();

  // Range controls
  const [start, setStart] = useState(1);
  const [end, setEnd] = useState(100);

  // Data state
  const [distribution, setDistribution] = useState<
    ClassificationDistribution[] | null
  >(null);
  const [heatmap, setHeatmap] = useState<HeatmapData | null>(null);
  const [trend, setTrend] = useState<EvaluationTrend | null>(null);
  const [trendPeriod, setTrendPeriod] = useState<TrendPeriod>("24h");
  const [analyzing, setAnalyzing] = useState(false);

  // Validation
  const startValid = Number.isInteger(start) && start >= 1 && start <= 10_000;
  const endValid = Number.isInteger(end) && end >= 1 && end <= 10_000;
  const rangeValid = startValid && endValid && start < end;

  // ---------------------------------------------------------------------------
  // Analyze handler — fetches distribution and heatmap for the given range
  // ---------------------------------------------------------------------------

  const handleAnalyze = useCallback(async () => {
    if (!rangeValid || analyzing) return;

    setAnalyzing(true);
    try {
      const [dist, heat] = await Promise.all([
        provider.getClassificationDistribution(start, end),
        provider.getDivisorHeatmap(start, end),
      ]);
      setDistribution(dist);
      setHeatmap(heat);
    } finally {
      setAnalyzing(false);
    }
  }, [provider, start, end, rangeValid, analyzing]);

  // ---------------------------------------------------------------------------
  // Fetch evaluation trend data
  // ---------------------------------------------------------------------------

  const fetchTrend = useCallback(async () => {
    const result = await provider.getEvaluationTrend(trendPeriod);
    setTrend(result);
  }, [provider, trendPeriod]);

  // Initial load for distribution, heatmap, and trend
  useEffect(() => {
    handleAnalyze();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    fetchTrend();
    const interval = setInterval(fetchTrend, TREND_REFRESH_INTERVAL);
    return () => clearInterval(interval);
  }, [fetchTrend]);

  // ---------------------------------------------------------------------------
  // Computed values
  // ---------------------------------------------------------------------------

  const totalInRange = distribution
    ? distribution.reduce((sum, d) => sum + d.count, 0)
    : 0;

  const donutSegments = distribution
    ? distribution.map((d) => ({
        label: CLASSIFICATION_LABELS[d.classification],
        value: d.count,
        color: d.color,
      }))
    : [];

  const trendChartData = trend
    ? trend.dataPoints.map((dp) => ({
        timestamp: dp.timestamp,
        value: dp.count,
      }))
    : [];

  // ---------------------------------------------------------------------------
  // Render
  // ---------------------------------------------------------------------------

  return (
    <div className="space-y-6">
      {/* Page header */}
      <Reveal>
        <div>
          <h1 className="heading-page">Analytics &amp; Intelligence</h1>
          <p className="mt-1 text-sm text-text-secondary">
            Statistical analysis of FizzBuzz classification distributions,
            divisibility patterns, and evaluation pipeline throughput trends.
          </p>
        </div>
      </Reveal>

      {/* ----------------------------------------------------------------- */}
      {/* Range Selector                                                     */}
      {/* ----------------------------------------------------------------- */}
      <Card>
        <CardContent>
          <div className="flex flex-wrap items-end gap-4">
            {/* Range Start */}
            <div>
              <label
                htmlFor="analytics-start"
                className="block text-xs font-medium text-text-secondary mb-1"
              >
                Range Start
              </label>
              <input
                id="analytics-start"
                type="number"
                min={1}
                max={10000}
                value={start}
                onChange={(e) => setStart(Number(e.target.value))}
                className={`w-32 rounded border bg-surface-base px-3 py-2 text-sm text-text-primary focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-offset-surface-ground ${
                  startValid
                    ? "border-border-subtle focus:ring-fizzbuzz-500"
                    : "border-red-600 focus:ring-red-500"
                }`}
              />
              {!startValid && (
                <p className="mt-1 text-xs text-red-400">
                  Must be an integer between 1 and 10,000
                </p>
              )}
            </div>

            {/* Range End */}
            <div>
              <label
                htmlFor="analytics-end"
                className="block text-xs font-medium text-text-secondary mb-1"
              >
                Range End
              </label>
              <input
                id="analytics-end"
                type="number"
                min={1}
                max={10000}
                value={end}
                onChange={(e) => setEnd(Number(e.target.value))}
                className={`w-32 rounded border bg-surface-base px-3 py-2 text-sm text-text-primary focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-offset-surface-ground ${
                  endValid
                    ? "border-border-subtle focus:ring-fizzbuzz-500"
                    : "border-red-600 focus:ring-red-500"
                }`}
              />
              {!endValid && (
                <p className="mt-1 text-xs text-red-400">
                  Must be an integer between 1 and 10,000
                </p>
              )}
            </div>

            {/* Analyze button */}
            <Button
              onClick={handleAnalyze}
              disabled={!rangeValid || analyzing}
              size="md"
            >
              {analyzing ? "Analyzing..." : "Analyze"}
            </Button>

            {!rangeValid && startValid && endValid && (
              <p className="text-xs text-red-400 self-center">
                Range start must be less than range end
              </p>
            )}
          </div>
        </CardContent>
      </Card>

      {/* ----------------------------------------------------------------- */}
      {/* Row 1: Classification Donut Chart + Distribution Statistics        */}
      {/* ----------------------------------------------------------------- */}
      {distribution && (
        <div className="grid grid-cols-1 lg:grid-cols-5 gap-6">
          {/* Donut Chart */}
          <Card className="lg:col-span-3">
            <CardHeader>
              <h2 className="heading-section">Classification Distribution</h2>
            </CardHeader>
            <CardContent className="flex justify-center">
              <DonutChart
                segments={donutSegments}
                size={280}
                thickness={0.35}
                centerLabel={String(totalInRange)}
                centerSubLabel="integers"
              />
            </CardContent>
          </Card>

          {/* Distribution Statistics */}
          <Card className="lg:col-span-2">
            <CardHeader>
              <h2 className="heading-section">Distribution Statistics</h2>
            </CardHeader>
            <CardContent className="space-y-3">
              {distribution.map((d) => (
                <div
                  key={d.classification}
                  className="flex items-center justify-between rounded bg-surface-base px-3 py-2"
                >
                  <div className="flex items-center gap-2">
                    <span
                      className={`h-2.5 w-2.5 rounded-full ${CLASSIFICATION_COLORS[d.classification]}`}
                    />
                    <span className="text-sm text-text-secondary">
                      {CLASSIFICATION_LABELS[d.classification]}
                    </span>
                  </div>
                  <div className="flex items-center gap-4 text-sm font-mono">
                    <span className="text-text-primary w-12 text-right">
                      {d.count}
                    </span>
                    <span className="text-text-secondary w-16 text-right">
                      {(d.proportion * 100).toFixed(2)}%
                    </span>
                    <span className="text-text-muted w-12 text-right">
                      {d.fraction}
                    </span>
                  </div>
                </div>
              ))}

              {/* Theoretical probabilities */}
              <div className="mt-4 border-t border-border-subtle pt-3">
                <p className="text-xs text-text-muted leading-relaxed">
                  Theoretical: Fizz 4/15 (26.67%) | Buzz 2/15 (13.33%) |
                  FizzBuzz 1/15 (6.67%) | Number 8/15 (53.33%)
                </p>
              </div>
            </CardContent>
          </Card>
        </div>
      )}

      {/* ----------------------------------------------------------------- */}
      {/* Row 2: Divisibility Heatmap                                       */}
      {/* ----------------------------------------------------------------- */}
      {heatmap && (
        <Card>
          <CardHeader>
            <h2 className="heading-section">Divisibility Heatmap</h2>
          </CardHeader>
          <CardContent>
            <HeatmapGrid
              data={heatmap}
              cellSize={28}
              highlightDivisors={[3, 5, 15]}
            />
          </CardContent>
        </Card>
      )}

      {/* ----------------------------------------------------------------- */}
      {/* Row 3: Evaluation Volume Trend                                    */}
      {/* ----------------------------------------------------------------- */}
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <h2 className="heading-section">Evaluation Volume Trend</h2>
            <div className="flex gap-1">
              {TREND_PERIODS.map((period) => (
                <button
                  key={period}
                  onClick={() => setTrendPeriod(period)}
                  className={`rounded px-3 py-1 text-xs font-medium transition-colors ${
                    trendPeriod === period
                      ? "bg-fizzbuzz-600 text-white"
                      : "bg-surface-overlay text-text-secondary hover:bg-surface-overlay"
                  }`}
                >
                  {PERIOD_LABELS[period]}
                </button>
              ))}
            </div>
          </div>
        </CardHeader>
        <CardContent>
          {trend && trendChartData.length > 0 ? (
            <>
              <LineChart
                data={trendChartData}
                color="var(--fizzbuzz-400)"
                unit="evaluations"
                label="Evaluation Volume"
                height={300}
              />
              <p className="mt-3 text-xs text-text-muted">
                Total evaluations in period:{" "}
                <span className="font-mono text-text-secondary">
                  {trend.totalEvaluations.toLocaleString()}
                </span>
              </p>
            </>
          ) : (
            <div className="flex items-center justify-center h-[300px] text-xs text-text-muted">
              Loading evaluation trend data...
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
