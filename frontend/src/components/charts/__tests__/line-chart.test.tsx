import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";

vi.mock("@/lib/hooks/use-reduced-motion", () => ({
  useReducedMotion: () => true,
}));

import { LineChart } from "../line-chart";

const sampleData = [
  { timestamp: 1710000000000, value: 42 },
  { timestamp: 1710000060000, value: 58 },
  { timestamp: 1710000120000, value: 51 },
  { timestamp: 1710000180000, value: 67 },
  { timestamp: 1710000240000, value: 45 },
];

describe("LineChart", () => {
  it("renders an SVG element with role img", () => {
    render(<LineChart data={sampleData} width={400} height={200} />);
    const svg = document.querySelector("svg");
    expect(svg).toBeInTheDocument();
    expect(svg).toHaveAttribute("role", "img");
  });

  it("includes a path element for the curve", () => {
    render(<LineChart data={sampleData} width={400} height={200} />);
    const paths = document.querySelectorAll("path");
    expect(paths.length).toBeGreaterThanOrEqual(1);
  });

  it("renders Y-axis tick labels", () => {
    render(<LineChart data={sampleData} width={400} height={200} />);
    const texts = document.querySelectorAll("text");
    expect(texts.length).toBeGreaterThan(0);
  });

  it("renders X-axis time labels", () => {
    const { container } = render(
      <LineChart data={sampleData} width={400} height={200} />,
    );
    const texts = container.querySelectorAll("text");
    const hasTime = Array.from(texts).some((t) => t.textContent?.includes(":"));
    expect(hasTime).toBe(true);
  });

  it("includes aria-label with metric label when provided", () => {
    render(
      <LineChart data={sampleData} width={400} height={200} label="Throughput" />,
    );
    const svg = document.querySelector("svg");
    expect(svg?.getAttribute("aria-label")).toContain("Throughput");
  });

  it("renders empty state message when data is empty", () => {
    render(<LineChart data={[]} width={400} height={200} />);
    expect(screen.getByText(/no data available/i)).toBeInTheDocument();
  });

  it("renders ZoomBrush when zoomable prop is set", () => {
    const { container } = render(
      <LineChart data={sampleData} width={400} height={200} zoomable />,
    );
    const rects = container.querySelectorAll("rect");
    expect(rects.length).toBeGreaterThan(0);
  });
});
