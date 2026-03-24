"use client";

import { useEffect, useState } from "react";

/**
 * Monitors the user's motion preference via the `prefers-reduced-motion`
 * media query. Returns `true` when the operating system or browser has
 * requested reduced motion, signaling that all non-essential animations
 * should be suppressed.
 *
 * This hook serves as the global motion gate for the Enterprise FizzBuzz
 * Platform. Every animation subsystem must consult this value before
 * initiating transitions, ensuring compliance with WCAG 2.1 Success
 * Criterion 2.3.3 (Animation from Interactions).
 */
export function useReducedMotion(): boolean {
  const [prefersReduced, setPrefersReduced] = useState(false);

  useEffect(() => {
    const query = window.matchMedia("(prefers-reduced-motion: reduce)");
    setPrefersReduced(query.matches);

    const handler = (event: MediaQueryListEvent) => {
      setPrefersReduced(event.matches);
    };

    query.addEventListener("change", handler);
    return () => query.removeEventListener("change", handler);
  }, []);

  return prefersReduced;
}
