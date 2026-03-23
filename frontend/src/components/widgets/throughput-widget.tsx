"use client";

import { useCallback, useEffect, useState } from "react";
import { useDataProvider } from "@/lib/data-providers";
import type { MetricsSummary } from "@/lib/data-providers";

/**
 * Renders an SVG sparkline from a numeric time series. The polyline is
 * normalized to the viewport dimensions and stroked with the FizzBuzz
 * accent color for maximum operational visibility.
 */
function Sparkline({ data, width, height }: { data: number[]; width: number; height: number }) {
  if (data.length < 2) return null;

  const min = Math.min(...data);
  const max = Math.max(...data);
  const range = max - min || 1;

  const points = data
    .map((value, index) => {
      const x = (index / (data.length - 1)) * width;
      const y = height - ((value - min) / range) * (height - 4) - 2;
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");

  // Gradient fill area beneath the line
  const firstX = 0;
  const lastX = width;
  const areaPoints = `${firstX},${height} ${points} ${lastX},${height}`;

  return (
    <svg
      width={width}
      height={height}
      viewBox={`0 0 ${width} ${height}`}
      className="overflow-visible"
      aria-label="Throughput sparkline"
    >
      <defs>
        <linearGradient id="sparkline-fill" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="var(--fizzbuzz-400)" stopOpacity="0.3" />
          <stop offset="100%" stopColor="var(--fizzbuzz-400)" stopOpacity="0.02" />
        </linearGradient>
      </defs>
      <polygon points={areaPoints} fill="url(#sparkline-fill)" />
      <polyline
        points={points}
        fill="none"
        stroke="var(--fizzbuzz-400)"
        strokeWidth="1.5"
        strokeLinejoin="round"
        strokeLinecap="round"
      />
    </svg>
  );
}

/**
 * Throughput Widget — Displays real-time evaluation throughput as an
 * SVG sparkline with supporting KPI metrics. Auto-refreshes every
 * 2 seconds to provide continuous operational telemetry.
 */
export function ThroughputWidget() {
  const provider = useDataProvider();
  const [metrics, setMetrics] = useState<MetricsSummary | null>(null);

  const refresh = useCallback(async () => {
    const data = await provider.getMetricsSummary();
    setMetrics(data);
  }, [provider]);

  useEffect(() => {
    refresh();
    const interval = setInterval(refresh, 2_000);
    return () => clearInterval(interval);
  }, [refresh]);

  if (!metrics) {
    return (
      <div className="flex h-40 items-center justify-center">
        <span className="text-xs text-panel-500">Initializing telemetry stream...</span>
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {/* KPI row */}
      <div className="grid grid-cols-2 gap-3">
        <div>
          <p className="text-xs text-panel-500">Throughput</p>
          <p className="text-lg font-mono font-semibold text-panel-50">
            {metrics.evaluationsPerSecond.toLocaleString()}
            <span className="text-xs text-panel-400 ml-1">eval/s</span>
          </p>
        </div>
        <div>
          <p className="text-xs text-panel-500">Avg Latency</p>
          <p className="text-lg font-mono font-semibold text-panel-50">
            {metrics.averageLatencyMs.toFixed(2)}
            <span className="text-xs text-panel-400 ml-1">ms</span>
          </p>
        </div>
        <div>
          <p className="text-xs text-panel-500">Total Evaluations</p>
          <p className="text-sm font-mono text-panel-200">
            {metrics.totalEvaluations.toLocaleString()}
          </p>
        </div>
        <div>
          <p className="text-xs text-panel-500">Cache Hit Rate</p>
          <p className="text-sm font-mono text-panel-200">
            {(metrics.cacheHitRate * 100).toFixed(1)}%
          </p>
        </div>
      </div>

      {/* Sparkline */}
      <div className="rounded border border-panel-700 bg-panel-900 p-2">
        <Sparkline
          data={metrics.throughputHistory}
          width={320}
          height={64}
        />
      </div>

      {/* Uptime */}
      <p className="text-[10px] text-panel-500 text-right">
        Uptime: {Math.floor(metrics.uptimeSeconds / 86_400)}d{" "}
        {Math.floor((metrics.uptimeSeconds % 86_400) / 3_600)}h{" "}
        {Math.floor((metrics.uptimeSeconds % 3_600) / 60)}m
      </p>
    </div>
  );
}
