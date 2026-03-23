"use client";

import { usePathname } from "next/navigation";
import Link from "next/link";

/**
 * Sub-navigation tabs for the Monitor route group. Provides persistent
 * tab-based navigation across Health, SLA, and future monitoring surfaces
 * without full page reloads.
 */
const MONITOR_TABS = [
  { label: "Health Matrix", href: "/monitor/health" },
  { label: "SLA Dashboard", href: "/monitor/sla" },
] as const;

export default function MonitorLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const pathname = usePathname();

  return (
    <div className="space-y-6">
      {/* Page header */}
      <div>
        <h1 className="text-2xl font-bold tracking-tight text-panel-50">
          Infrastructure Monitor
        </h1>
        <p className="mt-1 text-sm text-panel-400">
          Real-time operational visibility into all Enterprise FizzBuzz Platform
          subsystems, SLA compliance posture, and incident management.
        </p>
      </div>

      {/* Sub-navigation tabs */}
      <nav className="flex gap-1 border-b border-panel-700 pb-px">
        {MONITOR_TABS.map((tab) => {
          const isActive = pathname === tab.href;
          return (
            <Link
              key={tab.href}
              href={tab.href}
              className={`px-4 py-2 text-sm font-medium transition-colors rounded-t ${
                isActive
                  ? "bg-panel-800 text-panel-50 border border-panel-700 border-b-panel-800 -mb-px"
                  : "text-panel-400 hover:text-panel-200 hover:bg-panel-800/50"
              }`}
            >
              {tab.label}
            </Link>
          );
        })}
      </nav>

      {/* Active tab content */}
      {children}
    </div>
  );
}
