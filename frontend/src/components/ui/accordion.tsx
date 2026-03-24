"use client";

import { useCallback, useId, useState, type ReactNode } from "react";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface AccordionItem {
  /** Heading text displayed in the trigger row. */
  title: string;
  /** Content revealed when expanded. */
  content: ReactNode;
  /** Optional unique key — defaults to index. */
  key?: string;
}

interface AccordionProps {
  /** Collapsible section definitions. */
  items: AccordionItem[];
  /** Allow multiple sections open simultaneously. Defaults to false (single). */
  multiple?: boolean;
  /** Indices of sections open by default. */
  defaultOpen?: number[];
  /** Additional class names on the root container. */
  className?: string;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

/**
 * Collapsible content sections using CSS grid-template-rows animation.
 *
 * Height transitions are performed entirely via CSS: the inner wrapper
 * toggles between `grid-template-rows: 0fr` and `grid-template-rows: 1fr`,
 * with the child content in `overflow: hidden`. This approach requires
 * no JavaScript measurement of content height, eliminating layout thrash
 * during animation and producing smooth 200ms ease-out transitions at
 * any content size.
 *
 * The chevron indicator rotates 180 degrees on expansion. In single mode,
 * opening a new section automatically closes the previously open one.
 */
export function Accordion({
  items,
  multiple = false,
  defaultOpen = [],
  className = "",
}: AccordionProps) {
  const baseId = useId();
  const [openSet, setOpenSet] = useState<Set<number>>(
    () => new Set(defaultOpen),
  );

  const toggle = useCallback(
    (index: number) => {
      setOpenSet((prev) => {
        const next = new Set(prev);
        if (next.has(index)) {
          next.delete(index);
        } else {
          if (!multiple) next.clear();
          next.add(index);
        }
        return next;
      });
    },
    [multiple],
  );

  return (
    <div className={`divide-y divide-border-subtle ${className}`}>
      {items.map((item, i) => {
        const isOpen = openSet.has(i);
        const triggerId = `${baseId}-trigger-${i}`;
        const panelId = `${baseId}-panel-${i}`;
        return (
          <div key={item.key ?? i}>
            {/* Trigger */}
            <button
              id={triggerId}
              type="button"
              aria-expanded={isOpen}
              aria-controls={panelId}
              data-cursor="pointer"
              onClick={() => toggle(i)}
              className="flex w-full items-center justify-between gap-3 py-3 text-left text-xs font-medium text-text-primary hover:text-text-secondary transition-colors"
            >
              <span>{item.title}</span>
              <svg
                width="14"
                height="14"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
                className={`shrink-0 text-text-muted transition-transform duration-200 ${
                  isOpen ? "rotate-180" : ""
                }`}
                aria-hidden="true"
              >
                <path d="M6 9l6 6 6-6" />
              </svg>
            </button>

            {/* Collapsible panel — CSS grid animation */}
            <div
              id={panelId}
              role="region"
              aria-labelledby={triggerId}
              className="grid transition-[grid-template-rows] duration-200 ease-out"
              style={{
                gridTemplateRows: isOpen ? "1fr" : "0fr",
              }}
            >
              <div className="overflow-hidden">
                <div className="pb-3 text-xs text-text-secondary">
                  {item.content}
                </div>
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
}
