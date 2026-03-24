"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { Accordion } from "@/components/ui/accordion";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { CopyButton } from "@/components/ui/copy-button";
import { Dialog } from "@/components/ui/dialog";
import { Reveal } from "@/components/ui/reveal";
import { Skeleton } from "@/components/ui/skeleton";
import type {
  ConfigCategory,
  ConfigItem,
  FeatureFlag,
  FeatureFlagLifecycle,
} from "@/lib/data-providers";
import { useDataProvider } from "@/lib/data-providers";

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const REFRESH_INTERVAL_MS = 30_000;

const CATEGORY_TABS: {
  label: string;
  value: ConfigCategory | "feature_flags_tab";
}[] = [
  { label: "Evaluation", value: "evaluation" },
  { label: "Cache", value: "cache" },
  { label: "Compliance", value: "compliance" },
  { label: "Chaos Engineering", value: "chaos" },
  { label: "Blockchain", value: "blockchain" },
  { label: "ML", value: "ml" },
  { label: "Rate Limiting", value: "rate_limiting" },
  { label: "SLA", value: "sla" },
  { label: "Service Mesh", value: "service_mesh" },
  { label: "Observability", value: "observability" },
  { label: "Persistence", value: "persistence" },
  { label: "Feature Flags", value: "feature_flags_tab" },
];

const LIFECYCLE_BADGE_VARIANT: Record<
  FeatureFlagLifecycle,
  "error" | "warning" | "info" | "success"
> = {
  development: "info",
  testing: "warning",
  canary: "warning",
  ga: "success",
  deprecated: "error",
};

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function relativeTime(isoString: string): string {
  const now = Date.now();
  const then = new Date(isoString).getTime();
  const diffMs = now - then;
  const absDiffMs = Math.abs(diffMs);
  const inFuture = diffMs < 0;

  const seconds = Math.floor(absDiffMs / 1000);
  const minutes = Math.floor(seconds / 60);
  const hours = Math.floor(minutes / 60);
  const days = Math.floor(hours / 24);

  let label: string;
  if (days > 0) label = `${days}d`;
  else if (hours > 0) label = `${hours}h`;
  else if (minutes > 0) label = `${minutes}m`;
  else label = `${seconds}s`;

  return inFuture ? `in ${label}` : `${label} ago`;
}

// ---------------------------------------------------------------------------
// Pending change tracking
// ---------------------------------------------------------------------------

interface PendingChange {
  id: string;
  label: string;
  before: string;
  after: string;
  type: "config" | "flag";
}

// ---------------------------------------------------------------------------
// Page Component
// ---------------------------------------------------------------------------

