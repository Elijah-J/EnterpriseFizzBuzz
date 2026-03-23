"use client";

import { useMemo } from "react";

/**
 * Histogram bar chart with percentile overlay lines.
 *
 * Renders time series data as a bar chart approximation and computes
 * p50, p95, and p99 percentile lines overlaid on the distribution.
 * Used for latency and duration metrics where understanding the
 * distribution shape is more operationally useful than the mean.
 */

interface HistogramChartProps {
  /** Raw data points — values are bucketed into bars. */
  data: { timestamp: number; value: number }[];
  /** Chart width. */
  width?: number;
  /** Chart height. */
  height?: number;
  /** Bar fill color. */
  color?: string;
  /** Unit label for display. */
  unit?: string;
  /** Number of histogram buckets. */
  bucketCount?: number;
}

const MARGIN = { top: 12, right: 12, bottom: 28, left: 56 };

function percentile(sorted: number[], p: number): number {
  if (sorted.length === 0) return 0;
  const idx = (p / 100) * (sorted.length - 1);
  const lo = Math.floor(idx);
  const hi = Math.ceil(idx);
  if (lo === hi) return sorted[lo];
  return sorted[lo] + (sorted[hi] - sorted[lo]) * (idx - lo);
}

function formatValue(value: number): string {
  if (value >= 1_000_000) return `${(value / 1_000_000).toFixed(1)}M`;
  if (value >= 1_000) return `${(value / 1_000).toFixed(1)}K`;
  if (value >= 1) return value.toFixed(1);
  if (value >= 0.001) return value.toFixed(3);
  return value.toExponential(2);
}

export function HistogramChart({
  data,
  width = 700,
  height = 200,
  color = "var(--buzz-400)",
  unit = "",
  bucketCount = 30,
}: HistogramChartProps) {
  const plotWidth = width - MARGIN.left - MARGIN.right;
  const plotHeight = height - MARGIN.top - MARGIN.bottom;

  const { buckets, maxCount, p50, p95, p99, minVal, maxVal } = useMemo(() => {
    if (data.length === 0) {
      return { buckets: [], maxCount: 0, p50: 0, p95: 0, p99: 0, minVal: 0, maxVal: 1 };
    }

    const values = data.map((d) => d.value);
    const sorted = [...values].sort((a, b) => a - b);
    const lo = sorted[0];
    const hi = sorted[sorted.length - 1];
    const range = hi - lo || 1;
    const bucketWidth = range / bucketCount;

    const counts = new Array(bucketCount).fill(0) as number[];
    for (const v of values) {
      const idx = Math.min(Math.floor((v - lo) / bucketWidth), bucketCount - 1);
      counts[idx]++;
    }

    return {
      buckets: counts,
      maxCount: Math.max(...counts),
      p50: percentile(sorted, 50),
      p95: percentile(sorted, 95),
      p99: percentile(sorted, 99),
      minVal: lo,
      maxVal: hi,
    };
  }, [data, bucketCount]);

  if (data.length === 0) {
    return (
      <div
        className="flex items-center justify-center text-xs text-panel-500"
        style={{ width, height }}
      >
        No histogram data available
      </div>
    );
  }

  const barWidth = plotWidth / buckets.length;
  const range = maxVal - minVal || 1;

  const toX = (value: number) =>
    MARGIN.left + ((value - minVal) / range) * plotWidth;

  const percentileLines = [
    { value: p50, label: "p50", color: "var(--fizz-400)" },
    { value: p95, label: "p95", color: "var(--fizzbuzz-gold, #f59e0b)" },
    { value: p99, label: "p99", color: "#ef4444" },
  ];

  return (
    <svg
      width="100%"
      height={height}
      viewBox={`0 0 ${width} ${height}`}
      preserveAspectRatio="xMidYMid meet"
      className="overflow-visible"
    >
      {/* Bars */}
      {buckets.map((count, i) => {
        const barHeight = maxCount > 0 ? (count / maxCount) * plotHeight : 0;
        return (
          <rect
            key={i}
            x={MARGIN.left + i * barWidth + 1}
            y={MARGIN.top + plotHeight - barHeight}
            width={Math.max(0, barWidth - 2)}
            height={barHeight}
            fill={color}
            opacity={0.7}
            rx={1}
          />
        );
      })}

      {/* Percentile lines */}
      {percentileLines.map((pLine) => {
        const x = toX(pLine.value);
        return (
          <g key={pLine.label}>
            <line
              x1={x}
              x2={x}
              y1={MARGIN.top}
              y2={MARGIN.top + plotHeight}
              stroke={pLine.color}
              strokeWidth="1.5"
              strokeDasharray="4,3"
            />
            <text
              x={x}
              y={MARGIN.top - 2}
              textAnchor="middle"
              className="text-[9px] font-mono font-semibold"
              fill={pLine.color}
            >
              {pLine.label}
            </text>
          </g>
        );
      })}

      {/* X-axis labels (min, mid, max) */}
      {[minVal, (minVal + maxVal) / 2, maxVal].map((v, i) => (
        <text
          key={`x-${i}`}
          x={toX(v)}
          y={height - 4}
          textAnchor="middle"
          className="text-[10px] fill-panel-500"
        >
          {formatValue(v)} {i === 2 ? unit : ""}
        </text>
      ))}

      {/* Y-axis labels */}
      {[0, maxCount / 2, maxCount].map((count, i) => (
        <text
          key={`y-${i}`}
          x={MARGIN.left - 6}
          y={MARGIN.top + plotHeight - (count / (maxCount || 1)) * plotHeight}
          textAnchor="end"
          dominantBaseline="middle"
          className="text-[10px] fill-panel-500"
        >
          {Math.round(count)}
        </text>
      ))}
    </svg>
  );
}
