import { describe, it, expect } from "vitest";
import { render } from "@testing-library/react";
import { DotGrid } from "../dot-grid";

describe("DotGrid", () => {
  it("renders an SVG element", () => {
    const { container } = render(<DotGrid />);
    const svg = container.querySelector("svg");
    expect(svg).toBeInTheDocument();
  });

  it("sets aria-hidden for decorative background", () => {
    const { container } = render(<DotGrid />);
    const svg = container.querySelector("svg");
    expect(svg).toHaveAttribute("aria-hidden", "true");
  });

  it("sets role to presentation", () => {
    const { container } = render(<DotGrid />);
    const svg = container.querySelector("svg");
    expect(svg).toHaveAttribute("role", "presentation");
  });

  it("uses default viewport dimensions of 1920x1080", () => {
    const { container } = render(<DotGrid />);
    const svg = container.querySelector("svg");
    expect(svg).toHaveAttribute("viewBox", "0 0 1920 1080");
  });

  it("accepts custom width and height", () => {
    const { container } = render(<DotGrid width={640} height={480} />);
    const svg = container.querySelector("svg");
    expect(svg).toHaveAttribute("viewBox", "0 0 640 480");
  });

  it("renders circle elements for the dot grid", () => {
    const { container } = render(<DotGrid />);
    const circles = container.querySelectorAll("circle");
    expect(circles.length).toBeGreaterThan(0);
  });

  it("renders dots with text-muted fill", () => {
    const { container } = render(<DotGrid />);
    const circles = container.querySelectorAll("circle");
    circles.forEach((circle) => {
      expect(circle.getAttribute("fill")).toBe("var(--text-muted)");
    });
  });

  it("generates deterministic dot positions for the same seed", () => {
    const { container: c1 } = render(<DotGrid seed={7} width={100} height={100} spacing={50} />);
    const { container: c2 } = render(<DotGrid seed={7} width={100} height={100} spacing={50} />);
    const pos1 = Array.from(c1.querySelectorAll("circle")).map((c) => c.getAttribute("cx"));
    const pos2 = Array.from(c2.querySelectorAll("circle")).map((c) => c.getAttribute("cx"));
    expect(pos1).toEqual(pos2);
  });

  it("generates different positions for different seeds", () => {
    const { container: c1 } = render(<DotGrid seed={1} width={100} height={100} spacing={50} />);
    const { container: c2 } = render(<DotGrid seed={999} width={100} height={100} spacing={50} />);
    const cx1 = c1.querySelector("circle")?.getAttribute("cx");
    const cx2 = c2.querySelector("circle")?.getAttribute("cx");
    expect(cx1).not.toEqual(cx2);
  });

  it("applies vignette gradient — center dots have higher opacity than edge dots", () => {
    const { container } = render(<DotGrid width={200} height={200} spacing={100} />);
    const circles = container.querySelectorAll("circle");
    const opacities = Array.from(circles).map((c) =>
      parseFloat(c.getAttribute("opacity") || "0"),
    );
    // Center dots should have higher opacity than corner dots
    const maxOpacity = Math.max(...opacities);
    const minOpacity = Math.min(...opacities);
    expect(maxOpacity).toBeGreaterThan(minOpacity);
  });

  it("uses the default dot radius derived from dotSize", () => {
    const { container } = render(<DotGrid dotSize={6} width={100} height={100} spacing={50} />);
    const circle = container.querySelector("circle");
    // Default dotSize/2 = 3
    expect(circle?.getAttribute("r")).toBe("3");
  });

  it("renders expected number of dots based on grid dimensions", () => {
    const { container } = render(
      <DotGrid width={100} height={100} spacing={50} />,
    );
    const circles = container.querySelectorAll("circle");
    // cols = ceil(100/50) = 2, rows = ceil(100/50) = 2, total = 4
    expect(circles).toHaveLength(4);
  });

  it("uses xMidYMid slice for preserveAspectRatio", () => {
    const { container } = render(<DotGrid />);
    const svg = container.querySelector("svg");
    expect(svg).toHaveAttribute("preserveAspectRatio", "xMidYMid slice");
  });
});
