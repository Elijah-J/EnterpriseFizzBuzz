"use client";

import { useCallback, useEffect, useState } from "react";
import { AnimatedNumber } from "@/components/ui/animated-number";
import { Skeleton } from "@/components/ui/skeleton";
import type { SLAStatus } from "@/lib/data-providers";
import { useDataProvider } from "@/lib/data-providers";

/**
 * Renders a circular gauge as an SVG arc. The arc fills proportionally
 * to the value parameter and shifts color based on severity thresholds:
 *   - Green (> 60% remaining): nominal operations
 *   - Amber (20-60% remaining): caution, budget depleting
 *   - Red (< 20% remaining): critical, SLA at risk
 *
 * Threshold colors are desaturated to maintain cohesion with the warm
 * stone surface palette.
 */
function CircularGauge({
  value,
  size = 120,
}: {
  value: number;
  size?: number;
}) {
  const strokeWidth = 8;
  const radius = (size - strokeWidth) / 2;
  const circumference = 2 * Math.PI * radius;
  const offset = circumference * (1 - Math.max(0, Math.min(1, value)));

  let strokeColor = "var(--fizz-400)";
  if (value < 0.2) {
    strokeColor = "var(--status-error)";
  } else if (value < 0.6) {
    strokeColor = "var(--accent)";
  }

  return (
    <svg
      width={size}
      height={size}
      viewBox={`0 0 ${size} ${size}`}
      className="mx-auto"
      aria-label={`Error budget gauge: ${(value * 100).toFixed(1)}% remaining`}
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
      {/* Center label */}
      <text
        x={size / 2}
        y={size / 2 - 6}
        textAnchor="middle"
        dominantBaseline="middle"
        className="data-value text-lg"
        fill="var(--text-primary)"
      >
        {(value * 100).toFixed(1)}%
      </text>
      <text
        x={size / 2}
        y={size / 2 + 12}
        textAnchor="middle"
        dominantBaseline="middle"
        className="text-[10px]"
        fill="var(--text-muted)"
      >
        error budget
      </text>
    </svg>
  );
}

/**
 * SLA Budget Widget — Circular gauge showing error budget depletion
 * alongside key SLA compliance metrics. Auto-refreshes every 3 seconds
 * to track real-time SLA posture.
 *
 * All numeric values use AnimatedNumber for spring-based interpolation,
 * providing smooth transitions during data refreshes.
 */
export function SLABudgetWidget() {
  const provider = useDataProvider();
  const [sla, setSLA] = useState<SLAStatus | null>(null);

  const refresh = useCallback(async () => {
    const data = await provider.getSLAStatus();
    setSLA(data);
  }, [provider]);

  useEffect(() => {
    refresh();
    const interval = setInterval(refresh, 3_000);
    return () => clearInterval(interval);
  }, [refresh]);

  if (!sla) {
    return (
      <div className="space-y-3 flex flex-col items-center">
        <Skeleton variant="circle" width={120} height={120} />
        <div className="grid grid-cols-3 gap-2 w-full">
          <Skeleton variant="text" height="2rem" />
          <Skeleton variant="text" height="2rem" />
          <Skeleton variant="text" height="2rem" />
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-3">
      <CircularGauge value={sla.errorBudgetRemaining} />

      <div className="grid grid-cols-3 gap-2 text-center">
        <div>
          <p className="data-label text-[10px]">Availability</p>
          <AnimatedNumber
            value={sla.availabilityPercent}
            decimals={2}
            format="percent"
            className="text-sm font-mono text-fizz-400"
          />
        </div>
        <div>
          <p className="data-label text-[10px]">P99 Latency</p>
          <div className="flex items-baseline justify-center gap-0.5">
            <AnimatedNumber
              value={sla.latencyP99Ms}
              decimals={1}
              className="text-sm font-mono text-text-secondary"
            />
            <span className="data-unit text-[9px]">ms</span>
          </div>
        </div>
        <div>
          <p className="data-label text-[10px]">Correctness</p>
          <AnimatedNumber
            value={sla.correctnessPercent}
            decimals={1}
            format="percent"
            className="text-sm font-mono text-fizz-400"
          />
        </div>
      </div>
    </div>
  );
}
