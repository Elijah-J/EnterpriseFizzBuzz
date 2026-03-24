"use client";

import { useMemo } from "react";

/**
 * Generative SVG dot grid background.
 *
 * Renders a field of warm stone-toned dots in a regular grid with subtle
 * position jitter, producing a hand-stamped "paper" texture effect. Dots
 * near the center of the viewport are rendered at marginally higher
 * brightness, creating a natural vignette that draws the eye toward
 * primary content.
 *
 * Jitter is deterministic via a seeded PRNG, ensuring consistent rendering
 * across frames without animation overhead. The dot field is static SVG —
 * no requestAnimationFrame, no reflows, no runtime computation after
 * initial render.
 */

interface DotGridProps {
  /** Seed for deterministic jitter. */
  seed?: number;
  /** Dot diameter in pixels. */
  dotSize?: number;
  /** Grid spacing between dot centers. */
  spacing?: number;
  /** Maximum position jitter in pixels (applied per axis). */
  jitter?: number;
  /** Base opacity for dots (0-1). */
  opacity?: number;
  /** SVG viewport width. */
  width?: number;
  /** SVG viewport height. */
  height?: number;
}

/**
 * Deterministic pseudo-random number generator using a simple hash.
 * Returns values in [0, 1) for a given integer index and seed.
 */
function seededRandom(index: number, seed: number): number {
  let h = (index * 2654435761 + seed * 1597334677) | 0;
  h = ((h >>> 16) ^ h) * 0x45d9f3b;
  h = ((h >>> 16) ^ h) * 0x45d9f3b;
  h = (h >>> 16) ^ h;
  return (h >>> 0) / 4294967296;
}

export function DotGrid({
  seed = 7,
  dotSize = 3,
  spacing = 24,
  jitter = 2,
  opacity = 0.03,
  width = 1920,
  height = 1080,
}: DotGridProps) {
  const dots = useMemo(() => {
    const result: { cx: number; cy: number; opacity: number }[] = [];
    const cols = Math.ceil(width / spacing);
    const rows = Math.ceil(height / spacing);
    const centerX = width / 2;
    const centerY = height / 2;
    const maxDist = Math.hypot(centerX, centerY);

    for (let r = 0; r < rows; r++) {
      for (let c = 0; c < cols; c++) {
        const idx = r * cols + c;
        const jx = (seededRandom(idx * 2, seed) - 0.5) * 2 * jitter;
        const jy = (seededRandom(idx * 2 + 1, seed) - 0.5) * 2 * jitter;
        const cx = c * spacing + spacing / 2 + jx;
        const cy = r * spacing + spacing / 2 + jy;

        // Center dots are slightly brighter — vignette gradient
        const dist = Math.hypot(cx - centerX, cy - centerY);
        const normalizedDist = dist / maxDist;
        const dotOpacity = opacity * (1 + (1 - normalizedDist) * 0.4);

        result.push({ cx, cy, opacity: dotOpacity });
      }
    }

    return result;
  }, [seed, dotSize, spacing, jitter, opacity, width, height]);

  return (
    <svg
      width="100%"
      height="100%"
      viewBox={`0 0 ${width} ${height}`}
      preserveAspectRatio="xMidYMid slice"
      aria-hidden="true"
      role="presentation"
    >
      {dots.map((dot, i) => (
        <circle
          key={i}
          cx={dot.cx.toFixed(1)}
          cy={dot.cy.toFixed(1)}
          r={dotSize / 2}
          fill="var(--text-muted)"
          opacity={dot.opacity}
        />
      ))}
    </svg>
  );
}
