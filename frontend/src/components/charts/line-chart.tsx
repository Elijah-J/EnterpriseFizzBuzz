"use client";

import { useCallback, useMemo, useRef, useState } from "react";

/**
 * Full-featured SVG line chart with axes, auto-scaling, and hover tooltips.
 *
 * Designed for the primary metric visualization area in the Real-Time Metrics
 * Dashboard. Renders entirely in SVG with no external charting library
 * dependencies — maintaining the platform's zero-dependency policy for
 * visualization components until the D3 migration in Phase 4.
 */

interface LineChartProps {
  /** Ordered data points with timestamps and values. */
  data: { timestamp: number; value: number }[];
  /** SVG viewport width. Defaults to 100% of container via responsive wrapper. */
  width?: number;
  /** SVG viewport height. */
  height?: number;
  /** Line stroke color. */
  color?: string;
  /** Unit label for the Y-axis tooltip. */
  unit?: string;
  /** Metric name displayed in the tooltip header. */
  label?: string;
}

/** Formats a timestamp for the X-axis. Shows HH:MM:SS for sub-hour ranges. */
function formatTime(timestamp: number): string {
  const d = new Date(timestamp);
  return d.toLocaleTimeString([], {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
  });
}

/** Auto-scales Y-axis values to human-readable labels. */
function formatValue(value: number): string {
  if (value >= 1_000_000_000) return `${(value / 1_000_000_000).toFixed(1)}G`;
  if (value >= 1_000_000) return `${(value / 1_000_000).toFixed(1)}M`;
  if (value >= 1_000) return `${(value / 1_000).toFixed(1)}K`;
  if (value >= 1) return value.toFixed(1);
  if (value >= 0.001) return value.toFixed(3);
  return value.toExponential(2);
}

const MARGIN = { top: 16, right: 16, bottom: 32, left: 64 };

