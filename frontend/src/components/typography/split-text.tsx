"use client";

import { useMemo } from "react";
import { useReducedMotion } from "@/lib/hooks/use-reduced-motion";

/**
 * Per-character text decomposition component for staggered reveal animations.
 *
 * Splits a text string into individual span elements, each receiving a
 * progressive animation delay. This enables the per-character entrance
 * effects used in hero-level display headings throughout the Enterprise
 * FizzBuzz Operations Center.
 *
 * Two animation modes are available:
 * - `fade`: Characters transition from transparent to opaque sequentially
 * - `slide`: Characters translate upward 8px while fading, producing a
 *   typewriter-meets-curtain-rise effect
 *
 * When `prefers-reduced-motion` is active, all characters render at full
 * opacity with zero delay — content is immediately accessible without
 * any animation overhead.
 */

interface SplitTextProps {
  /** The text string to decompose into animated characters. */
  text: string;
  /** Delay between each character's animation start, in milliseconds. */
  staggerMs?: number;
  /** Animation variant. `fade` for opacity-only, `slide` for opacity + translateY. */
  animation?: "fade" | "slide";
  /** Additional CSS class applied to the outer wrapper. */
  className?: string;
}

export function SplitText({
  text,
  staggerMs = 20,
  animation = "fade",
  className = "",
}: SplitTextProps) {
  const prefersReduced = useReducedMotion();

  const characters = useMemo(() => text.split(""), [text]);

  if (prefersReduced) {
    return <span className={className}>{text}</span>;
  }

  return (
    <span className={className} aria-label={text}>
      {characters.map((char, i) => (
        <span
          key={`${i}-${char}`}
          className={
            animation === "slide"
              ? "split-text-char split-text-slide"
              : "split-text-char split-text-fade"
          }
          style={{
            animationDelay: `${i * staggerMs}ms`,
          }}
          aria-hidden="true"
        >
          {char === " " ? "\u00A0" : char}
        </span>
      ))}
    </span>
  );
}
