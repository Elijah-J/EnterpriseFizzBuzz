"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useDataProvider } from "@/lib/data-providers";
import type {
  ClusterTopology,
  ClusterNode,
  ClusterEdge,
  LeaderElection,
  PaxosMessage,
  PaxosMessageType,
} from "@/lib/data-providers";
import { Card, CardContent, CardHeader } from "@/components/ui/card";

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const REFRESH_INTERVAL_MS = 5_000;

/**
 * Deterministic node positions for SVG topology rendering.
 * Nodes are grouped by region: us-east-1 on the left, us-west-2 center,
 * eu-west-1 on the right. Positions are expressed as fractions of the
 * viewport to enable responsive scaling.
 */
const NODE_POSITIONS: Record<string, { x: number; y: number }> = {
  "fizz-eval-us-east-1a": { x: 0.15, y: 0.35 },
  "fizz-eval-us-east-1b": { x: 0.15, y: 0.65 },
  "fizz-eval-us-west-2a": { x: 0.45, y: 0.3 },
  "fizz-eval-us-west-2b": { x: 0.45, y: 0.7 },
  "fizz-eval-eu-west-1a": { x: 0.78, y: 0.25 },
  "fizz-eval-eu-west-1b": { x: 0.78, y: 0.55 },
  "fizz-eval-eu-west-1c": { x: 0.78, y: 0.82 },
};

/** Region bounding boxes for the subtle background grouping rectangles. */
const REGION_BOUNDS: Record<string, { x: number; y: number; w: number; h: number; label: string }> = {
  "us-east-1": { x: 0.04, y: 0.15, w: 0.22, h: 0.7, label: "us-east-1" },
  "us-west-2": { x: 0.34, y: 0.1, w: 0.22, h: 0.8, label: "us-west-2" },
  "eu-west-1": { x: 0.67, y: 0.05, w: 0.22, h: 0.9, label: "eu-west-1" },
};

const NODE_RADIUS = 22;

const STATUS_STYLES: Record<string, { fill: string; stroke: string; dash?: string }> = {
  healthy: { fill: "#475569", stroke: "#64748b" },        // panel-600/500
  degraded: { fill: "#92400e", stroke: "#f59e0b" },       // amber
  unreachable: { fill: "#7f1d1d", stroke: "#ef4444", dash: "4,4" }, // red dashed
  partitioned: { fill: "#7f1d1d", stroke: "#ef4444", dash: "4,4" }, // red dashed
};

const ROLE_BADGE_STYLES: Record<string, string> = {
  leader: "bg-fizzbuzz-400/20 text-fizzbuzz-400 border-fizzbuzz-400/30",
  follower: "bg-panel-600/20 text-panel-300 border-panel-500/30",
  candidate: "bg-yellow-500/20 text-yellow-400 border-yellow-500/30",
  observer: "bg-red-500/20 text-red-400 border-red-500/30",
};

const STATUS_BADGE_STYLES: Record<string, string> = {
  healthy: "bg-emerald-500/20 text-emerald-400",
  degraded: "bg-yellow-500/20 text-yellow-400",
  unreachable: "bg-red-500/20 text-red-400",
  partitioned: "bg-red-500/20 text-red-400",
};

const PAXOS_TYPE_STYLES: Record<PaxosMessageType, string> = {
  prepare: "bg-blue-500/20 text-blue-400 border-blue-500/30",
  promise: "bg-emerald-500/20 text-emerald-400 border-emerald-500/30",
  accept: "bg-yellow-500/20 text-yellow-400 border-yellow-500/30",
  accepted: "bg-teal-500/20 text-teal-400 border-teal-500/30",
};

const ELECTION_OUTCOME_STYLES: Record<string, string> = {
  elected: "bg-emerald-500/20 text-emerald-400 border-emerald-500/30",
  rejected: "bg-red-500/20 text-red-400 border-red-500/30",
  "timed-out": "bg-yellow-500/20 text-yellow-400 border-yellow-500/30",
  "in-progress": "bg-blue-500/20 text-blue-400 border-blue-500/30",
};

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/** Format an ISO timestamp as relative time (e.g., "3s ago", "2m ago"). */
function relativeTime(iso: string): string {
  const diffMs = Date.now() - new Date(iso).getTime();
  if (diffMs < 1_000) return "just now";
  if (diffMs < 60_000) return `${Math.floor(diffMs / 1_000)}s ago`;
  if (diffMs < 3_600_000) return `${Math.floor(diffMs / 60_000)}m ago`;
  if (diffMs < 86_400_000) return `${Math.floor(diffMs / 3_600_000)}h ago`;
  return `${Math.floor(diffMs / 86_400_000)}d ago`;
}

