"use client";

import { useCallback, useRef, useState } from "react";

/**
 * X-axis zoom brush for line chart data exploration.
 *
 * Renders a draggable selection rectangle at the bottom of the chart SVG.
 * The operator drags horizontally to define a time range, which triggers
 * a zoom callback with the selected domain boundaries. Double-click
 * resets the zoom to the full data range.
 *
 * The brush rectangle uses the accent-muted token at low opacity, ensuring
 * the selection is visible without obscuring the underlying chart data.
 * The drag interaction uses pointer capture for reliable tracking across
 * rapid mouse movements.
 */

interface ZoomBrushProps {
  /** Total X-axis pixel width available for the brush area. */
  width: number;
  /** Vertical position (y offset) where the brush area starts. */
  y: number;
  /** Height of the brush interaction area. */
  height: number;
  /** Left margin offset for the plot area. */
  marginLeft: number;
  /** Callback with normalized [start, end] in [0, 1] range. */
  onZoom: (start: number, end: number) => void;
  /** Callback to reset zoom to full range. */
  onReset: () => void;
}

export function ZoomBrush({
  width,
  y,
  height,
  marginLeft,
  onZoom,
  onReset,
}: ZoomBrushProps) {
  const [isDragging, setIsDragging] = useState(false);
  const [selection, setSelection] = useState<{
    startX: number;
    endX: number;
  } | null>(null);
  const dragStartRef = useRef(0);
  const areaRef = useRef<SVGRectElement>(null);

  const clampX = useCallback(
    (clientX: number): number => {
      if (!areaRef.current) return 0;
      const rect = areaRef.current.getBoundingClientRect();
      return Math.max(0, Math.min(width, clientX - rect.left));
    },
    [width],
  );

  const handlePointerDown = useCallback(
    (e: React.PointerEvent<SVGRectElement>) => {
      e.preventDefault();
      (e.target as SVGRectElement).setPointerCapture(e.pointerId);
      const x = clampX(e.clientX);
      dragStartRef.current = x;
      setIsDragging(true);
      setSelection({ startX: x, endX: x });
    },
    [clampX],
  );

  const handlePointerMove = useCallback(
    (e: React.PointerEvent<SVGRectElement>) => {
      if (!isDragging) return;
      const x = clampX(e.clientX);
      setSelection({ startX: dragStartRef.current, endX: x });
    },
    [isDragging, clampX],
  );

  const handlePointerUp = useCallback(
    (e: React.PointerEvent<SVGRectElement>) => {
      if (!isDragging) return;
      (e.target as SVGRectElement).releasePointerCapture(e.pointerId);
      setIsDragging(false);

      if (selection) {
        const start = Math.min(selection.startX, selection.endX);
        const end = Math.max(selection.startX, selection.endX);
        const minDrag = 8;

        if (end - start >= minDrag) {
          const normalizedStart = start / width;
          const normalizedEnd = end / width;
          onZoom(normalizedStart, normalizedEnd);
        }
      }

      setSelection(null);
    },
    [isDragging, selection, width, onZoom],
  );

  const handleDoubleClick = useCallback(() => {
    onReset();
  }, [onReset]);

  const selX = selection
    ? Math.min(selection.startX, selection.endX)
    : 0;
  const selW = selection
    ? Math.abs(selection.endX - selection.startX)
    : 0;

  return (
    <g>
      {/* Brush interaction area — transparent overlay for pointer events */}
      <rect
        ref={areaRef}
        x={marginLeft}
        y={y}
        width={width}
        height={height}
        fill="transparent"
        style={{ cursor: "crosshair" }}
        onPointerDown={handlePointerDown}
        onPointerMove={handlePointerMove}
        onPointerUp={handlePointerUp}
        onDoubleClick={handleDoubleClick}
      />

      {/* Selection rectangle — visible during drag */}
      {selection && selW > 1 && (
        <rect
          x={marginLeft + selX}
          y={y}
          width={selW}
          height={height}
          fill="var(--accent)"
          opacity={0.12}
          rx={2}
          pointerEvents="none"
        />
      )}
    </g>
  );
}
