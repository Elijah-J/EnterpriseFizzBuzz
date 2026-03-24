"use client";

import { useCallback, useEffect, useRef, useState } from "react";

/**
 * Konami Code detection hook.
 *
 * Listens for the classic directional input sequence
 * (Up Up Down Down Left Right Left Right B A) and returns an
 * activation state. Once activated, the state persists in
 * localStorage to survive page reloads and session boundaries.
 *
 * The hook uses a sliding window approach: each keydown event
 * advances or resets the sequence index. The full sequence must
 * be entered within a 5-second window to prevent false positives
 * from normal keyboard navigation.
 */

const KONAMI_SEQUENCE = [
  "ArrowUp",
  "ArrowUp",
  "ArrowDown",
  "ArrowDown",
  "ArrowLeft",
  "ArrowRight",
  "ArrowLeft",
  "ArrowRight",
  "KeyB",
  "KeyA",
];

const STORAGE_KEY = "efp-konami-activated";
const SEQUENCE_TIMEOUT_MS = 5_000;

interface UseKonamiResult {
  /** Whether the Konami code has been successfully entered. */
  activated: boolean;
  /** Resets activation state and clears localStorage. */
  reset: () => void;
}

export function useKonami(): UseKonamiResult {
  const [activated, setActivated] = useState(false);
  const indexRef = useRef(0);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Check localStorage on mount
  useEffect(() => {
    try {
      if (localStorage.getItem(STORAGE_KEY) === "true") {
        setActivated(true);
      }
    } catch {
      // localStorage unavailable — proceed without persistence
    }
  }, []);

  const handleKeyDown = useCallback(
    (e: KeyboardEvent) => {
      if (activated) return;

      // Ignore when focus is inside an input or textarea
      const tag = (e.target as HTMLElement)?.tagName;
      if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return;

      const expected = KONAMI_SEQUENCE[indexRef.current];

      if (e.code === expected) {
        indexRef.current++;

        // Reset timeout window
        if (timerRef.current) clearTimeout(timerRef.current);
        timerRef.current = setTimeout(() => {
          indexRef.current = 0;
        }, SEQUENCE_TIMEOUT_MS);

        // Check completion
        if (indexRef.current === KONAMI_SEQUENCE.length) {
          indexRef.current = 0;
          if (timerRef.current) clearTimeout(timerRef.current);
          setActivated(true);
          try {
            localStorage.setItem(STORAGE_KEY, "true");
          } catch {
            // Ignore storage errors
          }
        }
      } else {
        indexRef.current = 0;
      }
    },
    [activated],
  );

  useEffect(() => {
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [handleKeyDown]);

  const reset = useCallback(() => {
    setActivated(false);
    indexRef.current = 0;
    try {
      localStorage.removeItem(STORAGE_KEY);
    } catch {
      // Ignore storage errors
    }
  }, []);

  return { activated, reset };
}