export default function ConfigurationManagementPage() {
  const provider = useDataProvider();

  // Data state
  const [configItems, setConfigItems] = useState<ConfigItem[]>([]);
  const [featureFlags, setFeatureFlags] = useState<FeatureFlag[]>([]);

  // UI state
  const [activeTab, setActiveTab] = useState<
    ConfigCategory | "feature_flags_tab"
  >("evaluation");
  const [searchQuery, setSearchQuery] = useState("");

  // Pending changes — keyed by item/flag id
  const [pendingConfigChanges, setPendingConfigChanges] = useState<
    Map<string, { before: string; after: string }>
  >(new Map());
  const [pendingFlagChanges, setPendingFlagChanges] = useState<
    Map<
      string,
      {
        beforeEnabled: boolean;
        afterEnabled: boolean;
        beforeRollout: number;
        afterRollout: number;
      }
    >
  >(new Map());

  // Applying state
  const [applying, setApplying] = useState(false);

  // -----------------------------------------------------------------------
  // Data fetching
  // -----------------------------------------------------------------------

  const fetchData = useCallback(async () => {
    const [config, flags] = await Promise.all([
      provider.getConfiguration(),
      provider.getFeatureFlags(),
    ]);

    // Merge pending changes into fetched data so local edits are preserved
    setConfigItems((prev) => {
      const merged = config.map((item) => {
        const pending = pendingConfigChanges.get(item.id);
        if (pending) {
          return { ...item, value: pending.after };
        }
        return item;
      });
      return merged;
    });

    setFeatureFlags((prev) => {
      const merged = flags.map((flag) => {
        const pending = pendingFlagChanges.get(flag.id);
        if (pending) {
          return {
            ...flag,
            enabled: pending.afterEnabled,
            rolloutPercentage: pending.afterRollout,
          };
        }
        return flag;
      });
      return merged;
    });
  }, [provider, pendingConfigChanges, pendingFlagChanges]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  useEffect(() => {
    const timer = setInterval(fetchData, REFRESH_INTERVAL_MS);
    return () => clearInterval(timer);
  }, [fetchData]);

  // -----------------------------------------------------------------------
  // Pending changes aggregation
  // -----------------------------------------------------------------------

  const pendingChanges = useMemo((): PendingChange[] => {
    const changes: PendingChange[] = [];

    pendingConfigChanges.forEach((change, id) => {
      const item = configItems.find((i) => i.id === id);
      changes.push({
        id,
        label: item?.name ?? id,
        before: change.before,
        after: change.after,
        type: "config",
      });
    });

    pendingFlagChanges.forEach((change, id) => {
      const flag = featureFlags.find((f) => f.id === id);
      const parts: string[] = [];
      const beforeParts: string[] = [];
      if (change.beforeEnabled !== change.afterEnabled) {
        beforeParts.push(`enabled: ${change.beforeEnabled}`);
        parts.push(`enabled: ${change.afterEnabled}`);
      }
      if (change.beforeRollout !== change.afterRollout) {
        beforeParts.push(`rollout: ${change.beforeRollout}%`);
        parts.push(`rollout: ${change.afterRollout}%`);
      }
      changes.push({
        id,
        label: `${flag?.name ?? id} (flag)`,
        before: beforeParts.join(", "),
        after: parts.join(", "),
        type: "flag",
      });
    });

    return changes;
  }, [pendingConfigChanges, pendingFlagChanges, configItems, featureFlags]);

  // -----------------------------------------------------------------------
  // Change handlers
  // -----------------------------------------------------------------------

  function handleConfigChange(item: ConfigItem, newValue: string) {
    // Find original value from the saved state
    const originalValue = pendingConfigChanges.has(item.id)
      ? pendingConfigChanges.get(item.id)!.before
      : item.value;

    if (newValue === originalValue) {
      // Revert to original — remove from pending
      setPendingConfigChanges((prev) => {
        const next = new Map(prev);
        next.delete(item.id);
        return next;
      });
    } else {
      setPendingConfigChanges((prev) => {
        const next = new Map(prev);
        const before = prev.has(item.id)
          ? prev.get(item.id)!.before
          : item.value;
        next.set(item.id, { before, after: newValue });
        return next;
      });
    }

    // Update local display state
    setConfigItems((prev) =>
      prev.map((i) => (i.id === item.id ? { ...i, value: newValue } : i)),
    );
  }

  function handleFlagToggle(flag: FeatureFlag, enabled: boolean) {
    const originalEnabled = pendingFlagChanges.has(flag.id)
      ? pendingFlagChanges.get(flag.id)!.beforeEnabled
      : flag.enabled;
    const originalRollout = pendingFlagChanges.has(flag.id)
      ? pendingFlagChanges.get(flag.id)!.beforeRollout
      : flag.rolloutPercentage;
    const currentRollout = pendingFlagChanges.has(flag.id)
      ? pendingFlagChanges.get(flag.id)!.afterRollout
      : flag.rolloutPercentage;

    if (enabled === originalEnabled && currentRollout === originalRollout) {
      setPendingFlagChanges((prev) => {
        const next = new Map(prev);
        next.delete(flag.id);
        return next;
      });
    } else {
      setPendingFlagChanges((prev) => {
        const next = new Map(prev);
        next.set(flag.id, {
          beforeEnabled: originalEnabled,
          afterEnabled: enabled,
          beforeRollout: originalRollout,
          afterRollout: currentRollout,
        });
        return next;
      });
    }

    setFeatureFlags((prev) =>
      prev.map((f) => (f.id === flag.id ? { ...f, enabled } : f)),
    );
  }

  function handleFlagRollout(flag: FeatureFlag, rolloutPercentage: number) {
    const originalEnabled = pendingFlagChanges.has(flag.id)
      ? pendingFlagChanges.get(flag.id)!.beforeEnabled
      : flag.enabled;
    const originalRollout = pendingFlagChanges.has(flag.id)
      ? pendingFlagChanges.get(flag.id)!.beforeRollout
      : flag.rolloutPercentage;
    const currentEnabled = pendingFlagChanges.has(flag.id)
      ? pendingFlagChanges.get(flag.id)!.afterEnabled
      : flag.enabled;

    if (
      currentEnabled === originalEnabled &&
      rolloutPercentage === originalRollout
    ) {
      setPendingFlagChanges((prev) => {
        const next = new Map(prev);
        next.delete(flag.id);
        return next;
      });
    } else {
      setPendingFlagChanges((prev) => {
        const next = new Map(prev);
        next.set(flag.id, {
          beforeEnabled: originalEnabled,
          afterEnabled: currentEnabled,
          beforeRollout: originalRollout,
          afterRollout: rolloutPercentage,
        });
        return next;
      });
    }

    setFeatureFlags((prev) =>
      prev.map((f) => (f.id === flag.id ? { ...f, rolloutPercentage } : f)),
    );
  }

  // -----------------------------------------------------------------------
  // Apply / Discard
  // -----------------------------------------------------------------------

  async function handleApply() {
    setApplying(true);
    try {
      // Apply config changes sequentially
      for (const [itemId, change] of pendingConfigChanges) {
        const result = await provider.updateConfigItem(itemId, change.after);
        if (!result.success) {
          console.error(`Failed to update ${itemId}: ${result.error}`);
        }
      }

      // Apply flag changes sequentially
      for (const [flagId, change] of pendingFlagChanges) {
        const result = await provider.toggleFeatureFlag(
          flagId,
          change.afterEnabled,
          change.afterRollout,
        );
        if (!result.success) {
          console.error(`Failed to toggle ${flagId}: ${result.error}`);
        }
      }

      // Clear pending changes
      setPendingConfigChanges(new Map());
      setPendingFlagChanges(new Map());

      // Re-fetch
      const [config, flags] = await Promise.all([
        provider.getConfiguration(),
        provider.getFeatureFlags(),
      ]);
      setConfigItems(config);
      setFeatureFlags(flags);
    } finally {
      setApplying(false);
    }
  }

  function handleDiscard() {
    // Revert config items to their original values
    setConfigItems((prev) =>
      prev.map((item) => {
        const pending = pendingConfigChanges.get(item.id);
        if (pending) {
          return { ...item, value: pending.before };
        }
        return item;
      }),
    );

    // Revert flags to their original values
    setFeatureFlags((prev) =>
      prev.map((flag) => {
        const pending = pendingFlagChanges.get(flag.id);
        if (pending) {
          return {
            ...flag,
            enabled: pending.beforeEnabled,
            rolloutPercentage: pending.beforeRollout,
          };
        }
        return flag;
      }),
    );

    setPendingConfigChanges(new Map());
    setPendingFlagChanges(new Map());
  }

  // -----------------------------------------------------------------------
  // Derived state
  // -----------------------------------------------------------------------

  const isFeatureFlagsTab = activeTab === "feature_flags_tab";

  const filteredConfigItems = useMemo(() => {
    let items = configItems;
    if (!isFeatureFlagsTab) {
      items = items.filter((item) => item.category === activeTab);
    }
    if (searchQuery) {
      const q = searchQuery.toLowerCase();
      items = items.filter(
        (item) =>
          item.name.toLowerCase().includes(q) ||
          item.id.toLowerCase().includes(q) ||
          item.description.toLowerCase().includes(q),
      );
    }
    return items;
  }, [configItems, activeTab, searchQuery, isFeatureFlagsTab]);

  const filteredFlags = useMemo(() => {
    if (!isFeatureFlagsTab) return [];
    let flags = featureFlags;
    if (searchQuery) {
      const q = searchQuery.toLowerCase();
      flags = flags.filter(
        (flag) =>
          flag.name.toLowerCase().includes(q) ||
          flag.id.toLowerCase().includes(q) ||
          flag.description.toLowerCase().includes(q),
      );
    }
    return flags;
  }, [featureFlags, isFeatureFlagsTab, searchQuery]);

  // -----------------------------------------------------------------------
  // Render
  // -----------------------------------------------------------------------

  return (
    <div className="space-y-6">
      {/* Page header */}
      <div>
        <h1 className="text-xl font-bold tracking-tight text-text-primary">
          Configuration Management
        </h1>
        <p className="mt-1 text-xs text-text-secondary">
          Centralized parameter governance for all platform subsystems. Changes
          are staged locally, reviewed in the pending changes panel, and applied
          atomically.
        </p>
      </div>

      {/* Category tabs */}
      <div className="border-b border-border-subtle overflow-x-auto">
        <div className="flex gap-0">
          {CATEGORY_TABS.map((tab) => (
            <button
              key={tab.value}
              onClick={() => setActiveTab(tab.value)}
              className={`whitespace-nowrap px-4 py-2 text-xs font-medium transition-colors border-b-2 ${
                activeTab === tab.value
                  ? "border-fizzbuzz-400 text-fizzbuzz-400"
                  : "border-transparent text-text-secondary hover:text-text-secondary"
              }`}
            >
              {tab.label}
            </button>
          ))}
        </div>
      </div>

      {/* Search bar */}
      <div>
        <input
          type="text"
          placeholder="Search configuration items..."
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          className="w-full rounded-md border border-border-default bg-surface-raised px-3 py-2 text-sm text-text-secondary placeholder:text-text-muted focus:border-fizzbuzz-400 focus:outline-none focus:ring-1 focus:ring-fizzbuzz-400"
        />
      </div>

      {/* Configuration items form (non-feature-flag tabs) */}
      {!isFeatureFlagsTab && (
        <Card>
          <CardContent>
            <div className="divide-y divide-panel-700">
              {filteredConfigItems.length === 0 && (
                <p className="py-4 text-center text-xs text-text-muted">
                  No configuration items match the current filter.
                </p>
              )}
              {filteredConfigItems.map((item) => {
                const isPending = pendingConfigChanges.has(item.id);
                return (
                  <div
                    key={item.id}
                    className={`py-3 ${isPending ? "border-l-2 border-l-amber-400 pl-3" : ""}`}
                  >
                    <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2">
                      <div className="flex items-center gap-2">
                        <span className="text-sm font-medium text-text-primary">
                          {item.name}
                        </span>
                        {item.requiresRestart && (
                          <Badge variant="warning">Restart Required</Badge>
                        )}
                      </div>
                      <div className="flex-shrink-0">
                        <ConfigInput
                          item={item}
                          onChange={handleConfigChange}
                        />
                      </div>
                    </div>
                    <div className="mt-1 text-xs text-text-muted">
                      <span className="font-mono">{item.id}</span>
                      {" — "}
                      {item.description}
                    </div>
                    <div className="mt-0.5 flex gap-3 text-[10px] text-text-muted">
                      <span>
                        Default:{" "}
                        <span className="font-mono">{item.defaultValue}</span>
                      </span>
                      {item.lastModifiedAt && (
                        <span>
                          Last modified: {relativeTime(item.lastModifiedAt)} by{" "}
                          {item.lastModifiedBy ?? "unknown"}
                        </span>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Feature Flags tab */}
      {isFeatureFlagsTab && (
        <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
          {filteredFlags.length === 0 && (
            <p className="col-span-full py-4 text-center text-xs text-text-muted">
              No feature flags match the current filter.
            </p>
          )}
          {filteredFlags.map((flag) => {
            const isPending = pendingFlagChanges.has(flag.id);
            return (
              <Card
                key={flag.id}
                className={isPending ? "border-l-2 border-l-amber-400" : ""}
              >
                <CardContent>
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <h3 className="text-sm font-medium text-text-primary truncate">
                        {flag.name}
                      </h3>
                      <p className="text-xs font-mono text-text-muted mt-0.5">
                        {flag.id}
                      </p>
                    </div>
                    <button
                      onClick={() => handleFlagToggle(flag, !flag.enabled)}
                      className={`relative inline-flex h-5 w-9 flex-shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors ${
                        flag.enabled ? "bg-fizz-400" : "bg-panel-600"
                      }`}
                      role="switch"
                      aria-checked={flag.enabled}
                    >
                      <span
                        className={`inline-block h-4 w-4 transform rounded-full bg-white shadow transition-transform ${
                          flag.enabled ? "translate-x-4" : "translate-x-0"
                        }`}
                      />
                    </button>
                  </div>

                  <p className="mt-2 text-xs text-text-secondary leading-relaxed">
                    {flag.description}
                  </p>

                  {/* Rollout bar */}
                  <div className="mt-3">
                    <div className="flex items-center justify-between text-xs text-text-secondary mb-1">
                      <span>Rollout</span>
                      <span className="font-mono">
                        {flag.rolloutPercentage}%
                      </span>
                    </div>
                    <div className="flex items-center gap-2">
                      <div className="flex-1 h-1.5 rounded-full bg-surface-overlay overflow-hidden">
                        <div
                          className="h-full bg-fizzbuzz-400 rounded-full transition-all duration-300"
                          style={{ width: `${flag.rolloutPercentage}%` }}
                        />
                      </div>
                      <input
                        type="range"
                        min={0}
                        max={100}
                        value={flag.rolloutPercentage}
                        onChange={(e) =>
                          handleFlagRollout(flag, Number(e.target.value))
                        }
                        className="w-24 h-1 accent-fizzbuzz-400"
                      />
                    </div>
                  </div>

                  {/* Lifecycle and metadata */}
                  <div className="mt-3 flex items-center gap-3 text-[10px] text-text-muted">
                    <span>Lifecycle:</span>
                    <Badge variant={LIFECYCLE_BADGE_VARIANT[flag.lifecycle]}>
                      {flag.lifecycle}
                    </Badge>
                  </div>
                  <div className="mt-1 text-[10px] text-text-muted">
                    Last toggled: {relativeTime(flag.lastToggledAt)} by{" "}
                    {flag.lastToggledBy}
                  </div>
                </CardContent>
              </Card>
            );
          })}
        </div>
      )}

      {/* Pending Changes Panel */}
      {pendingChanges.length > 0 && (
        <div className="sticky bottom-0 z-10">
          <Card className="border-amber-800 bg-surface-base">
            <CardHeader>
              <div className="flex items-center justify-between">
                <h3 className="heading-section">
                  Pending Changes ({pendingChanges.length})
                </h3>
                <div className="flex gap-2">
                  <button
                    onClick={handleApply}
                    disabled={applying}
                    className="rounded-md bg-fizz-600 px-3 py-1 text-xs font-medium text-white hover:bg-fizz-500 disabled:opacity-50 transition-colors"
                  >
                    {applying ? "Applying..." : "Apply"}
                  </button>
                  <button
                    onClick={handleDiscard}
                    disabled={applying}
                    className="rounded-md border border-border-default px-3 py-1 text-xs font-medium text-text-secondary hover:bg-surface-raised disabled:opacity-50 transition-colors"
                  >
                    Discard
                  </button>
                </div>
              </div>
            </CardHeader>
            <CardContent>
              <table className="w-full">
                <thead>
                  <tr className="text-[10px] text-text-muted uppercase tracking-wider">
                    <th className="text-left pb-2 pr-4">Parameter</th>
                    <th className="text-left pb-2 pr-4">Before</th>
                    <th className="text-left pb-2">After</th>
                  </tr>
                </thead>
                <tbody>
                  {pendingChanges.map((change) => (
                    <tr
                      key={change.id}
                      className="border-t border-border-subtle"
                    >
                      <td className="py-1.5 pr-4 text-xs font-mono text-text-secondary">
                        {change.id}
                      </td>
                      <td className="py-1.5 pr-4">
                        <span className="rounded px-1.5 py-0.5 text-xs font-mono bg-red-950 text-red-400">
                          {change.before}
                        </span>
                      </td>
                      <td className="py-1.5">
                        <span className="rounded px-1.5 py-0.5 text-xs font-mono bg-fizz-950 text-fizz-400">
                          {change.after}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </CardContent>
          </Card>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Config Input Component
// ---------------------------------------------------------------------------

function ConfigInput({
  item,
  onChange,
}: {
  item: ConfigItem;
  onChange: (item: ConfigItem, value: string) => void;
}) {
  switch (item.type) {
    case "boolean":
      return (
        <button
          onClick={() =>
            onChange(item, item.value === "true" ? "false" : "true")
          }
          className={`relative inline-flex h-5 w-9 flex-shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors ${
            item.value === "true" ? "bg-fizz-400" : "bg-panel-600"
          }`}
          role="switch"
          aria-checked={item.value === "true"}
        >
          <span
            className={`inline-block h-4 w-4 transform rounded-full bg-white shadow transition-transform ${
              item.value === "true" ? "translate-x-4" : "translate-x-0"
            }`}
          />
        </button>
      );

    case "enum":
      return (
        <select
          value={item.value}
          onChange={(e) => onChange(item, e.target.value)}
          className="rounded-md border border-border-default bg-surface-raised px-2 py-1 text-xs text-text-secondary focus:border-fizzbuzz-400 focus:outline-none focus:ring-1 focus:ring-fizzbuzz-400"
        >
          {item.enumValues?.map((v) => (
            <option key={v} value={v}>
              {v}
            </option>
          ))}
        </select>
      );

    case "number":
      return (
        <input
          type="number"
          value={item.value}
          min={item.min}
          max={item.max}
          step={Number(item.value) < 1 && Number(item.value) > 0 ? 0.0001 : 1}
          onChange={(e) => onChange(item, e.target.value)}
          className="w-28 rounded-md border border-border-default bg-surface-raised px-2 py-1 text-xs text-text-secondary font-mono focus:border-fizzbuzz-400 focus:outline-none focus:ring-1 focus:ring-fizzbuzz-400"
        />
      );

    case "string":
    default:
      return (
        <input
          type="text"
          value={item.value}
          onChange={(e) => onChange(item, e.target.value)}
          className="w-44 rounded-md border border-border-default bg-surface-raised px-2 py-1 text-xs text-text-secondary font-mono focus:border-fizzbuzz-400 focus:outline-none focus:ring-1 focus:ring-fizzbuzz-400"
        />
      );
  }
}
