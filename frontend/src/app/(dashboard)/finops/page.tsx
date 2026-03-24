"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { Pagination } from "@/components/ui/pagination";
import { Reveal } from "@/components/ui/reveal";
import { Skeleton } from "@/components/ui/skeleton";
import { StatGroup } from "@/components/ui/stat-group";
import { Tabs } from "@/components/ui/tabs";
import type {
  BudgetStatus,
  CostAllocation,
  CostSummary,
  DailyCostPoint,
  FizzBuckExchangeRate,
  Invoice,
} from "@/lib/data-providers";
import { useDataProvider } from "@/lib/data-providers";

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

/** Exchange rate ticker polling interval. */
const EXCHANGE_RATE_POLL_MS = 5_000;

/** Last 6 months for the invoice period selector. */
function getRecentPeriods(): string[] {
  const periods: string[] = [];
  const now = new Date();
  for (let i = 0; i < 6; i++) {
    const d = new Date(now.getFullYear(), now.getMonth() - i, 1);
    const year = d.getFullYear();
    const month = String(d.getMonth() + 1).padStart(2, "0");
    periods.push(`${year}-${month}`);
  }
  return periods;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/** Format a FizzBuck amount with thousands separators. */
function formatFB(amount: number): string {
  return `FB$ ${amount.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

/** Map a utilization ratio (0-1+) to a Tailwind text color class. */
function utilizationColor(ratio: number): string {
  if (ratio >= 0.9) return "text-red-400";
  if (ratio >= 0.7) return "text-amber-400";
  return "text-fizz-400";
}

/** Map a utilization ratio to an SVG fill color. */
function utilizationFill(ratio: number): string {
  if (ratio >= 0.9) return "#f87171"; // red-400
  if (ratio >= 0.7) return "#fbbf24"; // amber-400
  return "#4ade80"; // green-400
}

/** Map a utilization ratio to a progress bar background class. */
function progressBarBg(ratio: number): string {
  if (ratio >= 0.9) return "bg-red-500";
  if (ratio >= 0.7) return "bg-amber-500";
  return "bg-fizz-500";
}

// ---------------------------------------------------------------------------
// SVG Treemap Layout (squarified algorithm approximation)
// ---------------------------------------------------------------------------

interface TreemapRect {
  x: number;
  y: number;
  w: number;
  h: number;
  allocation: CostAllocation;
}

/**
 * Computes a simple slice-and-dice treemap layout. Alternates between
 * horizontal and vertical subdivision at each split to produce visually
 * balanced rectangles. While a full Bruls squarified algorithm would
 * produce optimal aspect ratios, this approach is sufficient for the
 * 10-subsystem cost allocation treemap and avoids external dependencies.
 */
function computeTreemap(
  allocations: CostAllocation[],
  x: number,
  y: number,
  w: number,
  h: number,
): TreemapRect[] {
  if (allocations.length === 0) return [];
  if (allocations.length === 1) {
    return [{ x, y, w, h, allocation: allocations[0] }];
  }

  // Sort descending by cost for better visual balance
  const sorted = [...allocations].sort((a, b) => b.cost - a.cost);
  const totalCost = sorted.reduce((sum, a) => sum + a.cost, 0);

  if (totalCost <= 0) return [];

  // Split into two groups where the first group approaches 50% of total cost
  let groupCost = 0;
  let splitIndex = 0;
  for (let i = 0; i < sorted.length; i++) {
    groupCost += sorted[i].cost;
    if (groupCost >= totalCost * 0.5) {
      splitIndex = i + 1;
      break;
    }
  }
  if (splitIndex === 0) splitIndex = 1;
  if (splitIndex >= sorted.length) splitIndex = sorted.length - 1;

  const group1 = sorted.slice(0, splitIndex);
  const group2 = sorted.slice(splitIndex);
  const ratio1 = group1.reduce((s, a) => s + a.cost, 0) / totalCost;

  // Alternate split direction based on aspect ratio
  if (w >= h) {
    const w1 = w * ratio1;
    return [
      ...computeTreemap(group1, x, y, w1, h),
      ...computeTreemap(group2, x + w1, y, w - w1, h),
    ];
  } else {
    const h1 = h * ratio1;
    return [
      ...computeTreemap(group1, x, y, w, h1),
      ...computeTreemap(group2, x, y + h1, w, h - h1),
    ];
  }
}

// ---------------------------------------------------------------------------
// Component: KPI Summary Cards
// ---------------------------------------------------------------------------

function KPISummaryCards({
  costSummary,
  costBreakdown,
  exchangeRate,
  budgetStatuses,
}: {
  costSummary: CostSummary | null;
  costBreakdown: CostAllocation[];
  exchangeRate: FizzBuckExchangeRate | null;
  budgetStatuses: BudgetStatus[];
}) {
  // Total period spend
  const totalSpend = costBreakdown.reduce((s, c) => s + c.cost, 0);
  const trendDirection = costSummary ? costSummary.trend : "stable";
  // Compute period-over-period delta percentage from CostSummary
  const trendDelta =
    costSummary && costSummary.previousPeriodCost > 0
      ? ((costSummary.currentPeriodCost - costSummary.previousPeriodCost) /
          costSummary.previousPeriodCost) *
        100
      : 0;

  // Cost per evaluation from CostSummary
  const costPerEval = costSummary ? costSummary.costPerEvaluation : 0;

  // Overall budget utilization
  const totalAllocated = budgetStatuses.reduce((s, b) => s + b.allocated, 0);
  const totalSpent = budgetStatuses.reduce((s, b) => s + b.spent, 0);
  const overallUtilization =
    totalAllocated > 0 ? totalSpent / totalAllocated : 0;

  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
      {/* Total Period Spend */}
      <Card>
        <CardContent className="py-4">
          <p className="text-xs text-text-secondary uppercase tracking-wider mb-1">
            Total Period Spend
          </p>
          <p className="text-2xl font-semibold text-text-primary font-mono">
            {formatFB(totalSpend)}
          </p>
          <p
            className={`text-xs mt-1 ${trendDirection === "up" ? "text-red-400" : trendDirection === "down" ? "text-fizz-400" : "text-text-secondary"}`}
          >
            {trendDirection === "up"
              ? "\u2191"
              : trendDirection === "down"
                ? "\u2193"
                : "\u2194"}{" "}
            {Math.abs(trendDelta).toFixed(1)}% vs. previous period
          </p>
        </CardContent>
      </Card>

      {/* Cost Per Evaluation */}
      <Card>
        <CardContent className="py-4">
          <p className="text-xs text-text-secondary uppercase tracking-wider mb-1">
            Cost Per Evaluation
          </p>
          <p className="text-2xl font-semibold text-text-primary font-mono">
            FB$ {costPerEval.toFixed(4)}
          </p>
          <p className="text-xs text-text-muted mt-1">
            Across all evaluation strategies
          </p>
        </CardContent>
      </Card>

      {/* Exchange Rate */}
      <Card>
        <CardContent className="py-4">
          <p className="text-xs text-text-secondary uppercase tracking-wider mb-1">
            FB$/USD Exchange Rate
          </p>
          <p className="text-2xl font-semibold text-text-primary font-mono">
            ${exchangeRate ? exchangeRate.rate.toFixed(6) : "---"}
          </p>
          {exchangeRate && (
            <p
              className={`text-xs mt-1 ${exchangeRate.change24h >= 0 ? "text-fizz-400" : "text-red-400"}`}
            >
              {exchangeRate.trend === "up"
                ? "\u2191"
                : exchangeRate.trend === "down"
                  ? "\u2193"
                  : "\u2194"}{" "}
              {exchangeRate.change24h >= 0 ? "+" : ""}
              {exchangeRate.change24h.toFixed(2)}% (24h)
            </p>
          )}
        </CardContent>
      </Card>

      {/* Budget Health */}
      <Card>
        <CardContent className="py-4">
          <p className="text-xs text-text-secondary uppercase tracking-wider mb-1">
            Budget Health
          </p>
          <p
            className={`text-2xl font-semibold font-mono ${utilizationColor(overallUtilization)}`}
          >
            {(overallUtilization * 100).toFixed(1)}%
          </p>
          <p className="text-xs text-text-muted mt-1">
            {budgetStatuses.filter((b) => b.overBudget).length} categories
            projected over budget
          </p>
        </CardContent>
      </Card>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Component: Cost Allocation Treemap
// ---------------------------------------------------------------------------

function CostTreemap({ allocations }: { allocations: CostAllocation[] }) {
  const width = 700;
  const height = 400;
  const rects = useMemo(
    () => computeTreemap(allocations, 0, 0, width, height),
    [allocations],
  );

  return (
    <Card className="flex-1">
      <CardHeader>
        <h3 className="heading-section">Cost Allocation Treemap</h3>
        <p className="text-xs text-text-muted">
          Rectangle area proportional to FizzBuck spend. Color indicates budget
          utilization.
        </p>
      </CardHeader>
      <CardContent>
        <svg viewBox={`0 0 ${width} ${height}`} className="w-full h-auto">
          {rects.map((r, i) => {
            const fill = utilizationFill(r.allocation.utilizationRatio);
            // Only render text if rectangle is large enough
            const showLabel = r.w > 60 && r.h > 36;
            return (
              <g key={i}>
                <rect
                  x={r.x + 1}
                  y={r.y + 1}
                  width={Math.max(0, r.w - 2)}
                  height={Math.max(0, r.h - 2)}
                  fill={fill}
                  fillOpacity={0.25}
                  stroke={fill}
                  strokeWidth={1.5}
                  rx={3}
                />
                {showLabel && (
                  <>
                    <text
                      x={r.x + r.w / 2}
                      y={r.y + r.h / 2 - 6}
                      textAnchor="middle"
                      className="fill-panel-100 text-[11px] font-medium"
                    >
                      {r.allocation.subsystem}
                    </text>
                    <text
                      x={r.x + r.w / 2}
                      y={r.y + r.h / 2 + 10}
                      textAnchor="middle"
                      className="fill-panel-300 text-[10px] font-mono"
                    >
                      {formatFB(r.allocation.cost)}
                    </text>
                  </>
                )}
              </g>
            );
          })}
        </svg>
      </CardContent>
    </Card>
  );
}

// ---------------------------------------------------------------------------
// Component: Exchange Rate Ticker
// ---------------------------------------------------------------------------

function ExchangeRateTicker({
  exchangeRate,
}: {
  exchangeRate: FizzBuckExchangeRate | null;
}) {
  if (!exchangeRate) {
    return (
      <Card>
        <CardContent className="py-8 text-center text-text-muted text-sm">
          Loading exchange rate data...
        </CardContent>
      </Card>
    );
  }

  const { rate, trend, change24h, high24h, low24h, history } = exchangeRate;

  // Build sparkline SVG path from history
  const sparklineWidth = 280;
  const sparklineHeight = 80;
  const rates = history.map((h) => h.rate);
  const minRate = Math.min(...rates);
  const maxRate = Math.max(...rates);
  const range = maxRate - minRate || 0.0001;

  const points = history.map((h, i) => {
    const x = (i / (history.length - 1)) * sparklineWidth;
    const y = sparklineHeight - ((h.rate - minRate) / range) * sparklineHeight;
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  });
  const pathD = `M ${points.join(" L ")}`;

  const trendArrow =
    trend === "up" ? "\u2191" : trend === "down" ? "\u2193" : "\u2194";
  const trendColor =
    trend === "up"
      ? "text-fizz-400"
      : trend === "down"
        ? "text-red-400"
        : "text-text-secondary";

  return (
    <Card>
      <CardHeader>
        <h3 className="heading-section">FizzBuck Exchange Rate</h3>
        <p className="text-xs text-text-muted">
          1 FB$ to USD — 5-second polling
        </p>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="text-center">
          <p className="text-3xl font-semibold text-text-primary font-mono">
            ${rate.toFixed(6)}
          </p>
          <p className={`text-sm mt-1 ${trendColor}`}>
            {trendArrow} {change24h >= 0 ? "+" : ""}
            {change24h.toFixed(2)}% (24h)
          </p>
        </div>

        <div className="flex justify-between text-xs text-text-secondary">
          <span>24h High: ${high24h.toFixed(6)}</span>
          <span>24h Low: ${low24h.toFixed(6)}</span>
        </div>

        <svg
          viewBox={`0 0 ${sparklineWidth} ${sparklineHeight}`}
          className="w-full h-20"
          preserveAspectRatio="none"
        >
          <path
            d={pathD}
            fill="none"
            stroke={
              trend === "up"
                ? "#4ade80"
                : trend === "down"
                  ? "#f87171"
                  : "#94a3b8"
            }
            strokeWidth={1.5}
          />
        </svg>

        <div className="flex items-center gap-2 text-xs text-text-muted">
          <span className="h-1.5 w-1.5 rounded-full bg-fizz-400 animate-pulse" />
          Live — refreshes every 5s
        </div>
      </CardContent>
    </Card>
  );
}

// ---------------------------------------------------------------------------
// Component: Budget Progress Bars
// ---------------------------------------------------------------------------

function BudgetProgressBars({ budgets }: { budgets: BudgetStatus[] }) {
  return (
    <Card>
      <CardHeader>
        <h3 className="heading-section">Budget Status</h3>
        <p className="text-xs text-text-muted">
          Current period budget utilization by category with end-of-period
          projections
        </p>
      </CardHeader>
      <CardContent className="space-y-4">
        {budgets.map((b) => {
          const ratio = b.allocated > 0 ? b.spent / b.allocated : 0;
          const projectedRatio =
            b.allocated > 0 ? b.projectedSpend / b.allocated : 0;
          const barWidth = Math.min(ratio * 100, 100);
          const projectedWidth = Math.min(projectedRatio * 100, 100);

          return (
            <div key={b.category}>
              <div className="flex items-center justify-between mb-1">
                <div className="flex items-center gap-2">
                  <span className="text-sm text-text-secondary">{b.label}</span>
                  {b.overBudget && <Badge variant="error">Over Budget</Badge>}
                </div>
                <span className="text-xs text-text-secondary font-mono">
                  {formatFB(b.spent)} / {formatFB(b.allocated)}
                </span>
              </div>
              <div className="relative h-3 bg-surface-overlay rounded-full overflow-hidden">
                {/* Projected spend marker */}
                {projectedRatio > ratio && (
                  <div
                    className="absolute top-0 h-full bg-panel-600 rounded-full"
                    style={{ width: `${projectedWidth}%` }}
                  />
                )}
                {/* Actual spend bar */}
                <div
                  className={`absolute top-0 h-full rounded-full transition-all ${progressBarBg(ratio)}`}
                  style={{ width: `${barWidth}%` }}
                />
                {/* Budget limit marker at 100% */}
                {projectedRatio > 1.0 && (
                  <div className="absolute top-0 right-0 h-full w-0.5 bg-red-400" />
                )}
              </div>
              <div className="flex justify-between mt-0.5">
                <span className="text-[10px] text-text-muted">
                  {(ratio * 100).toFixed(1)}% utilized
                </span>
                <span
                  className={`text-[10px] ${b.overBudget ? "text-red-400" : "text-text-muted"}`}
                >
                  Projected: {formatFB(b.projectedSpend)}
                </span>
              </div>
            </div>
          );
        })}
      </CardContent>
    </Card>
  );
}

// ---------------------------------------------------------------------------
// Component: 30-Day Cost Trend Chart
// ---------------------------------------------------------------------------

function CostTrendChart({ data }: { data: DailyCostPoint[] }) {
  if (data.length === 0) return null;

  const chartWidth = 500;
  const chartHeight = 250;
  const padding = { top: 20, right: 20, bottom: 40, left: 60 };
  const plotWidth = chartWidth - padding.left - padding.right;
  const plotHeight = chartHeight - padding.top - padding.bottom;

  const costs = data.map((d) => d.totalCost);
  const maxCost = Math.max(...costs) * 1.1;
  const minCost = 0;
  const costRange = maxCost - minCost || 1;

  // Daily budget target: allocated monthly budget / 30
  const dailyBudget = 96_500 / 30; // ~3,217 FB$/day

  const points = data.map((d, i) => {
    const x = padding.left + (i / (data.length - 1)) * plotWidth;
    const y =
      padding.top +
      plotHeight -
      ((d.totalCost - minCost) / costRange) * plotHeight;
    return { x, y, data: d };
  });

  const linePath = `M ${points.map((p) => `${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(" L ")}`;
  const budgetY =
    padding.top +
    plotHeight -
    ((dailyBudget - minCost) / costRange) * plotHeight;

  // Y-axis ticks
  const yTicks = Array.from({ length: 5 }, (_, i) => {
    const val = minCost + (costRange * i) / 4;
    const y = padding.top + plotHeight - (i / 4) * plotHeight;
    return { val, y };
  });

  // X-axis labels (every 5th day)
  const xLabels = data.filter((_, i) => i % 5 === 0 || i === data.length - 1);

  return (
    <Card className="flex-1">
      <CardHeader>
        <h3 className="heading-section">30-Day Cost Trend</h3>
        <p className="text-xs text-text-muted">
          Daily FizzBuck expenditure with budget target reference line
        </p>
      </CardHeader>
      <CardContent>
        <svg
          viewBox={`0 0 ${chartWidth} ${chartHeight}`}
          className="w-full h-auto"
        >
          {/* Y-axis grid lines and labels */}
          {yTicks.map((t, i) => (
            <g key={i}>
              <line
                x1={padding.left}
                y1={t.y}
                x2={chartWidth - padding.right}
                y2={t.y}
                stroke="#334155"
                strokeWidth={0.5}
              />
              <text
                x={padding.left - 8}
                y={t.y + 3}
                textAnchor="end"
                className="fill-text-muted text-[9px] font-mono"
              >
                {t.val >= 1000
                  ? `${(t.val / 1000).toFixed(1)}k`
                  : t.val.toFixed(0)}
              </text>
            </g>
          ))}

          {/* Budget target dashed line */}
          <line
            x1={padding.left}
            y1={budgetY}
            x2={chartWidth - padding.right}
            y2={budgetY}
            stroke="#f59e0b"
            strokeWidth={1}
            strokeDasharray="6 3"
            opacity={0.6}
          />
          <text
            x={chartWidth - padding.right + 2}
            y={budgetY - 4}
            className="fill-amber-400 text-[8px]"
          >
            Budget
          </text>

          {/* Cost line */}
          <path d={linePath} fill="none" stroke="#818cf8" strokeWidth={1.5} />

          {/* Data point dots */}
          {points.map((p, i) => (
            <circle
              key={i}
              cx={p.x}
              cy={p.y}
              r={2}
              fill="#818cf8"
              opacity={0.6}
            />
          ))}

          {/* X-axis labels */}
          {xLabels.map((d) => {
            const idx = data.indexOf(d);
            const x = padding.left + (idx / (data.length - 1)) * plotWidth;
            return (
              <text
                key={d.date}
                x={x}
                y={chartHeight - 8}
                textAnchor="middle"
                className="fill-text-muted text-[8px] font-mono"
              >
                {d.date.slice(5)}
              </text>
            );
          })}
        </svg>
      </CardContent>
    </Card>
  );
}

// ---------------------------------------------------------------------------
// Component: Invoice Generator
// ---------------------------------------------------------------------------

function InvoiceGenerator({
  onGenerate,
  invoice,
  loading,
}: {
  onGenerate: (period: string) => void;
  invoice: Invoice | null;
  loading: boolean;
}) {
  const periods = useMemo(() => getRecentPeriods(), []);
  const [selectedPeriod, setSelectedPeriod] = useState(periods[0]);

  return (
    <Card className="flex-1">
      <CardHeader>
        <h3 className="heading-section">Invoice Generator</h3>
        <p className="text-xs text-text-muted">
          Generate FizzBuck invoices with itemized subsystem cost attribution
        </p>
      </CardHeader>
      <CardContent className="space-y-4">
        {/* Controls */}
        <div className="flex items-center gap-3">
          <select
            value={selectedPeriod}
            onChange={(e) => setSelectedPeriod(e.target.value)}
            className="h-10 rounded bg-surface-overlay border border-border-default text-text-secondary text-sm px-3 focus:outline-none focus:ring-2 focus:ring-fizzbuzz-500"
          >
            {periods.map((p) => (
              <option key={p} value={p}>
                {p}
              </option>
            ))}
          </select>
          <Button
            variant="primary"
            size="sm"
            onClick={() => onGenerate(selectedPeriod)}
            disabled={loading}
          >
            {loading ? "Generating..." : "Generate Invoice"}
          </Button>
        </div>

        {/* Invoice Display */}
        {invoice && (
          <div className="border border-border-default rounded-lg p-4 bg-surface-base space-y-3">
            {/* Invoice Header */}
            <div className="flex items-start justify-between">
              <div>
                <p className="text-lg font-semibold text-text-primary font-mono">
                  {invoice.id}
                </p>
                <p className="text-xs text-text-secondary">
                  Period: {invoice.period}
                </p>
              </div>
              <Badge
                variant={
                  invoice.status === "paid"
                    ? "success"
                    : invoice.status === "overdue"
                      ? "error"
                      : "info"
                }
              >
                {invoice.status.toUpperCase()}
              </Badge>
            </div>

            {/* Line Items Table */}
            <div className="overflow-x-auto">
              <table className="w-full text-xs">
                <thead>
                  <tr className="border-b border-border-default text-text-secondary">
                    <th className="text-left py-1.5 pr-2">Description</th>
                    <th className="text-right py-1.5 px-2">Qty</th>
                    <th className="text-right py-1.5 px-2">Unit Cost</th>
                    <th className="text-right py-1.5 pl-2">Total</th>
                  </tr>
                </thead>
                <tbody>
                  {invoice.lines.map((line, i) => (
                    <tr
                      key={i}
                      className="border-b border-border-subtle/50 text-text-secondary"
                    >
                      <td className="py-1.5 pr-2">{line.description}</td>
                      <td className="text-right py-1.5 px-2 font-mono">
                        {line.quantity.toLocaleString()}
                      </td>
                      <td className="text-right py-1.5 px-2 font-mono">
                        {line.unitCost.toFixed(4)}
                      </td>
                      <td className="text-right py-1.5 pl-2 font-mono">
                        {formatFB(line.total)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {/* Totals */}
            <div className="border-t border-border-default pt-2 space-y-1">
              <div className="flex justify-between text-xs text-text-secondary">
                <span>Subtotal</span>
                <span className="font-mono">{formatFB(invoice.subtotal)}</span>
              </div>
              <div className="flex justify-between text-xs text-text-secondary">
                <span>FBVAT (7.5%)</span>
                <span className="font-mono">{formatFB(invoice.tax)}</span>
              </div>
              <div className="flex justify-between text-sm font-semibold text-text-primary">
                <span>Grand Total</span>
                <span className="font-mono">{formatFB(invoice.total)}</span>
              </div>
            </div>

            <p className="text-[10px] text-text-muted">
              Issued: {new Date(invoice.issuedAt).toLocaleString()}
            </p>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

// ---------------------------------------------------------------------------
// Main Page
// ---------------------------------------------------------------------------

export default function FinOpsPage() {
  const provider = useDataProvider();

  // State
  const [costBreakdown, setCostBreakdown] = useState<CostAllocation[]>([]);
  const [budgetStatuses, setBudgetStatuses] = useState<BudgetStatus[]>([]);
  const [exchangeRate, setExchangeRate] = useState<FizzBuckExchangeRate | null>(
    null,
  );
  const [costTrend, setCostTrend] = useState<DailyCostPoint[]>([]);
  const [costSummary, setCostSummary] = useState<CostSummary | null>(null);
  const [invoice, setInvoice] = useState<Invoice | null>(null);
  const [invoiceLoading, setInvoiceLoading] = useState(false);
  const [loading, setLoading] = useState(true);

  // Load all data on mount
  const loadData = useCallback(async () => {
    setLoading(true);
    try {
      const [breakdown, budgets, trend, summary] = await Promise.all([
        provider.getCostBreakdown(),
        provider.getBudgetStatus(),
        provider.getDailyCostTrend(),
        provider.getCostSummary(),
      ]);
      setCostBreakdown(breakdown);
      setBudgetStatuses(budgets);
      setCostTrend(trend);
      setCostSummary(summary);
    } finally {
      setLoading(false);
    }
  }, [provider]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  // Exchange rate polling at 5-second intervals
  useEffect(() => {
    let active = true;

    const fetchRate = async () => {
      try {
        const rate = await provider.getExchangeRateHistory();
        if (active) setExchangeRate(rate);
      } catch {
        // Telemetry gap — exchange rate unavailable
      }
    };

    fetchRate();
    const interval = setInterval(fetchRate, EXCHANGE_RATE_POLL_MS);
    return () => {
      active = false;
      clearInterval(interval);
    };
  }, [provider]);

  // Invoice generation handler
  const handleGenerateInvoice = useCallback(
    async (period: string) => {
      setInvoiceLoading(true);
      try {
        const inv = await provider.generateInvoice(period);
        setInvoice(inv);
      } finally {
        setInvoiceLoading(false);
      }
    },
    [provider],
  );

  return (
    <div className="space-y-6">
      {/* Page Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="heading-page">FinOps Billing Center</h1>
          <p className="text-sm text-text-secondary mt-1">
            FizzBuck cost governance, budget enforcement, and financial
            reporting
          </p>
        </div>
        <Button
          variant="secondary"
          size="sm"
          onClick={loadData}
          disabled={loading}
        >
          {loading ? "Refreshing..." : "Refresh"}
        </Button>
      </div>

      {/* Row 1 — KPI Summary Cards */}
      <KPISummaryCards
        costSummary={costSummary}
        costBreakdown={costBreakdown}
        exchangeRate={exchangeRate}
        budgetStatuses={budgetStatuses}
      />

      {/* Row 2 — Cost Treemap + Exchange Rate Ticker */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <div className="lg:col-span-2">
          <CostTreemap allocations={costBreakdown} />
        </div>
        <div className="lg:col-span-1">
          <ExchangeRateTicker exchangeRate={exchangeRate} />
        </div>
      </div>

      {/* Row 3 — Budget Progress Bars */}
      <BudgetProgressBars budgets={budgetStatuses} />

      {/* Row 4 — Cost Trend + Invoice Generator */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <CostTrendChart data={costTrend} />
        <InvoiceGenerator
          onGenerate={handleGenerateInvoice}
          invoice={invoice}
          loading={invoiceLoading}
        />
      </div>
    </div>
  );
}
