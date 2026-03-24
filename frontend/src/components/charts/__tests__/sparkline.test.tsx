import { describe, it, expect, vi, beforeAll } from "vitest";
import { render } from "@testing-library/react";

beforeAll(() => {
  if (!SVGElement.prototype.getTotalLength) {
    SVGElement.prototype.getTotalLength = () => 100;
  }
});

vi.mock("@/lib/hooks/use-reduced-motion", () => ({
  useReducedMotion: () => true,
}));

import { Sparkline } from "../sparkline";

describe("Sparkline", () => {
  it("renders an SVG element", () => {
    render(<Sparkline data={[10, 14, 12, 18, 15, 20]} />);
    expect(document.querySelector("svg")).toBeInTheDocument();
  });

  it("renders a path element for the curve", () => {
    render(<Sparkline data={[10, 14, 12, 18, 15, 20]} />);
    const path = document.querySelector("path");
    expect(path).toBeInTheDocument();
    expect(path?.getAttribute("d")).toBeTruthy();
  });

  it("renders an endpoint dot circle", () => {
    render(<Sparkline data={[10, 14, 12, 18, 15, 20]} />);
    const circles = document.querySelectorAll("circle");
    expect(circles.length).toBeGreaterThanOrEqual(1);
  });

  it("respects custom width and height", () => {
    render(<Sparkline data={[10, 14, 12, 18, 15, 20]} width={120} height={40} />);
    const svg = document.querySelector("svg");
    expect(svg?.getAttribute("viewBox")).toContain("120");
    expect(svg?.getAttribute("viewBox")).toContain("40");
  });
});
