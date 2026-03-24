"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

interface PaletteItem {
  label: string;
  href?: string;
  section: "Navigation" | "Actions" | "Recent";
  action?: () => void;
  /** Keyboard shortcut hint displayed beside the item label. */
  shortcut?: string;
}

const RECENT_COMMANDS_KEY = "efp-recent-commands";
const MAX_RECENT = 5;

/**
 * Retrieves the most recently used command labels from localStorage.
 */
function getRecentCommands(): string[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = localStorage.getItem(RECENT_COMMANDS_KEY);
    return raw ? JSON.parse(raw) : [];
  } catch {
    return [];
  }
}

/**
 * Records a command label to the recent commands list in localStorage.
 * Maintains a rolling window of the last 5 unique commands.
 */
function recordRecentCommand(label: string): void {
  if (typeof window === "undefined") return;
  try {
    const recent = getRecentCommands().filter((l) => l !== label);
    recent.unshift(label);
    localStorage.setItem(
      RECENT_COMMANDS_KEY,
      JSON.stringify(recent.slice(0, MAX_RECENT))
    );
  } catch {
    // localStorage quota exceeded or unavailable — silent degradation
  }
}

interface CommandPaletteProps {
  /** Whether the palette overlay is visible. */
  open: boolean;
  /** Callback to close the palette. */
  onClose: () => void;
  /** Callback to toggle sidebar collapse state. */
  onToggleSidebar?: () => void;
}

/**
 * Command palette overlay for the Enterprise FizzBuzz Operations Center.
 *
 * Activated via Cmd+K (macOS) or Ctrl+K (Windows/Linux), this component
 * provides rapid keyboard-driven navigation across all 21 dashboard pages
 * and system actions. Results are grouped by section (Navigation, Actions)
 * with keyboard arrow navigation and Enter to select.
 *
 * The overlay uses a solid dark backdrop at 80% opacity rather than blur
 * effects, maintaining rendering performance and design consistency with
 * the Warm Precision visual language.
 *
 * Fuzzy matching is implemented as case-insensitive substring inclusion —
 * zero runtime dependencies, sufficient for the platform's navigation scope.
 */