/** Truncate a node ID to its region suffix for compact display. */
function shortNodeId(id: string): string {
  const parts = id.split("-");
  return parts.slice(2).join("-");
}

/** Format a timestamp for display in the message log. */
function formatTimestamp(iso: string): string {
  const d = new Date(iso);
  return d.toLocaleTimeString("en-US", { hour12: false, hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

/** Compute duration between two ISO timestamps in a human-friendly format. */
function electionDuration(start: string, end?: string): string {
  if (!end) return "pending";
  const ms = new Date(end).getTime() - new Date(start).getTime();
  if (ms < 1_000) return `${ms}ms`;
  return `${(ms / 1_000).toFixed(1)}s`;
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

/** SVG topology graph rendering the cluster node mesh. */
function TopologyGraph({
  topology,
  selectedNodeId,
  onSelectNode,
}: {
  topology: ClusterTopology;
  selectedNodeId: string | null;
  onSelectNode: (id: string | null) => void;
}) {
  const svgWidth = 800;
  const svgHeight = 400;

  const nodeMap = useMemo(() => {
    const map = new Map<string, ClusterNode>();
    for (const node of topology.nodes) {
      map.set(node.id, node);
    }
    return map;
  }, [topology.nodes]);

  return (
    <svg
      viewBox={`0 0 ${svgWidth} ${svgHeight}`}
      className="w-full h-auto"
      style={{ minHeight: 320 }}
    >
      {/* Region grouping rectangles */}
      {Object.entries(REGION_BOUNDS).map(([region, bounds]) => (
        <g key={region}>
          <rect
            x={bounds.x * svgWidth}
            y={bounds.y * svgHeight}
            width={bounds.w * svgWidth}
            height={bounds.h * svgHeight}
            rx={8}
            fill="rgba(100,116,139,0.06)"
            stroke="rgba(100,116,139,0.15)"
            strokeWidth={1}
          />
          <text
            x={bounds.x * svgWidth + (bounds.w * svgWidth) / 2}
            y={bounds.y * svgHeight + 16}
            textAnchor="middle"
            fill="rgba(148,163,184,0.6)"
            fontSize={11}
            fontFamily="var(--font-geist-mono)"
          >
            {bounds.label}
          </text>
        </g>
      ))}

      {/* Edges */}
      {topology.edges.map((edge) => {
        const fromPos = NODE_POSITIONS[edge.from];
        const toPos = NODE_POSITIONS[edge.to];
        if (!fromPos || !toPos) return null;

        return (
          <line
            key={`${edge.from}-${edge.to}`}
            x1={fromPos.x * svgWidth}
            y1={fromPos.y * svgHeight}
            x2={toPos.x * svgWidth}
            y2={toPos.y * svgHeight}
            stroke={edge.healthy ? "rgba(100,116,139,0.4)" : "rgba(239,68,68,0.6)"}
            strokeWidth={edge.healthy ? 1 : 1.5}
            strokeDasharray={edge.healthy ? undefined : "6,4"}
          />
        );
      })}

      {/* Nodes */}
      {topology.nodes.map((node) => {
        const pos = NODE_POSITIONS[node.id];
        if (!pos) return null;

        const cx = pos.x * svgWidth;
        const cy = pos.y * svgHeight;
        const style = STATUS_STYLES[node.status] || STATUS_STYLES.healthy;
        const isLeader = node.role === "leader";
        const isSelected = selectedNodeId === node.id;

        return (
          <g
            key={node.id}
            className="cursor-pointer"
            onClick={() => onSelectNode(isSelected ? null : node.id)}
          >
            {/* Leader highlight ring */}
            {isLeader && (
              <circle
                cx={cx}
                cy={cy}
                r={NODE_RADIUS + 6}
                fill="none"
                stroke="rgba(250,204,21,0.5)"
                strokeWidth={2}
                strokeDasharray="4,3"
              />
            )}
            {/* Selection ring */}
            {isSelected && (
              <circle
                cx={cx}
                cy={cy}
                r={NODE_RADIUS + 4}
                fill="none"
                stroke="rgba(96,165,250,0.7)"
                strokeWidth={2}
              />
            )}
            {/* Node circle */}
            <circle
              cx={cx}
              cy={cy}
              r={NODE_RADIUS}
              fill={style.fill}
              stroke={style.stroke}
              strokeWidth={1.5}
              strokeDasharray={style.dash}
            />
            {/* Node label */}
            <text
              x={cx}
              y={cy + 1}
              textAnchor="middle"
              dominantBaseline="middle"
              fill="#e2e8f0"
              fontSize={8}
              fontFamily="var(--font-geist-mono)"
            >
              {shortNodeId(node.id)}
            </text>
            {/* Role indicator below node */}
            <text
              x={cx}
              y={cy + NODE_RADIUS + 14}
              textAnchor="middle"
              fill={isLeader ? "#facc15" : "rgba(148,163,184,0.7)"}
              fontSize={9}
              fontFamily="var(--font-geist-sans)"
              fontWeight={isLeader ? "600" : "400"}
            >
              {node.role}
            </text>
          </g>
        );
      })}

      {/* Legend */}
      <g transform={`translate(${svgWidth - 160}, 16)`}>
        <rect x={0} y={0} width={150} height={100} rx={6} fill="rgba(15,23,42,0.8)" stroke="rgba(100,116,139,0.3)" strokeWidth={1} />
        <text x={10} y={16} fill="#94a3b8" fontSize={9} fontWeight="600">Legend</text>
        {/* Leader */}
        <circle cx={18} cy={32} r={6} fill="#475569" stroke="#facc15" strokeWidth={1.5} strokeDasharray="2,2" />
        <text x={30} y={35} fill="#94a3b8" fontSize={8}>Leader</text>
        {/* Follower */}
        <circle cx={18} cy={48} r={6} fill="#475569" stroke="#64748b" strokeWidth={1.5} />
        <text x={30} y={51} fill="#94a3b8" fontSize={8}>Follower</text>
        {/* Degraded */}
        <circle cx={18} cy={64} r={6} fill="#92400e" stroke="#f59e0b" strokeWidth={1.5} />
        <text x={30} y={67} fill="#94a3b8" fontSize={8}>Degraded</text>
        {/* Partitioned */}
        <circle cx={18} cy={80} r={6} fill="#7f1d1d" stroke="#ef4444" strokeWidth={1.5} strokeDasharray="2,2" />
        <text x={30} y={83} fill="#94a3b8" fontSize={8}>Partitioned</text>
        {/* Edge healthy */}
        <line x1={85} y1={32} x2={110} y2={32} stroke="rgba(100,116,139,0.6)" strokeWidth={1} />
        <text x={115} y={35} fill="#94a3b8" fontSize={8}>OK</text>
        {/* Edge unhealthy */}
        <line x1={85} y1={48} x2={110} y2={48} stroke="rgba(239,68,68,0.6)" strokeWidth={1.5} strokeDasharray="4,3" />
        <text x={115} y={51} fill="#94a3b8" fontSize={8}>Down</text>
      </g>
    </svg>
  );
}

/** Node detail panel displayed when a node is selected in the topology graph. */
function NodeDetailPanel({
  node,
  isLeader,
  currentTerm,
  onClose,
}: {
  node: ClusterNode;
  isLeader: boolean;
  currentTerm: number;
  onClose: () => void;
}) {
  return (
    <Card className="absolute top-4 right-4 w-72 z-10 shadow-lg">
      <CardHeader className="flex flex-row items-center justify-between">
        <span className="text-sm font-semibold text-panel-100 font-mono">{node.id}</span>
        <button
          onClick={onClose}
          className="text-panel-400 hover:text-panel-200 text-lg leading-none"
          aria-label="Close node detail panel"
        >
          &times;
        </button>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="flex items-center justify-between">
          <span className="text-xs text-panel-400">Role</span>
          <span className={`text-xs px-2 py-0.5 rounded border ${ROLE_BADGE_STYLES[node.role]}`}>
            {node.role}
          </span>
        </div>
        <div className="flex items-center justify-between">
          <span className="text-xs text-panel-400">Status</span>
          <span className={`text-xs px-2 py-0.5 rounded ${STATUS_BADGE_STYLES[node.status]}`}>
            {node.status}
          </span>
        </div>
        <div className="flex items-center justify-between">
          <span className="text-xs text-panel-400">Region</span>
          <span className="text-xs text-panel-200 font-mono">{node.region}</span>
        </div>
        <div className="flex items-center justify-between">
          <span className="text-xs text-panel-400">Last Heartbeat</span>
          <span className="text-xs text-panel-200">{relativeTime(node.lastHeartbeat)}</span>
        </div>
        <div className="flex items-center justify-between">
          <span className="text-xs text-panel-400">Ballot Number</span>
          <span className="text-xs text-panel-200 font-mono">{node.ballotNumber}</span>
        </div>
        <div className="flex items-center justify-between">
          <span className="text-xs text-panel-400">Log Index</span>
          <span className="text-xs text-panel-200 font-mono">{node.logIndex.toLocaleString()}</span>
        </div>
        {isLeader && (
          <div className="mt-2 pt-2 border-t border-panel-700">
            <span className="text-xs text-fizzbuzz-400 font-medium">
              Leader since term {currentTerm}
            </span>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

/** Horizontal scrollable election timeline. */
function ElectionTimeline({ elections }: { elections: LeaderElection[] }) {
  const [hoveredTerm, setHoveredTerm] = useState<number | null>(null);

  // Display in chronological order (oldest left, newest right)
  const sorted = useMemo(
    () => [...elections].sort((a, b) => a.term - b.term),
    [elections],
  );

  return (
    <div className="relative">
      {/* Timeline axis */}
      <div className="absolute top-1/2 left-0 right-0 h-px bg-panel-700" />

      <div className="flex gap-3 overflow-x-auto pb-4 pt-2 px-2 relative">
        {sorted.map((election) => {
          const isHovered = hoveredTerm === election.term;

          return (
            <div
              key={election.term}
              className="relative flex-shrink-0"
              onMouseEnter={() => setHoveredTerm(election.term)}
              onMouseLeave={() => setHoveredTerm(null)}
            >
              {/* Election card */}
              <div
                className={`px-3 py-2 rounded-lg border transition-all cursor-default ${
                  isHovered ? "bg-panel-700 border-panel-500 scale-105" : "bg-panel-800 border-panel-700"
                }`}
                style={{ minWidth: 120 }}
              >
                <div className="flex items-center justify-between gap-2 mb-1">
                  <span className="text-xs font-mono text-panel-300">T{election.term}</span>
                  <span className={`text-[10px] px-1.5 py-0.5 rounded border ${ELECTION_OUTCOME_STYLES[election.outcome]}`}>
                    {election.outcome}
                  </span>
                </div>
                <div className="text-[10px] text-panel-400 truncate" title={election.candidateId}>
                  {shortNodeId(election.candidateId)}
                </div>
              </div>

              {/* Hover tooltip with full details */}
              {isHovered && (
                <div className="absolute bottom-full left-1/2 -translate-x-1/2 mb-2 z-20 bg-panel-900 border border-panel-600 rounded-lg p-3 shadow-xl whitespace-nowrap">
                  <div className="text-xs text-panel-200 font-semibold mb-2">Term {election.term} Election</div>
                  <div className="space-y-1 text-[11px]">
                    <div className="flex justify-between gap-4">
                      <span className="text-panel-400">Candidate</span>
                      <span className="text-panel-200 font-mono">{election.candidateId}</span>
                    </div>
                    <div className="flex justify-between gap-4">
                      <span className="text-panel-400">Votes</span>
                      <span className="text-panel-200">{election.votes}/{election.totalVoters}</span>
                    </div>
                    <div className="flex justify-between gap-4">
                      <span className="text-panel-400">Started</span>
                      <span className="text-panel-200">{formatTimestamp(election.startedAt)}</span>
                    </div>
                    {election.resolvedAt && (
                      <div className="flex justify-between gap-4">
                        <span className="text-panel-400">Resolved</span>
                        <span className="text-panel-200">{formatTimestamp(election.resolvedAt)}</span>
                      </div>
                    )}
                    <div className="flex justify-between gap-4">
                      <span className="text-panel-400">Duration</span>
                      <span className="text-panel-200">{electionDuration(election.startedAt, election.resolvedAt)}</span>
                    </div>
                  </div>
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

/** Paxos message log table with type filtering. */
function PaxosMessageLog({ messages }: { messages: PaxosMessage[] }) {
  const [typeFilter, setTypeFilter] = useState<PaxosMessageType | "all">("all");

  const filtered = useMemo(() => {
    const result = typeFilter === "all"
      ? messages
      : messages.filter((m) => m.type === typeFilter);
    return result.slice(-50);
  }, [messages, typeFilter]);

  return (
    <div className="flex flex-col h-full">
      {/* Filter bar */}
      <div className="flex items-center gap-2 mb-3">
        <span className="text-xs text-panel-400">Filter:</span>
        <select
          value={typeFilter}
          onChange={(e) => setTypeFilter(e.target.value as PaxosMessageType | "all")}
          className="text-xs bg-panel-900 border border-panel-700 rounded px-2 py-1 text-panel-200 focus:outline-none focus:border-panel-500"
        >
          <option value="all">All Types</option>
          <option value="prepare">Prepare</option>
          <option value="promise">Promise</option>
          <option value="accept">Accept</option>
          <option value="accepted">Accepted</option>
        </select>
      </div>

      {/* Message table */}
      <div className="flex-1 overflow-y-auto">
        <table className="w-full text-xs">
          <thead>
            <tr className="text-panel-400 border-b border-panel-700">
              <th className="text-left py-1.5 px-2 font-medium">Time</th>
              <th className="text-left py-1.5 px-2 font-medium">Type</th>
              <th className="text-left py-1.5 px-2 font-medium">From</th>
              <th className="text-left py-1.5 px-2 font-medium"></th>
              <th className="text-left py-1.5 px-2 font-medium">To</th>
              <th className="text-right py-1.5 px-2 font-medium">Ballot</th>
            </tr>
          </thead>
          <tbody>
            {filtered.map((msg) => (
              <tr key={msg.id} className="border-b border-panel-700/50 hover:bg-panel-700/30">
                <td className="py-1.5 px-2 text-panel-300 font-mono">{formatTimestamp(msg.timestamp)}</td>
                <td className="py-1.5 px-2">
                  <span className={`px-1.5 py-0.5 rounded border text-[10px] ${PAXOS_TYPE_STYLES[msg.type]}`}>
                    {msg.type}
                  </span>
                </td>
                <td className="py-1.5 px-2 text-panel-200 font-mono">{shortNodeId(msg.from)}</td>
                <td className="py-1.5 px-2 text-panel-500">&rarr;</td>
                <td className="py-1.5 px-2 text-panel-200 font-mono">{shortNodeId(msg.to)}</td>
                <td className="py-1.5 px-2 text-right text-panel-300 font-mono">{msg.ballotNumber}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {filtered.length === 0 && (
          <div className="text-center text-panel-500 text-xs py-6">
            No messages match the selected filter.
          </div>
        )}
      </div>
    </div>
  );
}

/** Network partition simulator panel. */
function PartitionSimulator({
  nodes,
  onSimulate,
  onReset,
  simulationResult,
  isSimulating,
}: {
  nodes: ClusterNode[];
  onSimulate: (nodeIds: string[]) => void;
  onReset: () => void;
  simulationResult: { summary: string; leaderElected: boolean; newTerm?: number; newLeader?: string } | null;
  isSimulating: boolean;
}) {
  const [selectedNodes, setSelectedNodes] = useState<Set<string>>(new Set());

  const toggleNode = useCallback((nodeId: string) => {
    setSelectedNodes((prev) => {
      const next = new Set(prev);
      if (next.has(nodeId)) {
        next.delete(nodeId);
      } else {
        next.add(nodeId);
      }
      return next;
    });
  }, []);

  const handleSimulate = useCallback(() => {
    onSimulate(Array.from(selectedNodes));
  }, [selectedNodes, onSimulate]);

  const handleReset = useCallback(() => {
    setSelectedNodes(new Set());
    onReset();
  }, [onReset]);

  return (
    <div className="space-y-3">
      <p className="text-xs text-panel-400">
        Select nodes to isolate behind a network partition. The cluster will
        attempt to maintain quorum and elect a new leader if necessary.
      </p>

      {/* Node checkbox list */}
      <div className="space-y-1.5 max-h-48 overflow-y-auto">
        {nodes.map((node) => (
          <label
            key={node.id}
            className="flex items-center gap-2 text-xs cursor-pointer hover:bg-panel-700/30 rounded px-2 py-1"
          >
            <input
              type="checkbox"
              checked={selectedNodes.has(node.id)}
              onChange={() => toggleNode(node.id)}
              className="rounded border-panel-600 bg-panel-900 text-fizzbuzz-400 focus:ring-fizzbuzz-400/50"
              disabled={isSimulating}
            />
            <span className="font-mono text-panel-200">{node.id}</span>
            <span className={`ml-auto text-[10px] px-1.5 py-0.5 rounded ${ROLE_BADGE_STYLES[node.role]}`}>
              {node.role}
            </span>
          </label>
        ))}
      </div>

      {/* Action buttons */}
      <div className="flex gap-2">
        <button
          onClick={handleSimulate}
          disabled={selectedNodes.size === 0 || isSimulating}
          className="flex-1 text-xs px-3 py-1.5 rounded bg-red-500/20 text-red-400 border border-red-500/30 hover:bg-red-500/30 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
        >
          {isSimulating ? "Simulating..." : "Simulate Partition"}
        </button>
        <button
          onClick={handleReset}
          className="text-xs px-3 py-1.5 rounded bg-panel-700 text-panel-300 border border-panel-600 hover:bg-panel-600 transition-colors"
        >
          Reset
        </button>
      </div>

      {/* Simulation result */}
      {simulationResult && (
        <div className="mt-3 p-3 rounded bg-panel-900 border border-panel-700 space-y-2">
          <p className="text-xs text-panel-200 leading-relaxed">{simulationResult.summary}</p>
          {simulationResult.leaderElected && (
            <div className="flex items-center gap-2 text-xs">
              <span className="text-panel-400">New Leader:</span>
              <span className="font-mono text-fizzbuzz-400">{simulationResult.newLeader}</span>
              <span className="text-panel-400">Term:</span>
              <span className="font-mono text-panel-200">{simulationResult.newTerm}</span>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main Page Component
// ---------------------------------------------------------------------------

export default function ConsensusPage() {
  const provider = useDataProvider();

  // Data state
  const [topology, setTopology] = useState<ClusterTopology | null>(null);
  const [elections, setElections] = useState<LeaderElection[]>([]);
  const [paxosMessages, setPaxosMessages] = useState<PaxosMessage[]>([]);
  const [loading, setLoading] = useState(true);

  // UI state
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);
  const [simulationResult, setSimulationResult] = useState<{
    summary: string;
    leaderElected: boolean;
    newTerm?: number;
    newLeader?: string;
  } | null>(null);
  const [isSimulating, setIsSimulating] = useState(false);

  // -----------------------------------------------------------------------
  // Data fetching
  // -----------------------------------------------------------------------

  const fetchData = useCallback(async () => {
    try {
      const [topo, electionList] = await Promise.all([
        provider.getClusterTopology(),
        provider.getElectionHistory(20),
      ]);
      setTopology(topo);
      setElections(electionList);

      // Generate Paxos messages from the topology state
      // Messages are embedded in the topology data flow; for the simulation
      // provider they come from the pre-seeded buffer
      const now = Date.now();
      const nodeIds = topo.nodes.map((n) => n.id);
      const types: PaxosMessageType[] = ["prepare", "promise", "accept", "accepted"];
      const newMessages: PaxosMessage[] = [];
      for (let i = 0; i < 5; i++) {
        const fromIdx = Math.floor(Math.random() * nodeIds.length);
        let toIdx = Math.floor(Math.random() * (nodeIds.length - 1));
        if (toIdx >= fromIdx) toIdx++;
        newMessages.push({
          id: `pxm-live-${now}-${i}`,
          type: types[Math.floor(Math.random() * types.length)],
          from: nodeIds[fromIdx],
          to: nodeIds[toIdx],
          ballotNumber: topo.currentTerm,
          timestamp: new Date(now - Math.floor(Math.random() * 10_000)).toISOString(),
        });
      }

      setPaxosMessages((prev) => {
        const combined = [...prev, ...newMessages];
        // Keep the most recent 50 messages
        return combined.slice(-50);
      });
    } catch {
      // Telemetry would capture this in production; silently retry on next interval
    } finally {
      setLoading(false);
    }
  }, [provider]);

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, REFRESH_INTERVAL_MS);
    return () => clearInterval(interval);
  }, [fetchData]);

  // -----------------------------------------------------------------------
  // Partition simulation handler
  // -----------------------------------------------------------------------

  const handleSimulatePartition = useCallback(
    async (nodeIds: string[]) => {
      setIsSimulating(true);
      try {
        const result = await provider.simulatePartition(nodeIds);
        setTopology(result.topology);
        if (result.messages.length > 0) {
          setPaxosMessages((prev) => [...prev, ...result.messages].slice(-50));
        }
        setSimulationResult({
          summary: result.summary,
          leaderElected: result.leaderElected,
          newTerm: result.newTerm,
          newLeader: result.newLeader,
        });
      } catch {
        // Error handling deferred to production telemetry integration
      } finally {
        setIsSimulating(false);
      }
    },
    [provider],
  );

  const handleResetPartition = useCallback(() => {
    setSimulationResult(null);
    fetchData();
  }, [fetchData]);

  // -----------------------------------------------------------------------
  // Derived state
  // -----------------------------------------------------------------------

  const selectedNode = useMemo(() => {
    if (!topology || !selectedNodeId) return null;
    return topology.nodes.find((n) => n.id === selectedNodeId) ?? null;
  }, [topology, selectedNodeId]);

  // -----------------------------------------------------------------------
  // Render
  // -----------------------------------------------------------------------

  if (loading || !topology) {
    return (
      <div className="flex items-center justify-center h-64 text-panel-400 text-sm">
        Initializing Paxos cluster telemetry...
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Section 4a: Cluster Topology Graph */}
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <div>
              <h2 className="text-sm font-semibold text-panel-100">Cluster Topology</h2>
              <p className="text-xs text-panel-400 mt-0.5">
                7-node Paxos consensus cluster spanning 3 availability regions
              </p>
            </div>
            <div className="flex items-center gap-3">
              <div className="flex items-center gap-1.5">
                <span className="text-xs text-panel-400">Leader:</span>
                <span className="text-xs font-mono text-fizzbuzz-400 bg-fizzbuzz-400/10 px-2 py-0.5 rounded">
                  {topology.currentLeader}
                </span>
              </div>
              <div className="flex items-center gap-1.5">
                <span className="text-xs text-panel-400">Term:</span>
                <span className="text-xs font-mono text-panel-200 bg-panel-700 px-2 py-0.5 rounded">
                  {topology.currentTerm}
                </span>
              </div>
            </div>
          </div>
        </CardHeader>
        <CardContent className="relative">
          <TopologyGraph
            topology={topology}
            selectedNodeId={selectedNodeId}
            onSelectNode={setSelectedNodeId}
          />
          {/* Section 4b: Node Detail Panel (overlay) */}
          {selectedNode && (
            <NodeDetailPanel
              node={selectedNode}
              isLeader={selectedNode.id === topology.currentLeader}
              currentTerm={topology.currentTerm}
              onClose={() => setSelectedNodeId(null)}
            />
          )}
        </CardContent>
      </Card>

      {/* Section 4c: Election Timeline */}
      <Card>
        <CardHeader>
          <h2 className="text-sm font-semibold text-panel-100">Election Timeline</h2>
          <p className="text-xs text-panel-400 mt-0.5">
            Leader election history across the Paxos consensus cluster
          </p>
        </CardHeader>
        <CardContent>
          <ElectionTimeline elections={elections} />
        </CardContent>
      </Card>

      {/* Bottom row: Paxos Messages + Partition Simulator */}
      <div className="grid grid-cols-1 lg:grid-cols-5 gap-6">
        {/* Section 4d: Paxos Message Log (~60% width) */}
        <Card className="lg:col-span-3">
          <CardHeader>
            <h2 className="text-sm font-semibold text-panel-100">Paxos Message Log</h2>
            <p className="text-xs text-panel-400 mt-0.5">
              Real-time protocol messages exchanged between cluster nodes
            </p>
          </CardHeader>
          <CardContent className="h-72">
            <PaxosMessageLog messages={paxosMessages} />
          </CardContent>
        </Card>

        {/* Section 4e: Partition Simulator (~40% width) */}
        <Card className="lg:col-span-2">
          <CardHeader>
            <h2 className="text-sm font-semibold text-panel-100">Network Partition Simulator</h2>
            <p className="text-xs text-panel-400 mt-0.5">
              Validate cluster fault tolerance by injecting network partitions
            </p>
          </CardHeader>
          <CardContent>
            <PartitionSimulator
              nodes={topology.nodes}
              onSimulate={handleSimulatePartition}
              onReset={handleResetPartition}
              simulationResult={simulationResult}
              isSimulating={isSimulating}
            />
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
