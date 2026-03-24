import { describe, it, expect, afterEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { SplitText } from "../split-text";

describe("SplitText", () => {
  const originalMatchMedia = window.matchMedia;

  afterEach(() => {
    Object.defineProperty(window, "matchMedia", {
      writable: true,
      value: originalMatchMedia,
    });
  });

  it("renders the full text", () => {
    render(<SplitText text="FizzBuzz" />);
    expect(screen.getByLabelText("FizzBuzz")).toBeInTheDocument();
  });

  it("splits text into individual character spans", () => {
    const { container } = render(<SplitText text="Hello" />);
    const charSpans = container.querySelectorAll(".split-text-char");
    expect(charSpans).toHaveLength(5);
  });

  it("applies stagger delay to each character span", () => {
    const { container } = render(<SplitText text="AB" staggerMs={30} />);
    const spans = container.querySelectorAll(".split-text-char");
    expect(spans[0]).toHaveStyle({ animationDelay: "0ms" });
    expect(spans[1]).toHaveStyle({ animationDelay: "30ms" });
  });

  it("applies fade animation class by default", () => {
    const { container } = render(<SplitText text="Hi" />);
    const span = container.querySelector(".split-text-char");
    expect(span).toHaveClass("split-text-fade");
  });

  it("applies slide animation class when animation is slide", () => {
    const { container } = render(<SplitText text="Hi" animation="slide" />);
    const span = container.querySelector(".split-text-char");
    expect(span).toHaveClass("split-text-slide");
  });

  it("sets aria-hidden on individual character spans", () => {
    const { container } = render(<SplitText text="AB" />);
    const spans = container.querySelectorAll(".split-text-char");
    spans.forEach((span) => {
      expect(span).toHaveAttribute("aria-hidden", "true");
    });
  });

  it("renders plain text without animation when reduced motion is preferred", () => {
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
    const { container } = render(<SplitText text="Hello" />);
    const charSpans = container.querySelectorAll(".split-text-char");
    expect(charSpans).toHaveLength(0);
    expect(container.textContent).toBe("Hello");
  });

  it("replaces spaces with non-breaking spaces in character spans", () => {
    const { container } = render(<SplitText text="A B" />);
    const spans = container.querySelectorAll(".split-text-char");
    expect(spans[1].textContent).toBe("\u00A0");
  });

  it("merges custom className on wrapper", () => {
    const { container } = render(<SplitText text="Test" className="text-2xl" />);
    const wrapper = container.firstElementChild!;
    expect(wrapper).toHaveClass("text-2xl");
  });
});