export function CommandPalette({
  open,
  onClose,
  onToggleSidebar,
}: CommandPaletteProps) {
  const router = useRouter();
  const inputRef = useRef<HTMLInputElement>(null);
  const [query, setQuery] = useState("");
  const [activeIndex, setActiveIndex] = useState(0);

  const [recentLabels, setRecentLabels] = useState<string[]>([]);

  // Load recent commands on mount
  useEffect(() => {
    setRecentLabels(getRecentCommands());
  }, [open]);

  const navigationItems: PaletteItem[] = useMemo(
    () => [
      { label: "Dashboard", href: "/", section: "Navigation" },
      { label: "Evaluation Console", href: "/evaluate", section: "Navigation" },
      {
        label: "Infrastructure Monitor",
        href: "/monitor/health",
        section: "Navigation",
      },
      { label: "Metrics", href: "/monitor/metrics", section: "Navigation" },
      { label: "Traces", href: "/monitor/traces", section: "Navigation" },
      { label: "Alerts", href: "/monitor/alerts", section: "Navigation" },
      { label: "Cache Coherence", href: "/cache", section: "Navigation" },
      {
        label: "Consensus",
        href: "/monitor/consensus",
        section: "Navigation",
      },
      { label: "SLA Budget", href: "/monitor/sla", section: "Navigation" },
      { label: "Compliance", href: "/compliance", section: "Navigation" },
      { label: "Blockchain", href: "/blockchain", section: "Navigation" },
      { label: "Analytics", href: "/analytics", section: "Navigation" },
      {
        label: "Configuration",
        href: "/configuration",
        section: "Navigation",
      },
      { label: "Audit Log", href: "/audit", section: "Navigation" },
      { label: "Chaos Engineering", href: "/chaos", section: "Navigation" },
      { label: "Digital Twin", href: "/digital-twin", section: "Navigation" },
      { label: "FinOps", href: "/finops", section: "Navigation" },
      {
        label: "Quantum Workbench",
        href: "/quantum",
        section: "Navigation",
      },
      {
        label: "Evolution Observatory",
        href: "/evolution",
        section: "Navigation",
      },
      {
        label: "Federated Learning",
        href: "/federated-learning",
        section: "Navigation",
      },
      {
        label: "Archaeological Recovery",
        href: "/archaeology",
        section: "Navigation",
      },
    ],
    [],
  );

  const actionItems: PaletteItem[] = useMemo(
    () => [
      {
        label: "Toggle Sidebar",
        section: "Actions",
        action: onToggleSidebar,
        shortcut: "\u2318B",
      },
      {
        label: "Keyboard Shortcuts",
        section: "Actions",
        action: () => {
          // Dispatching a custom key event to trigger the overlay
          document.dispatchEvent(
            new KeyboardEvent("keydown", { key: "?" })
          );
        },
        shortcut: "?",
      },
      {
        label: "Refresh Data",
        section: "Actions",
        action: () => window.location.reload(),
      },
    ],
    [onToggleSidebar],
  );

  const allItems: PaletteItem[] = useMemo(() => {
    const allNav = [...navigationItems, ...actionItems];
    // Build Recent section from stored labels
    const recentItems: PaletteItem[] = [];
    for (const label of recentLabels) {
      const found = allNav.find((item) => item.label === label);
      if (found) {
        recentItems.push({ ...found, section: "Recent" });
      }
    }

    return [...recentItems, ...navigationItems, ...actionItems];
  }, [navigationItems, actionItems, recentLabels]);

  const filtered = useMemo(() => {
    if (!query.trim()) return allItems;
    const lower = query.toLowerCase();
    return allItems.filter((item) => item.label.toLowerCase().includes(lower));
  }, [query, allItems]);

  const grouped = useMemo(() => {
    const sections: Record<string, PaletteItem[]> = {};
    for (const item of filtered) {
      if (!sections[item.section]) sections[item.section] = [];
      sections[item.section].push(item);
    }
    return sections;
  }, [filtered]);

  const selectItem = useCallback(
    (item: PaletteItem) => {
      recordRecentCommand(item.label);
      if (item.href) {
        router.push(item.href);
      } else if (item.action) {
        item.action();
      }
      onClose();
    },
    [router, onClose],
  );

  // Reset state when opened
  useEffect(() => {
    if (open) {
      setQuery("");
      setActiveIndex(0);
      // Focus input after animation frame
      requestAnimationFrame(() => inputRef.current?.focus());
    }
  }, [open]);

  // Keyboard navigation
  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key === "ArrowDown") {
        e.preventDefault();
        setActiveIndex((prev) => Math.min(prev + 1, filtered.length - 1));
      } else if (e.key === "ArrowUp") {
        e.preventDefault();
        setActiveIndex((prev) => Math.max(prev - 1, 0));
      } else if (e.key === "Enter" && filtered[activeIndex]) {
        e.preventDefault();
        selectItem(filtered[activeIndex]);
      } else if (e.key === "Escape") {
        e.preventDefault();
        onClose();
      }
    },
    [filtered, activeIndex, selectItem, onClose],
  );

  // Reset active index when query changes
  // biome-ignore lint/correctness/useExhaustiveDependencies: query is the intentional trigger for resetting the index
  useEffect(() => {
    setActiveIndex(0);
  }, [query]);

  if (!open) return null;

  let flatIndex = 0;

  return (
    <div
      className="fixed inset-0 z-50 flex items-start justify-center pt-[20vh]"
      style={{ animation: "enter 150ms ease-out" }}
    >
      {/* Backdrop — solid dark, not blur */}
      {/* biome-ignore lint/a11y/useKeyWithClickEvents: Backdrop dismiss on click is standard palette UX */}
      {/* biome-ignore lint/a11y/noStaticElementInteractions: Backdrop overlay uses click for standard dismiss pattern */}
      <div
        className="absolute inset-0 bg-surface-ground/80"
        onClick={onClose}
      />

      {/* Dialog */}
      <div
        className="relative w-full max-w-lg rounded-lg border border-border-subtle bg-surface-base overflow-hidden"
        role="dialog"
        aria-modal="true"
        aria-label="Command palette"
        onKeyDown={handleKeyDown}
      >
        {/* Search input */}
        <div className="border-b border-border-subtle px-4 py-3">
          <input
            ref={inputRef}
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search pages and actions..."
            className="w-full bg-transparent text-sm text-text-primary placeholder:text-text-muted focus:outline-none"
          />
        </div>

        {/* Results */}
        <div className="max-h-80 overflow-y-auto py-2">
          {Object.entries(grouped).map(([section, items]) => (
            <div key={section}>
              <p className="heading-section px-4 py-1">{section}</p>
              <ul>
                {items.map((item) => {
                  const currentIndex = flatIndex;
                  flatIndex++;
                  const isActive = currentIndex === activeIndex;
                  return (
                    <li key={item.label}>
                      <button
                        type="button"
                        className={`w-full text-left px-4 py-2 text-sm transition-colors duration-150 flex items-center gap-2 ${
                          isActive
                            ? "bg-surface-raised text-text-primary border-l-2 border-l-[var(--accent)]"
                            : "text-text-secondary hover:bg-surface-raised"
                        }`}
                        onClick={() => selectItem(item)}
                        onMouseEnter={() => setActiveIndex(currentIndex)}
                      >
                        <span className="flex-1 truncate">{item.label}</span>
                        {item.shortcut && (
                          <kbd className="shrink-0 font-mono text-[10px] text-text-muted border border-border-subtle rounded px-1 py-0.5">
                            {item.shortcut}
                          </kbd>
                        )}
                      </button>
                    </li>
                  );
                })}
              </ul>
            </div>
          ))}
          {filtered.length === 0 && (
            <p className="px-4 py-6 text-sm text-text-muted text-center">
              No results found.
            </p>
          )}
        </div>
      </div>
    </div>
  );
}
