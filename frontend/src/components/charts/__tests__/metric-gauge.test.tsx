import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";

vi.mock("@/lib/hooks/use-reduced-motion", () => ({
  useReducedMotion: () => true,
}));

vi.mock("@/lib/hooks/use-animated-number", () => ({
  useAnimatedNumber: (value: number) => String(value),
}));

import { MetricGauge } from "../metric-gauge";

describe("MetricGauge", () => {
  it("renders an SVG element", () => {
    render(<MetricGauge value={87} />);
    expect(document.querySelector("svg")).toBeInTheDocument();
  });

  it("renders arc path elements for threshold zones", () => {
    const { container } = render(<MetricGauge value={87} />);
    const circles = container.querySelectorAll("circle");
    expect(circles.length).toBeGreaterThanOrEqual(2);
  });

  it("displays the value in the center", () => {
    render(<MetricGauge value={87} />);
    expect(screen.getByText("87")).toBeInTheDocument();
  });

  it("renders a label when provided", () => {
    render(<MetricGauge value={65} label="Cache Hit Rate" />);
    expect(screen.getByText("Cache Hit Rate")).toBeInTheDocument();
  });

  it("applies green color for high values", () => {
    const { container } = render(<MetricGauge value={90} />);
    const circles = container.querySelectorAll("circle");
    const valueCircle = circles[circles.length - 1];
    expect(valueCircle?.getAttribute("stroke")).toContain("fizz");
  });
});
