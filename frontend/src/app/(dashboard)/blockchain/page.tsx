"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Sparkline } from "@/components/charts/sparkline";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { CopyButton } from "@/components/ui/copy-button";
import { Reveal } from "@/components/ui/reveal";
import { Skeleton } from "@/components/ui/skeleton";
import type {
  Block,
  BlockchainStats,
  BlockTransaction,
} from "@/lib/data-providers";
import { useDataProvider } from "@/lib/data-providers";

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const STATS_REFRESH_INTERVAL_MS = 15_000;

const CLASSIFICATION_BADGE_VARIANT: Record<
  BlockTransaction["classification"],
  "success" | "info" | "warning" | "error"
> = {
  fizz: "success",
  buzz: "info",
  fizzbuzz: "warning",
  number: "error",
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

function formatHashRate(rate: number): string {
  if (rate >= 1000) return `${(rate / 1000).toFixed(1)} kH/s`;
  return `${rate.toFixed(1)} H/s`;
}

function formatNumber(n: number): string {
  return n.toLocaleString();
}

// ---------------------------------------------------------------------------
// Page component
// ---------------------------------------------------------------------------

export default function BlockchainExplorerPage() {
  const provider = useDataProvider();

  const [blocks, setBlocks] = useState<Block[]>([]);
  const [stats, setStats] = useState<BlockchainStats | null>(null);
  const [selectedBlockHash, setSelectedBlockHash] = useState<string | null>(
    null,
  );
  const [searchQuery, setSearchQuery] = useState("");
  const [copiedHash, setCopiedHash] = useState(false);

  const chainScrollRef = useRef<HTMLDivElement>(null);
  const newestBlockRef = useRef<HTMLDivElement>(null);
  const initialScrollDone = useRef(false);

  // -----------------------------------------------------------------------
  // Data fetching
  // -----------------------------------------------------------------------

  const fetchBlocks = useCallback(async () => {
    const result = await provider.getBlockchain(50);
    setBlocks(result);
  }, [provider]);

  const fetchStats = useCallback(async () => {
    const result = await provider.getBlockchainStats();
    setStats(result);
  }, [provider]);

  const refreshAll = useCallback(() => {
    fetchBlocks();
    fetchStats();
  }, [fetchBlocks, fetchStats]);

  useEffect(() => {
    fetchBlocks();
    fetchStats();
  }, [fetchBlocks, fetchStats]);

  useEffect(() => {
    const id = setInterval(fetchStats, STATS_REFRESH_INTERVAL_MS);
    return () => clearInterval(id);
  }, [fetchStats]);

  // Auto-scroll to newest block (rightmost) on initial load
  useEffect(() => {
    if (
      blocks.length > 0 &&
      !initialScrollDone.current &&
      newestBlockRef.current
    ) {
      newestBlockRef.current.scrollIntoView({
        behavior: "auto",
        inline: "end",
      });
      initialScrollDone.current = true;
    }
  }, [blocks]);

  // -----------------------------------------------------------------------
  // Derived data
  // -----------------------------------------------------------------------

  /** Blocks in chronological order (oldest first) for the chain strip. */
  const chronologicalBlocks = useMemo(() => [...blocks].reverse(), [blocks]);

  const selectedBlock = useMemo(
    () =>
      selectedBlockHash
        ? (blocks.find((b) => b.hash === selectedBlockHash) ?? null)
        : null,
    [blocks, selectedBlockHash],
  );

  /** Sparkline data: mining times in chronological order. */
  const miningTimeSeries = useMemo(
    () => chronologicalBlocks.map((b) => b.miningDurationMs),
    [chronologicalBlocks],
  );

  /** Transaction search results. */
  const searchResults = useMemo(() => {
    if (!searchQuery.trim()) return [];
    const query = searchQuery.trim().toLowerCase();
    const isNumeric = /^\d+$/.test(query);
    const results: Array<{ tx: BlockTransaction; block: Block }> = [];

    for (const block of blocks) {
      for (const tx of block.transactions) {
        if (isNumeric) {
          if (tx.input === Number(query)) {
            results.push({ tx, block });
          }
        } else {
          if (tx.hash.toLowerCase().startsWith(query)) {
            results.push({ tx, block });
          }
        }
      }
      if (results.length >= 20) break;
    }

    return results;
  }, [searchQuery, blocks]);

  // -----------------------------------------------------------------------
  // Handlers
  // -----------------------------------------------------------------------

  function handleBlockSelect(hash: string) {
    setSelectedBlockHash(hash);
    setSearchQuery("");
  }

  function handleSearchResultClick(blockHash: string) {
    setSelectedBlockHash(blockHash);
    setSearchQuery("");
    // Scroll chain visualization to the selected block
    const el = document.getElementById(`block-${blockHash}`);
    if (el) {
      el.scrollIntoView({ behavior: "smooth", inline: "center" });
    }
  }

  async function copyToClipboard(text: string) {
    try {
      await navigator.clipboard.writeText(text);
      setCopiedHash(true);
      setTimeout(() => setCopiedHash(false), 2000);
    } catch {
      // Clipboard API unavailable in some contexts
    }
  }

  // -----------------------------------------------------------------------
  // Render
  // -----------------------------------------------------------------------

  return (
    <div className="space-y-6">
      {/* Page header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="heading-page">Blockchain Ledger Explorer</h1>
          <p className="mt-1 text-sm text-text-secondary">
            Immutable proof-of-work audit chain for FizzBuzz evaluation receipts
          </p>
        </div>
        <button
          onClick={refreshAll}
          className="rounded border border-border-default bg-surface-raised px-3 py-1.5 text-xs text-text-secondary hover:bg-surface-overlay transition-colors"
        >
          Refresh Chain
        </button>
      </div>

      {/* Section A: Chain Overview Stats Bar */}
      {stats && (
        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-4">
          <Card>
            <CardContent>
              <p className="text-xs text-text-secondary">Block Height</p>
              <p className="text-lg font-semibold text-text-primary font-mono">
                #{stats.height}
              </p>
            </CardContent>
          </Card>
          <Card>
            <CardContent>
              <p className="text-xs text-text-secondary">Total Transactions</p>
              <p className="text-lg font-semibold text-text-primary">
                {formatNumber(stats.totalTransactions)}
              </p>
            </CardContent>
          </Card>
          <Card>
            <CardContent>
              <p className="text-xs text-text-secondary">Avg Mining Time</p>
              <p className="text-lg font-semibold text-text-primary">
                {stats.averageMiningTimeMs.toFixed(1)}ms
              </p>
            </CardContent>
          </Card>
          <Card>
            <CardContent>
              <p className="text-xs text-text-secondary">Difficulty</p>
              <p className="text-lg font-semibold text-text-primary">
                <span className="text-fizzbuzz-400 font-mono">
                  {"0".repeat(stats.currentDifficulty)}
                </span>{" "}
                {stats.currentDifficulty}
              </p>
            </CardContent>
          </Card>
          <Card>
            <CardContent>
              <p className="text-xs text-text-secondary">Hash Rate</p>
              <p className="text-lg font-semibold text-text-primary">
                {formatHashRate(stats.hashRate)}
              </p>
            </CardContent>
          </Card>
          <Card>
            <CardContent>
              <p className="text-xs text-text-secondary">Chain Integrity</p>
              <div className="mt-1">
                {stats.chainValid ? (
                  <Badge variant="success">VALID</Badge>
                ) : (
                  <Badge variant="error">BROKEN</Badge>
                )}
              </div>
            </CardContent>
          </Card>
        </div>
      )}

      {/* Section D: Mining Activity Sparkline */}
      {miningTimeSeries.length >= 2 && (
        <Card>
          <CardHeader>
            <p className="heading-section">Mining Time Trend</p>
          </CardHeader>
          <CardContent>
            <Sparkline
              data={miningTimeSeries}
              width={800}
              height={48}
              color="var(--fizzbuzz-400)"
              showArea
            />
          </CardContent>
        </Card>
      )}

      {/* Section B: Block Chain Visualization */}
      <Card>
        <CardHeader>
          <p className="heading-section">Chain Visualization</p>
        </CardHeader>
        <CardContent className="p-0">
          <div ref={chainScrollRef} className="overflow-x-auto px-4 py-4">
            <div
              className="flex items-center gap-0"
              style={{ minWidth: "max-content" }}
            >
              {chronologicalBlocks.map((block, idx) => {
                const isGenesis = block.index === 0;
                const isSelected = block.hash === selectedBlockHash;
                const isNewest = idx === chronologicalBlocks.length - 1;

                return (
                  <div key={block.hash} className="flex items-center">
                    {idx > 0 && (
                      <div className="flex items-center px-1">
                        <div className="w-6 h-px bg-panel-500" />
                        <div className="w-0 h-0 border-t-[4px] border-t-transparent border-b-[4px] border-b-transparent border-l-[6px] border-l-panel-500" />
                      </div>
                    )}
                    <div
                      id={`block-${block.hash}`}
                      ref={isNewest ? newestBlockRef : undefined}
                      onClick={() => handleBlockSelect(block.hash)}
                      className={`
                        flex-shrink-0 w-[120px] rounded-lg border p-2 cursor-pointer transition-all
                        ${isGenesis ? "border-fizzbuzz-400" : "border-border-default"}
                        ${isSelected ? "ring-2 ring-fizzbuzz-400 bg-surface-overlay" : "bg-surface-raised hover:bg-panel-750"}
                      `}
                    >
                      <p className="text-xs font-bold text-text-primary">
                        #{block.index}
                      </p>
                      <p className="text-[10px] font-mono text-text-secondary truncate">
                        {block.hash.slice(0, 8)}
                      </p>
                      <p className="text-[10px] text-text-secondary mt-1">
                        {block.transactions.length} txn
                        {block.transactions.length !== 1 ? "s" : ""}
                      </p>
                      <p className="text-[10px] text-text-muted">
                        {relativeTime(block.timestamp)}
                      </p>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Section E: Transaction Search */}
      <Card>
        <CardHeader>
          <p className="heading-section">Transaction Search</p>
        </CardHeader>
        <CardContent>
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Search by transaction hash or input number..."
            className="w-full rounded border border-border-default bg-surface-base px-3 py-2 text-sm text-text-secondary placeholder:text-text-muted focus:border-fizzbuzz-400 focus:outline-none focus:ring-1 focus:ring-fizzbuzz-400"
          />
          {searchResults.length > 0 && (
            <div className="mt-3 space-y-1 max-h-48 overflow-y-auto">
              {searchResults.map((result, idx) => (
                <div
                  key={`${result.tx.hash}-${idx}`}
                  onClick={() => handleSearchResultClick(result.block.hash)}
                  className="flex items-center justify-between rounded px-3 py-1.5 text-xs hover:bg-surface-overlay cursor-pointer transition-colors"
                >
                  <div className="flex items-center gap-3">
                    <span className="font-mono text-text-secondary">
                      {result.tx.hash.slice(0, 12)}
                    </span>
                    <span className="text-text-secondary">
                      Input: {result.tx.input}
                    </span>
                    <span className="text-text-secondary">
                      {result.tx.output}
                    </span>
                  </div>
                  <span className="text-text-muted">
                    Block #{result.block.index}
                  </span>
                </div>
              ))}
            </div>
          )}
          {searchQuery.trim() && searchResults.length === 0 && (
            <p className="mt-2 text-xs text-text-muted">
              No matching transactions found.
            </p>
          )}
        </CardContent>
      </Card>

      {/* Section C: Block Detail Panel */}
      <Card>
        <CardHeader>
          <p className="heading-section">Block Detail</p>
        </CardHeader>
        <CardContent>
          {selectedBlock ? (
            <div className="space-y-4">
              {/* Block header */}
              <div>
                <div className="flex items-center gap-3">
                  <h2 className="text-base font-semibold text-text-primary">
                    Block #{selectedBlock.index}
                  </h2>
                  <CopyButton text={selectedBlock.hash} />
                </div>
                <p className="font-mono text-xs text-text-secondary mt-1 break-all">
                  {selectedBlock.hash}
                </p>
              </div>

              {/* Metadata grid */}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3 text-sm">
                <div>
                  <p className="text-xs text-text-muted">Previous Hash</p>
                  <p
                    className="font-mono text-xs text-text-secondary truncate"
                    title={selectedBlock.previousHash}
                  >
                    {selectedBlock.previousHash.slice(0, 16)}...
                  </p>
                </div>
                <div>
                  <p className="text-xs text-text-muted">Nonce</p>
                  <p className="font-mono text-xs text-text-secondary">
                    {formatNumber(selectedBlock.nonce)}
                  </p>
                </div>
                <div>
                  <p className="text-xs text-text-muted">Difficulty</p>
                  <p className="text-xs text-text-secondary">
                    {selectedBlock.difficulty}
                  </p>
                </div>
                <div>
                  <p className="text-xs text-text-muted">Mining Duration</p>
                  <p className="text-xs text-text-secondary">
                    {selectedBlock.miningDurationMs.toFixed(1)}ms
                  </p>
                </div>
                <div className="md:col-span-2">
                  <p className="text-xs text-text-muted">Timestamp</p>
                  <p className="text-xs text-text-secondary">
                    {selectedBlock.timestamp}
                  </p>
                </div>
              </div>

              {/* Transactions table */}
              {selectedBlock.transactions.length > 0 ? (
                <div className="overflow-x-auto">
                  <table className="w-full text-xs">
                    <thead>
                      <tr className="border-b border-border-subtle text-text-secondary">
                        <th className="py-2 pr-4 text-left font-medium">
                          Hash
                        </th>
                        <th className="py-2 pr-4 text-left font-medium">
                          Input
                        </th>
                        <th className="py-2 pr-4 text-left font-medium">
                          Output
                        </th>
                        <th className="py-2 pr-4 text-left font-medium">
                          Classification
                        </th>
                        <th className="py-2 text-left font-medium">
                          Timestamp
                        </th>
                      </tr>
                    </thead>
                    <tbody>
                      {selectedBlock.transactions.map((tx) => (
                        <tr
                          key={tx.hash}
                          className="border-b border-border-subtle/50"
                        >
                          <td className="py-2 pr-4 font-mono text-text-secondary">
                            {tx.hash.slice(0, 12)}
                          </td>
                          <td className="py-2 pr-4 text-text-secondary">
                            {tx.input}
                          </td>
                          <td className="py-2 pr-4 text-text-secondary">
                            {tx.output}
                          </td>
                          <td className="py-2 pr-4">
                            <Badge
                              variant={
                                CLASSIFICATION_BADGE_VARIANT[tx.classification]
                              }
                            >
                              {tx.classification}
                            </Badge>
                          </td>
                          <td className="py-2 text-text-secondary">
                            {relativeTime(tx.timestamp)}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <p className="text-xs text-text-muted">
                  Genesis block contains no transactions.
                </p>
              )}
            </div>
          ) : (
            <div className="flex items-center justify-center py-12">
              <p className="text-sm text-text-muted">
                Select a block to inspect its contents and transactions.
              </p>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
