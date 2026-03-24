import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { renderHook, act } from "@testing-library/react";
import { useStreamingData } from "../use-streaming-data";

describe("useStreamingData", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("returns null data before first fetch completes", () => {
    const fetcher = vi.fn().mockResolvedValue({ value: 42 });
    const { result } = renderHook(() =>
      useStreamingData({ fetcher }),
    );
    expect(result.current.data).toBeNull();
  });

  it("returns fetched data after first poll", async () => {
    const fetcher = vi.fn().mockResolvedValue({ value: 42 });
    const { result } = renderHook(() =>
      useStreamingData({ fetcher }),
    );
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(result.current.data).toEqual({ value: 42 });
  });

  it("sets lastUpdated after successful fetch", async () => {
    const fetcher = vi.fn().mockResolvedValue({ count: 100 });
    const { result } = renderHook(() =>
      useStreamingData({ fetcher }),
    );
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(result.current.lastUpdated).toBeGreaterThan(0);
  });

  it("detects stale data after 2x interval without update", async () => {
    let callCount = 0;
    const fetcher = vi.fn().mockImplementation(async () => {
      callCount++;
      if (callCount === 1) return { v: 1 };
      throw new Error("fetch failed");
    });
    const { result } = renderHook(() =>
      useStreamingData({ fetcher, interval: 1000 }),
    );
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(result.current.isStale).toBe(false);
    // Advance past 2x interval + staleness check
    await act(async () => {
      await vi.advanceTimersByTimeAsync(3000);
    });
    expect(result.current.isStale).toBe(true);
  });

  it("calls fetcher on each poll interval", async () => {
    const fetcher = vi.fn().mockResolvedValue({ v: 1 });
    renderHook(() =>
      useStreamingData({ fetcher, interval: 2000 }),
    );
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(fetcher).toHaveBeenCalledTimes(1);
    await act(async () => {
      await vi.advanceTimersByTimeAsync(2000);
    });
    expect(fetcher).toHaveBeenCalledTimes(2);
  });

  it("tracks secondsSinceUpdate", async () => {
    const fetcher = vi.fn().mockResolvedValue({ v: 1 });
    const { result } = renderHook(() =>
      useStreamingData({ fetcher, interval: 5000 }),
    );
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(3000);
    });
    expect(result.current.secondsSinceUpdate).toBeGreaterThanOrEqual(2);
  });
});
