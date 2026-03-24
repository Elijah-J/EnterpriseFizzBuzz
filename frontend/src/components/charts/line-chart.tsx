"use client";

import { useCallback, useMemo, useRef, useState } from "react";
import { ZoomBrush } from "./zoom-brush";

/**
 * Full-featured SVG line chart with catmull-rom spline interpolation,
 * auto-scaling axes, warm gradient fill, and hover crosshair tooltips.
 *
 * The catmull-rom algorithm generates smooth curves through data points
 * without the angular artifacts of polyline rendering. The warm gradient
 * fill beneath the curve uses the domain color at 15% opacity, fading
 * to transparent at the baseline — providing area context without
 * competing with the stroke for visual attention.
 *
 * Designed for the primary metric visualization area in the Real-Time
 * Metrics Dashboard. Renders entirely in SVG with no external charting
 * library dependencies.
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
  /** When true, renders a draggable zoom brush at the bottom of the chart. */
  zoomable?: boolean;
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

/**
 * Generates a cubic bezier SVG path string using catmull-rom spline
 * interpolation. The algorithm computes control points from each set
 * of four consecutive points, producing C1-continuous curves that pass
 * through every data point.
 *
 * The tension parameter (alpha) controls curve tightness: 0.5 produces
 * centripetal catmull-rom splines, which avoid cusps and self-intersection.
 */
function catmullRomPath(
  points: { x: number; y: number }[],
  alpha = 0.5,
): string {
  if (points.length < 2) return "";
  if (points.length === 2) {
    return `M ${points[0].x},${points[0].y} L ${points[1].x},${points[1].y}`;
  }

  let d = `M ${points[0].x},${points[0].y}`;

  for (let i = 0; i < points.length - 1; i++) {
    const p0 = points[Math.max(0, i - 1)];
    const p1 = points[i];
    const p2 = points[i + 1];
    const p3 = points[Math.min(points.length - 1, i + 2)];

    const d1 = Math.hypot(p2.x - p1.x, p2.y - p1.y);
    const d0 = Math.hypot(p1.x - p0.x, p1.y - p0.y);
    const d2 = Math.hypot(p3.x - p2.x, p3.y - p2.y);

    const a = d0 ** (2 * alpha);
    const b = d1 ** (2 * alpha);
    const c = d2 ** (2 * alpha);

    const denom1 = 2 * a + 3 * Math.sqrt(a) * Math.sqrt(b) + b;
    const denom2 = 2 * c + 3 * Math.sqrt(c) * Math.sqrt(b) + b;

    let cp1x: number;
    let cp1y: number;
    let cp2x: number;
    let cp2y: number;

    if (denom1 > 0) {
      cp1x =
        (b * p0.x - a * p2.x + (2 * a + 3 * Math.sqrt(a * b)) * p1.x) / denom1;
      cp1y =
        (b * p0.y - a * p2.y + (2 * a + 3 * Math.sqrt(a * b)) * p1.y) / denom1;
    } else {
      cp1x = p1.x;
      cp1y = p1.y;
    }

    if (denom2 > 0) {
      cp2x =
        (b * p3.x - c * p2.x + (2 * c + 3 * Math.sqrt(c * b)) * p2.x) / denom2;
      cp2y =
        (b * p3.y - c * p2.y + (2 * c + 3 * Math.sqrt(c * b)) * p2.y) / denom2;
    } else {
      cp2x = p2.x;
      cp2y = p2.y;
    }

    d += ` C ${cp1x.toFixed(1)},${cp1y.toFixed(1)} ${cp2x.toFixed(1)},${cp2y.toFixed(1)} ${p2.x.toFixed(1)},${p2.y.toFixed(1)}`;
  }

  return d;
}

const MARGIN = { top: 16, right: 16, bottom: 32, left: 64 };

