import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { Skeleton } from "../skeleton";

describe("Skeleton", () => {
  it("renders with role status for accessibility", () => {
    render(<Skeleton />);
    expect(screen.getByRole("status")).toBeInTheDocument();
  });

  it("includes aria-label Loading for assistive technology", () => {
    render(<Skeleton />);
    expect(screen.getByRole("status")).toHaveAttribute("aria-label", "Loading");
  });

  it("applies rect variant by default with rounded class", () => {
    render(<Skeleton />);
    expect(screen.getByRole("status")).toHaveClass("rounded");
  });

  it("applies circle variant with rounded-full class", () => {
    render(<Skeleton variant="circle" />);
    expect(screen.getByRole("status")).toHaveClass("rounded-full");
  });

  it("applies text variant with rounded class", () => {
    render(<Skeleton variant="text" />);
    expect(screen.getByRole("status")).toHaveClass("rounded");
  });

  it("applies card variant with internal skeleton structure", () => {
    render(<Skeleton variant="card" />);
    const skeleton = screen.getByRole("status");
    const innerDivs = skeleton.querySelectorAll(".bg-surface-overlay");
    expect(innerDivs.length).toBeGreaterThanOrEqual(3);
  });

  it("applies shimmer animation class when motion is enabled", () => {
    render(<Skeleton />);
    expect(screen.getByRole("status")).toHaveClass("animate-shimmer");
  });

  it("suppresses shimmer animation when reduced motion is preferred", () => {
    // Override the global matchMedia to return matches: true for reduced motion
    const originalMatchMedia = window.matchMedia;
    Object.defineProperty(window, "matchMedia", {
      writable: true,
      value: (query: string) => ({
        matches: query === "(prefers-reduced-motion: reduce)",
        media: query,
        onchange: null,
        addListener: () => {},
        removeListener: () => {},
        addEventListener: () => {},
        removeEventListener: () => {},
        dispatchEvent: () => false,
      }),
    });
    render(<Skeleton />);
    expect(screen.getByRole("status")).not.toHaveClass("animate-shimmer");
    // Restore original mock
    Object.defineProperty(window, "matchMedia", {
      writable: true,
      value: originalMatchMedia,
    });
  });

  it("applies custom width via style attribute", () => {
    render(<Skeleton width={200} />);
    expect(screen.getByRole("status")).toHaveStyle({ width: "200px" });
  });

  it("applies custom height via style attribute", () => {
    render(<Skeleton height={48} />);
    expect(screen.getByRole("status")).toHaveStyle({ height: "48px" });
  });

  it("accepts string values for width and height", () => {
    render(<Skeleton width="50%" height="3rem" />);
    const skeleton = screen.getByRole("status");
    expect(skeleton).toHaveStyle({ width: "50%", height: "3rem" });
  });

  it("applies default width of 100% for non-circle variants", () => {
    render(<Skeleton variant="rect" />);
    expect(screen.getByRole("status")).toHaveStyle({ width: "100%" });
  });

  it("applies base surface classes", () => {
    render(<Skeleton />);
    const skeleton = screen.getByRole("status");
    expect(skeleton).toHaveClass("bg-surface-raised");
    expect(skeleton).toHaveClass("overflow-hidden");
  });

  it("merges custom className", () => {
    render(<Skeleton className="mt-4" />);
    const skeleton = screen.getByRole("status");
    expect(skeleton).toHaveClass("mt-4");
    expect(skeleton).toHaveClass("bg-surface-raised");
  });
});
