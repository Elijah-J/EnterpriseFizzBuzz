"use client";

import { useEffect, useRef } from "react";
import { AnimatedNumber } from "@/components/ui/animated-number";
import { useReducedMotion } from "@/lib/hooks/use-reduced-motion";

/**
 * Circular gauge component for percentage-based metrics (0-100%).
 *
 * The gauge color transitions from desaturated green through amber to
 * red as the value approaches critical thresholds. Background arcs
 * indicate threshold zones with desaturated fills, providing context
 * for the current reading against operational boundaries.
 *
 * The value arc animates via stroke-dashoffset (300ms) and the center
 * displays an AnimatedNumber with spring interpolation. No glow filters
 * are applied — depth comes from the stroke layering alone.
 *
 * Used primarily for SLA error budget remaining, compliance audit scores,
 * and cache hit ratio visualization where percentage context is essential.
 */

interface MetricGaugeProps {
  /** Value to display, clamped to 0-100. */
  value: number;
  /** Diameter of the gauge in pixels. */
  size?: number;
  /** Stroke width of the gauge arc. */
  strokeWidth?: number;
  /** Label displayed below the percentage. */
  label?: string;
  /** If true, lower values are considered better (inverts color mapping). */
  invertColor?: boolean;
}

function getGaugeColor(value: number, invert: boolean): string {
  const v = invert ? 100 - value : value;
  if (v >= 80) return "var(--fizz-400)";
  if (v >= 50) return "var(--fizzbuzz-gold, #f59e0b)";
  return "#ef4444";
}

/**
 * Threshold zone definitions for background arc segments.
 * Each zone represents an operational severity band with
 * a desaturated fill color.
 */
const THRESHOLD_ZONES = [
  { start: 0, end: 50, color: "rgba(239, 68, 68, 0.08)" },
  { start: 50, end: 80, color: "rgba(245, 158, 11, 0.08)" },
  { start: 80, end: 100, color: "rgba(74, 222, 128, 0.08)" },
];

export function MetricGauge({
  value,
  size = 96,
  strokeWidth = 8,
  label,
  invertColor = false,
}: MetricGaugeProps) {
  const circleRef = useRef<SVGCircleElement>(null);
  const prefersReduced = useReducedMotion();
  const clamped = Math.max(0, Math.min(100, value));
  const radius = (size - strokeWidth) / 2;
  const circumference = 2 * Math.PI * radius;
  const dashOffset = circumference * (1 - clamped / 100);
  const color = getGaugeColor(clamped, invertColor);
  const center = size / 2;

  // Animate strokeDashoffset on value change
  useEffect(() => {
    if (prefersReduced || !circleRef.current) return;
    const circle = circleRef.current;
    circle.style.transition = "stroke-dashoffset 300ms ease-out";
  }, [prefersReduced]);

  return (
    <div className="flex flex-col items-center gap-1">
      <svg
        width={size}
        height={size}
        viewBox={`0 0 ${size} ${size}`}
        role="img"
        aria-label={`Gauge showing ${clamped.toFixed(1)}%${label ? ` for ${label}` : ""}`}
      >
        {/* Background track */}
        <circle
          cx={center}
          cy={center}
          r={radius}
          fill="none"
          stroke="var(--border-subtle)"
          strokeWidth={strokeWidth}
        />

        {/* Threshold zone background arcs */}
        {THRESHOLD_ZONES.map((zone) => {
          const startOffset = circumference * (1 - zone.start / 100);
          const endOffset = circumference * (1 - zone.end / 100);
          const zoneDash = startOffset - endOffset;

          return (
            <circle
              key={`zone-${zone.start}`}
              cx={center}
              cy={center}
              r={radius}
              fill="none"
              stroke={zone.color}
              strokeWidth={strokeWidth + 4}
              strokeDasharray={`${zoneDash} ${circumference - zoneDash}`}
              strokeDashoffset={startOffset}
              transform={`rotate(-90 ${center} ${center})`}
            />
          );
        })}

        {/* Value arc — animated stroke-dashoffset */}
        <circle
          ref={circleRef}
          cx={center}
          cy={center}
          r={radius}
          fill="none"
          stroke={color}
          strokeWidth={strokeWidth}
          strokeDasharray={circumference}
          strokeDashoffset={dashOffset}
          strokeLinecap="round"
          transform={`rotate(-90 ${center} ${center})`}
        />

        {/* Center value — AnimatedNumber rendered via foreignObject */}
        <foreignObject
          x={center - size * 0.35}
          y={center - 10}
          width={size * 0.7}
          height={20}
        >
          <div className="flex items-center justify-center w-full h-full">
            <AnimatedNumber
              value={clamped}
              decimals={1}
              duration={300}
              className="text-sm font-mono font-semibold text-text-primary"
            />
            <span className="text-sm font-mono font-semibold text-text-primary">
              %
            </span>
          </div>
        </foreignObject>
      </svg>
      {label && (
        <span className="text-[10px] text-text-secondary text-center leading-tight">
          {label}
        </span>
      )}
    </div>
  );
}
