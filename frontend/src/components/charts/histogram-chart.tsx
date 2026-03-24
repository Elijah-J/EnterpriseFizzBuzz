"use client";

import { useEffect, useMemo, useState } from "react";
import { useReducedMotion } from "@/lib/hooks/use-reduced-motion";

/**
 * Histogram bar chart with staggered entrance animation, warm gradients,
 * rounded top corners, and percentile overlay lines.
 *
 * Bars grow from the baseline with 50ms stagger between consecutive bins,
 * creating a left-to-right wave entrance. Each bar has a subtle vertical
 * gradient (slightly lighter at top) for depth without shadow effects.
 * Top corners are rounded; bottom corners remain square to anchor to the axis.
 *
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
  const prefersReduced = useReducedMotion();
  const [animationProgress, setAnimationProgress] = useState(
    prefersReduced ? 1 : 0,
  );
  const gradientId = useMemo(
    () => `histogram-bar-${Math.random().toString(36).slice(2, 8)}`,
    [],
  );

  const { buckets, maxCount, p50, p95, p99, minVal, maxVal } = useMemo(() => {
    if (data.length === 0) {
      return {
        buckets: [],
        maxCount: 0,
        p50: 0,
        p95: 0,
        p99: 0,
        minVal: 0,
        maxVal: 1,
      };
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

  // Staggered bar entrance animation
  useEffect(() => {
    if (prefersReduced || data.length === 0) {
      setAnimationProgress(1);
      return;
    }

    setAnimationProgress(0);
    const startTime = performance.now();
    const duration = 400 + buckets.length * 50;
    let frameId: number;

    const animate = (now: number) => {
      const elapsed = now - startTime;
      const t = Math.min(elapsed / duration, 1);
      setAnimationProgress(t);
      if (t < 1) {
        frameId = requestAnimationFrame(animate);
      }
    };

    frameId = requestAnimationFrame(animate);
    return () => cancelAnimationFrame(frameId);
  }, [prefersReduced, data, buckets.length]);

  if (data.length === 0) {
    return (
      <div
        className="flex items-center justify-center text-xs text-text-muted"
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
      role="img"
      aria-label="Histogram distribution chart"
    >
      <defs>
        {/* Subtle vertical gradient — slightly lighter at top for depth */}
        <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={color} stopOpacity="0.9" />
          <stop offset="100%" stopColor={color} stopOpacity="0.6" />
        </linearGradient>
      </defs>

      {/* Bars with staggered grow-from-bottom entrance */}
      {buckets.map((count, i) => {
        const fullBarHeight =
          maxCount > 0 ? (count / maxCount) * plotHeight : 0;
        // Each bar has an individual stagger delay
        const staggerT = Math.max(
          0,
          Math.min(
            1,
            (animationProgress * (400 + buckets.length * 50) - i * 50) / 400,
          ),
        );
        // Ease-out quadratic
        const easedT = 1 - (1 - staggerT) ** 2;
        const barHeight = fullBarHeight * easedT;
        const bw = Math.max(0, barWidth - 2);
        const cornerRadius = Math.min(3, bw / 2);

        return (
          <rect
            key={`bucket-${i}`}
            x={MARGIN.left + i * barWidth + 1}
            y={MARGIN.top + plotHeight - barHeight}
            width={bw}
            height={barHeight}
            fill={`url(#${gradientId})`}
            rx={cornerRadius}
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
      {[
        { v: minVal, label: "" },
        { v: (minVal + maxVal) / 2, label: "" },
        { v: maxVal, label: unit },
      ].map(({ v, label: unitLabel }) => (
        <text
          key={`x-${v}`}
          x={toX(v)}
          y={height - 4}
          textAnchor="middle"
          className="text-[10px] fill-text-muted"
        >
          {formatValue(v)} {unitLabel}
        </text>
      ))}

      {/* Y-axis labels */}
      {[0, maxCount / 2, maxCount].map((count) => (
        <text
          key={`y-${count}`}
          x={MARGIN.left - 6}
          y={MARGIN.top + plotHeight - (count / (maxCount || 1)) * plotHeight}
          textAnchor="end"
          dominantBaseline="middle"
          className="text-[10px] fill-text-muted"
        >
          {Math.round(count)}
        </text>
      ))}
    </svg>
  );
}
