"use client";

import { useMemo } from "react";

/**
 * Generative SVG topographic contour background.
 *
 * Renders layered contour lines using 2D simplex noise, producing organic
 * terrain patterns unique to each page in the Enterprise FizzBuzz Operations
 * Center. Route-seeded via a hash of the current pathname, ensuring
 * deterministic terrain generation — the same page always renders the same
 * topography for visual consistency across sessions.
 *
 * Contour lines are rendered as thin stone-500 strokes at low opacity,
 * providing subtle depth without competing with foreground content. The
 * noise function is implemented inline (~50 lines) to avoid external
 * dependencies, consistent with the platform's zero-dependency policy.
 */

interface TopographicProps {
  /** Seed value for noise generation. Determines terrain shape. */
  seed?: number;
  /** Number of contour lines to render. Higher values increase detail. */
  density?: number;
  /** Stroke opacity for contour lines (0-1). Default 0.04. */
  opacity?: number;
  /** SVG viewport width. */
  width?: number;
  /** SVG viewport height. */
  height?: number;
}

// --- Simplex Noise Implementation ---
// 2D simplex noise based on the Simplex Noise algorithm. Produces coherent
// gradient noise suitable for terrain generation without external dependencies.

const GRAD2: [number, number][] = [
  [1, 1], [-1, 1], [1, -1], [-1, -1],
  [1, 0], [-1, 0], [0, 1], [0, -1],
];

const F2 = 0.5 * (Math.sqrt(3) - 1);
const G2 = (3 - Math.sqrt(3)) / 6;

function createPermutation(seed: number): Uint8Array {
  const perm = new Uint8Array(512);
  const source = new Uint8Array(256);
  for (let i = 0; i < 256; i++) source[i] = i;

  // Fisher-Yates shuffle seeded with a simple LCG
  let s = seed | 0;
  for (let i = 255; i > 0; i--) {
    s = (s * 1664525 + 1013904223) | 0;
    const j = ((s >>> 0) % (i + 1));
    const tmp = source[i];
    source[i] = source[j];
    source[j] = tmp;
  }

  for (let i = 0; i < 512; i++) perm[i] = source[i & 255];
  return perm;
}

function simplex2D(x: number, y: number, perm: Uint8Array): number {
  const s = (x + y) * F2;
  const i = Math.floor(x + s);
  const j = Math.floor(y + s);
  const t = (i + j) * G2;

  const x0 = x - (i - t);
  const y0 = y - (j - t);

  const i1 = x0 > y0 ? 1 : 0;
  const j1 = x0 > y0 ? 0 : 1;

  const x1 = x0 - i1 + G2;
  const y1 = y0 - j1 + G2;
  const x2 = x0 - 1 + 2 * G2;
  const y2 = y0 - 1 + 2 * G2;

  const ii = i & 255;
  const jj = j & 255;

  let n0 = 0;
  let n1 = 0;
  let n2 = 0;

  let t0 = 0.5 - x0 * x0 - y0 * y0;
  if (t0 >= 0) {
    t0 *= t0;
    const g = GRAD2[perm[ii + perm[jj]] % 8];
    n0 = t0 * t0 * (g[0] * x0 + g[1] * y0);
  }

  let t1 = 0.5 - x1 * x1 - y1 * y1;
  if (t1 >= 0) {
    t1 *= t1;
    const g = GRAD2[perm[ii + i1 + perm[jj + j1]] % 8];
    n1 = t1 * t1 * (g[0] * x1 + g[1] * y1);
  }

  let t2 = 0.5 - x2 * x2 - y2 * y2;
  if (t2 >= 0) {
    t2 *= t2;
    const g = GRAD2[perm[ii + 1 + perm[jj + 1]] % 8];
    n2 = t2 * t2 * (g[0] * x2 + g[1] * y2);
  }

  return 70 * (n0 + n1 + n2);
}

/**
 * Generates contour paths using marching squares on a simplex noise field.
 * Each contour level produces a set of line segments connecting threshold
 * crossings in adjacent cells — the standard approach for extracting
 * isolines from scalar fields.
 */
function generateContours(
  seed: number,
  width: number,
  height: number,
  density: number,
): string[] {
  const perm = createPermutation(seed);
  const step = 20;
  const cols = Math.ceil(width / step) + 1;
  const rows = Math.ceil(height / step) + 1;
  const scale = 0.008;

  // Sample noise field
  const field: number[][] = [];
  for (let r = 0; r < rows; r++) {
    const row: number[] = [];
    for (let c = 0; c < cols; c++) {
      row.push(simplex2D(c * scale * step + seed * 0.1, r * scale * step + seed * 0.1, perm));
    }
    field.push(row);
  }

  // Generate contour lines at evenly spaced threshold levels
  const paths: string[] = [];
  const levels = density;

  for (let l = 0; l < levels; l++) {
    const threshold = -0.8 + (1.6 * (l + 1)) / (levels + 1);
    const segments: string[] = [];

    for (let r = 0; r < rows - 1; r++) {
      for (let c = 0; c < cols - 1; c++) {
        const v00 = field[r][c];
        const v10 = field[r][c + 1];
        const v01 = field[r + 1][c];
        const v11 = field[r + 1][c + 1];

        const x = c * step;
        const y = r * step;

        // Marching squares case index
        let caseIndex = 0;
        if (v00 >= threshold) caseIndex |= 1;
        if (v10 >= threshold) caseIndex |= 2;
        if (v11 >= threshold) caseIndex |= 4;
        if (v01 >= threshold) caseIndex |= 8;

        if (caseIndex === 0 || caseIndex === 15) continue;

        const lerp = (a: number, b: number) => {
          const d = b - a;
          return d === 0 ? 0.5 : (threshold - a) / d;
        };

        // Edge interpolation points
        const top = { x: x + lerp(v00, v10) * step, y };
        const right = { x: x + step, y: y + lerp(v10, v11) * step };
        const bottom = { x: x + lerp(v01, v11) * step, y: y + step };
        const left = { x, y: y + lerp(v00, v01) * step };

        const addLine = (a: { x: number; y: number }, b: { x: number; y: number }) => {
          segments.push(`M${a.x.toFixed(1)},${a.y.toFixed(1)}L${b.x.toFixed(1)},${b.y.toFixed(1)}`);
        };

        switch (caseIndex) {
          case 1: case 14: addLine(top, left); break;
          case 2: case 13: addLine(top, right); break;
          case 3: case 12: addLine(left, right); break;
          case 4: case 11: addLine(right, bottom); break;
          case 5:
            addLine(top, right);
            addLine(bottom, left);
            break;
          case 6: case 9: addLine(top, bottom); break;
          case 7: case 8: addLine(left, bottom); break;
          case 10:
            addLine(top, left);
            addLine(right, bottom);
            break;
        }
      }
    }

    if (segments.length > 0) {
      paths.push(segments.join(" "));
    }
  }

  return paths;
}

export function Topographic({
  seed = 42,
  density = 12,
  opacity = 0.04,
  width = 1920,
  height = 1080,
}: TopographicProps) {
  const contourPaths = useMemo(
    () => generateContours(seed, width, height, density),
    [seed, width, height, density],
  );

  return (
    <svg
      width="100%"
      height="100%"
      viewBox={`0 0 ${width} ${height}`}
      preserveAspectRatio="xMidYMid slice"
      aria-hidden="true"
      role="presentation"
    >
      {contourPaths.map((d, i) => (
        <path
          key={i}
          d={d}
          fill="none"
          stroke="var(--text-muted)"
          strokeWidth="0.75"
          opacity={opacity}
        />
      ))}
    </svg>
  );
}
