import type { ReactNode } from "react";

interface Breadcrumb {
  label: string;
  href?: string;
}

interface TopBarProps {
  /** Breadcrumb trail for the current view. */
  breadcrumbs: Breadcrumb[];
  /** Optional content rendered in the trailing slot (theme toggle, user menu, etc.). */
  trailing?: ReactNode;
}

/**
 * Top navigation bar for the Enterprise FizzBuzz Operations Center.
 * Renders the current location breadcrumb and provides a trailing
 * slot for global actions such as theme switching and user controls.
 */
export function TopBar({ breadcrumbs, trailing }: TopBarProps) {
  return (
    <header className="flex h-14 items-center justify-between border-b border-panel-700 bg-panel-900 px-6">
      <nav className="flex items-center gap-2 text-sm" aria-label="Breadcrumb">
        {breadcrumbs.map((crumb, index) => {
          const isLast = index === breadcrumbs.length - 1;
          return (
            <span key={crumb.label} className="flex items-center gap-2">
              {index > 0 && <span className="text-panel-600">/</span>}
              {isLast ? (
                <span className="text-panel-50 font-medium">{crumb.label}</span>
              ) : (
                <span className="text-panel-400">{crumb.label}</span>
              )}
            </span>
          );
        })}
      </nav>

      {trailing && <div className="flex items-center gap-4">{trailing}</div>}
    </header>
  );
}
