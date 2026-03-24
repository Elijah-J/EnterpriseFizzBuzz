import { describe, it, expect, vi, afterEach } from "vitest";
import { renderHook } from "@testing-library/react";
import { useCursor } from "../use-cursor";

describe("useCursor", () => {
  afterEach(() => {
    // Restore default matchMedia (non-touch, no reduced motion)
    Object.defineProperty(window, "matchMedia", {
      writable: true,
      value: (query: string) => ({
        matches: false,
        media: query,
        onchange: null,
        addListener: () => {},
        removeListener: () => {},
        addEventListener: () => {},
        removeEventListener: () => {},
        dispatchEvent: () => false,
      }),
    });
  });

  it("returns position coordinates", () => {
    const { result } = renderHook(() => useCursor());
    expect(typeof result.current.x).toBe("number");
    expect(typeof result.current.y).toBe("number");
  });

  it("returns cursorState string", () => {
    const { result } = renderHook(() => useCursor());
    expect(["default", "pointer", "text"]).toContain(result.current.cursorState);
  });

  it("returns visible boolean", () => {
    const { result } = renderHook(() => useCursor());
    expect(typeof result.current.visible).toBe("boolean");
  });

  it("returns isHovering boolean", () => {
    const { result } = renderHook(() => useCursor());
    expect(typeof result.current.isHovering).toBe("boolean");
  });

  it("is not visible on touch devices", () => {
    // Simulate touch device
    Object.defineProperty(window, "ontouchstart", {
      writable: true,
      configurable: true,
      value: () => {},
    });
    const { result } = renderHook(() => useCursor());
    expect(result.current.visible).toBe(false);
    // Cleanup
    delete (window as unknown as Record<string, unknown>).ontouchstart;
  });

  it("accepts custom lerp factor", () => {
    expect(() => {
      renderHook(() => useCursor(0.25));
    }).not.toThrow();
  });
});
