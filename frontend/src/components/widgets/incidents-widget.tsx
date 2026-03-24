"use client";

import { useCallback, useEffect, useState } from "react";
import { AnimatedNumber } from "@/components/ui/animated-number";
import { Badge } from "@/components/ui/badge";
import { Reveal } from "@/components/ui/reveal";
import { Skeleton } from "@/components/ui/skeleton";
import type { SLAStatus } from "@/lib/data-providers";
import { useDataProvider } from "@/lib/data-providers";

/**
 * Incidents Widget — Displays active incident count with severity
 * classification and the current on-call engineer. Shares the SLA
 * data feed to avoid redundant polling. Auto-refreshes every 3 seconds.
 *
 * Incident detail sections use Reveal entrance animations to
 * communicate state transitions when new incidents appear.
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
      <div className="space-y-4">
        <div className="flex items-center justify-between">
          <Skeleton variant="rect" width="8rem" height="3rem" />
          <Skeleton variant="rect" width="5rem" height="1.5rem" />
        </div>
        <Skeleton variant="rect" height="3rem" />
        <Skeleton variant="rect" height="2.5rem" />
      </div>
    );
  }

  const hasIncidents = sla.activeIncidents > 0;

  return (
    <div className="space-y-4">
      {/* Incident count */}
      <div className="flex items-center justify-between">
        <div>
          <p className="data-label">Active Incidents</p>
          <AnimatedNumber
            value={sla.activeIncidents}
            className={`data-value text-3xl ${hasIncidents ? "text-[var(--status-error)]" : "text-fizz-400"}`}
          />
        </div>
        <Badge variant={hasIncidents ? "error" : "success"}>
          {hasIncidents ? "SEV-3" : "ALL CLEAR"}
        </Badge>
      </div>

      {/* Incident detail (if active) */}
      {hasIncidents && (
        <Reveal delay={50}>
          <div className="rounded border border-[var(--status-error)]/20 bg-[var(--status-error)]/5 px-3 py-2">
            <p className="text-xs text-[var(--status-error)] font-medium">
              Blockchain block propagation latency exceeding threshold
            </p>
            <p className="text-[10px] text-[var(--status-error)]/60 mt-1">
              Duration: {Math.floor(Math.random() * 12) + 3}m &middot; Impact:
              Low
            </p>
          </div>
        </Reveal>
      )}

      {/* On-call */}
      <div className="flex items-center justify-between border-t border-border-subtle pt-3">
        <div>
          <p className="heading-section text-[10px]">On-Call Engineer</p>
          <p className="text-sm text-text-secondary mt-0.5">
            {sla.onCallEngineer}
          </p>
        </div>
        <div className="h-8 w-8 rounded-full bg-surface-overlay flex items-center justify-center">
          <span className="text-xs font-medium text-text-muted">
            {sla.onCallEngineer
              .split(" ")
              .map((w) => w[0])
              .join("")
              .slice(0, 2)}
          </span>
        </div>
      </div>
    </div>
  );
}
