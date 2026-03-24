import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";

vi.mock("@/lib/hooks/use-reduced-motion", () => ({
  useReducedMotion: () => true,
}));

import { DonutChart } from "../donut-chart";

const segments = [
  { label: "Fizz", value: 27, color: "var(--fizz-400)" },
  { label: "Buzz", value: 14, color: "var(--buzz-400)" },
  { label: "FizzBuzz", value: 6, color: "var(--fizzbuzz-400)" },
  { label: "Number", value: 53, color: "var(--text-muted)" },
];

describe("DonutChart", () => {
  it("renders an SVG element", () => {
    render(<DonutChart segments={segments} />);
    expect(document.querySelector("svg")).toBeInTheDocument();
  });

  it("renders path elements for each segment", () => {
    render(<DonutChart segments={segments} />);
    const paths = document.querySelectorAll("path");
    expect(paths.length).toBeGreaterThanOrEqual(segments.length);
  });

  it("renders the chart legend with segment labels", () => {
    render(<DonutChart segments={segments} />);
    expect(screen.getByText("Fizz")).toBeInTheDocument();
    expect(screen.getByText("Buzz")).toBeInTheDocument();
    expect(screen.getByText("FizzBuzz")).toBeInTheDocument();
  });

  it("renders center labels when provided", () => {
    render(
      <DonutChart segments={segments} centerLabel="100" centerSubLabel="total" />,
    );
    expect(screen.getByText("100")).toBeInTheDocument();
    expect(screen.getByText("total")).toBeInTheDocument();
  });

  it("applies segment colors to path fills", () => {
    render(<DonutChart segments={segments} />);
    const fizzPath = document.querySelector('path[fill="var(--fizz-400)"]');
    expect(fizzPath).toBeInTheDocument();
  });
});
