"use client";

import {
  createContext,
  useCallback,
  useContext,
  useId,
  useLayoutEffect,
  useRef,
  useState,
  type KeyboardEvent,
  type ReactNode,
} from "react";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface TabItem {
  /** Display label rendered in the tab trigger. */
  label: string;
  /** Content rendered when this tab is active. */
  content: ReactNode;
  /** Optional unique key — defaults to index. */
  key?: string;
}

interface TabsProps {
  /** Tab definitions. */
  items: TabItem[];
  /** Initially active tab index. Defaults to 0. */
  defaultIndex?: number;
  /** Controlled active index. Takes precedence over defaultIndex. */
  activeIndex?: number;
  /** Called when the active tab changes. */
  onChange?: (index: number) => void;
  /** Additional class names applied to the root container. */
  className?: string;
}

// ---------------------------------------------------------------------------
// Internal context — avoids prop drilling between TabList and TabPanels.
// ---------------------------------------------------------------------------

interface TabsContextValue {
  activeIndex: number;
  setActiveIndex: (index: number) => void;
  baseId: string;
  count: number;
}

const TabsContext = createContext<TabsContextValue | null>(null);

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

/**
 * Horizontal tab navigation implementing the WAI-ARIA Tabs pattern.
 *
 * The active tab indicator is a 2px amber bottom border that animates
 * smoothly to the newly selected tab via CSS transitions on `left` and
 * `width`. Keyboard navigation follows the ARIA authoring practices:
 * Arrow Left/Right moves focus between tabs, Home/End jumps to first/last,
 * and the focused tab is activated automatically on focus.
 *
 * Tab panels are rendered in place — only the active panel is visible.
 * Inactive panels remain in the DOM with `hidden` to preserve internal
 * component state across tab switches when needed.
 */
export function Tabs({
  items,
  defaultIndex = 0,
  activeIndex: controlledIndex,
  onChange,
  className = "",
}: TabsProps) {
  const baseId = useId();
  const [internalIndex, setInternalIndex] = useState(defaultIndex);

  const isControlled = controlledIndex !== undefined;
  const activeIndex = isControlled ? controlledIndex : internalIndex;

  const setActiveIndex = useCallback(
    (index: number) => {
      if (!isControlled) setInternalIndex(index);
      onChange?.(index);
    },
    [isControlled, onChange],
  );

  // Indicator position tracking
  const tabListRef = useRef<HTMLDivElement>(null);
  const [indicator, setIndicator] = useState({ left: 0, width: 0 });

  useLayoutEffect(() => {
    const tabList = tabListRef.current;
    if (!tabList) return;
    const activeTab = tabList.querySelector<HTMLElement>(
      `[data-tab-index="${activeIndex}"]`,
    );
    if (!activeTab) return;
    setIndicator({
      left: activeTab.offsetLeft,
      width: activeTab.offsetWidth,
    });
  }, [activeIndex, items.length]);

  // Keyboard handler — WAI-ARIA tab pattern
  const handleKeyDown = useCallback(
    (e: KeyboardEvent<HTMLDivElement>) => {
      const count = items.length;
      let next: number | null = null;

      switch (e.key) {
        case "ArrowRight":
          next = (activeIndex + 1) % count;
          break;
        case "ArrowLeft":
          next = (activeIndex - 1 + count) % count;
          break;
        case "Home":
          next = 0;
          break;
        case "End":
          next = count - 1;
          break;
        default:
          return;
      }

      e.preventDefault();
      setActiveIndex(next);

      // Move focus to the newly active tab trigger
      const tabList = tabListRef.current;
      if (tabList) {
        const target = tabList.querySelector<HTMLElement>(
          `[data-tab-index="${next}"]`,
        );
        target?.focus();
      }
    },
    [activeIndex, items.length, setActiveIndex],
  );

  return (
    <TabsContext.Provider
      value={{ activeIndex, setActiveIndex, baseId, count: items.length }}
    >
      <div className={className}>
        {/* Tab list */}
        <div
          ref={tabListRef}
          role="tablist"
          aria-orientation="horizontal"
          onKeyDown={handleKeyDown}
          className="relative flex border-b border-border-subtle"
        >
          {items.map((item, i) => {
            const isActive = i === activeIndex;
            const tabId = `${baseId}-tab-${i}`;
            const panelId = `${baseId}-panel-${i}`;
            return (
              <button
                key={item.key ?? i}
                id={tabId}
                role="tab"
                type="button"
                aria-selected={isActive}
                aria-controls={panelId}
                tabIndex={isActive ? 0 : -1}
                data-tab-index={i}
                data-cursor="pointer"
                onClick={() => setActiveIndex(i)}
                className={`relative px-4 py-2.5 text-xs font-medium transition-colors whitespace-nowrap ${
                  isActive
                    ? "text-text-primary"
                    : "text-text-muted hover:text-text-secondary"
                }`}
              >
                {item.label}
              </button>
            );
          })}

          {/* Animated indicator — 2px amber bar */}
          <span
            className="absolute bottom-0 h-0.5 bg-accent transition-all duration-200 ease-out"
            style={{ left: indicator.left, width: indicator.width }}
            aria-hidden="true"
          />
        </div>

        {/* Tab panels */}
        {items.map((item, i) => {
          const isActive = i === activeIndex;
          const tabId = `${baseId}-tab-${i}`;
          const panelId = `${baseId}-panel-${i}`;
          return (
            <div
              key={item.key ?? i}
              id={panelId}
              role="tabpanel"
              aria-labelledby={tabId}
              tabIndex={0}
              hidden={!isActive}
              className="pt-4 focus-visible:outline-none"
            >
              {item.content}
            </div>
          );
        })}
      </div>
    </TabsContext.Provider>
  );
}
