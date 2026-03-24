"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { Pagination } from "@/components/ui/pagination";
import { Reveal } from "@/components/ui/reveal";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs } from "@/components/ui/tabs";
import type { Alert } from "@/lib/data-providers";
import { useDataProvider } from "@/lib/data-providers";

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const REFRESH_INTERVAL_MS = 5_000;

const SEVERITY_ORDER: Record<Alert["severity"], number> = {
  critical: 0,
  warning: 1,
  info: 2,
};

const SEVERITY_STYLES: Record<
  Alert["severity"],
  { badge: string; border: string; dot: string }
> = {
  critical: {
    badge: "bg-red-500/20 text-red-400 border-red-500/30",
    border: "border-l-red-500",
    dot: "bg-red-500",
  },
  warning: {
    badge: "bg-yellow-500/20 text-yellow-400 border-yellow-500/30",
    border: "border-l-yellow-500",
    dot: "bg-yellow-500",
  },
  info: {
    badge: "bg-blue-500/20 text-blue-400 border-blue-500/30",
    border: "border-l-blue-500",
    dot: "bg-blue-500",
  },
};

type SeverityFilter = Alert["severity"] | "all";

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export default function AlertsPage() {
  const provider = useDataProvider();

  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [loading, setLoading] = useState(true);

  // Filter state
  const [severityFilter, setSeverityFilter] = useState<SeverityFilter>("all");
  const [subsystemFilter, setSubsystemFilter] = useState<string>("all");
  const [showAcknowledged, setShowAcknowledged] = useState(true);
  const [showSilenced, setShowSilenced] = useState(true);
  const [alertPage, setAlertPage] = useState(1);
  const ALERTS_PER_PAGE = 10;

  // -----------------------------------------------------------------------
  // Data fetching
  // -----------------------------------------------------------------------

  const fetchAlerts = useCallback(async () => {
    const data = await provider.getAlerts();
    setAlerts(data);
    setLoading(false);
  }, [provider]);

  useEffect(() => {
    fetchAlerts();
  }, [fetchAlerts]);

  useEffect(() => {
    const timer = setInterval(fetchAlerts, REFRESH_INTERVAL_MS);
    return () => clearInterval(timer);
  }, [fetchAlerts]);

  // -----------------------------------------------------------------------
  // Local state mutations (acknowledge / silence)
  // -----------------------------------------------------------------------

  const toggleAcknowledged = useCallback((alertId: string) => {
    setAlerts((prev) =>
      prev.map((a) =>
        a.id === alertId ? { ...a, acknowledged: !a.acknowledged } : a,
      ),
    );
  }, []);

  const toggleSilenced = useCallback((alertId: string) => {
    setAlerts((prev) =>
      prev.map((a) => (a.id === alertId ? { ...a, silenced: !a.silenced } : a)),
    );
  }, []);

  // -----------------------------------------------------------------------
  // Derived state
  // -----------------------------------------------------------------------

  const subsystems = useMemo(
    () => Array.from(new Set(alerts.map((a) => a.subsystem))).sort(),
    [alerts],
  );

  const filteredAlerts = useMemo(() => {
    let result = [...alerts];

    if (severityFilter !== "all") {
      result = result.filter((a) => a.severity === severityFilter);
    }
    if (subsystemFilter !== "all") {
      result = result.filter((a) => a.subsystem === subsystemFilter);
    }
    if (!showAcknowledged) {
      result = result.filter((a) => !a.acknowledged);
    }
    if (!showSilenced) {
      result = result.filter((a) => !a.silenced);
    }

    // Sort: severity first, then most recent
    result.sort((a, b) => {
      const severityDiff =
        SEVERITY_ORDER[a.severity] - SEVERITY_ORDER[b.severity];
      if (severityDiff !== 0) return severityDiff;
      return new Date(b.firedAt).getTime() - new Date(a.firedAt).getTime();
    });

    return result;
  }, [alerts, severityFilter, subsystemFilter, showAcknowledged, showSilenced]);

  const summary = useMemo(() => {
    const counts = { critical: 0, warning: 0, info: 0 };
    let acknowledged = 0;
    let silenced = 0;

    for (const alert of alerts) {
      counts[alert.severity]++;
      if (alert.acknowledged) acknowledged++;
      if (alert.silenced) silenced++;
    }

    return { counts, acknowledged, silenced, total: alerts.length };
  }, [alerts]);

  // -----------------------------------------------------------------------
  // Render
  // -----------------------------------------------------------------------

  if (loading) {
    return (
      <div className="flex h-64 items-center justify-center">
        <span className="text-xs text-text-muted">
          Connecting to alert management subsystem...
        </span>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Page header */}
      <div>
        <h1 className="text-xl font-bold tracking-tight text-text-primary">
          Alert Management
        </h1>
        <p className="mt-1 text-xs text-text-secondary">
          Centralized alert feed for the Enterprise FizzBuzz Platform. Alerts
          are generated by the monitoring subsystem when operational thresholds
          are breached. Auto-refreshes every 5 seconds.
        </p>
      </div>

      {/* Summary bar */}
      <div className="flex flex-wrap items-center gap-4 rounded-lg border border-border-subtle bg-surface-raised px-4 py-3">
        <div className="flex items-center gap-3 text-xs">
          <span className="flex items-center gap-1.5">
            <span className="h-2 w-2 rounded-full bg-red-500" />
            <span className="text-text-secondary">
              {summary.counts.critical} Critical
            </span>
          </span>
          <span className="text-panel-600">/</span>
          <span className="flex items-center gap-1.5">
            <span className="h-2 w-2 rounded-full bg-yellow-500" />
            <span className="text-text-secondary">
              {summary.counts.warning} Warning
            </span>
          </span>
          <span className="text-panel-600">/</span>
          <span className="flex items-center gap-1.5">
            <span className="h-2 w-2 rounded-full bg-blue-500" />
            <span className="text-text-secondary">
              {summary.counts.info} Info
            </span>
          </span>
        </div>
        <span className="text-panel-700">|</span>
        <div className="flex items-center gap-3 text-xs text-text-secondary">
          <span>{summary.acknowledged} Acknowledged</span>
          <span className="text-panel-600">/</span>
          <span>{summary.silenced} Silenced</span>
        </div>
      </div>

      {/* Filter bar */}
      <div className="flex flex-wrap items-center gap-3">
        {/* Severity filter — Tabs component */}
        <Tabs
          items={(["all", "critical", "warning", "info"] as const).map((sev) => ({
            label: sev === "all" ? `All (${summary.total})` : `${sev.charAt(0).toUpperCase() + sev.slice(1)} (${summary.counts[sev === "all" ? "critical" : sev]})`,
            content: null as unknown as React.ReactNode,
          }))}
          activeIndex={(["all", "critical", "warning", "info"] as const).indexOf(severityFilter)}
          onChange={(idx) => setSeverityFilter((["all", "critical", "warning", "info"] as const)[idx])}
          className="[&_[role=tabpanel]]:hidden [&_[role=tablist]]:border-0"
        />

        {/* Subsystem filter */}
        <select
          value={subsystemFilter}
          onChange={(e) => setSubsystemFilter(e.target.value)}
          className="rounded border border-border-subtle bg-surface-raised px-2.5 py-1 text-xs text-text-secondary outline-none focus:border-panel-500"
        >
          <option value="all">All Subsystems</option>
          {subsystems.map((s) => (
            <option key={s} value={s}>
              {s}
            </option>
          ))}
        </select>

        {/* Toggle filters */}
        <div className="flex items-center gap-3 ml-auto">
          <label className="flex items-center gap-1.5 text-xs text-text-secondary cursor-pointer">
            <input
              type="checkbox"
              checked={showAcknowledged}
              onChange={(e) => setShowAcknowledged(e.target.checked)}
              className="rounded border-border-default bg-surface-base text-fizz-400 focus:ring-0 focus:ring-offset-0 h-3 w-3"
            />
            Show Acknowledged
          </label>
          <label className="flex items-center gap-1.5 text-xs text-text-secondary cursor-pointer">
            <input
              type="checkbox"
              checked={showSilenced}
              onChange={(e) => setShowSilenced(e.target.checked)}
              className="rounded border-border-default bg-surface-base text-fizz-400 focus:ring-0 focus:ring-offset-0 h-3 w-3"
            />
            Show Silenced
          </label>
        </div>
      </div>

      {/* Alert feed */}
      <div className="space-y-3">
        {filteredAlerts.length === 0 && (
          <div className="flex h-32 items-center justify-center rounded-lg border border-border-subtle bg-surface-raised">
            <span className="text-xs text-text-muted">
              No alerts match the current filter criteria
            </span>
          </div>
        )}

        {filteredAlerts.slice((alertPage - 1) * ALERTS_PER_PAGE, alertPage * ALERTS_PER_PAGE).map((alert) => {
          const styles = SEVERITY_STYLES[alert.severity];

          return (
            <Card
              key={alert.id}
              className={`border-l-4 ${styles.border} ${
                alert.silenced ? "opacity-50" : ""
              } ${alert.acknowledged ? "opacity-75" : ""}`}
            >
              <CardContent className="py-3">
                <div className="flex items-start gap-3">
                  {/* Main content */}
                  <div className="flex-1 min-w-0">
                    {/* Badges row */}
                    <div className="flex flex-wrap items-center gap-2 mb-1.5">
                      <span
                        className={`rounded px-1.5 py-0.5 text-[10px] font-medium border ${styles.badge}`}
                      >
                        {alert.severity.toUpperCase()}
                      </span>
                      <span className="rounded bg-surface-base px-1.5 py-0.5 text-[10px] text-text-secondary border border-border-subtle">
                        {alert.subsystem}
                      </span>
                      {alert.acknowledged && (
                        <span className="rounded bg-surface-base px-1.5 py-0.5 text-[10px] text-text-muted border border-border-subtle">
                          Acknowledged
                        </span>
                      )}
                      {alert.silenced && (
                        <span className="rounded bg-surface-base px-1.5 py-0.5 text-[10px] text-text-muted border border-border-subtle">
                          Silenced
                        </span>
                      )}
                    </div>

                    {/* Title and description */}
                    <h3 className="text-sm font-medium text-text-primary">
                      {alert.title}
                    </h3>
                    <p className="text-xs text-text-secondary mt-1 leading-relaxed">
                      {alert.description}
                    </p>

                    {/* Timestamp */}
                    <p className="text-[10px] text-text-muted mt-2">
                      Fired {formatRelativeTime(alert.firedAt)}
                    </p>
                  </div>

                  {/* Action buttons */}
                  <div className="flex flex-col gap-1.5 shrink-0">
                    <button
                      type="button"
                      onClick={() => toggleAcknowledged(alert.id)}
                      className={`rounded px-2.5 py-1 text-[10px] font-medium border transition-colors ${
                        alert.acknowledged
                          ? "bg-fizz-400/20 text-fizz-400 border-fizz-400/30"
                          : "bg-surface-base text-text-secondary border-border-subtle hover:border-panel-500 hover:text-text-secondary"
                      }`}
                    >
                      {alert.acknowledged ? "Ack'd" : "Acknowledge"}
                    </button>
                    <button
                      type="button"
                      onClick={() => toggleSilenced(alert.id)}
                      className={`rounded px-2.5 py-1 text-[10px] font-medium border transition-colors ${
                        alert.silenced
                          ? "bg-yellow-500/20 text-yellow-400 border-yellow-500/30"
                          : "bg-surface-base text-text-secondary border-border-subtle hover:border-panel-500 hover:text-text-secondary"
                      }`}
                    >
                      {alert.silenced ? "Silenced" : "Silence"}
                    </button>
                  </div>
                </div>
              </CardContent>
            </Card>
          );
        })}

        {/* Pagination for large alert lists */}
        {filteredAlerts.length > ALERTS_PER_PAGE && (
          <div className="flex justify-center pt-2">
            <Pagination
              total={filteredAlerts.length}
              current={alertPage}
              onPageChange={setAlertPage}
              pageSize={ALERTS_PER_PAGE}
            />
          </div>
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function formatRelativeTime(isoString: string): string {
  const deltaMs = Date.now() - new Date(isoString).getTime();
  const seconds = Math.floor(deltaMs / 1000);
  if (seconds < 5) return "just now";
  if (seconds < 60) return `${seconds}s ago`;
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  return `${days}d ago`;
}
