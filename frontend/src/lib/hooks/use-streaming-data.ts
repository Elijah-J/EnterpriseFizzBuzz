"use client";

import { useCallback, useEffect, useRef, useState } from "react";

interface UseStreamingDataOptions<T> {
  /** Async function that fetches the latest data. */
  fetcher: () => Promise<T>;
  /** Polling interval in milliseconds. Default: 2000 */
  interval?: number;
  /** Extract a numeric value from the data for interpolation. */
  extractValue?: (data: T) => number;
}

interface StreamingDataResult<T> {
  /** The latest fetched data. Null until first fetch completes. */
  data: T | null;
  /** Smoothly interpolated numeric value between poll updates. */
  interpolatedValue: number;
  /** Whether the data is considered stale (no update in 2x interval). */
  isStale: boolean;
  /** Seconds since the last successful data update. */
  secondsSinceUpdate: number;
  /** Timestamp of the last successful fetch. */
  lastUpdated: number | null;
}

/**
 * Streaming data simulation hook for the Enterprise FizzBuzz Platform.
 *
 * Wraps a polling-based data fetcher with smooth value interpolation,
 * jitter reduction, and stale-data detection. This creates the perceptual
 * effect of continuous real-time streaming from the evaluation pipeline
 * telemetry endpoints.
 *
 * Value interpolation uses linear interpolation between the previous and
 * current poll values, distributing the delta across animation frames
 * between polls. Stale-data detection triggers after 2x the configured
 * poll interval has elapsed without a successful update, surfacing
 * temporal context to the operator.
 */
export function useStreamingData<T>({
  fetcher,
  interval = 2000,
  extractValue,
}: UseStreamingDataOptions<T>): StreamingDataResult<T> {
  const [data, setData] = useState<T | null>(null);
  const [isStale, setIsStale] = useState(false);
  const [secondsSinceUpdate, setSecondsSinceUpdate] = useState(0);
  const [lastUpdated, setLastUpdated] = useState<number | null>(null);
  const [interpolatedValue, setInterpolatedValue] = useState(0);

  const prevValue = useRef(0);
  const targetValue = useRef(0);
  const interpStart = useRef(0);
  const rafId = useRef(0);

  const doFetch = useCallback(async () => {
    try {
      const result = await fetcher();
      setData(result);
      setLastUpdated(Date.now());
      setIsStale(false);

      if (extractValue) {
        prevValue.current = targetValue.current;
        targetValue.current = extractValue(result);
        interpStart.current = Date.now();
      }
    } catch {
      // Fetch failure — data becomes stale naturally via the staleness timer
    }
  }, [fetcher, extractValue]);

  // Polling loop
  useEffect(() => {
    doFetch();
    const id = setInterval(doFetch, interval);
    return () => clearInterval(id);
  }, [doFetch, interval]);

  // Staleness detection timer
  useEffect(() => {
    const id = setInterval(() => {
      if (lastUpdated) {
        const elapsed = (Date.now() - lastUpdated) / 1000;
        setSecondsSinceUpdate(Math.floor(elapsed));
        setIsStale(elapsed > (interval * 2) / 1000);
      }
    }, 1000);
    return () => clearInterval(id);
  }, [lastUpdated, interval]);

  // Smooth value interpolation via requestAnimationFrame
  useEffect(() => {
    if (!extractValue) return;

    const animate = () => {
      const elapsed = Date.now() - interpStart.current;
      const progress = Math.min(elapsed / interval, 1);
      // Ease-out cubic for natural deceleration
      const eased = 1 - Math.pow(1 - progress, 3);
      const value =
        prevValue.current +
        (targetValue.current - prevValue.current) * eased;
      setInterpolatedValue(value);
      rafId.current = requestAnimationFrame(animate);
    };

    rafId.current = requestAnimationFrame(animate);
    return () => cancelAnimationFrame(rafId.current);
  }, [extractValue, interval]);

  return {
    data,
    interpolatedValue,
    isStale,
    secondsSinceUpdate,
    lastUpdated,
  };
}
