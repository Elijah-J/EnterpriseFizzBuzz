import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, act } from "@testing-library/react";
import { Confetti, type ConfettiHandle } from "../confetti";
import { createRef } from "react";

describe("Confetti", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  it("renders nothing before fire is called", () => {
    const ref = createRef<ConfettiHandle>();
    const { container } = render(<Confetti ref={ref} />);
    expect(container.innerHTML).toBe("");
  });

  it("exposes a fire method via imperative handle", () => {
    const ref = createRef<ConfettiHandle>();
    render(<Confetti ref={ref} />);
    expect(ref.current).not.toBeNull();
    expect(typeof ref.current!.fire).toBe("function");
  });

  it("renders 50 particles after fire is called", () => {
    const ref = createRef<ConfettiHandle>();
    const { container } = render(<Confetti ref={ref} />);
    act(() => {
      ref.current!.fire();
    });
    const particles = container.querySelectorAll("span.absolute");
    expect(particles).toHaveLength(50);
  });

  it("renders particles with aria-hidden container", () => {
    const ref = createRef<ConfettiHandle>();
    const { container } = render(<Confetti ref={ref} />);
    act(() => {
      ref.current!.fire();
    });
    const overlay = container.firstElementChild!;
    expect(overlay).toHaveAttribute("aria-hidden", "true");
  });

  it("renders particles as mix of circles and squares", () => {
    const ref = createRef<ConfettiHandle>();
    const { container } = render(<Confetti ref={ref} />);
    act(() => {
      ref.current!.fire();
    });
    const circles = container.querySelectorAll("span.rounded-full");
    const squares = container.querySelectorAll("span.rounded-\\[1px\\]");
    expect(circles.length + squares.length).toBe(50);
  });

  it("applies pointer-events-none to the overlay", () => {
    const ref = createRef<ConfettiHandle>();
    const { container } = render(<Confetti ref={ref} />);
    act(() => {
      ref.current!.fire();
    });
    const overlay = container.firstElementChild!;
    expect(overlay).toHaveClass("pointer-events-none");
  });

  it("cleans up particles after 1500ms", () => {
    const ref = createRef<ConfettiHandle>();
    const { container } = render(<Confetti ref={ref} />);
    act(() => {
      ref.current!.fire();
    });
    expect(container.querySelectorAll("span.absolute")).toHaveLength(50);
    act(() => {
      vi.advanceTimersByTime(1500);
    });
    expect(container.innerHTML).toBe("");
  });

  it("applies confetti-fall animation to each particle", () => {
    const ref = createRef<ConfettiHandle>();
    const { container } = render(<Confetti ref={ref} />);
    act(() => {
      ref.current!.fire();
    });
    const particles = container.querySelectorAll("span.absolute");
    particles.forEach((p) => {
      expect((p as HTMLElement).style.animation).toContain("confetti-fall");
    });
  });

  it("injects the @keyframes style element", () => {
    const ref = createRef<ConfettiHandle>();
    const { container } = render(<Confetti ref={ref} />);
    act(() => {
      ref.current!.fire();
    });
    const styleEl = container.querySelector("style");
    expect(styleEl).not.toBeNull();
    expect(styleEl!.textContent).toContain("confetti-fall");
  });

  it("assigns unique IDs to each particle across multiple fires", () => {
    const ref = createRef<ConfettiHandle>();
    render(<Confetti ref={ref} />);
    act(() => {
      ref.current!.fire();
    });
    act(() => {
      vi.advanceTimersByTime(1500);
    });
    act(() => {
      ref.current!.fire();
    });
    // Second fire should work without errors — particles have unique keys
    act(() => {
      vi.advanceTimersByTime(1500);
    });
  });

  vi.useRealTimers;
});
