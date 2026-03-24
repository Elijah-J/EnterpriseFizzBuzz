"use client";

import { useEffect, useRef, useState } from "react";

/**
 * Configuration for the IntersectionObserver wrapper.
 */
interface UseIntersectionObserverOptions {
  /** Viewport margin for triggering intersection. Default "0px". */
  rootMargin?: string;
  /** Visibility fraction required to trigger. Default 0.1 (10%). */
  threshold?: number;
  /** If true, observation stops after the first intersection. Default true. */
  triggerOnce?: boolean;
}

/**
 * Wraps the IntersectionObserver API into a declarative hook for
 * visibility-triggered behavior. Returns a ref to attach to the
 * observed element and a boolean indicating current visibility state.
 *
 * By default, the observer disconnects after the first intersection
 * (`triggerOnce: true`), which is the correct behavior for entrance
 * animations that should not replay on scroll reversal.
 */
export function useIntersectionObserver<T extends HTMLElement = HTMLDivElement>(
  options: UseIntersectionObserverOptions = {},
): { ref: React.RefObject<T | null>; isVisible: boolean } {
  const { rootMargin = "0px", threshold = 0.1, triggerOnce = true } = options;
  const ref = useRef<T | null>(null);
  const [isVisible, setIsVisible] = useState(false);

  useEffect(() => {
    const element = ref.current;
    if (!element) return;

    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          setIsVisible(true);
          if (triggerOnce) {
            observer.disconnect();
          }
        } else if (!triggerOnce) {
          setIsVisible(false);
        }
      },
      { rootMargin, threshold },
    );

    observer.observe(element);

    return () => observer.disconnect();
  }, [rootMargin, threshold, triggerOnce]);

  return { ref, isVisible };
}
