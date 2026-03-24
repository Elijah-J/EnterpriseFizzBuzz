"use client";

import { useEffect, useRef, useState, type ReactNode } from "react";

/**
 * Unified chart tooltip for the Enterprise FizzBuzz data visualization system.
 *
 * Renders a warm surface-raised card that follows the cursor with a fixed
 * pixel offset. Smart edge detection flips the tooltip's anchor direction
 * when it approaches viewport boundaries, ensuring content remains visible
 * regardless of cursor position.
 *
 * Typography follows the platform convention: Geist Mono for values,
 * Geist Sans for labels. The tooltip uses the border-subtle token for
 * its border, consistent with all overlay surfaces.
 */

interface ChartTooltipProps {
  /** Viewport-relative X coordinate of the cursor. */
  x: number;
  /** Viewport-relative Y coordinate of the cursor. */
  y: number;
  /** Tooltip content — flexible ReactNode for chart-specific formatting. */
  content: ReactNode;
  /** Whether the tooltip is currently visible. */
  visible: boolean;
  /** X offset from cursor. Default 12. */
  offsetX?: number;
  /** Y offset from cursor. Default -8. */
  offsetY?: number;
}

export function ChartTooltip({
  x,
  y,
  content,
  visible,
  offsetX = 12,
  offsetY = -8,
}: ChartTooltipProps) {
  const tooltipRef = useRef<HTMLDivElement>(null);
  const [position, setPosition] = useState({ left: 0, top: 0 });

  useEffect(() => {
    if (!visible || !tooltipRef.current) return;

    const el = tooltipRef.current;
    const rect = el.getBoundingClientRect();
    const viewportW = window.innerWidth;
    const viewportH = window.innerHeight;

    // Smart edge detection: flip anchor if tooltip exceeds viewport
    let left = x + offsetX;
    let top = y + offsetY;

    if (left + rect.width > viewportW - 8) {
      left = x - rect.width - offsetX;
    }

    if (top < 8) {
      top = y + Math.abs(offsetY);
    }

    if (top + rect.height > viewportH - 8) {
      top = viewportH - rect.height - 8;
    }

    setPosition({ left: Math.max(8, left), top: Math.max(8, top) });
  }, [x, y, visible, offsetX, offsetY]);

  if (!visible) return null;

  return (
    <div
      ref={tooltipRef}
      className="fixed z-50 pointer-events-none rounded border border-border-subtle bg-surface-raised px-3 py-2 shadow-sm"
      style={{
        left: position.left,
        top: position.top,
        transition: "left 50ms ease-out, top 50ms ease-out",
      }}
    >
      {content}
    </div>
  );
}
