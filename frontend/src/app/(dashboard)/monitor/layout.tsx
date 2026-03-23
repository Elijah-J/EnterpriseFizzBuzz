/**
 * Monitor route group layout.
 *
 * Provides shared context for all monitoring subsystem pages including
 * Metrics, Traces, and Alerts (when implemented). The layout inherits
 * the DataProvider from the parent dashboard layout and adds a
 * monitor-specific navigation header.
 */
export default function MonitorLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3 border-b border-panel-700 pb-3">
        <span className="text-xs text-panel-500 uppercase tracking-wider">
          Monitor
        </span>
        <nav className="flex gap-1">
          <a
            href="/monitor/metrics"
            className="rounded px-2.5 py-1 text-xs font-medium bg-panel-800 text-panel-50 transition-colors"
          >
            Metrics
          </a>
          <a
            href="/monitor/traces"
            className="rounded px-2.5 py-1 text-xs font-medium bg-panel-800 text-panel-50 transition-colors"
          >
            Traces
          </a>
          <a
            href="/monitor/alerts"
            className="rounded px-2.5 py-1 text-xs font-medium bg-panel-800 text-panel-50 transition-colors"
          >
            Alerts
          </a>
        </nav>
      </div>
      {children}
    </div>
  );
}
