"use client";

import { usePathname } from "next/navigation";
import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { useReducedMotion } from "@/lib/hooks/use-reduced-motion";

interface PageTransitionProps {
  children: ReactNode;
}

/**
 * Page-level transition orchestrator for the Enterprise FizzBuzz Platform.
 *
 * Leverages the View Transitions API when available in the browser runtime
 * to deliver hardware-accelerated crossfade transitions between dashboard
 * pages. For browsers without View Transitions API support, a CSS-based
 * opacity crossfade fallback ensures consistent behavior across all
 * supported platforms.
 *
 * Transition timing:
 * - Exit phase: 150ms fade-out of the departing view
 * - Enter phase: 200ms fade-in of the arriving view
 *
 * All motion is suppressed when the user has enabled reduced-motion
 * preferences at the operating system level, in compliance with WCAG 2.1
 * Success Criterion 2.3.3.
 */
export function PageTransition({ children }: PageTransitionProps) {
  const pathname = usePathname();
  const reducedMotion = useReducedMotion();
  const prevPathname = useRef(pathname);
  const containerRef = useRef<HTMLDivElement>(null);
  const [phase, setPhase] = useState<"idle" | "exit" | "enter">("idle");
  const [supportsViewTransitions, setSupportsViewTransitions] = useState(false);

  useEffect(() => {
    setSupportsViewTransitions("startViewTransition" in document);
  }, []);

  const triggerFallbackTransition = useCallback(() => {
    if (reducedMotion) return;

    setPhase("exit");
    const exitTimer = setTimeout(() => {
      setPhase("enter");
      const enterTimer = setTimeout(() => {
        setPhase("idle");
      }, 200);
      return () => clearTimeout(enterTimer);
    }, 150);
    return () => clearTimeout(exitTimer);
  }, [reducedMotion]);

  useEffect(() => {
    if (pathname === prevPathname.current) return;
    prevPathname.current = pathname;

    if (reducedMotion) return;

    if (supportsViewTransitions) {
      // The View Transitions API handles the visual transition natively.
      // The browser captures a snapshot of the old state and crossfades
      // to the new state. CSS rules for ::view-transition pseudos are
      // defined in globals.css.
      (document as Document & { startViewTransition: (cb: () => void) => void })
        .startViewTransition(() => {
          // The DOM update is already committed by React at this point.
          // This callback signals the transition to capture the new state.
        });
    } else {
      triggerFallbackTransition();
    }
  }, [pathname, reducedMotion, supportsViewTransitions, triggerFallbackTransition]);

  const fallbackStyle: React.CSSProperties =
    phase === "exit"
      ? { opacity: 0, transition: "opacity 150ms ease-out" }
      : phase === "enter"
        ? { opacity: 1, transition: "opacity 200ms ease-in" }
        : { opacity: 1 };

  return (
    <div
      ref={containerRef}
      style={supportsViewTransitions && !reducedMotion ? undefined : fallbackStyle}
    >
      {children}
    </div>
  );
}
