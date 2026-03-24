"use client";

import { useEffect, useRef, useState } from "react";
import { useReducedMotion } from "./use-reduced-motion";

/**
 * Configuration for the animated number interpolation engine.
 */
interface UseAnimatedNumberOptions {
  /** Target duration in milliseconds. The spring model may slightly overshoot this. Default 600. */
  duration?: number;
  /** Number of decimal places to retain in the interpolated output. Default 0. */
  decimals?: number;
  /** Numeric format applied to the final display value. Default "number". */
  format?: "number" | "currency" | "percent";
}

/**
 * Interpolates a numeric value from its previous state to the current target
 * using a critically-damped spring model. The spring eliminates the mechanical
 * feel of linear interpolation and provides natural deceleration as the value
 * approaches its target.
 *
 * The animation is driven by `requestAnimationFrame` for frame-perfect
 * synchronization with the display refresh cycle. When `prefers-reduced-motion`
 * is active, the target value is applied immediately without interpolation.
 *
 * Returns the current interpolated value as a formatted string.
 */
export function useAnimatedNumber(
  target: number,
  options: UseAnimatedNumberOptions = {},
): string {
  const { duration = 600, decimals = 0, format = "number" } = options;
  const prefersReduced = useReducedMotion();
  const [display, setDisplay] = useState(target);
  const prevTarget = useRef(target);
  const frameRef = useRef<number>(0);

  useEffect(() => {
    if (prefersReduced) {
      setDisplay(target);
      prevTarget.current = target;
      return;
    }

    const from = prevTarget.current;
    const to = target;
    prevTarget.current = target;

    if (from === to) {
      setDisplay(to);
      return;
    }

    const startTime = performance.now();

    /**
     * Critically-damped spring response curve.
     * At t=0 returns 0, at t>=1 returns ~1, with smooth deceleration.
     * The (1 + t) term provides slight overshoot characteristic of
     * physical spring systems before settling.
     */
    const spring = (t: number): number => {
      const clamped = Math.min(t, 1);
      return 1 - Math.exp(-6 * clamped) * (1 + 6 * clamped * (1 - clamped));
    };

    const animate = (now: number) => {
      const elapsed = now - startTime;
      const t = elapsed / duration;

      if (t >= 1) {
        setDisplay(to);
        return;
      }

      const progress = spring(t);
      setDisplay(from + (to - from) * progress);
      frameRef.current = requestAnimationFrame(animate);
    };

    frameRef.current = requestAnimationFrame(animate);

    return () => {
      if (frameRef.current) {
        cancelAnimationFrame(frameRef.current);
      }
    };
  }, [target, duration, prefersReduced]);

  return formatNumber(display, decimals, format);
}

/**
 * Applies locale-aware formatting to the interpolated numeric value.
 */
function formatNumber(
  value: number,
  decimals: number,
  format: "number" | "currency" | "percent",
): string {
  switch (format) {
    case "currency":
      return new Intl.NumberFormat("en-US", {
        style: "currency",
        currency: "USD",
        minimumFractionDigits: decimals,
        maximumFractionDigits: decimals,
      }).format(value);
    case "percent":
      return new Intl.NumberFormat("en-US", {
        style: "percent",
        minimumFractionDigits: decimals,
        maximumFractionDigits: decimals,
      }).format(value / 100);
    default:
      return new Intl.NumberFormat("en-US", {
        minimumFractionDigits: decimals,
        maximumFractionDigits: decimals,
      }).format(value);
  }
}
