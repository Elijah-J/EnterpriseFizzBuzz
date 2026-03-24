"use client";

import { useAnimatedNumber } from "@/lib/hooks/use-animated-number";

/**
 * Animated numeric display component that interpolates between values
 * using a critically-damped spring model.
 *
 * Designed for KPI displays, dashboard counters, and any numeric readout
 * where value transitions should communicate data updates with physical
 * credibility. The spring easing provides natural deceleration that
 * matches human expectations of momentum-based motion.
 *
 * Respects `prefers-reduced-motion` — when active, values update instantly
 * without interpolation.
 */

interface AnimatedNumberProps {
  /** The target numeric value to display. */
  value: number;
  /** Formatting mode applied to the output string. Default "number". */
  format?: "number" | "currency" | "percent";
  /** Interpolation duration in milliseconds. Default 600. */
  duration?: number;
  /** Number of decimal places. Default 0. */
  decimals?: number;
  /** Additional CSS classes for the container span. */
  className?: string;
}

export function AnimatedNumber({
  value,
  format = "number",
  duration = 600,
  decimals = 0,
  className = "",
}: AnimatedNumberProps) {
  const display = useAnimatedNumber(value, { duration, decimals, format });

  return (
    <span className={className} aria-live="polite">
      {display}
    </span>
  );
}
