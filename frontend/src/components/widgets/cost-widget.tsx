"use client";

import { useCallback, useEffect, useState } from "react";
import { AnimatedNumber } from "@/components/ui/animated-number";
import { Skeleton } from "@/components/ui/skeleton";
import type { CostSummary } from "@/lib/data-providers";
import { useDataProvider } from "@/lib/data-providers";

/**
 * Trend arrow indicators for FinOps cost direction. Upward trends
 * are flagged in the error domain color (increased spend), downward
 * in the success domain color (savings), and stable in muted tone.
 */
const TREND_CONFIG: Record<
  CostSummary["trend"],
  { arrow: string; color: string; label: string }
> = {
  up: {
    arrow: "\u2191",
    color: "text-[var(--status-error)]",
    label: "increase",
  },
  down: { arrow: "\u2193", color: "text-fizz-400", label: "decrease" },
  stable: { arrow: "\u2192", color: "text-text-muted", label: "stable" },
};

/**
 * Cost Widget — FizzBuck expenditure summary for the current billing
 * period. Shows total spend, trend direction vs. previous period, and
 * per-evaluation unit cost. Auto-refreshes every 5 seconds.
 *
 * All monetary values use AnimatedNumber with currency formatting
 * for smooth transitions during data refreshes.
 */
export function CostWidget() {
  const provider = useDataProvider();
  const [cost, setCost] = useState<CostSummary | null>(null);

  const refresh = useCallback(async () => {
    const data = await provider.getCostSummary();
    setCost(data);
  }, [provider]);

  useEffect(() => {
    refresh();
    const interval = setInterval(refresh, 5_000);
    return () => clearInterval(interval);
  }, [refresh]);

  if (!cost) {
    return (
      <div className="space-y-4">
        <Skeleton variant="rect" height="3rem" />
        <div className="grid grid-cols-2 gap-3">
          <Skeleton variant="rect" height="2.5rem" />
          <Skeleton variant="rect" height="2.5rem" />
        </div>
        <Skeleton variant="text" width="60%" />
      </div>
    );
  }

  const trend = TREND_CONFIG[cost.trend];
  const delta = Math.abs(cost.currentPeriodCost - cost.previousPeriodCost);
  const deltaPercent =
    cost.previousPeriodCost > 0
      ? ((delta / cost.previousPeriodCost) * 100).toFixed(1)
      : "0.0";

  return (
    <div className="space-y-4">
      {/* Primary cost figure */}
      <div>
        <p className="data-label">Current Period Expenditure</p>
        <div className="flex items-baseline gap-2 mt-1">
          <span className="text-2xl font-mono font-bold text-fizzbuzz-gold">
            FB${" "}
          </span>
          <AnimatedNumber
            value={cost.currentPeriodCost}
            decimals={2}
            className="data-value text-2xl text-fizzbuzz-gold"
          />
          <span className={`text-sm font-mono ${trend.color}`}>
            {trend.arrow} {deltaPercent}%
          </span>
        </div>
      </div>

      {/* Details */}
      <div className="grid grid-cols-2 gap-3">
        <div>
          <p className="data-label text-[10px]">Previous Period</p>
          <div className="flex items-baseline gap-1">
            <span className="text-sm font-mono text-text-secondary">FB$ </span>
            <AnimatedNumber
              value={cost.previousPeriodCost}
              decimals={2}
              className="text-sm font-mono text-text-secondary"
            />
          </div>
        </div>
        <div>
          <p className="data-label text-[10px]">Cost per Evaluation</p>
          <div className="flex items-baseline gap-1">
            <span className="text-sm font-mono text-text-secondary">FB$ </span>
            <AnimatedNumber
              value={cost.costPerEvaluation}
              decimals={7}
              className="text-sm font-mono text-text-secondary"
            />
          </div>
        </div>
      </div>

      {/* Trend label */}
      <p className={`text-[10px] ${trend.color} text-right`}>
        Spend trend: {trend.label} vs. prior period
      </p>
    </div>
  );
}
