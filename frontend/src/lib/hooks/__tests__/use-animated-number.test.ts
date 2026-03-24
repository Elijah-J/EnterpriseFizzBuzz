import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { renderHook, act } from "@testing-library/react";
import { useAnimatedNumber } from "../use-animated-number";

// Default matchMedia mock returns matches: false (motion enabled)
// We test reduced motion by overriding matchMedia per test

describe("useAnimatedNumber", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("returns the initial value as a formatted string", () => {
    const { result } = renderHook(() => useAnimatedNumber(42));
    expect(result.current).toBe("42");
  });

  it("formats with specified decimal places", () => {
    const { result } = renderHook(() =>
      useAnimatedNumber(3.14159, { decimals: 2 }),
    );
    expect(result.current).toBe("3.14");
  });

  it("formats as currency when format is currency", () => {
    const { result } = renderHook(() =>
      useAnimatedNumber(1000, { format: "currency", decimals: 0 }),
    );
    expect(result.current).toBe("$1,000");
  });

  it("formats as percent when format is percent", () => {
    const { result } = renderHook(() =>
      useAnimatedNumber(75, { format: "percent", decimals: 0 }),
    );
    expect(result.current).toBe("75%");
  });

  it("returns the target value immediately when reduced motion is active", () => {
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

    const { result, rerender } = renderHook(
      ({ value }) => useAnimatedNumber(value),
      { initialProps: { value: 0 } },
    );
    act(() => {
      rerender({ value: 100 });
    });
    expect(result.current).toBe("100");

    Object.defineProperty(window, "matchMedia", {
      writable: true,
      value: originalMatchMedia,
    });
  });

  it("applies locale formatting with commas for large numbers", () => {
    const { result } = renderHook(() => useAnimatedNumber(12345));
    expect(result.current).toBe("12,345");
  });
});
