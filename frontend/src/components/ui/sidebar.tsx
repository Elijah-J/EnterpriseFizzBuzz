"use client";

import { useState } from "react";

interface NavItem {
  label: string;
  href: string;
  active?: boolean;
}

interface SidebarProps {
  /** Navigation items rendered in the sidebar menu. */
  items: NavItem[];
  /** Optional handler invoked when a navigation item is selected. */
  onNavigate?: (href: string) => void;
}

/**
 * Collapsible sidebar navigation component for the FizzBuzz Operations Center.
 * Provides persistent access to all platform subsystems. Collapse state is
 * maintained locally; future iterations will persist preference to the
 * configuration management layer.
 */
export function Sidebar({ items, onNavigate }: SidebarProps) {
  const [collapsed, setCollapsed] = useState(false);

  return (
    <aside
      className={`flex flex-col border-r border-panel-700 bg-panel-900 transition-all duration-200 ${
        collapsed ? "w-16" : "w-64"
      }`}
    >
      {/* Header */}
      <div className="flex h-14 items-center justify-between border-b border-panel-700 px-4">
        {!collapsed && (
          <div className="flex items-center gap-1">
            <span className="text-sm font-semibold tracking-wide text-fizzbuzz-400">
              EFP
            </span>
            <span className="text-sm text-panel-400">Ops</span>
          </div>
        )}
        <button
          type="button"
          onClick={() => setCollapsed((prev) => !prev)}
          className="rounded p-1 text-panel-400 hover:bg-panel-800 hover:text-panel-200 transition-colors"
          aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
        >
          <svg
            xmlns="http://www.w3.org/2000/svg"
            width="16"
            height="16"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
          >
            {collapsed ? (
              <path d="M9 18l6-6-6-6" />
            ) : (
              <path d="M15 18l-6-6 6-6" />
            )}
          </svg>
        </button>
      </div>

      {/* Navigation */}
      <nav className="flex-1 p-2">
        {!collapsed && (
          <p className="px-2 py-1 text-xs text-panel-500 uppercase tracking-wider">
            Subsystems
          </p>
        )}
        <ul className="mt-1 space-y-0.5">
          {items.map((item) => (
            <li key={item.href}>
              <button
                type="button"
                onClick={() => onNavigate?.(item.href)}
                className={`flex w-full items-center rounded px-2 py-1.5 text-sm transition-colors ${
                  item.active
                    ? "bg-panel-800 text-panel-50"
                    : "text-panel-300 hover:bg-panel-800 hover:text-panel-100"
                }`}
                title={collapsed ? item.label : undefined}
              >
                {collapsed ? (
                  <span className="mx-auto text-xs font-medium">
                    {item.label.charAt(0)}
                  </span>
                ) : (
                  item.label
                )}
              </button>
            </li>
          ))}
        </ul>
      </nav>
    </aside>
  );
}
