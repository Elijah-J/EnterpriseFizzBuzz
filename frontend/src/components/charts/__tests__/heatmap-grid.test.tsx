import { describe, it, expect, vi } from "vitest";
import { render, act } from "@testing-library/react";

vi.mock("@/lib/hooks/use-reduced-motion", () => ({
  useReducedMotion: () => true,
}));

import { HeatmapGrid } from "../heatmap-grid";

const heatmapData = {
  cells: [
    { number: 1, divisor: 3, divisible: false, remainder: 1 },
    { number: 1, divisor: 5, divisible: false, remainder: 1 },
    { number: 3, divisor: 3, divisible: true, remainder: 0 },
    { number: 3, divisor: 5, divisible: false, remainder: 3 },
    { number: 5, divisor: 3, divisible: false, remainder: 2 },
    { number: 5, divisor: 5, divisible: true, remainder: 0 },
    { number: 15, divisor: 3, divisible: true, remainder: 0 },
    { number: 15, divisor: 5, divisible: true, remainder: 0 },
  ],
  numbers: [1, 3, 5, 15],
  divisors: [3, 5],
};

describe("HeatmapGrid", () => {
  it("renders an SVG element", async () => {
    await act(async () => {
      render(<HeatmapGrid data={heatmapData} />);
    });
    expect(document.querySelector("svg")).toBeInTheDocument();
  });

  it("renders rect elements for heatmap cells", async () => {
    let container: HTMLElement;
    await act(async () => {
      const result = render(<HeatmapGrid data={heatmapData} />);
      container = result.container;
    });
    const rects = container!.querySelectorAll("rect");
    expect(rects.length).toBeGreaterThanOrEqual(heatmapData.cells.length);
  });

  it("renders row and column labels", async () => {
    let container: HTMLElement;
    await act(async () => {
      const result = render(<HeatmapGrid data={heatmapData} />);
      container = result.container;
    });
    const texts = container!.querySelectorAll("text");
    expect(texts.length).toBeGreaterThan(0);
  });

  it("applies FizzBuzz domain colors to divisible cells", async () => {
    let container: HTMLElement;
    await act(async () => {
      const result = render(<HeatmapGrid data={heatmapData} />);
      container = result.container;
    });
    const fizzCell = container!.querySelector('rect[fill="var(--fizz-400)"]');
    expect(fizzCell).toBeInTheDocument();
  });
});