export function LineChart({
  data,
  width = 700,
  height = 300,
  color = "var(--fizzbuzz-400)",
  unit = "",
  label = "",
  zoomable = false,
}: LineChartProps) {
  const svgRef = useRef<SVGSVGElement>(null);
  const [hoverIndex, setHoverIndex] = useState<number | null>(null);
  const [zoomRange, setZoomRange] = useState<[number, number] | null>(null);

  const handleZoom = useCallback(
    (start: number, end: number) => {
      const startIdx = Math.floor(start * (data.length - 1));
      const endIdx = Math.ceil(end * (data.length - 1));
      if (endIdx > startIdx) {
        setZoomRange([startIdx, endIdx]);
      }
    },
    [data.length],
  );

  const handleZoomReset = useCallback(() => {
    setZoomRange(null);
  }, []);

  // Apply zoom filter to data
  const visibleData = useMemo(() => {
    if (!zoomRange) return data;
    return data.slice(zoomRange[0], zoomRange[1] + 1);
  }, [data, zoomRange]);

  const plotWidth = width - MARGIN.left - MARGIN.right;
  const plotHeight = height - MARGIN.top - MARGIN.bottom;

  const { minVal, maxVal, minTime, maxTime, yTicks, xTicks } = useMemo(() => {
    if (visibleData.length === 0) {
      return {
        minVal: 0,
        maxVal: 1,
        minTime: 0,
        maxTime: 1,
        yTicks: [0, 0.5, 1],
        xTicks: [] as number[],
      };
    }

    const values = visibleData.map((d) => d.value);
    const times = visibleData.map((d) => d.timestamp);
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

    return {
      minVal: lo,
      maxVal: hi,
      minTime: tMin,
      maxTime: tMax,
      yTicks: yt,
      xTicks: xt,
    };
  }, [visibleData]);

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

  const dataPoints = useMemo(
    () => visibleData.map((d) => ({ x: toX(d.timestamp), y: toY(d.value) })),
    [visibleData, toX, toY],
  );

  const curvePath = useMemo(() => catmullRomPath(dataPoints), [dataPoints]);

  const areaPath = useMemo(() => {
    if (dataPoints.length === 0) return "";
    const bottom = MARGIN.top + plotHeight;
    const first = dataPoints[0];
    const last = dataPoints[dataPoints.length - 1];
    return `${curvePath} L ${last.x.toFixed(1)},${bottom} L ${first.x.toFixed(1)},${bottom} Z`;
  }, [curvePath, dataPoints, plotHeight]);

  const gradientId = useMemo(
    () => `line-chart-fill-${Math.random().toString(36).slice(2, 8)}`,
    [],
  );

  const handleMouseMove = useCallback(
    (e: React.MouseEvent<SVGSVGElement>) => {
      if (visibleData.length === 0 || !svgRef.current) return;
      const rect = svgRef.current.getBoundingClientRect();
      const mouseX = e.clientX - rect.left;
      const relX = mouseX - MARGIN.left;
      const fraction = relX / plotWidth;
      const idx = Math.round(fraction * (visibleData.length - 1));
      setHoverIndex(Math.max(0, Math.min(visibleData.length - 1, idx)));
    },
    [visibleData, plotWidth],
  );

  const handleMouseLeave = useCallback(() => {
    setHoverIndex(null);
  }, []);

  if (visibleData.length === 0) {
    return (
      <div
        className="flex items-center justify-center text-xs text-text-muted"
        style={{ width, height }}
      >
        No data available for the selected time range
      </div>
    );
  }

  const hoverPoint = hoverIndex !== null ? visibleData[hoverIndex] : null;

  return (
    <svg
      ref={svgRef}
      width="100%"
      height={height}
      viewBox={`0 0 ${width} ${height}`}
      preserveAspectRatio="xMidYMid meet"
      className="overflow-visible"
      role="img"
      aria-label={`Line chart${label ? ` for ${label}` : ""}`}
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
      {yTicks.map((tick) => (
        <line
          key={`y-grid-${tick}`}
          x1={MARGIN.left}
          x2={width - MARGIN.right}
          y1={toY(tick)}
          y2={toY(tick)}
          stroke="var(--border-subtle)"
          strokeWidth="0.5"
        />
      ))}

      {/* Y-axis labels */}
      {yTicks.map((tick) => (
        <text
          key={`y-label-${tick}`}
          x={MARGIN.left - 8}
          y={toY(tick)}
          textAnchor="end"
          dominantBaseline="middle"
          className="text-[10px] fill-text-muted"
        >
          {formatValue(tick)}
        </text>
      ))}

      {/* X-axis labels */}
      {xTicks.map((tick) => (
        <text
          key={`x-label-${tick}`}
          x={toX(tick)}
          y={height - 6}
          textAnchor="middle"
          className="text-[10px] fill-text-muted"
        >
          {formatTime(tick)}
        </text>
      ))}

      {/* Area fill with warm gradient */}
      <path d={areaPath} fill={`url(#${gradientId})`} />

      {/* Smooth data line — catmull-rom spline interpolation */}
      <path
        d={curvePath}
        fill="none"
        stroke={color}
        strokeWidth="1.5"
        strokeLinejoin="round"
        strokeLinecap="round"
        className="transition-[d] duration-300 ease-out"
      />

      {/* Hover crosshair and tooltip */}
      {hoverPoint && hoverIndex !== null && (
        <>
          {/* Crosshair — thin stone-500 vertical line */}
          <line
            x1={toX(hoverPoint.timestamp)}
            x2={toX(hoverPoint.timestamp)}
            y1={MARGIN.top}
            y2={MARGIN.top + plotHeight}
            stroke="var(--text-muted)"
            strokeWidth="0.5"
          />
          <circle
            cx={toX(hoverPoint.timestamp)}
            cy={toY(hoverPoint.value)}
            r={4}
            fill={color}
            stroke="var(--surface-base)"
            strokeWidth="2"
          />
          {/* Tooltip — warm surface, no blur */}
          <rect
            x={Math.min(
              toX(hoverPoint.timestamp) + 8,
              width - MARGIN.right - 160,
            )}
            y={Math.max(MARGIN.top, toY(hoverPoint.value) - 36)}
            width={150}
            height={36}
            rx={4}
            fill="var(--surface-raised)"
            stroke="var(--border-default)"
            strokeWidth="0.5"
          />
          <text
            x={
              Math.min(
                toX(hoverPoint.timestamp) + 16,
                width - MARGIN.right - 152,
              ) + 0
            }
            y={Math.max(MARGIN.top, toY(hoverPoint.value) - 36) + 14}
            className="text-[10px] fill-text-secondary"
          >
            {label ? `${label} @ ` : ""}
            {formatTime(hoverPoint.timestamp)}
          </text>
          <text
            x={
              Math.min(
                toX(hoverPoint.timestamp) + 16,
                width - MARGIN.right - 152,
              ) + 0
            }
            y={Math.max(MARGIN.top, toY(hoverPoint.value) - 36) + 28}
            className="text-[11px] fill-text-primary font-mono font-semibold"
          >
            {formatValue(hoverPoint.value)} {unit}
          </text>
        </>
      )}

      {/* Zoom brush — drag-to-select time range */}
      {zoomable && (
        <ZoomBrush
          width={plotWidth}
          y={MARGIN.top + plotHeight - 20}
          height={20}
          marginLeft={MARGIN.left}
          onZoom={handleZoom}
          onReset={handleZoomReset}
        />
      )}
    </svg>
  );
}
