"use client";

import { useEffect, useMemo, useRef, useState } from "react";

// ---------------------------------------------------------------------------
// FizzBuzz Sequence Generator
// ---------------------------------------------------------------------------

function generateFizzBuzzSequence(count: number): string[] {
  const results: string[] = [];
  for (let i = 1; i <= count; i++) {
    if (i % 15 === 0) results.push("FizzBuzz");
    else if (i % 3 === 0) results.push("Fizz");
    else if (i % 5 === 0) results.push("Buzz");
    else results.push(String(i));
  }
  return results;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

/**
 * Resource Location Failure Interface (404 Page).
 *
 * Renders a full-screen error state for unresolvable routes. The large
 * Instrument Serif "404" heading establishes the error category, while
 * the subtitle explains the failure in operational terms. Below the
 * primary message, a continuously scrolling FizzBuzz evaluation sequence
 * provides ambient visual texture using muted text that reinforces
 * the platform's core domain.
 *
 * The grain overlay is applied to the background to maintain visual
 * continuity with the authenticated dashboard experience.
 */
export function FizzBuzz404() {
  const sequence = useMemo(() => generateFizzBuzzSequence(200), []);
  const scrollRef = useRef<HTMLDivElement>(null);
  const [scrollOffset, setScrollOffset] = useState(0);

  // Slow continuous scroll animation
  useEffect(() => {
    let animationId: number;
    let lastTime = performance.now();

    function tick(now: number) {
      const delta = now - lastTime;
      lastTime = now;
      setScrollOffset((prev) => (prev + delta * 0.015) % 2000);
      animationId = requestAnimationFrame(tick);
    }

    animationId = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(animationId);
  }, []);

  return (
    <div className="relative flex min-h-screen flex-col items-center justify-center overflow-hidden bg-surface-ground">
      {/* Grain overlay */}
      <div
        className="absolute inset-0 pointer-events-none z-[1]"
        style={{
          backgroundImage: "var(--texture-grain)",
          backgroundRepeat: "repeat",
          opacity: 0.03,
        }}
      />

      {/* Scrolling FizzBuzz sequence background */}
      <div
        ref={scrollRef}
        className="absolute inset-0 z-0 overflow-hidden opacity-[0.06]"
        aria-hidden="true"
      >
        <div
          className="flex flex-wrap gap-x-4 gap-y-2 justify-center px-8 py-8"
          style={{
            transform: `translateY(-${scrollOffset}px)`,
          }}
        >
          {sequence.concat(sequence).map((item, i) => (
            <span
              key={i}
              className={`text-sm font-mono ${
                item === "FizzBuzz"
                  ? "text-fizzbuzz-400"
                  : item === "Fizz"
                    ? "text-fizz-400"
                    : item === "Buzz"
                      ? "text-buzz-400"
                      : "text-text-muted"
              }`}
            >
              {item}
            </span>
          ))}
        </div>
      </div>

      {/* Primary content */}
      <div className="relative z-10 text-center px-6 max-w-lg">
        <h1
          className="text-[8rem] leading-none font-normal tracking-tight text-text-primary"
          style={{
            fontFamily: "var(--font-serif, var(--font-geist-sans)), serif",
          }}
        >
          404
        </h1>
        <p className="mt-4 text-lg text-text-secondary">
          The requested resource was not found in any registered evaluation
          pipeline.
        </p>
        <p className="mt-6 text-xs text-text-muted">
          The routing subsystem has exhausted all registered path matchers
          without producing a valid handler reference. Please verify the
          requested URL against the platform documentation.
        </p>
        <a
          href="/"
          className="mt-8 inline-flex items-center gap-2 rounded bg-accent px-4 py-2 text-sm font-medium text-text-inverse hover:bg-accent-hover transition-colors"
        >
          Return to Operations Center
        </a>
      </div>
    </div>
  );
}
