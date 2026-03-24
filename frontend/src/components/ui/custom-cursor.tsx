"use client";

import { useCursor } from "@/lib/hooks/use-cursor";

/**
 * Custom cursor overlay for the Enterprise FizzBuzz Operations Center.
 *
 * Renders a warm amber dot that follows the physical cursor with interpolated
 * lag (lerp 0.15), producing a fluid, physical tracking behavior. The cursor
 * morphs between three states based on the element beneath it:
 *
 * - **Default**: 8px solid amber dot — neutral navigation state
 * - **Pointer**: 32px amber ring (stroke only) — interactive element hover
 * - **Text**: 2px vertical amber bar — text selection readiness
 *
 * The component renders as a `position: fixed` overlay with `pointer-events: none`,
 * ensuring zero interference with the underlying interaction layer. It is
 * disabled entirely on touch devices and when `prefers-reduced-motion` is active,
 * falling back to the platform's native cursor.
 */

export function CustomCursor() {
  const { x, y, cursorState, visible } = useCursor(0.15);

  if (!visible) return null;

  return (
    <div
      className="custom-cursor-container"
      style={{
        position: "fixed",
        top: 0,
        left: 0,
        width: "100%",
        height: "100%",
        pointerEvents: "none",
        zIndex: 9999,
        overflow: "hidden",
      }}
      aria-hidden="true"
    >
      <div
        style={{
          position: "absolute",
          left: x,
          top: y,
          transform: "translate(-50%, -50%)",
          transition: "width 200ms ease-out, height 200ms ease-out, border-width 200ms ease-out, border-radius 200ms ease-out",
          ...(cursorState === "pointer"
            ? {
                width: 32,
                height: 32,
                borderRadius: "50%",
                border: "2px solid var(--accent)",
                backgroundColor: "transparent",
              }
            : cursorState === "text"
              ? {
                  width: 2,
                  height: 24,
                  borderRadius: 1,
                  border: "none",
                  backgroundColor: "var(--accent)",
                }
              : {
                  width: 8,
                  height: 8,
                  borderRadius: "50%",
                  border: "none",
                  backgroundColor: "var(--accent)",
                }),
        }}
      />
    </div>
  );
}
