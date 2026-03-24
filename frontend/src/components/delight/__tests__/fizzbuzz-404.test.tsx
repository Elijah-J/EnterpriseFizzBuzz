import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { FizzBuzz404 } from "../fizzbuzz-404";

describe("FizzBuzz404", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    // Mock performance.now for the animation tick
    vi.spyOn(performance, "now").mockReturnValue(0);
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("renders the 404 heading", () => {
    render(<FizzBuzz404 />);
    expect(
      screen.getByRole("heading", { level: 1 }),
    ).toHaveTextContent("404");
  });

  it("renders the resource not found description", () => {
    render(<FizzBuzz404 />);
    expect(
      screen.getByText(/not found in any registered evaluation pipeline/),
    ).toBeInTheDocument();
  });

  it("renders the detailed routing subsystem explanation", () => {
    render(<FizzBuzz404 />);
    expect(
      screen.getByText(/routing subsystem has exhausted all registered path matchers/),
    ).toBeInTheDocument();
  });

  it("renders a return link to the Operations Center", () => {
    render(<FizzBuzz404 />);
    const link = screen.getByRole("link", {
      name: "Return to Operations Center",
    });
    expect(link).toHaveAttribute("href", "/");
  });

  it("renders the scrolling FizzBuzz sequence background", () => {
    const { container } = render(<FizzBuzz404 />);
    const bgContainer = container.querySelector("[aria-hidden='true']");
    expect(bgContainer).toBeInTheDocument();
  });

  it("generates FizzBuzz sequence with correct values", () => {
    const { container } = render(<FizzBuzz404 />);
    // The sequence contains Fizz, Buzz, FizzBuzz, and numbers
    const fizzElements = container.querySelectorAll(".text-fizz-400");
    const buzzElements = container.querySelectorAll(".text-buzz-400");
    const fizzbuzzElements = container.querySelectorAll(".text-fizzbuzz-400");
    expect(fizzElements.length).toBeGreaterThan(0);
    expect(buzzElements.length).toBeGreaterThan(0);
    expect(fizzbuzzElements.length).toBeGreaterThan(0);
  });

  it("renders the grain overlay for visual continuity", () => {
    const { container } = render(<FizzBuzz404 />);
    const grainOverlay = container.querySelector(".pointer-events-none.z-\\[1\\]");
    expect(grainOverlay).toBeInTheDocument();
  });

  it("uses serif font family for the 404 heading", () => {
    render(<FizzBuzz404 />);
    const heading = screen.getByRole("heading", { level: 1 });
    expect(heading.style.fontFamily).toContain("serif");
  });

  it("renders the return link with accent background", () => {
    render(<FizzBuzz404 />);
    const link = screen.getByRole("link", {
      name: "Return to Operations Center",
    });
    expect(link).toHaveClass("bg-accent");
  });
});
