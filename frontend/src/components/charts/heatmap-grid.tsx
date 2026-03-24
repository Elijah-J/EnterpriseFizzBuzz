"use client";

import { useEffect, useState } from "react";
import type { HeatmapData } from "@/lib/data-providers";
import { useReducedMotion } from "@/lib/hooks/use-reduced-motion";

/**
 * SVG divisibility heatmap grid with staggered center-outward fade-in
 * and accent-colored hover borders.
 *
 * Cells fade in from the center of the grid outward, with each distance
 * ring receiving a progressive delay. This radial stagger communicates
 * the grid's mathematical structure — the center of the integer range
 * appears first, with the boundaries resolving last.
 *
 * Hover highlights apply a border in the accent color with no scale
 * transform or glow effect — consistent with the platform's restrained
 * motion philosophy.
 *
 * This visualization reveals the periodic structure of modular arithmetic
 * that underpins the FizzBuzz classification engine.
 */

interface HeatmapGridProps {
  /** Heatmap data containing cells, numbers (rows), and divisors (columns). */
  data: HeatmapData;
  /** Cell size in pixels. Default 28. */
  cellSize?: number;
  /** Divisor columns to highlight as FizzBuzz-critical. */
  highlightDivisors?: number[];
}

/**
 * Determines the fill color for a heatmap cell based on divisibility
 * and the divisor's relationship to the FizzBuzz classification rules.
 */
function getCellColor(divisor: number, divisible: boolean): string {
  if (!divisible) {
    return "var(--surface-raised)";
  }
  if (divisor === 15) return "var(--fizzbuzz-400)";
  if (divisor === 3) return "var(--fizz-400)";
  if (divisor === 5) return "var(--buzz-400)";
  return "var(--fizzbuzz-gold)";
}

const LABEL_MARGIN_LEFT = 44;
const LABEL_MARGIN_TOP = 28;
const CELL_GAP = 1;

