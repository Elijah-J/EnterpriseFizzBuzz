"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useReducedMotion } from "@/lib/hooks/use-reduced-motion";
import { ChartLegend, type ChartLegendItem } from "./chart-legend";

/**
 * SVG donut chart with sweep-from-zero entrance animation and
 * desaturated domain colors.
 *
 * On mount, arc segments animate from zero sweep angle to their final
 * proportional angle, creating a clockwise reveal from 12 o'clock.
 * Hover state applies a slight opacity increase on the active segment
 * and reduces non-active segments — no glow, no scale transforms.
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
  const [explodedIndex, setExplodedIndex] = useState<number | null>(null);
  const [animationProgress, setAnimationProgress] = useState(0);
  const prefersReduced = useReducedMotion();

  const handleSegmentClick = useCallback((index: number) => {
    setExplodedIndex((prev) => (prev === index ? null : index));
  }, []);

  const cx = size / 2;
  const cy = size / 2;
  const outerRadius = size / 2 - 8;
  const innerRadius = outerRadius * (1 - thickness);

  const total = useMemo(
    () => segments.reduce((sum, s) => sum + s.value, 0),
    [segments],
  );

  // Sweep-from-zero entrance animation
  useEffect(() => {
    if (prefersReduced) {
      setAnimationProgress(1);
      return;
    }

    setAnimationProgress(0);
    const startTime = performance.now();
    const duration = 600;
    let frameId: number;

    const animate = (now: number) => {
      const elapsed = now - startTime;
      const t = Math.min(elapsed / duration, 1);
      // Ease-out cubic
      const eased = 1 - (1 - t) ** 3;
      setAnimationProgress(eased);
      if (t < 1) {
        frameId = requestAnimationFrame(animate);
      }
    };

    frameId = requestAnimationFrame(animate);
    return () => cancelAnimationFrame(frameId);
  }, [prefersReduced]);

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
      const sweepAngle = fraction * 2 * Math.PI * animationProgress;
      const startAngle = cumulative;
      const endAngle = cumulative + sweepAngle;
      const midAngle = (startAngle + endAngle) / 2;

      // Prevent rendering a full circle as a zero-length arc
      const adjustedEnd =
        sweepAngle >= 2 * Math.PI - 0.001 ? endAngle - 0.001 : endAngle;

      if (sweepAngle > 0.001) {
        result.push({
          path: describeArc(
            cx,
            cy,
            outerRadius,
            innerRadius,
            startAngle,
            adjustedEnd,
          ),
          midAngle,
          startAngle,
          endAngle,
          segment,
          index,
        });
      }

      // Advance cumulative by full fraction regardless of animation
      cumulative += fraction * 2 * Math.PI * animationProgress;
    });

    return result;
  }, [segments, total, cx, cy, outerRadius, innerRadius, animationProgress]);

  const hoveredArc =
    hoveredIndex !== null ? arcs.find((a) => a.index === hoveredIndex) : null;

  return (
    <>
    <svg
      width="100%"
      height={size}
      viewBox={`0 0 ${size} ${size}`}
      preserveAspectRatio="xMidYMid meet"
      className="overflow-visible"
      role="img"
      aria-label="Donut chart showing proportional distribution"
    >
      {/* Arc segments — desaturated domain colors with explode-on-click */}
      {arcs.map((arc) => {
        const isExploded = explodedIndex === arc.index;
        const explodeOffset = isExploded ? 8 : 0;
        const tx = explodeOffset * Math.cos(arc.midAngle);
        const ty = explodeOffset * Math.sin(arc.midAngle);

        return (
          <path
            key={arc.index}
            d={arc.path}
            fill={arc.segment.color}
            opacity={
              hoveredIndex !== null && arc.index !== hoveredIndex ? 0.5 : 0.85
            }
            className="transition-[opacity,transform] duration-200"
            transform={`translate(${tx.toFixed(1)}, ${ty.toFixed(1)})`}
            onMouseEnter={() => setHoveredIndex(arc.index)}
            onMouseLeave={() => setHoveredIndex(null)}
            onClick={() => handleSegmentClick(arc.index)}
            aria-label={arc.segment.label}
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
          className="text-2xl font-bold fill-text-primary"
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
          className="text-xs fill-text-secondary"
        >
          {centerSubLabel}
        </text>
      )}

      {/* Hover tooltip */}
      {hoveredArc &&
        (() => {
          const tooltipX =
            cx + (outerRadius + 16) * Math.cos(hoveredArc.midAngle);
          const tooltipY =
            cy + (outerRadius + 16) * Math.sin(hoveredArc.midAngle);
          const rectW = 140;
          const rectH = 52;
          const clampedX = Math.max(
            4,
            Math.min(size - rectW - 4, tooltipX - rectW / 2),
          );
          const clampedY = Math.max(
            4,
            Math.min(size - rectH - 4, tooltipY - rectH / 2),
          );
          const percentage =
            total > 0
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
                fill="var(--surface-raised)"
                stroke="var(--border-default)"
                strokeWidth="0.5"
              />
              <text
                x={clampedX + 8}
                y={clampedY + 16}
                className="text-[11px] font-semibold fill-text-primary"
              >
                {hoveredArc.segment.label}
              </text>
              <text
                x={clampedX + 8}
                y={clampedY + 32}
                className="text-[10px] fill-text-secondary"
              >
                Count: {hoveredArc.segment.value}
              </text>
              <text
                x={clampedX + 8}
                y={clampedY + 44}
                className="text-[10px] fill-text-secondary"
              >
                {percentage}%
              </text>
            </g>
          );
        })()}
    </svg>

    {/* Legend below chart */}
    <div className="mt-3 flex justify-center">
      <ChartLegend
        items={segments.map((s, i): ChartLegendItem => ({
          key: String(i),
          label: s.label,
          color: s.color,
          active: true,
        }))}
        orientation="horizontal"
        highlightedKey={hoveredIndex !== null ? String(hoveredIndex) : null}
        onHighlight={(key) =>
          setHoveredIndex(key !== null ? Number(key) : null)
        }
      />
    </div>
    </>
  );
}
