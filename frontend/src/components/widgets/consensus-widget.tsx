"use client";

import { useCallback, useEffect, useState } from "react";
import { useDataProvider } from "@/lib/data-providers";
import { Badge } from "@/components/ui/badge";
import type { ConsensusStatus } from "@/lib/data-providers";

/**
 * Consensus Widget — Displays the Paxos distributed consensus state
 * for the FizzBuzz evaluation cluster. Shows current leader, ballot
 * number, cluster acknowledgment status, and consensus/election state.
 * Auto-refreshes every 3 seconds.
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
      <div className="flex h-24 items-center justify-center">
        <span className="text-xs text-panel-500">Querying consensus state...</span>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* Consensus status badge */}
      <div className="flex items-center justify-between">
        <p className="text-xs text-panel-500">Cluster Consensus</p>
        <Badge variant={consensus.consensusAchieved ? "success" : "warning"}>
          {consensus.consensusAchieved ? "CONSENSUS ACHIEVED" : "ELECTION IN PROGRESS"}
        </Badge>
      </div>

      {/* Leader info */}
      <div>
        <p className="text-[10px] text-panel-500 uppercase tracking-wider">Current Leader</p>
        <p className="text-sm font-mono text-fizzbuzz-400 mt-0.5 truncate" title={consensus.leaderNode}>
          {consensus.leaderNode}
        </p>
      </div>

      {/* Cluster details */}
      <div className="grid grid-cols-3 gap-2">
        <div>
          <p className="text-[10px] text-panel-500">Ballot #</p>
          <p className="text-sm font-mono text-panel-200">{consensus.ballotNumber}</p>
        </div>
        <div>
          <p className="text-[10px] text-panel-500">Nodes ACK</p>
          <p className={`text-sm font-mono ${
            consensus.nodesAcknowledged === consensus.clusterSize
              ? "text-fizz-400"
              : "text-amber-400"
          }`}>
            {consensus.nodesAcknowledged}/{consensus.clusterSize}
          </p>
        </div>
        <div>
          <p className="text-[10px] text-panel-500">Cluster Size</p>
          <p className="text-sm font-mono text-panel-200">{consensus.clusterSize}</p>
        </div>
      </div>

      {/* Node visualization */}
      <div className="flex items-center justify-center gap-1.5 pt-1">
        {Array.from({ length: consensus.clusterSize }, (_, i) => (
          <div
            key={i}
            className={`h-3 w-3 rounded-full border transition-colors ${
              i < consensus.nodesAcknowledged
                ? "bg-fizz-500 border-fizz-400"
                : "bg-panel-700 border-panel-600"
            } ${!consensus.consensusAchieved && i >= consensus.nodesAcknowledged ? "animate-pulse" : ""}`}
            title={`Node ${i + 1}: ${i < consensus.nodesAcknowledged ? "acknowledged" : "pending"}`}
          />
        ))}
      </div>
    </div>
  );
}
