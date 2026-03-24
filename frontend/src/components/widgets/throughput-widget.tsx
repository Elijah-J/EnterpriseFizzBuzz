"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Sparkline } from "@/components/charts";
import { AnimatedNumber } from "@/components/ui/animated-number";
import { Skeleton } from "@/components/ui/skeleton";
import type { MetricsSummary } from "@/lib/data-providers";
import { useDataProvider } from "@/lib/data-providers";

/**
 * Throughput Widget — Displays real-time evaluation throughput as an
 * SVG sparkline with supporting KPI metrics. Auto-refreshes every
 * 2 seconds to provide continuous operational telemetry.
 *
 * Loading state uses warm-toned skeleton placeholders to maintain
 * spatial stability during data initialization. All numeric KPIs
 * use spring-based animated interpolation for fluid value transitions.
 */
export function ThroughputWidget() {
  const provider = useDataProvider();
  const [metrics, setMetrics] = useState<MetricsSummary | null>(null);
  const [prevEvalPerSec, setPrevEvalPerSec] = useState<number | null>(null);
  const [deltaFlash, setDeltaFlash] = useState(false);
  const flashTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const refresh = useCallback(async () => {
    const data = await provider.getMetricsSummary();
    setMetrics((prev) => {
      if (prev) {
        setPrevEvalPerSec(prev.evaluationsPerSecond);
        // Trigger delta flash on value change
        if (prev.evaluationsPerSecond !== data.evaluationsPerSecond) {
          setDeltaFlash(true);
          if (flashTimer.current) clearTimeout(flashTimer.current);
          flashTimer.current = setTimeout(() => setDeltaFlash(false), 200);
        }
      }
      return data;
    });
  }, [provider]);

  useEffect(() => {
    refresh();
    const interval = setInterval(refresh, 2_000);
    return () => clearInterval(interval);
  }, [refresh]);

  if (!metrics) {
    return (
      <div className="space-y-3">
        <div className="grid grid-cols-2 gap-3">
          <Skeleton variant="rect" height="3rem" />
          <Skeleton variant="rect" height="3rem" />
          <Skeleton variant="rect" height="2rem" />
          <Skeleton variant="rect" height="2rem" />
        </div>
        <Skeleton variant="rect" height="4.5rem" />
      </div>
    );
  }

  const throughputDelta =
    prevEvalPerSec !== null && prevEvalPerSec > 0
      ? ((metrics.evaluationsPerSecond - prevEvalPerSec) / prevEvalPerSec) * 100
      : null;

  return (
    <div className="space-y-3">
      {/* KPI row */}
      <div className="grid grid-cols-2 gap-3">
        <div>
          <p className="data-label">Throughput</p>
          <div
            className="flex items-baseline gap-1.5 rounded px-1 -mx-1 transition-colors duration-200"
            style={{
              backgroundColor: deltaFlash ? "var(--accent-muted)" : "transparent",
            }}
          >
            <AnimatedNumber
              value={metrics.evaluationsPerSecond}
              className="data-value text-2xl"
            />
            <span className="data-unit">eval/s</span>
          </div>
          {throughputDelta !== null && (
            <span
              className={`text-xs font-medium ${throughputDelta >= 0 ? "text-fizz-400" : "text-[var(--status-error)]"}`}
            >
              {throughputDelta >= 0 ? "\u25B2" : "\u25BC"}{" "}
              {Math.abs(throughputDelta).toFixed(1)}%
            </span>
          )}
        </div>
        <div>
          <p className="data-label">Avg Latency</p>
          <div className="flex items-baseline gap-1.5">
            <AnimatedNumber
              value={metrics.averageLatencyMs}
              decimals={2}
              className="data-value text-2xl"
            />
            <span className="data-unit">ms</span>
          </div>
        </div>
        <div>
          <p className="data-label">Total Evaluations</p>
          <AnimatedNumber
            value={metrics.totalEvaluations}
            className="text-sm font-mono text-text-secondary"
          />
        </div>
        <div>
          <p className="data-label">Cache Hit Rate</p>
          <AnimatedNumber
            value={metrics.cacheHitRate * 100}
            decimals={1}
            format="percent"
            className="text-sm font-mono text-text-secondary"
          />
        </div>
      </div>

      {/* Sparkline */}
      <div className="rounded border border-border-subtle bg-surface-base p-2">
        <Sparkline data={metrics.throughputHistory} width={320} height={64} />
      </div>

      {/* Uptime */}
      <p className="text-[10px] text-text-muted text-right">
        Uptime: {Math.floor(metrics.uptimeSeconds / 86_400)}d{" "}
        {Math.floor((metrics.uptimeSeconds % 86_400) / 3_600)}h{" "}
        {Math.floor((metrics.uptimeSeconds % 3_600) / 60)}m
      </p>
    </div>
  );
}
