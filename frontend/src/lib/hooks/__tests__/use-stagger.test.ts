import { describe, it, expect } from "vitest";
import { renderHook } from "@testing-library/react";
import { useStagger } from "../use-stagger";

describe("useStagger", () => {
  it("returns an array with length matching count", () => {
    const { result } = renderHook(() => useStagger(5));
    expect(result.current).toHaveLength(5);
  });

  it("returns delays starting from 0 by default", () => {
    const { result } = renderHook(() => useStagger(3));
    expect(result.current[0]).toBe(0);
  });

  it("applies default 50ms increment between items", () => {
    const { result } = renderHook(() => useStagger(4));
    expect(result.current).toEqual([0, 50, 100, 150]);
  });

  it("applies custom baseDelay", () => {
    const { result } = renderHook(() => useStagger(3, { baseDelay: 100 }));
    expect(result.current).toEqual([100, 150, 200]);
  });

  it("applies custom increment", () => {
    const { result } = renderHook(() => useStagger(3, { increment: 30 }));
    expect(result.current).toEqual([0, 30, 60]);
  });

  it("applies both custom baseDelay and increment", () => {
    const { result } = renderHook(() =>
      useStagger(4, { baseDelay: 200, increment: 75 }),
    );
    expect(result.current).toEqual([200, 275, 350, 425]);
  });

  it("returns empty array for count of 0", () => {
    const { result } = renderHook(() => useStagger(0));
    expect(result.current).toEqual([]);
  });

  it("returns single element for count of 1", () => {
    const { result } = renderHook(() => useStagger(1));
    expect(result.current).toEqual([0]);
  });
});
