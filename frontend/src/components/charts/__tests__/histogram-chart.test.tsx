import { describe, it, expect, vi } from "vitest";
import { render } from "@testing-library/react";

vi.mock("@/lib/hooks/use-reduced-motion", () => ({
  useReducedMotion: () => true,
}));

import { HistogramChart } from "../histogram-chart";

const sampleData = [
  { timestamp: 1710000000000, value: 1.2 },
  { timestamp: 1710000060000, value: 2.5 },
  { timestamp: 1710000120000, value: 1.8 },
  { timestamp: 1710000180000, value: 3.1 },
  { timestamp: 1710000240000, value: 2.0 },
  { timestamp: 1710000300000, value: 4.5 },
  { timestamp: 1710000360000, value: 1.5 },
  { timestamp: 1710000420000, value: 2.8 },
];

describe("HistogramChart", () => {
  it("renders an SVG element", () => {
    render(<HistogramChart data={sampleData} width={400} height={200} />);
    expect(document.querySelector("svg")).toBeInTheDocument();
  });

  it("renders bar rect elements", () => {
    const { container } = render(
      <HistogramChart data={sampleData} width={400} height={200} />,
    );
    const rects = container.querySelectorAll("rect");
    expect(rects.length).toBeGreaterThan(0);
  });

  it("renders Y-axis labels", () => {
    const { container } = render(
      <HistogramChart data={sampleData} width={400} height={200} unit="ms" />,
    );
    const texts = container.querySelectorAll("text");
    expect(texts.length).toBeGreaterThan(0);
  });

  it("renders empty state for empty data", () => {
    const { container } = render(
      <HistogramChart data={[]} width={400} height={200} />,
    );
    expect(container.querySelector("svg") || container.textContent).toBeTruthy();
  });
});
