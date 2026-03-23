"use client";

import { useMemo, useState } from "react";

/**
 * SVG donut chart for visualizing proportional distributions.
 *
 * Renders arc segments from cumulative proportions using SVG path
 * arc commands. Designed for the Analytics & Intelligence page to
 * display FizzBuzz classification distributions with interactive
 * hover state and center summary text.
 *
 * Pure SVG implementation — no external charting dependencies.
 */

interface DonutChartProps {
  /** Segments to render, ordered clockwise from 12 o'clock. */
  segments: {
    label: string;
    value: number;
    color: string;
  }[];
  /** Outer diameter in pixels. Default 280. */
  size?: number;
  /** Donut ring thickness as fraction of radius (0..1). Default 0.35. */
  thickness?: number;
  /** Primary text displayed in the center of the donut. */
  centerLabel?: string;
  /** Secondary text displayed below the center label. */
  centerSubLabel?: string;
}

/**
 * Converts polar coordinates to Cartesian for SVG arc endpoint computation.
 */
function polarToCartesian(
  cx: number,
  cy: number,
  radius: number,
  angleRad: number,
): { x: number; y: number } {
  return {
    x: cx + radius * Math.cos(angleRad),
    y: cy + radius * Math.sin(angleRad),
  };
}

/**
 * Generates an SVG path `d` attribute for a donut arc segment.
 * Uses the large-arc-flag to handle arcs greater than 180 degrees.
 */
function describeArc(
  cx: number,
  cy: number,
  outerRadius: number,
  innerRadius: number,
  startAngle: number,
  endAngle: number,
): string {
  const outerStart = polarToCartesian(cx, cy, outerRadius, startAngle);
  const outerEnd = polarToCartesian(cx, cy, outerRadius, endAngle);
  const innerStart = polarToCartesian(cx, cy, innerRadius, endAngle);
  const innerEnd = polarToCartesian(cx, cy, innerRadius, startAngle);

  const largeArc = endAngle - startAngle > Math.PI ? 1 : 0;

  return [
    `M ${outerStart.x} ${outerStart.y}`,
    `A ${outerRadius} ${outerRadius} 0 ${largeArc} 1 ${outerEnd.x} ${outerEnd.y}`,
    `L ${innerStart.x} ${innerStart.y}`,
    `A ${innerRadius} ${innerRadius} 0 ${largeArc} 0 ${innerEnd.x} ${innerEnd.y}`,
    "Z",
  ].join(" ");
}

export function DonutChart({
  segments,
  size = 280,
  thickness = 0.35,
  centerLabel,
  centerSubLabel,
}: DonutChartProps) {
  const [hoveredIndex, setHoveredIndex] = useState<number | null>(null);

  const cx = size / 2;
  const cy = size / 2;
  const outerRadius = size / 2 - 8; // Leave margin for hover expansion
  const innerRadius = outerRadius * (1 - thickness);

  const total = useMemo(
    () => segments.reduce((sum, s) => sum + s.value, 0),
    [segments],
  );

  const arcs = useMemo(() => {
    const result: {
      path: string;
      midAngle: number;
      startAngle: number;
      endAngle: number;
      segment: (typeof segments)[number];
      index: number;
    }[] = [];

    // Start from -90 degrees (12 o'clock position)
    let cumulative = -Math.PI / 2;

    segments.forEach((segment, index) => {
      if (segment.value === 0) return;

      const fraction = total > 0 ? segment.value / total : 0;
      const sweepAngle = fraction * 2 * Math.PI;
      const startAngle = cumulative;
      const endAngle = cumulative + sweepAngle;
      const midAngle = (startAngle + endAngle) / 2;

      // Prevent rendering a full circle as a zero-length arc
      const adjustedEnd =
        sweepAngle >= 2 * Math.PI - 0.001 ? endAngle - 0.001 : endAngle;

      result.push({
        path: describeArc(cx, cy, outerRadius, innerRadius, startAngle, adjustedEnd),
        midAngle,
        startAngle,
        endAngle,
        segment,
        index,
      });

      cumulative = endAngle;
    });

    return result;
  }, [segments, total, cx, cy, outerRadius, innerRadius]);

  const hoveredArc = hoveredIndex !== null ? arcs.find((a) => a.index === hoveredIndex) : null;

  return (
    <svg
      width="100%"
      height={size}
      viewBox={`0 0 ${size} ${size}`}
      preserveAspectRatio="xMidYMid meet"
      className="overflow-visible"
    >
      {/* Arc segments */}
      {arcs.map((arc) => {
        const isHovered = arc.index === hoveredIndex;
        // On hover, translate the segment 6px outward along its bisector
        const dx = isHovered ? 6 * Math.cos(arc.midAngle) : 0;
        const dy = isHovered ? 6 * Math.sin(arc.midAngle) : 0;

        return (
          <path
            key={arc.index}
            d={arc.path}
            fill={arc.segment.color}
            opacity={hoveredIndex !== null && !isHovered ? 0.6 : 1}
            transform={`translate(${dx}, ${dy})`}
            className="transition-transform duration-200"
            onMouseEnter={() => setHoveredIndex(arc.index)}
            onMouseLeave={() => setHoveredIndex(null)}
            style={{ cursor: "pointer" }}
          />
        );
      })}

      {/* Center text */}
      {centerLabel && (
        <text
          x={cx}
          y={centerSubLabel ? cy - 8 : cy}
          textAnchor="middle"
          dominantBaseline="central"
          className="text-2xl font-bold fill-panel-50"
        >
          {centerLabel}
        </text>
      )}
      {centerSubLabel && (
        <text
          x={cx}
          y={cy + 14}
          textAnchor="middle"
          dominantBaseline="central"
          className="text-xs fill-panel-400"
        >
          {centerSubLabel}
        </text>
      )}

      {/* Hover tooltip */}
      {hoveredArc && (
        (() => {
          const tooltipX = cx + (outerRadius + 16) * Math.cos(hoveredArc.midAngle);
          const tooltipY = cy + (outerRadius + 16) * Math.sin(hoveredArc.midAngle);
          const rectW = 140;
          const rectH = 52;
          // Clamp tooltip within SVG bounds
          const clampedX = Math.max(4, Math.min(size - rectW - 4, tooltipX - rectW / 2));
          const clampedY = Math.max(4, Math.min(size - rectH - 4, tooltipY - rectH / 2));
          const percentage = total > 0
            ? ((hoveredArc.segment.value / total) * 100).toFixed(2)
            : "0.00";

          return (
            <g>
              <rect
                x={clampedX}
                y={clampedY}
                width={rectW}
                height={rectH}
                rx={4}
                fill="var(--panel-800)"
                stroke="var(--panel-600)"
                strokeWidth="0.5"
              />
              <text
                x={clampedX + 8}
                y={clampedY + 16}
                className="text-[11px] font-semibold fill-panel-50"
              >
                {hoveredArc.segment.label}
              </text>
              <text
                x={clampedX + 8}
                y={clampedY + 32}
                className="text-[10px] fill-panel-400"
              >
                Count: {hoveredArc.segment.value}
              </text>
              <text
                x={clampedX + 8}
                y={clampedY + 44}
                className="text-[10px] fill-panel-400"
              >
                {percentage}%
              </text>
            </g>
          );
        })()
      )}
    </svg>
  );
}
