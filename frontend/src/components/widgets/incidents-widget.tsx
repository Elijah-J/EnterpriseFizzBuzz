"use client";

import { useCallback, useEffect, useState } from "react";
import { useDataProvider } from "@/lib/data-providers";
import { Badge } from "@/components/ui/badge";
import type { SLAStatus } from "@/lib/data-providers";

/**
 * Incidents Widget — Displays active incident count with severity
 * classification and the current on-call engineer. Shares the SLA
 * data feed to avoid redundant polling. Auto-refreshes every 3 seconds.
 */
export function IncidentsWidget() {
  const provider = useDataProvider();
  const [sla, setSLA] = useState<SLAStatus | null>(null);

  const refresh = useCallback(async () => {
    const data = await provider.getSLAStatus();
    setSLA(data);
  }, [provider]);

  useEffect(() => {
    refresh();
    const interval = setInterval(refresh, 3_000);
    return () => clearInterval(interval);
  }, [refresh]);

  if (!sla) {
    return (
      <div className="flex h-24 items-center justify-center">
        <span className="text-xs text-panel-500">Loading incident feed...</span>
      </div>
    );
  }

  const hasIncidents = sla.activeIncidents > 0;

  return (
    <div className="space-y-4">
      {/* Incident count */}
      <div className="flex items-center justify-between">
        <div>
          <p className="text-xs text-panel-500">Active Incidents</p>
          <p className={`text-3xl font-mono font-bold ${hasIncidents ? "text-red-400" : "text-fizz-400"}`}>
            {sla.activeIncidents}
          </p>
        </div>
        <Badge variant={hasIncidents ? "error" : "success"}>
          {hasIncidents ? "SEV-3" : "ALL CLEAR"}
        </Badge>
      </div>

      {/* Incident detail (if active) */}
      {hasIncidents && (
        <div className="rounded border border-red-900 bg-red-950/30 px-3 py-2">
          <p className="text-xs text-red-400 font-medium">
            Blockchain block propagation latency exceeding threshold
          </p>
          <p className="text-[10px] text-red-500/80 mt-1">
            Duration: {Math.floor(Math.random() * 12) + 3}m &middot; Impact: Low
          </p>
        </div>
      )}

      {/* On-call */}
      <div className="flex items-center justify-between border-t border-panel-700 pt-3">
        <div>
          <p className="text-[10px] text-panel-500 uppercase tracking-wider">On-Call Engineer</p>
          <p className="text-sm text-panel-200 mt-0.5">{sla.onCallEngineer}</p>
        </div>
        <div className="h-8 w-8 rounded-full bg-panel-700 flex items-center justify-center">
          <span className="text-xs font-medium text-panel-300">
            {sla.onCallEngineer.split(" ").map((w) => w[0]).join("").slice(0, 2)}
          </span>
        </div>
      </div>
    </div>
  );
}
