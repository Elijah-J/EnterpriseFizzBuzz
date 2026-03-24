"use client";

import { Sparkline } from "@/components/charts";
import { AnimatedNumber } from "./animated-number";
import { Card, CardContent } from "./card";

interface DataCardProps {
  /** Descriptive label for the KPI metric. */
  label: string;
  /** Current numeric value. */
  value: number;
  /** Unit label displayed adjacent to the value (e.g., "ms", "%", "req/s"). */
  unit?: string;
  /** Percentage change for the trend indicator. Positive = up, negative = down. */
  trend?: number;
  /** Ordered data points for the mini sparkline visualization. */
  sparklineData?: number[];
  /** Additional CSS classes for the outer card container. */
  className?: string;
}

/**
 * Key Performance Indicator display card for the FizzBuzz Operations Center.
 *
 * Composes Card, AnimatedNumber, and Sparkline into a unified KPI surface.
 * The large animated number (Geist Mono) serves as the primary data signal,
 * supported by a unit label (muted), mini sparkline for temporal context,
 * and a directional trend indicator showing period-over-period change.
 *
 * Trend direction is communicated through both color (desaturated green/red)
 * and symbol (geometric arrow) to maintain accessibility under color vision
 * deficiency conditions.
 */
export function DataCard({
  label,
  value,
  unit,
  trend,
  sparklineData,
  className = "",
}: DataCardProps) {
  const trendColor =
    trend !== undefined && trend >= 0
      ? "text-fizz-400"
      : "text-[var(--status-error)]";
  const trendSymbol = trend !== undefined && trend >= 0 ? "\u25B2" : "\u25BC";

  return (
    <Card variant="default" className={className}>
      <CardContent>
        <p className="data-label mb-1">{label}</p>
        <div className="flex items-baseline gap-2 mb-2">
          <AnimatedNumber value={value} className="data-value text-2xl" />
          {unit && <span className="data-unit">{unit}</span>}
        </div>
        <div className="flex items-center justify-between gap-3">
          {sparklineData && sparklineData.length >= 2 && (
            <Sparkline data={sparklineData} width={80} height={24} />
          )}
          {trend !== undefined && (
            <span className={`text-xs font-medium ${trendColor}`}>
              {trendSymbol} {Math.abs(trend).toFixed(1)}%
            </span>
          )}
        </div>
      </CardContent>
    </Card>
  );
}
