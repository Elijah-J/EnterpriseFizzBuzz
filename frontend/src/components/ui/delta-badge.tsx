"use client";

import { useEffect, useRef, useState } from "react";
import { useReducedMotion } from "@/lib/hooks/use-reduced-motion";

interface DeltaBadgeProps {
  /** The percentage change value. Positive = increase, negative = decrease. */
  value: number;
  /** Number of decimal places. Default: 1 */
  decimals?: number;
}

/**
 * Inline value change indicator for the Enterprise FizzBuzz Operations Center.
 *
 * Renders a directional arrow (up/down) with the percentage delta, colored
 * in desaturated green (increase) or desaturated red (decrease). A subtle
 * scale-up animation triggers on each value refresh to draw operator
 * attention to changing metrics without requiring full-screen alerts.
 *
 * The animation is suppressed when reduced-motion preferences are active.
 */
export function DeltaBadge({ value, decimals = 1 }: DeltaBadgeProps) {
  const reducedMotion = useReducedMotion();
  const [animating, setAnimating] = useState(false);
  const prevValue = useRef(value);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    if (prevValue.current !== value && !reducedMotion) {
      setAnimating(true);
      if (timer.current) clearTimeout(timer.current);
      timer.current = setTimeout(() => setAnimating(false), 300);
    }
    prevValue.current = value;
  }, [value, reducedMotion]);

  const isPositive = value >= 0;
  const arrow = isPositive ? "\u25B2" : "\u25BC";
  const colorClass = isPositive ? "text-fizz-400" : "text-[var(--status-error)]";

  return (
    <span
      className={`inline-flex items-center gap-0.5 text-xs font-medium ${colorClass} transition-transform duration-300`}
      style={{
        transform: animating ? "scale(1.1)" : "scale(1)",
      }}
    >
      {arrow} {Math.abs(value).toFixed(decimals)}%
    </span>
  );
}
