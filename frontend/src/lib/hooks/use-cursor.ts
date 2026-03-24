"use client";

import { useCallback, useEffect, useRef, useState } from "react";

/**
 * High-performance cursor tracking hook with requestAnimationFrame interpolation.
 *
 * Tracks the physical cursor position and applies linear interpolation (lerp)
 * at 60fps to produce smooth, lagged coordinates suitable for custom cursor
 * rendering. The lerp factor (0.15) creates a subtle trailing effect that
 * communicates physicality without introducing input lag perceptible to the
 * operator.
 *
 * Interactive element detection uses a two-tier strategy:
 * 1. Explicit `data-cursor` attributes for precise cursor state control
 * 2. Implicit detection via semantic selectors (button, a, [role="button"])
 *
 * The hook automatically disables on touch devices and when the
 * `prefers-reduced-motion` media query is active.
 */

export type CursorState = "default" | "pointer" | "text";

interface UseCursorReturn {
  /** Interpolated X coordinate (viewport-relative). */
  x: number;
  /** Interpolated Y coordinate (viewport-relative). */
  y: number;
  /** Whether the cursor is over an interactive element. */
  isHovering: boolean;
  /** Current cursor visual state. */
  cursorState: CursorState;
  /** Whether the custom cursor should be visible. */
  visible: boolean;
}

const INTERACTIVE_SELECTORS =
  'button, a, [role="button"], input[type="submit"], input[type="button"], [data-cursor]';

const TEXT_SELECTORS =
  'p, span, h1, h2, h3, h4, h5, h6, label, td, th, li, blockquote, [contenteditable="true"]';

function isTouchDevice(): boolean {
  if (typeof window === "undefined") return true;
  return "ontouchstart" in window || navigator.maxTouchPoints > 0;
}

function prefersReducedMotion(): boolean {
  if (typeof window === "undefined") return true;
  return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

export function useCursor(lerpFactor = 0.15): UseCursorReturn {
  const [visible, setVisible] = useState(false);
  const targetRef = useRef({ x: 0, y: 0 });
  const currentRef = useRef({ x: 0, y: 0 });
  const [position, setPosition] = useState({ x: 0, y: 0 });
  const [cursorState, setCursorState] = useState<CursorState>("default");
  const [isHovering, setIsHovering] = useState(false);
  const rafRef = useRef<number>(0);
  const enabledRef = useRef(false);

  useEffect(() => {
    if (isTouchDevice() || prefersReducedMotion()) {
      enabledRef.current = false;
      setVisible(false);
      return;
    }

    enabledRef.current = true;
    setVisible(true);

    const handleMouseMove = (e: MouseEvent) => {
      targetRef.current = { x: e.clientX, y: e.clientY };

      // Determine cursor state from hovered element
      const el = document.elementFromPoint(e.clientX, e.clientY);
      if (!el) {
        setCursorState("default");
        setIsHovering(false);
        return;
      }

      const interactive = el.closest(INTERACTIVE_SELECTORS);
      if (interactive) {
        const dataCursor = interactive.getAttribute("data-cursor");
        setCursorState(
          dataCursor === "text" ? "text" : "pointer",
        );
        setIsHovering(true);
        return;
      }

      const textEl = el.closest(TEXT_SELECTORS);
      if (textEl && !textEl.closest(INTERACTIVE_SELECTORS)) {
        setCursorState("text");
        setIsHovering(false);
        return;
      }

      setCursorState("default");
      setIsHovering(false);
    };

    const handleMouseLeave = () => {
      setVisible(false);
    };

    const handleMouseEnter = () => {
      if (enabledRef.current) setVisible(true);
    };

    document.addEventListener("mousemove", handleMouseMove);
    document.documentElement.addEventListener("mouseleave", handleMouseLeave);
    document.documentElement.addEventListener("mouseenter", handleMouseEnter);

    // rAF interpolation loop
    const animate = () => {
      const curr = currentRef.current;
      const target = targetRef.current;
      curr.x += (target.x - curr.x) * lerpFactor;
      curr.y += (target.y - curr.y) * lerpFactor;
      setPosition({ x: curr.x, y: curr.y });
      rafRef.current = requestAnimationFrame(animate);
    };

    rafRef.current = requestAnimationFrame(animate);

    return () => {
      document.removeEventListener("mousemove", handleMouseMove);
      document.documentElement.removeEventListener(
        "mouseleave",
        handleMouseLeave,
      );
      document.documentElement.removeEventListener(
        "mouseenter",
        handleMouseEnter,
      );
      cancelAnimationFrame(rafRef.current);
    };
  }, [lerpFactor]);

  return {
    x: position.x,
    y: position.y,
    isHovering,
    cursorState,
    visible,
  };
}
