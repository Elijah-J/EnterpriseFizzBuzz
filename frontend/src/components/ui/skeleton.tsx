"use client";

import { useReducedMotion } from "@/lib/hooks/use-reduced-motion";

/**
 * Loading skeleton component with a warm-toned shimmer animation.
 *
 * Provides visual placeholders during data fetching operations, maintaining
 * spatial stability and communicating loading state without the cognitive
 * disruption of spinner animations. The shimmer uses a warm white sweep
 * over the stone surface palette, consistent with the Warm Precision
 * design language.
 *
 * Four variants map to common layout patterns:
 * - `text`: Single line of text (full width, 1rem height)
 * - `circle`: Avatar or icon placeholder
 * - `rect`: Generic rectangular region
 * - `card`: Full card placeholder with internal structure
 *
 * When `prefers-reduced-motion` is active, the shimmer animation is
 * suppressed and a static placeholder is displayed instead.
 */

interface SkeletonProps {
  /** Shape variant. Default "rect". */
  variant?: "text" | "circle" | "rect" | "card";
  /** Width in pixels or CSS value. Default "100%". */
  width?: number | string;
  /** Height in pixels or CSS value. Default determined by variant. */
  height?: number | string;
  /** Additional CSS classes. */
  className?: string;
}

const DEFAULT_HEIGHTS: Record<string, string> = {
  text: "1rem",
  circle: "2.5rem",
  rect: "4rem",
  card: "8rem",
};

export function Skeleton({
  variant = "rect",
  width,
  height,
  className = "",
}: SkeletonProps) {
  const prefersReduced = useReducedMotion();

  const resolvedWidth =
    variant === "circle"
      ? (width ?? DEFAULT_HEIGHTS.circle)
      : (width ?? "100%");
  const resolvedHeight = height ?? DEFAULT_HEIGHTS[variant] ?? "4rem";

  const baseClasses = "bg-surface-raised overflow-hidden";
  const shapeClasses = variant === "circle" ? "rounded-full" : "rounded";
  const animationClass = prefersReduced ? "" : "animate-shimmer";

  return (
    <div
      className={`${baseClasses} ${shapeClasses} ${animationClass} ${className}`}
      style={{
        width:
          typeof resolvedWidth === "number"
            ? `${resolvedWidth}px`
            : resolvedWidth,
        height:
          typeof resolvedHeight === "number"
            ? `${resolvedHeight}px`
            : resolvedHeight,
      }}
      role="status"
      aria-label="Loading"
    >
      {variant === "card" && (
        <div className="p-4 space-y-3 h-full">
          <div
            className={`bg-surface-overlay rounded h-3 w-1/3 ${prefersReduced ? "" : "animate-shimmer"}`}
          />
          <div
            className={`bg-surface-overlay rounded h-6 w-2/3 ${prefersReduced ? "" : "animate-shimmer"}`}
          />
          <div
            className={`bg-surface-overlay rounded h-3 w-1/2 ${prefersReduced ? "" : "animate-shimmer"}`}
          />
        </div>
      )}
    </div>
  );
}
