"use client";

import { useCallback, useEffect, useRef, type RefObject } from "react";
import { useReducedMotion } from "./use-reduced-motion";

/**
 * Press interaction hook implementing spring-based scale feedback for
 * interactive elements in the Enterprise FizzBuzz Operations Center.
 *
 * On pointer down (mouse or touch), the element compresses to scale(0.97).
 * On release, a spring overshoot easing restores the element to scale(1),
 * creating a physical, tactile response that communicates interactivity.
 *
 * The effect is disabled when reduced-motion preferences are active.
 */
export function usePress<T extends HTMLElement>(
  ref: RefObject<T | null>
) {
  const reducedMotion = useReducedMotion();
  const isPressed = useRef(false);

  const handleDown = useCallback(() => {
    if (reducedMotion || !ref.current) return;
    isPressed.current = true;
    ref.current.style.transform = "scale(0.97)";
    ref.current.style.transition = "transform 100ms ease-out";
  }, [ref, reducedMotion]);

  const handleUp = useCallback(() => {
    if (reducedMotion || !ref.current || !isPressed.current) return;
    isPressed.current = false;
    ref.current.style.transform = "scale(1)";
    ref.current.style.transition = "transform 300ms cubic-bezier(0.34, 1.56, 0.64, 1)";
  }, [ref, reducedMotion]);

  useEffect(() => {
    if (reducedMotion) return;
    const el = ref.current;
    if (!el) return;

    el.addEventListener("mousedown", handleDown);
    el.addEventListener("mouseup", handleUp);
    el.addEventListener("mouseleave", handleUp);
    el.addEventListener("touchstart", handleDown, { passive: true });
    el.addEventListener("touchend", handleUp);
    el.addEventListener("touchcancel", handleUp);

    return () => {
      el.removeEventListener("mousedown", handleDown);
      el.removeEventListener("mouseup", handleUp);
      el.removeEventListener("mouseleave", handleUp);
      el.removeEventListener("touchstart", handleDown);
      el.removeEventListener("touchend", handleUp);
      el.removeEventListener("touchcancel", handleUp);
    };
  }, [handleDown, handleUp, reducedMotion, ref]);
}
