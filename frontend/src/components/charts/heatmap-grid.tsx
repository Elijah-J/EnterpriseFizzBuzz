"use client";

import { useState } from "react";
import type { HeatmapData } from "@/lib/data-providers";

/**
 * SVG divisibility heatmap grid for visualizing modular arithmetic patterns.
 *
 * Renders a grid where rows represent integers and columns represent divisors.
 * Cells are colored based on divisibility, with classification-appropriate colors
 * for divisors 3, 5, and 15 (the FizzBuzz-critical divisors). Non-divisible cells
 * use a neutral background at reduced opacity.
 *
 * This visualization reveals the periodic structure of modular arithmetic that
 * underpins the FizzBuzz classification engine, enabling operators to visually
 * confirm correct divisor behavior across arbitrary integer ranges.
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
    return "var(--panel-800)";
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

  const totalWidth =
    LABEL_MARGIN_LEFT +
    data.divisors.length * (cellSize + CELL_GAP);
  const totalHeight =
    LABEL_MARGIN_TOP +
    data.numbers.length * (cellSize + CELL_GAP);

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
      >
        {/* Column headers (divisors) */}
        {data.divisors.map((divisor, colIdx) => {
          const x = LABEL_MARGIN_LEFT + colIdx * (cellSize + CELL_GAP) + cellSize / 2;
          const isHighlighted = highlightDivisors.includes(divisor);

          return (
            <g key={`col-${divisor}`}>
              <text
                x={x}
                y={LABEL_MARGIN_TOP - 10}
                textAnchor="middle"
                className={`text-[10px] ${isHighlighted ? "fill-panel-200 font-semibold" : "fill-panel-500"}`}
              >
                {divisor}
              </text>
              {/* Column highlight for FizzBuzz-critical divisors */}
              {isHighlighted && (
                <line
                  x1={LABEL_MARGIN_LEFT + colIdx * (cellSize + CELL_GAP)}
                  x2={LABEL_MARGIN_LEFT + colIdx * (cellSize + CELL_GAP) + cellSize}
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
                className="text-[10px] fill-panel-500"
              >
                {num}
              </text>

              {/* Cells */}
              {data.divisors.map((divisor, colIdx) => {
                const cell = cellMap.get(`${num}-${divisor}`);
                if (!cell) return null;

                const cellX = LABEL_MARGIN_LEFT + colIdx * (cellSize + CELL_GAP);

                return (
                  <rect
                    key={`cell-${num}-${divisor}`}
                    x={cellX}
                    y={y}
                    width={cellSize}
                    height={cellSize}
                    rx={2}
                    fill={getCellColor(divisor, cell.divisible)}
                    opacity={cell.divisible ? 0.8 : 0.4}
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
                    style={{ cursor: "pointer" }}
                  />
                );
              })}
            </g>
          );
        })}

        {/* Hover tooltip */}
        {hoveredCell && (
          (() => {
            const text = hoveredCell.divisible
              ? `${hoveredCell.number} mod ${hoveredCell.divisor} = 0 (divisible)`
              : `${hoveredCell.number} mod ${hoveredCell.divisor} = ${hoveredCell.remainder}`;
            const rectW = text.length * 6.5 + 16;
            const rectH = 24;
            const tx = Math.min(hoveredCell.x - rectW / 2, totalWidth - rectW - 4);
            const ty = hoveredCell.y - rectH - 6;

            return (
              <g>
                <rect
                  x={Math.max(4, tx)}
                  y={Math.max(4, ty)}
                  width={rectW}
                  height={rectH}
                  rx={4}
                  fill="var(--panel-800)"
                  stroke="var(--panel-600)"
                  strokeWidth="0.5"
                />
                <text
                  x={Math.max(4, tx) + 8}
                  y={Math.max(4, ty) + 15}
                  className="text-[10px] fill-panel-200 font-mono"
                >
                  {text}
                </text>
              </g>
            );
          })()
        )}
      </svg>
    </div>
  );
}
