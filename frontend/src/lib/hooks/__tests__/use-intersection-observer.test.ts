import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderHook } from "@testing-library/react";
import { useIntersectionObserver } from "../use-intersection-observer";

describe("useIntersectionObserver", () => {
  const mockObserve = vi.fn();
  const mockDisconnect = vi.fn();

  beforeEach(() => {
    mockObserve.mockClear();
    mockDisconnect.mockClear();

    const MockIO = vi.fn((callback) => ({
      observe: mockObserve,
      unobserve: vi.fn(),
      disconnect: mockDisconnect,
      _callback: callback,
    }));

    Object.defineProperty(window, "IntersectionObserver", {
      writable: true,
      configurable: true,
      value: MockIO,
    });
  });

  it("returns a ref object", () => {
    const { result } = renderHook(() => useIntersectionObserver());
    expect(result.current.ref).toBeDefined();
    expect(result.current.ref.current).toBeNull();
  });

  it("returns isVisible as false initially", () => {
    const { result } = renderHook(() => useIntersectionObserver());
    expect(result.current.isVisible).toBe(false);
  });

  it("accepts rootMargin and threshold options without error", () => {
    expect(() => {
      renderHook(() => useIntersectionObserver({ rootMargin: "10px", threshold: 0.5 }));
    }).not.toThrow();
  });

  it("accepts triggerOnce option without error", () => {
    expect(() => {
      renderHook(() => useIntersectionObserver({ triggerOnce: true }));
    }).not.toThrow();
  });

  it("accepts triggerOnce false without error", () => {
    expect(() => {
      renderHook(() => useIntersectionObserver({ triggerOnce: false }));
    }).not.toThrow();
  });
});
