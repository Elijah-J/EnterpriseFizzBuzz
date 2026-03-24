"use client";

import { useCallback, useEffect, useRef, type RefObject } from "react";
import { useReducedMotion } from "./use-reduced-motion";

interface UseMagneticOptions {
  /** Displacement strength multiplier (0-1). Default: 0.3 */
  strength?: number;
  /** Activation radius in pixels from element center. Default: 100 */
  radius?: number;
}

/**
 * Magnetic cursor-following interaction hook for the Enterprise FizzBuzz
 * Platform's primary action triggers.
 *
 * Calculates the distance between the cursor and the target element's
 * center point, applying a proportional `translate()` transform when the
 * cursor enters the activation radius. Maximum displacement is capped at
 * 4px to maintain spatial predictability. A spring-based return animation
 * restores the element to its origin when the cursor exits the radius.
 *
 * The effect is disabled entirely when the user has enabled reduced-motion
 * preferences, in compliance with WCAG accessibility guidelines.
 */
export function useMagnetic<T extends HTMLElement>(
  ref: RefObject<T | null>,
  options: UseMagneticOptions = {}
) {
  const { strength = 0.3, radius = 100 } = options;
  const reducedMotion = useReducedMotion();
  const rafId = useRef<number>(0);

  const handleMouseMove = useCallback(
    (e: MouseEvent) => {
      if (reducedMotion || !ref.current) return;

      const el = ref.current;
      const rect = el.getBoundingClientRect();
      const centerX = rect.left + rect.width / 2;
      const centerY = rect.top + rect.height / 2;

      const distX = e.clientX - centerX;
      const distY = e.clientY - centerY;
      const distance = Math.sqrt(distX * distX + distY * distY);

      if (distance < radius) {
        cancelAnimationFrame(rafId.current);
        rafId.current = requestAnimationFrame(() => {
          const factor = (1 - distance / radius) * strength;
          const maxDisplacement = 4;
          const tx = Math.max(-maxDisplacement, Math.min(maxDisplacement, distX * factor));
          const ty = Math.max(-maxDisplacement, Math.min(maxDisplacement, distY * factor));
          el.style.transform = `translate(${tx}px, ${ty}px)`;
          el.style.transition = "transform 150ms cubic-bezier(0.34, 1.56, 0.64, 1)";
        });
      } else {
        cancelAnimationFrame(rafId.current);
        rafId.current = requestAnimationFrame(() => {
          el.style.transform = "translate(0px, 0px)";
          el.style.transition = "transform 300ms cubic-bezier(0.34, 1.56, 0.64, 1)";
        });
      }
    },
    [ref, strength, radius, reducedMotion]
  );

  const handleMouseLeave = useCallback(() => {
    if (!ref.current) return;
    ref.current.style.transform = "translate(0px, 0px)";
    ref.current.style.transition = "transform 300ms cubic-bezier(0.34, 1.56, 0.64, 1)";
  }, [ref]);

  useEffect(() => {
    if (reducedMotion) return;

    document.addEventListener("mousemove", handleMouseMove);
    const el = ref.current;
    if (el) {
      el.addEventListener("mouseleave", handleMouseLeave);
    }

    return () => {
      document.removeEventListener("mousemove", handleMouseMove);
      if (el) {
        el.removeEventListener("mouseleave", handleMouseLeave);
      }
      cancelAnimationFrame(rafId.current);
    };
  }, [handleMouseMove, handleMouseLeave, reducedMotion, ref]);
}
