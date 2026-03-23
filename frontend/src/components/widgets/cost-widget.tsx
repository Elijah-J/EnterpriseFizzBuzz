"use client";

import { useCallback, useEffect, useState } from "react";
import { useDataProvider } from "@/lib/data-providers";
import type { CostSummary } from "@/lib/data-providers";

/**
 * Trend arrow indicators for FinOps cost direction. Upward trends
 * are flagged in red (increased spend), downward in green (savings),
 * and stable in neutral gray.
 */
const TREND_CONFIG: Record<CostSummary["trend"], { arrow: string; color: string; label: string }> = {
  up: { arrow: "\u2191", color: "text-red-400", label: "increase" },
  down: { arrow: "\u2193", color: "text-fizz-400", label: "decrease" },
  stable: { arrow: "\u2192", color: "text-panel-400", label: "stable" },
};

/**
 * Cost Widget — FizzBuck expenditure summary for the current billing
 * period. Shows total spend, trend direction vs. previous period, and
 * per-evaluation unit cost. Auto-refreshes every 5 seconds.
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
      <div className="flex h-24 items-center justify-center">
        <span className="text-xs text-panel-500">Calculating expenditure...</span>
      </div>
    );
  }

  const trend = TREND_CONFIG[cost.trend];
  const delta = Math.abs(cost.currentPeriodCost - cost.previousPeriodCost);
  const deltaPercent = cost.previousPeriodCost > 0
    ? ((delta / cost.previousPeriodCost) * 100).toFixed(1)
    : "0.0";

  return (
    <div className="space-y-4">
      {/* Primary cost figure */}
      <div>
        <p className="text-xs text-panel-500">Current Period Expenditure</p>
        <div className="flex items-baseline gap-2 mt-1">
          <span className="text-2xl font-mono font-bold text-fizzbuzz-gold">
            FB$ {cost.currentPeriodCost.toFixed(2)}
          </span>
          <span className={`text-sm font-mono ${trend.color}`}>
            {trend.arrow} {deltaPercent}%
          </span>
        </div>
      </div>

      {/* Details */}
      <div className="grid grid-cols-2 gap-3">
        <div>
          <p className="text-[10px] text-panel-500">Previous Period</p>
          <p className="text-sm font-mono text-panel-300">
            FB$ {cost.previousPeriodCost.toFixed(2)}
          </p>
        </div>
        <div>
          <p className="text-[10px] text-panel-500">Cost per Evaluation</p>
          <p className="text-sm font-mono text-panel-300">
            FB$ {cost.costPerEvaluation.toFixed(7)}
          </p>
        </div>
      </div>

      {/* Trend label */}
      <p className={`text-[10px] ${trend.color} text-right`}>
        Spend trend: {trend.label} vs. prior period
      </p>
    </div>
  );
}
