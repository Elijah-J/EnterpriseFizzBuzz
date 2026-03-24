"use client";

import type { ReactNode } from "react";
import { useIntersectionObserver } from "@/lib/hooks/use-intersection-observer";
import { useReducedMotion } from "@/lib/hooks/use-reduced-motion";

/**
 * Entrance animation wrapper that reveals children when they enter the
 * viewport. Applies a subtle fade combined with a 4px upward translation
 * — restrained enough to communicate state change without theatrical
 * flourish.
 *
 * The animation is triggered by IntersectionObserver and fires only once
 * per element lifecycle. When `prefers-reduced-motion` is active, children
 * are displayed immediately without any transition.
 *
 * Maximum recommended delay is 400ms to prevent the perception of broken
 * or unresponsive interface elements.
 */

interface RevealProps {
  /** Content to reveal on viewport entry. */
  children: ReactNode;
  /** Animation delay in milliseconds. Used for staggered sequences. Default 0. */
  delay?: number;
  /** Additional CSS classes for the wrapper div. */
  className?: string;
}

export function Reveal({ children, delay = 0, className = "" }: RevealProps) {
  const { ref, isVisible } = useIntersectionObserver<HTMLDivElement>({
    threshold: 0.1,
    triggerOnce: true,
  });
  const prefersReduced = useReducedMotion();

  const shouldAnimate = !prefersReduced && isVisible;
  const shouldShow = prefersReduced || isVisible;

  return (
    <div
      ref={ref}
      className={className}
      style={{
        opacity: shouldShow ? 1 : 0,
        transform:
          shouldAnimate || prefersReduced ? "translateY(0)" : "translateY(4px)",
        transition: prefersReduced
          ? "none"
          : `opacity 300ms ease-out ${delay}ms, transform 300ms ease-out ${delay}ms`,
      }}
    >
      {children}
    </div>
  );
}
