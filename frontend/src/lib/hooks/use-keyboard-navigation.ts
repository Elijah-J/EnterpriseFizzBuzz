"use client";

import { useCallback, useEffect, useRef } from "react";
import { usePathname } from "next/navigation";

/**
 * Ordered route table for bracket-key page cycling.
 * Sequence matches the sidebar navigation hierarchy.
 */
const PAGE_ORDER = [
  "/",
  "/evaluate",
  "/monitor/health",
  "/monitor/metrics",
  "/monitor/traces",
  "/monitor/alerts",
  "/cache",
  "/monitor/consensus",
  "/monitor/sla",
  "/compliance",
  "/blockchain",
  "/analytics",
  "/configuration",
  "/audit",
  "/chaos",
  "/digital-twin",
  "/finops",
  "/quantum",
  "/evolution",
  "/federated-learning",
  "/archaeology",
];

interface UseKeyboardNavigationOptions {
  /** Callback to open the command palette search. */
  onOpenSearch: () => void;
  /** Callback to toggle the keyboard shortcut overlay. */
  onToggleOverlay: () => void;
  /** Navigation function for page changes. */
  navigate: (href: string) => void;
}

/**
 * Global keyboard navigation system for the Enterprise FizzBuzz Platform.
 *
 * Implements a vim-inspired shortcut vocabulary enabling operators to navigate
 * the entire dashboard without mouse interaction. This reduces mean time to
 * response (MTTR) during incident triage by eliminating cursor travel overhead.
 *
 * Shortcut bindings:
 * - j/k: Navigate between focusable cards on the current page
 * - h/l: Collapse/expand sidebar sections (reserved for future use)
 * - g g: Scroll to top of page
 * - G: Scroll to bottom of page
 * - /: Open command palette search
 * - ?: Toggle keyboard shortcut overlay
 * - [ / ]: Navigate to previous/next page in sidebar order
 * - Escape: Clear current focus and close overlays
 *
 * All shortcuts are automatically disabled when the active element is an
 * input, textarea, select, or contenteditable element to prevent interference
 * with data entry workflows.
 */
export function useKeyboardNavigation({
  onOpenSearch,
  onToggleOverlay,
  navigate,
}: UseKeyboardNavigationOptions) {
  const pathname = usePathname();
  const gPending = useRef(false);
  const gTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const isInputFocused = useCallback(() => {
    const el = document.activeElement;
    if (!el) return false;
    const tag = el.tagName.toLowerCase();
    if (tag === "input" || tag === "textarea" || tag === "select") return true;
    if ((el as HTMLElement).isContentEditable) return true;
    return false;
  }, []);

  const getCards = useCallback((): HTMLElement[] => {
    return Array.from(
      document.querySelectorAll<HTMLElement>("[data-card-index]")
    ).sort(
      (a, b) =>
        Number(a.dataset.cardIndex) - Number(b.dataset.cardIndex)
    );
  }, []);

  const getCurrentCardIndex = useCallback((): number => {
    const cards = getCards();
    const active = document.activeElement as HTMLElement;
    return cards.indexOf(active);
  }, [getCards]);

  const focusCard = useCallback(
    (index: number) => {
      const cards = getCards();
      if (cards.length === 0) return;
      const target = Math.max(0, Math.min(index, cards.length - 1));
      cards[target].focus();
    },
    [getCards]
  );

  const navigatePage = useCallback(
    (direction: -1 | 1) => {
      const currentIndex = PAGE_ORDER.indexOf(pathname);
      if (currentIndex === -1) return;
      const nextIndex =
        (currentIndex + direction + PAGE_ORDER.length) % PAGE_ORDER.length;
      navigate(PAGE_ORDER[nextIndex]);
    },
    [pathname, navigate]
  );

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (isInputFocused()) return;

      const key = e.key;

      // g g — double-tap g to scroll to top
      if (key === "g" && !e.metaKey && !e.ctrlKey && !e.altKey) {
        if (gPending.current) {
          e.preventDefault();
          window.scrollTo({ top: 0, behavior: "smooth" });
          gPending.current = false;
          if (gTimer.current) clearTimeout(gTimer.current);
          gTimer.current = null;
          return;
        }
        gPending.current = true;
        gTimer.current = setTimeout(() => {
          gPending.current = false;
          gTimer.current = null;
        }, 300);
        return;
      }

      // Reset g-pending on any other key
      if (gPending.current) {
        gPending.current = false;
        if (gTimer.current) clearTimeout(gTimer.current);
        gTimer.current = null;
      }

      switch (key) {
        case "j": {
          e.preventDefault();
          const current = getCurrentCardIndex();
          focusCard(current + 1);
          break;
        }
        case "k": {
          e.preventDefault();
          const current = getCurrentCardIndex();
          focusCard(current === -1 ? 0 : current - 1);
          break;
        }
        case "G": {
          if (!e.metaKey && !e.ctrlKey) {
            e.preventDefault();
            window.scrollTo({
              top: document.documentElement.scrollHeight,
              behavior: "smooth",
            });
          }
          break;
        }
        case "/": {
          e.preventDefault();
          onOpenSearch();
          break;
        }
        case "?": {
          e.preventDefault();
          onToggleOverlay();
          break;
        }
        case "[": {
          e.preventDefault();
          navigatePage(-1);
          break;
        }
        case "]": {
          e.preventDefault();
          navigatePage(1);
          break;
        }
        case "Escape": {
          (document.activeElement as HTMLElement)?.blur();
          break;
        }
      }
    };

    document.addEventListener("keydown", handler);
    return () => {
      document.removeEventListener("keydown", handler);
      if (gTimer.current) clearTimeout(gTimer.current);
    };
  }, [
    isInputFocused,
    getCurrentCardIndex,
    focusCard,
    navigatePage,
    onOpenSearch,
    onToggleOverlay,
  ]);
}
