"use client";

import { useCallback, useEffect, useState } from "react";
import { AnimatedNumber } from "@/components/ui/animated-number";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import type { ConsensusStatus } from "@/lib/data-providers";
import { useDataProvider } from "@/lib/data-providers";

/**
 * Consensus Widget — Displays the Paxos distributed consensus state
 * for the FizzBuzz evaluation cluster. Shows current leader, ballot
 * number, cluster acknowledgment status, and consensus/election state.
 * Auto-refreshes every 3 seconds.
 *
 * Node visualization dots use solid fills without animation — the
 * platform's motion philosophy prohibits ambient pulse effects.
 * State changes are communicated through color transitions only.
 */
export function ConsensusWidget() {
  const provider = useDataProvider();
  const [consensus, setConsensus] = useState<ConsensusStatus | null>(null);

  const refresh = useCallback(async () => {
    const data = await provider.getConsensusStatus();
    setConsensus(data);
  }, [provider]);

  useEffect(() => {
    refresh();
    const interval = setInterval(refresh, 3_000);
    return () => clearInterval(interval);
  }, [refresh]);

  if (!consensus) {
    return (
      <div className="space-y-4">
        <div className="flex items-center justify-between">
          <Skeleton variant="text" width="6rem" />
          <Skeleton variant="rect" width="8rem" height="1.5rem" />
        </div>
        <Skeleton variant="rect" height="2.5rem" />
        <div className="grid grid-cols-3 gap-2">
          <Skeleton variant="rect" height="2.5rem" />
          <Skeleton variant="rect" height="2.5rem" />
          <Skeleton variant="rect" height="2.5rem" />
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* Consensus status badge */}
      <div className="flex items-center justify-between">
        <p className="data-label">Cluster Consensus</p>
        <Badge variant={consensus.consensusAchieved ? "success" : "warning"}>
          {consensus.consensusAchieved
            ? "CONSENSUS ACHIEVED"
            : "ELECTION IN PROGRESS"}
        </Badge>
      </div>

      {/* Leader info */}
      <div>
        <p className="heading-section text-[10px]">Current Leader</p>
        <p
          className="text-sm font-mono text-[var(--accent)] mt-0.5 truncate"
          title={consensus.leaderNode}
        >
          {consensus.leaderNode}
        </p>
      </div>

      {/* Cluster details */}
      <div className="grid grid-cols-3 gap-2">
        <div>
          <p className="data-label text-[10px]">Ballot #</p>
          <AnimatedNumber
            value={consensus.ballotNumber}
            className="text-sm font-mono text-text-secondary"
          />
        </div>
        <div>
          <p className="data-label text-[10px]">Nodes ACK</p>
          <span
            className={`text-sm font-mono ${
              consensus.nodesAcknowledged === consensus.clusterSize
                ? "text-fizz-400"
                : "text-[var(--accent)]"
            }`}
          >
            <AnimatedNumber
              value={consensus.nodesAcknowledged}
              className="inline"
            />
            /{consensus.clusterSize}
          </span>
        </div>
        <div>
          <p className="data-label text-[10px]">Cluster Size</p>
          <AnimatedNumber
            value={consensus.clusterSize}
            className="text-sm font-mono text-text-secondary"
          />
        </div>
      </div>

      {/* Node visualization — solid dots, no ambient animation */}
      <div className="flex items-center justify-center gap-1.5 pt-1">
        {Array.from({ length: consensus.clusterSize }, (_, i) => (
          <div
            // biome-ignore lint/suspicious/noArrayIndexKey: node dots are positional, not reorderable
            key={i}
            className={`h-3 w-3 rounded-full border transition-colors ${
              i < consensus.nodesAcknowledged
                ? "bg-fizz-500 border-fizz-400"
                : "bg-surface-overlay border-border-subtle"
            }`}
            title={`Node ${i + 1}: ${i < consensus.nodesAcknowledged ? "acknowledged" : "pending"}`}
          />
        ))}
      </div>
    </div>
  );
}
