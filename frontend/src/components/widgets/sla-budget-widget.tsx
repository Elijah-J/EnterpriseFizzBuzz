"use client";

import { useCallback, useEffect, useState } from "react";
import { useDataProvider } from "@/lib/data-providers";
import type { SLAStatus } from "@/lib/data-providers";

/**
 * Renders a circular gauge as an SVG arc. The arc fills proportionally
 * to the value parameter and shifts color based on severity thresholds:
 *   - Green (> 60% remaining): nominal
 *   - Amber (20-60% remaining): caution
 *   - Red (< 20% remaining): critical
 */
function CircularGauge({ value, size = 120 }: { value: number; size?: number }) {
  const strokeWidth = 8;
  const radius = (size - strokeWidth) / 2;
  const circumference = 2 * Math.PI * radius;
  const offset = circumference * (1 - Math.max(0, Math.min(1, value)));

  let strokeColor = "var(--fizz-400)";
  if (value < 0.2) {
    strokeColor = "#ef4444";
  } else if (value < 0.6) {
    strokeColor = "#f59e0b";
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
        stroke="var(--panel-700)"
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
        className="text-lg font-mono font-bold"
        fill="var(--panel-50)"
      >
        {(value * 100).toFixed(1)}%
      </text>
      <text
        x={size / 2}
        y={size / 2 + 12}
        textAnchor="middle"
        dominantBaseline="middle"
        className="text-[10px]"
        fill="var(--panel-400)"
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
      <div className="flex h-40 items-center justify-center">
        <span className="text-xs text-panel-500">Loading SLA metrics...</span>
      </div>
    );
  }

  return (
    <div className="space-y-3">
      <CircularGauge value={sla.errorBudgetRemaining} />

      <div className="grid grid-cols-3 gap-2 text-center">
        <div>
          <p className="text-[10px] text-panel-500">Availability</p>
          <p className="text-sm font-mono text-fizz-400">
            {sla.availabilityPercent.toFixed(2)}%
          </p>
        </div>
        <div>
          <p className="text-[10px] text-panel-500">P99 Latency</p>
          <p className="text-sm font-mono text-panel-200">
            {sla.latencyP99Ms.toFixed(1)}ms
          </p>
        </div>
        <div>
          <p className="text-[10px] text-panel-500">Correctness</p>
          <p className="text-sm font-mono text-fizz-400">
            {sla.correctnessPercent.toFixed(1)}%
          </p>
        </div>
      </div>
    </div>
  );
}
