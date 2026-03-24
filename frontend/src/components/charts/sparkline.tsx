"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { useReducedMotion } from "@/lib/hooks/use-reduced-motion";

/**
 * Reusable SVG sparkline component with catmull-rom curve interpolation
 * and stroke-dashoffset drawing animation on mount.
 *
 * Renders a smooth curve with optional gradient fill area beneath.
 * On mount, the path animates from zero length to full via a
 * stroke-dashoffset transition (400ms), creating a drawing effect
 * that communicates data arrival. The endpoint receives a solid dot
 * (no pulse animation) to mark the most recent value.
 *
 * When `prefers-reduced-motion` is active, the path renders at full
 * length immediately without the drawing animation.
 */

interface SparklineProps {
  /** Ordered numeric values to plot. Minimum 2 points required. */
  data: number[];
  /** SVG viewport width in pixels. */
  width?: number;
  /** SVG viewport height in pixels. */
  height?: number;
  /** Stroke color. Accepts CSS custom properties. */
  color?: string;
  /** Whether to render a gradient fill beneath the curve. */
  showArea?: boolean;
}

/**
 * Generates a catmull-rom spline SVG path through the given points.
 * Uses centripetal parameterization (alpha=0.5) to avoid cusps.
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

export function Sparkline({
  data,
  width = 120,
  height = 32,
  color = "var(--fizzbuzz-400)",
  showArea = true,
}: SparklineProps) {
  const pathRef = useRef<SVGPathElement>(null);
  const prefersReduced = useReducedMotion();
  const [mounted, setMounted] = useState(false);
  const gradientId = useMemo(
    () => `sparkline-fill-${Math.random().toString(36).slice(2, 8)}`,
    [],
  );

  const { curvePath, areaPath, lastPoint } = useMemo(() => {
    if (data.length < 2) {
      return { curvePath: "", areaPath: "", lastPoint: null };
    }

    const min = Math.min(...data);
    const max = Math.max(...data);
    const range = max - min || 1;
    const padding = 2;

    const points = data.map((value, index) => ({
      x: (index / (data.length - 1)) * width,
      y: height - ((value - min) / range) * (height - padding * 2) - padding,
    }));

    const curve = catmullRomPath(points);
    const area = `${curve} L ${width},${height} L 0,${height} Z`;

    return {
      curvePath: curve,
      areaPath: area,
      lastPoint: points[points.length - 1],
    };
  }, [data, width, height]);

  // Drawing animation via stroke-dashoffset
  useEffect(() => {
    if (prefersReduced || !pathRef.current || !curvePath) {
      setMounted(true);
      return;
    }

    const path = pathRef.current;
    const length = path.getTotalLength();
    path.style.strokeDasharray = `${length}`;
    path.style.strokeDashoffset = `${length}`;

    // Trigger reflow to ensure the initial state is applied
    path.getBoundingClientRect();

    path.style.transition = "stroke-dashoffset 400ms ease-out";
    path.style.strokeDashoffset = "0";

    const timer = setTimeout(() => setMounted(true), 400);
    return () => clearTimeout(timer);
  }, [prefersReduced, curvePath]);

  if (!curvePath || !lastPoint) return null;

  return (
    <svg
      width={width}
      height={height}
      viewBox={`0 0 ${width} ${height}`}
      className="overflow-visible"
      aria-label="Metric sparkline"
    >
      {showArea && (
        <defs>
          <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={color} stopOpacity="0.25" />
            <stop offset="100%" stopColor={color} stopOpacity="0.02" />
          </linearGradient>
        </defs>
      )}
      {showArea && (
        <path
          d={areaPath}
          fill={`url(#${gradientId})`}
          style={{ opacity: mounted ? 1 : 0, transition: "opacity 200ms" }}
        />
      )}
      <path
        ref={pathRef}
        d={curvePath}
        fill="none"
        stroke={color}
        strokeWidth="1.5"
        strokeLinejoin="round"
        strokeLinecap="round"
      />
      {/* Solid endpoint dot — no pulse animation */}
      <circle
        cx={lastPoint.x}
        cy={lastPoint.y}
        r={2}
        fill={color}
        style={{
          opacity: mounted || prefersReduced ? 1 : 0,
          transition: prefersReduced ? "none" : "opacity 200ms ease-out 300ms",
        }}
      />
    </svg>
  );
}
