import type { ReactNode } from "react";
import { LiveIndicator } from "./live-indicator";

interface Breadcrumb {
  label: string;
  href?: string;
}

interface TopBarProps {
  /** Breadcrumb trail for the current view. */
  breadcrumbs: Breadcrumb[];
  /** Optional content rendered in the trailing slot (theme toggle, user menu, etc.). */
  trailing?: ReactNode;
  /** Callback triggered when the search trigger is activated. */
  onSearchClick?: () => void;
  /** Timestamp of the last telemetry data update, for the LiveIndicator. */
  lastUpdated?: number | null;
  /** Whether telemetry data is stale. */
  isDataStale?: boolean;
}

/**
 * Top navigation bar for the Enterprise FizzBuzz Operations Center.
 *
 * Renders the current location breadcrumb, operational status indicator,
 * and a keyboard-shortcut search trigger. The solid surface-base background
 * maintains the layered depth system — no glassmorphism, no blur, no
 * transparency effects that would compromise rendering performance or
 * visual clarity.
 */
export function TopBar({ breadcrumbs, trailing, onSearchClick, lastUpdated, isDataStale }: TopBarProps) {
  return (
    <header className="flex h-14 items-center justify-between border-b border-border-subtle bg-surface-base px-6">
      <nav className="flex items-center gap-2 text-sm" aria-label="Breadcrumb">
        {breadcrumbs.map((crumb, index) => {
          const isLast = index === breadcrumbs.length - 1;
          return (
            <span key={crumb.label} className="flex items-center gap-2">
              {index > 0 && <span className="text-text-muted">/</span>}
              {isLast ? (
                <span className="text-text-primary font-medium">
                  {crumb.label}
                </span>
              ) : (
                <span className="text-text-secondary">{crumb.label}</span>
              )}
            </span>
          );
        })}
      </nav>

      <div className="flex items-center gap-4">
        {/* Search trigger — keyboard shortcut hint */}
        {onSearchClick && (
          <button
            type="button"
            onClick={onSearchClick}
            className="inline-flex items-center gap-2 rounded bg-transparent text-text-muted hover:bg-surface-raised hover:text-text-secondary px-2.5 py-1.5 text-xs transition-colors duration-150"
            aria-label="Open command palette"
          >
            <svg
              width="14"
              height="14"
              viewBox="0 0 14 14"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.5"
              strokeLinecap="round"
              strokeLinejoin="round"
              aria-hidden={true}
            >
              <circle cx="6" cy="6" r="4.5" />
              <path d="M9.5 9.5 13 13" />
            </svg>
            <kbd className="font-mono text-[10px] text-text-muted border border-border-subtle rounded px-1 py-0.5">
              Cmd+K
            </kbd>
          </button>
        )}

        {/* Operational status — live temporal indicator */}
        <LiveIndicator lastUpdated={lastUpdated ?? null} isStale={isDataStale} />

        {trailing && <>{trailing}</>}
      </div>
    </header>
  );
}