export function HeatmapGrid({
  data,
  cellSize = 28,
  highlightDivisors = [3, 5, 15],
}: HeatmapGridProps) {
  const [hoveredCell, setHoveredCell] = useState<{
    number: number;
    divisor: number;
    remainder: number;
    divisible: boolean;
    x: number;
    y: number;
  } | null>(null);

  const prefersReduced = useReducedMotion();
  const [animationProgress, setAnimationProgress] = useState(
    prefersReduced ? 1 : 0,
  );

  const totalWidth =
    LABEL_MARGIN_LEFT + data.divisors.length * (cellSize + CELL_GAP);
  const totalHeight =
    LABEL_MARGIN_TOP + data.numbers.length * (cellSize + CELL_GAP);

  // Center of the grid for radial stagger calculation
  const centerRow = (data.numbers.length - 1) / 2;
  const centerCol = (data.divisors.length - 1) / 2;
  const maxDist = Math.hypot(centerRow, centerCol) || 1;

  // Staggered center-outward fade-in
  useEffect(() => {
    if (prefersReduced) {
      setAnimationProgress(1);
      return;
    }

    setAnimationProgress(0);
    const startTime = performance.now();
    const duration = 600;
    let frameId: number;

    const animate = (now: number) => {
      const elapsed = now - startTime;
      const t = Math.min(elapsed / duration, 1);
      setAnimationProgress(t);
      if (t < 1) {
        frameId = requestAnimationFrame(animate);
      }
    };

    frameId = requestAnimationFrame(animate);
    return () => cancelAnimationFrame(frameId);
  }, [prefersReduced]);

  // Build a lookup for fast cell access
  const cellMap = new Map<string, (typeof data.cells)[number]>();
  for (const cell of data.cells) {
    cellMap.set(`${cell.number}-${cell.divisor}`, cell);
  }

  return (
    <div className="overflow-x-auto">
      <svg
        width={totalWidth}
        height={totalHeight}
        viewBox={`0 0 ${totalWidth} ${totalHeight}`}
        className="overflow-visible"
        role="img"
        aria-label="Divisibility heatmap grid"
      >
        {/* Column headers (divisors) */}
        {data.divisors.map((divisor, colIdx) => {
          const x =
            LABEL_MARGIN_LEFT + colIdx * (cellSize + CELL_GAP) + cellSize / 2;
          const isHighlighted = highlightDivisors.includes(divisor);

          return (
            <g key={`col-${divisor}`}>
              <text
                x={x}
                y={LABEL_MARGIN_TOP - 10}
                textAnchor="middle"
                className={`text-[10px] ${isHighlighted ? "fill-text-primary font-semibold" : "fill-text-muted"}`}
              >
                {divisor}
              </text>
              {/* Column highlight for FizzBuzz-critical divisors */}
              {isHighlighted && (
                <line
                  x1={LABEL_MARGIN_LEFT + colIdx * (cellSize + CELL_GAP)}
                  x2={
                    LABEL_MARGIN_LEFT +
                    colIdx * (cellSize + CELL_GAP) +
                    cellSize
                  }
                  y1={LABEL_MARGIN_TOP - 4}
                  y2={LABEL_MARGIN_TOP - 4}
                  stroke={
                    divisor === 15
                      ? "var(--fizzbuzz-400)"
                      : divisor === 3
                        ? "var(--fizz-400)"
                        : "var(--buzz-400)"
                  }
                  strokeWidth={divisor === 15 ? 2 : 1}
                  opacity={divisor === 15 ? 0.9 : 0.6}
                />
              )}
            </g>
          );
        })}

        {/* Row labels (numbers) and cells */}
        {data.numbers.map((num, rowIdx) => {
          const y = LABEL_MARGIN_TOP + rowIdx * (cellSize + CELL_GAP);

          return (
            <g key={`row-${num}`}>
              {/* Row label */}
              <text
                x={LABEL_MARGIN_LEFT - 8}
                y={y + cellSize / 2}
                textAnchor="end"
                dominantBaseline="central"
                className="text-[10px] fill-text-muted"
              >
                {num}
              </text>

              {/* Cells */}
              {data.divisors.map((divisor, colIdx) => {
                const cell = cellMap.get(`${num}-${divisor}`);
                if (!cell) return null;

                const cellX =
                  LABEL_MARGIN_LEFT + colIdx * (cellSize + CELL_GAP);

                // Distance from center for stagger delay
                const dist = Math.hypot(rowIdx - centerRow, colIdx - centerCol);
                const normalizedDist = dist / maxDist;
                // Cell becomes visible when animation progress exceeds its distance threshold
                const cellOpacity =
                  animationProgress >= 1
                    ? cell.divisible
                      ? 0.8
                      : 0.4
                    : Math.max(
                        0,
                        Math.min(
                          1,
                          (animationProgress - normalizedDist * 0.6) / 0.4,
                        ),
                      ) * (cell.divisible ? 0.8 : 0.4);

                const isHovered =
                  hoveredCell?.number === num &&
                  hoveredCell?.divisor === divisor;

                return (
                  <rect
                    key={`cell-${num}-${divisor}`}
                    x={cellX}
                    y={y}
                    width={cellSize}
                    height={cellSize}
                    rx={2}
                    fill={getCellColor(divisor, cell.divisible)}
                    opacity={cellOpacity}
                    stroke={isHovered ? "var(--accent)" : "transparent"}
                    strokeWidth={isHovered ? 1.5 : 0}
                    onMouseEnter={() =>
                      setHoveredCell({
                        number: num,
                        divisor,
                        remainder: cell.remainder,
                        divisible: cell.divisible,
                        x: cellX + cellSize / 2,
                        y,
                      })
                    }
                    onMouseLeave={() => setHoveredCell(null)}
                    aria-label={`${num} mod ${divisor}`}
                    style={{ cursor: "pointer" }}
                    className="transition-[stroke] duration-150"
                  />
                );
              })}
            </g>
          );
        })}

        {/* Hover tooltip */}
        {hoveredCell &&
          (() => {
            const text = hoveredCell.divisible
              ? `${hoveredCell.number} mod ${hoveredCell.divisor} = 0 (divisible)`
              : `${hoveredCell.number} mod ${hoveredCell.divisor} = ${hoveredCell.remainder}`;
            const rectW = text.length * 6.5 + 16;
            const rectH = 24;
            const tx = Math.min(
              hoveredCell.x - rectW / 2,
              totalWidth - rectW - 4,
            );
            const ty = hoveredCell.y - rectH - 6;

            return (
              <g>
                <rect
                  x={Math.max(4, tx)}
                  y={Math.max(4, ty)}
                  width={rectW}
                  height={rectH}
                  rx={4}
                  fill="var(--surface-raised)"
                  stroke="var(--border-default)"
                  strokeWidth="0.5"
                />
                <text
                  x={Math.max(4, tx) + 8}
                  y={Math.max(4, ty) + 15}
                  className="text-[10px] fill-text-primary font-mono"
                >
                  {text}
                </text>
              </g>
            );
          })()}
      </svg>
    </div>
  );
}
