"use client";

import {
  useCallback,
  useEffect,
  useId,
  useRef,
  useState,
  type KeyboardEvent,
} from "react";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface SelectOption {
  label: string;
  value: string;
}

interface SelectProps {
  /** Available options. */
  options: SelectOption[];
  /** Currently selected value. */
  value: string;
  /** Called when the selection changes. */
  onChange: (value: string) => void;
  /** Placeholder shown when no value is selected. */
  placeholder?: string;
  /** Enable search/filter input for long option lists. */
  searchable?: boolean;
  /** Additional class names on the root container. */
  className?: string;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

/**
 * Custom dropdown select with keyboard navigation and optional search
 * filtering. Implements the WAI-ARIA Listbox pattern: the trigger is an
 * ARIA combobox, the dropdown is a listbox, and each option is an
 * option role element.
 *
 * Keyboard navigation: ArrowDown/ArrowUp moves the highlighted option,
 * Enter selects, Escape closes. When searchable is enabled, typing
 * filters the visible options in real time.
 *
 * The active option receives a surface-raised background with a 2px
 * amber left accent border, providing a consistent selection indicator
 * that aligns with the platform's accent vocabulary.
 */
export function Select({
  options,
  value,
  onChange,
  placeholder = "Select...",
  searchable = false,
  className = "",
}: SelectProps) {
  const baseId = useId();
  const [isOpen, setIsOpen] = useState(false);
  const [search, setSearch] = useState("");
  const [highlightIndex, setHighlightIndex] = useState(-1);

  const rootRef = useRef<HTMLDivElement>(null);
  const listRef = useRef<HTMLUListElement>(null);
  const searchRef = useRef<HTMLInputElement>(null);

  const selectedOption = options.find((o) => o.value === value);

  // Filter options based on search query
  const filteredOptions = search
    ? options.filter((o) =>
        o.label.toLowerCase().includes(search.toLowerCase()),
      )
    : options;

  // -----------------------------------------------------------------------
  // Open / close
  // -----------------------------------------------------------------------

  const open = useCallback(() => {
    setIsOpen(true);
    setSearch("");
    // Set initial highlight to the currently selected option
    const idx = options.findIndex((o) => o.value === value);
    setHighlightIndex(idx >= 0 ? idx : 0);
  }, [options, value]);

  const close = useCallback(() => {
    setIsOpen(false);
    setSearch("");
    setHighlightIndex(-1);
  }, []);

  const selectOption = useCallback(
    (optValue: string) => {
      onChange(optValue);
      close();
    },
    [onChange, close],
  );

  // -----------------------------------------------------------------------
  // Click outside
  // -----------------------------------------------------------------------

  useEffect(() => {
    if (!isOpen) return;
    function handleClick(e: Event) {
      if (rootRef.current && !rootRef.current.contains(e.target as Node)) {
        close();
      }
    }
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, [isOpen, close]);

  // Focus search input when dropdown opens
  useEffect(() => {
    if (isOpen && searchable) {
      requestAnimationFrame(() => searchRef.current?.focus());
    }
  }, [isOpen, searchable]);

  // Scroll highlighted item into view
  useEffect(() => {
    if (!isOpen || highlightIndex < 0) return;
    const list = listRef.current;
    if (!list) return;
    const item = list.children[highlightIndex] as HTMLElement | undefined;
    item?.scrollIntoView({ block: "nearest" });
  }, [isOpen, highlightIndex]);

  // -----------------------------------------------------------------------
  // Keyboard
  // -----------------------------------------------------------------------

  const handleKeyDown = useCallback(
    (e: KeyboardEvent<HTMLDivElement>) => {
      if (!isOpen) {
        if (e.key === "ArrowDown" || e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          open();
        }
        return;
      }

      switch (e.key) {
        case "ArrowDown":
          e.preventDefault();
          setHighlightIndex((prev) =>
            prev < filteredOptions.length - 1 ? prev + 1 : 0,
          );
          break;
        case "ArrowUp":
          e.preventDefault();
          setHighlightIndex((prev) =>
            prev > 0 ? prev - 1 : filteredOptions.length - 1,
          );
          break;
        case "Enter":
          e.preventDefault();
          if (
            highlightIndex >= 0 &&
            highlightIndex < filteredOptions.length
          ) {
            selectOption(filteredOptions[highlightIndex].value);
          }
          break;
        case "Escape":
          e.preventDefault();
          close();
          break;
        case "Home":
          e.preventDefault();
          setHighlightIndex(0);
          break;
        case "End":
          e.preventDefault();
          setHighlightIndex(filteredOptions.length - 1);
          break;
      }
    },
    [isOpen, filteredOptions, highlightIndex, open, close, selectOption],
  );

  // -----------------------------------------------------------------------
  // Render
  // -----------------------------------------------------------------------

  return (
    <div
      ref={rootRef}
      className={`relative ${className}`}
      onKeyDown={handleKeyDown}
    >
      {/* Trigger */}
      <button
        type="button"
        id={`${baseId}-trigger`}
        role="combobox"
        aria-expanded={isOpen}
        aria-haspopup="listbox"
        aria-controls={`${baseId}-listbox`}
        data-cursor="pointer"
        onClick={() => (isOpen ? close() : open())}
        className="flex w-full items-center justify-between gap-2 rounded border border-border-default bg-surface-raised px-3 py-1.5 text-xs transition-colors hover:border-panel-500"
      >
        <span
          className={`truncate ${selectedOption ? "text-text-primary" : "text-text-muted"}`}
        >
          {selectedOption ? selectedOption.label : placeholder}
        </span>
        <svg
          width="12"
          height="12"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          className={`shrink-0 transition-transform ${isOpen ? "rotate-180" : ""}`}
        >
          <path d="M6 9l6 6 6-6" />
        </svg>
      </button>

      {/* Dropdown */}
      {isOpen && (
        <div
          className="absolute z-50 mt-1 w-full min-w-[200px] rounded border border-border-default bg-surface-raised shadow-xl"
          role="presentation"
        >
          {/* Search input */}
          {searchable && (
            <div className="border-b border-border-subtle p-2">
              <input
                ref={searchRef}
                type="text"
                value={search}
                onChange={(e) => {
                  setSearch(e.target.value);
                  setHighlightIndex(0);
                }}
                placeholder="Search..."
                className="w-full rounded bg-surface-base px-2 py-1 text-xs text-text-primary placeholder-panel-500 outline-none border border-border-subtle focus:border-panel-500"
                aria-label="Filter options"
              />
            </div>
          )}

          {/* Options list */}
          <ul
            ref={listRef}
            id={`${baseId}-listbox`}
            role="listbox"
            aria-labelledby={`${baseId}-trigger`}
            className="max-h-60 overflow-y-auto py-1"
          >
            {filteredOptions.map((opt, i) => {
              const isSelected = opt.value === value;
              const isHighlighted = i === highlightIndex;
              return (
                <li
                  key={opt.value}
                  role="option"
                  aria-selected={isSelected}
                  data-cursor="pointer"
                  onClick={() => selectOption(opt.value)}
                  onMouseEnter={() => setHighlightIndex(i)}
                  className={`flex items-center px-3 py-1.5 text-xs cursor-pointer transition-colors ${
                    isHighlighted
                      ? "bg-surface-raised border-l-2 border-l-accent"
                      : "border-l-2 border-l-transparent"
                  } ${isSelected ? "text-text-primary font-medium" : "text-text-secondary"}`}
                >
                  {opt.label}
                </li>
              );
            })}
            {filteredOptions.length === 0 && (
              <li className="px-3 py-2 text-xs text-text-muted">
                No options match the current filter
              </li>
            )}
          </ul>
        </div>
      )}
    </div>
  );
}