export function LineChart({
  data,
  width = 700,
  height = 300,
  color = "var(--fizzbuzz-400)",
  unit = "",
  label = "",
}: LineChartProps) {
  const svgRef = useRef<SVGSVGElement>(null);
  const [hoverIndex, setHoverIndex] = useState<number | null>(null);

  const plotWidth = width - MARGIN.left - MARGIN.right;
  const plotHeight = height - MARGIN.top - MARGIN.bottom;

  const { minVal, maxVal, minTime, maxTime, yTicks, xTicks } = useMemo(() => {
    if (data.length === 0) {
      return {
        minVal: 0,
        maxVal: 1,
        minTime: 0,
        maxTime: 1,
        yTicks: [0, 0.5, 1],
        xTicks: [] as number[],
      };
    }

    const values = data.map((d) => d.value);
    const times = data.map((d) => d.timestamp);
    let lo = Math.min(...values);
    let hi = Math.max(...values);

    // Add 10% padding to Y range
    const padding = (hi - lo) * 0.1 || hi * 0.1 || 1;
    lo = Math.max(0, lo - padding);
    hi = hi + padding;

    // Generate ~5 Y-axis ticks
    const yStep = (hi - lo) / 4;
    const yt = Array.from({ length: 5 }, (_, i) => lo + yStep * i);

    // Generate ~6 X-axis ticks
    const tMin = Math.min(...times);
    const tMax = Math.max(...times);
    const xStep = (tMax - tMin) / 5;
    const xt = Array.from({ length: 6 }, (_, i) => tMin + xStep * i);

    return { minVal: lo, maxVal: hi, minTime: tMin, maxTime: tMax, yTicks: yt, xTicks: xt };
  }, [data]);

  const toX = useCallback(
    (timestamp: number) => {
      const range = maxTime - minTime || 1;
      return MARGIN.left + ((timestamp - minTime) / range) * plotWidth;
    },
    [minTime, maxTime, plotWidth],
  );

  const toY = useCallback(
    (value: number) => {
      const range = maxVal - minVal || 1;
      return MARGIN.top + plotHeight - ((value - minVal) / range) * plotHeight;
    },
    [minVal, maxVal, plotHeight],
  );

  const polylinePoints = useMemo(() => {
    return data
      .map((d) => `${toX(d.timestamp).toFixed(1)},${toY(d.value).toFixed(1)}`)
      .join(" ");
  }, [data, toX, toY]);

  const areaPoints = useMemo(() => {
    if (data.length === 0) return "";
    const first = toX(data[0].timestamp);
    const last = toX(data[data.length - 1].timestamp);
    const bottom = MARGIN.top + plotHeight;
    return `${first},${bottom} ${polylinePoints} ${last},${bottom}`;
  }, [data, polylinePoints, toX, plotHeight]);

  const gradientId = `line-chart-fill-${useMemo(() => Math.random().toString(36).slice(2, 8), [])}`;

  const handleMouseMove = useCallback(
    (e: React.MouseEvent<SVGSVGElement>) => {
      if (data.length === 0 || !svgRef.current) return;
      const rect = svgRef.current.getBoundingClientRect();
      const mouseX = e.clientX - rect.left;
      const relX = mouseX - MARGIN.left;
      const fraction = relX / plotWidth;
      const idx = Math.round(fraction * (data.length - 1));
      setHoverIndex(Math.max(0, Math.min(data.length - 1, idx)));
    },
    [data, plotWidth],
  );

  const handleMouseLeave = useCallback(() => {
    setHoverIndex(null);
  }, []);

  if (data.length === 0) {
    return (
      <div
        className="flex items-center justify-center text-xs text-panel-500"
        style={{ width, height }}
      >
        No data available for the selected time range
      </div>
    );
  }

  const hoverPoint = hoverIndex !== null ? data[hoverIndex] : null;

  return (
    <svg
      ref={svgRef}
      width="100%"
      height={height}
      viewBox={`0 0 ${width} ${height}`}
      preserveAspectRatio="xMidYMid meet"
      className="overflow-visible"
      onMouseMove={handleMouseMove}
      onMouseLeave={handleMouseLeave}
    >
      <defs>
        <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={color} stopOpacity="0.15" />
          <stop offset="100%" stopColor={color} stopOpacity="0.01" />
        </linearGradient>
      </defs>

      {/* Grid lines */}
      {yTicks.map((tick, i) => (
        <line
          key={`y-grid-${i}`}
          x1={MARGIN.left}
          x2={width - MARGIN.right}
          y1={toY(tick)}
          y2={toY(tick)}
          stroke="var(--panel-700)"
          strokeWidth="0.5"
        />
      ))}

      {/* Y-axis labels */}
      {yTicks.map((tick, i) => (
        <text
          key={`y-label-${i}`}
          x={MARGIN.left - 8}
          y={toY(tick)}
          textAnchor="end"
          dominantBaseline="middle"
          className="text-[10px] fill-panel-500"
        >
          {formatValue(tick)}
        </text>
      ))}

      {/* X-axis labels */}
      {xTicks.map((tick, i) => (
        <text
          key={`x-label-${i}`}
          x={toX(tick)}
          y={height - 6}
          textAnchor="middle"
          className="text-[10px] fill-panel-500"
        >
          {formatTime(tick)}
        </text>
      ))}

      {/* Area fill */}
      <polygon points={areaPoints} fill={`url(#${gradientId})`} />

      {/* Data line */}
      <polyline
        points={polylinePoints}
        fill="none"
        stroke={color}
        strokeWidth="1.5"
        strokeLinejoin="round"
        strokeLinecap="round"
      />

      {/* Hover crosshair and tooltip */}
      {hoverPoint && hoverIndex !== null && (
        <>
          <line
            x1={toX(hoverPoint.timestamp)}
            x2={toX(hoverPoint.timestamp)}
            y1={MARGIN.top}
            y2={MARGIN.top + plotHeight}
            stroke="var(--panel-500)"
            strokeWidth="0.5"
            strokeDasharray="3,3"
          />
          <circle
            cx={toX(hoverPoint.timestamp)}
            cy={toY(hoverPoint.value)}
            r={4}
            fill={color}
            stroke="var(--panel-900)"
            strokeWidth="2"
          />
          {/* Tooltip background */}
          <rect
            x={Math.min(toX(hoverPoint.timestamp) + 8, width - MARGIN.right - 160)}
            y={Math.max(MARGIN.top, toY(hoverPoint.value) - 36)}
            width={150}
            height={36}
            rx={4}
            fill="var(--panel-800)"
            stroke="var(--panel-600)"
            strokeWidth="0.5"
          />
          <text
            x={Math.min(toX(hoverPoint.timestamp) + 16, width - MARGIN.right - 152) + 0}
            y={Math.max(MARGIN.top, toY(hoverPoint.value) - 36) + 14}
            className="text-[10px] fill-panel-400"
          >
            {label ? `${label} @ ` : ""}{formatTime(hoverPoint.timestamp)}
          </text>
          <text
            x={Math.min(toX(hoverPoint.timestamp) + 16, width - MARGIN.right - 152) + 0}
            y={Math.max(MARGIN.top, toY(hoverPoint.value) - 36) + 28}
            className="text-[11px] fill-panel-50 font-mono font-semibold"
          >
            {formatValue(hoverPoint.value)} {unit}
          </text>
        </>
      )}
    </svg>
  );
}
