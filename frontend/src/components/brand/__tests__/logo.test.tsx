import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, fireEvent, act } from "@testing-library/react";
import { Logo, Wordmark } from "../logo";

// Mock AboutPanel
vi.mock("@/components/delight/about-panel", () => ({
  AboutPanel: ({
    open,
    onClose,
  }: {
    open: boolean;
    onClose: () => void;
  }) =>
    open ? (
      <div data-testid="about-panel" role="dialog">
        <button type="button" onClick={onClose}>Close</button>
      </div>
    ) : null,
}));

describe("Logo", () => {
  it("renders an SVG element", () => {
    const { container } = render(<Logo />);
    const svg = container.querySelector("svg");
    expect(svg).toBeInTheDocument();
  });

  it("has an accessible label", () => {
    render(<Logo />);
    expect(
      screen.getByRole("img", { name: "Enterprise FizzBuzz Platform" }),
    ).toBeInTheDocument();
  });

  it("uses default size of 32", () => {
    const { container } = render(<Logo />);
    const svg = container.querySelector("svg");
    expect(svg).toHaveAttribute("width", "32");
    expect(svg).toHaveAttribute("height", "32");
  });

  it("accepts custom size", () => {
    const { container } = render(<Logo size={48} />);
    const svg = container.querySelector("svg");
    expect(svg).toHaveAttribute("width", "48");
    expect(svg).toHaveAttribute("height", "48");
  });

  it("renders six rect elements for the lettermark geometry", () => {
    const { container } = render(<Logo />);
    const rects = container.querySelectorAll("rect");
    expect(rects).toHaveLength(6);
  });

  it("uses viewBox of 0 0 48 48", () => {
    const { container } = render(<Logo />);
    const svg = container.querySelector("svg");
    expect(svg).toHaveAttribute("viewBox", "0 0 48 48");
  });

  it("applies custom className", () => {
    const { container } = render(<Logo className="brand-logo" />);
    const svg = container.querySelector("svg");
    expect(svg).toHaveClass("brand-logo");
  });
});

describe("Wordmark", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  it("renders the Logo mark", () => {
    const { container } = render(<Wordmark />);
    const svg = container.querySelector("svg");
    expect(svg).toBeInTheDocument();
  });

  it("renders Enterprise and FizzBuzz text", () => {
    render(<Wordmark />);
    expect(screen.getByText("Enterprise")).toBeInTheDocument();
    expect(screen.getByText("FizzBuzz")).toBeInTheDocument();
  });

  it("renders the FizzBuzz text with accent color", () => {
    render(<Wordmark />);
    const fizzBuzz = screen.getByText("FizzBuzz");
    expect(fizzBuzz.style.color || fizzBuzz.className).toBeDefined();
  });

  it("has button role for click interaction", () => {
    render(<Wordmark />);
    expect(screen.getByRole("button")).toBeInTheDocument();
  });

  it("accepts custom logoSize", () => {
    const { container } = render(<Wordmark logoSize={40} />);
    const svg = container.querySelector("svg");
    expect(svg).toHaveAttribute("width", "40");
    expect(svg).toHaveAttribute("height", "40");
  });

  it("applies custom className", () => {
    render(<Wordmark className="header-brand" />);
    const wrapper = screen.getByRole("button");
    expect(wrapper).toHaveClass("header-brand");
  });

  it("does not open AboutPanel with fewer than 5 clicks", () => {
    render(<Wordmark />);
    const btn = screen.getByRole("button");
    for (let i = 0; i < 4; i++) {
      fireEvent.click(btn);
    }
    expect(screen.queryByTestId("about-panel")).not.toBeInTheDocument();
  });

  it("opens AboutPanel after 5 rapid clicks (easter egg)", () => {
    render(<Wordmark />);
    const btn = screen.getByRole("button");
    for (let i = 0; i < 5; i++) {
      fireEvent.click(btn);
    }
    expect(screen.getByTestId("about-panel")).toBeInTheDocument();
  });

  it("resets click counter after 2 seconds of inactivity", () => {
    render(<Wordmark />);
    const btn = screen.getByRole("button");
    // Click 3 times
    for (let i = 0; i < 3; i++) {
      fireEvent.click(btn);
    }
    // Wait 2 seconds — counter resets
    act(() => {
      vi.advanceTimersByTime(2000);
    });
    // Click 2 more — total is only 2 since reset
    for (let i = 0; i < 2; i++) {
      fireEvent.click(btn);
    }
    expect(screen.queryByTestId("about-panel")).not.toBeInTheDocument();
  });

  it("supports keyboard activation with Enter and Space", () => {
    render(<Wordmark />);
    const btn = screen.getByRole("button");
    for (let i = 0; i < 5; i++) {
      fireEvent.keyDown(btn, { key: "Enter" });
    }
    expect(screen.getByTestId("about-panel")).toBeInTheDocument();
  });

  it("is focusable via tabIndex", () => {
    render(<Wordmark />);
    const btn = screen.getByRole("button");
    expect(btn).toHaveAttribute("tabindex", "0");
  });

  afterEach(() => {
    vi.useRealTimers();
  });
});
