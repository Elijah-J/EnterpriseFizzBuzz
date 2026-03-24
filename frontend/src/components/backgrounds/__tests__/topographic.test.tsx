import { describe, it, expect } from "vitest";
import { render } from "@testing-library/react";
import { Topographic } from "../topographic";

describe("Topographic", () => {
  it("renders an SVG element", () => {
    const { container } = render(<Topographic />);
    const svg = container.querySelector("svg");
    expect(svg).toBeInTheDocument();
  });

  it("sets aria-hidden for decorative background", () => {
    const { container } = render(<Topographic />);
    const svg = container.querySelector("svg");
    expect(svg).toHaveAttribute("aria-hidden", "true");
  });

  it("sets role to presentation", () => {
    const { container } = render(<Topographic />);
    const svg = container.querySelector("svg");
    expect(svg).toHaveAttribute("role", "presentation");
  });

  it("uses default viewport dimensions of 1920x1080", () => {
    const { container } = render(<Topographic />);
    const svg = container.querySelector("svg");
    expect(svg).toHaveAttribute("viewBox", "0 0 1920 1080");
  });

  it("accepts custom width and height", () => {
    const { container } = render(<Topographic width={800} height={600} />);
    const svg = container.querySelector("svg");
    expect(svg).toHaveAttribute("viewBox", "0 0 800 600");
  });

  it("renders contour path elements", () => {
    const { container } = render(<Topographic />);
    const paths = container.querySelectorAll("path");
    expect(paths.length).toBeGreaterThan(0);
  });

  it("applies default opacity of 0.04 to paths", () => {
    const { container } = render(<Topographic />);
    const paths = container.querySelectorAll("path");
    paths.forEach((path) => {
      expect(path.getAttribute("opacity")).toBe("0.04");
    });
  });

  it("accepts custom opacity", () => {
    const { container } = render(<Topographic opacity={0.1} />);
    const paths = container.querySelectorAll("path");
    paths.forEach((path) => {
      expect(path.getAttribute("opacity")).toBe("0.1");
    });
  });

  it("renders paths with no fill", () => {
    const { container } = render(<Topographic />);
    const paths = container.querySelectorAll("path");
    paths.forEach((path) => {
      expect(path.getAttribute("fill")).toBe("none");
    });
  });

  it("renders paths with text-muted stroke", () => {
    const { container } = render(<Topographic />);
    const paths = container.querySelectorAll("path");
    paths.forEach((path) => {
      expect(path.getAttribute("stroke")).toBe("var(--text-muted)");
    });
  });

  it("generates deterministic contours for the same seed", () => {
    const { container: c1 } = render(<Topographic seed={42} />);
    const { container: c2 } = render(<Topographic seed={42} />);
    const paths1 = Array.from(c1.querySelectorAll("path")).map((p) =>
      p.getAttribute("d"),
    );
    const paths2 = Array.from(c2.querySelectorAll("path")).map((p) =>
      p.getAttribute("d"),
    );
    expect(paths1).toEqual(paths2);
  });

  it("generates different contours for different seeds", () => {
    const { container: c1 } = render(<Topographic seed={1} />);
    const { container: c2 } = render(<Topographic seed={999} />);
    const d1 = c1.querySelector("path")?.getAttribute("d");
    const d2 = c2.querySelector("path")?.getAttribute("d");
    expect(d1).not.toEqual(d2);
  });

  it("renders more paths with higher density", () => {
    const { container: low } = render(<Topographic density={4} />);
    const { container: high } = render(<Topographic density={20} />);
    const lowCount = low.querySelectorAll("path").length;
    const highCount = high.querySelectorAll("path").length;
    expect(highCount).toBeGreaterThanOrEqual(lowCount);
  });

  it("uses xMidYMid slice for preserveAspectRatio", () => {
    const { container } = render(<Topographic />);
    const svg = container.querySelector("svg");
    expect(svg).toHaveAttribute("preserveAspectRatio", "xMidYMid slice");
  });
});
