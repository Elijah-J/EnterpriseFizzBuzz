"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { Reveal } from "@/components/ui/reveal";
import { Skeleton } from "@/components/ui/skeleton";
import type { Trace, TraceSpan } from "@/lib/data-providers";
import { useDataProvider } from "@/lib/data-providers";

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const REFRESH_INTERVAL_MS = 5_000;

/** Color mapping for span status indicators. */
const STATUS_COLORS = {
  ok: "bg-fizz-400",
  error: "bg-red-500",
} as const;

const STATUS_BAR_COLORS = {
  ok: "bg-fizz-400/80",
  error: "bg-red-500/80",
} as const;

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export default function TracesPage() {
  const provider = useDataProvider();

  const [traces, setTraces] = useState<Trace[]>([]);
  const [selectedTraceId, setSelectedTraceId] = useState<string | null>(null);
  const [selectedSpan, setSelectedSpan] = useState<TraceSpan | null>(null);
  const [loading, setLoading] = useState(true);

  // -----------------------------------------------------------------------
  // Data fetching
  // -----------------------------------------------------------------------

  const fetchTraces = useCallback(async () => {
    const data = await provider.getTraces(25);
    setTraces(data);
    setLoading(false);
  }, [provider]);

  useEffect(() => {
    fetchTraces();
  }, [fetchTraces]);

  useEffect(() => {
    const timer = setInterval(fetchTraces, REFRESH_INTERVAL_MS);
    return () => clearInterval(timer);
  }, [fetchTraces]);

  // -----------------------------------------------------------------------
  // Derived state
  // -----------------------------------------------------------------------

  const selectedTrace = useMemo(
    () => traces.find((t) => t.traceId === selectedTraceId) ?? null,
    [traces, selectedTraceId],
  );

  // Auto-select first trace
  useEffect(() => {
    if (traces.length > 0 && !selectedTraceId) {
      setSelectedTraceId(traces[0].traceId);
    }
  }, [traces, selectedTraceId]);

  // Clear span selection when trace changes
  useEffect(() => {
    setSelectedSpan(null);
  }, [selectedTraceId]);

  // Build span tree for indentation
  const spanTree = useMemo(() => {
    if (!selectedTrace) return [];
    const spans = selectedTrace.spans;
    const depthMap = new Map<string, number>();

    // Root span has depth 0
    for (const span of spans) {
      if (!span.parentSpanId) {
        depthMap.set(span.spanId, 0);
      }
    }

    // Assign depths via parent lookup
    let changed = true;
    while (changed) {
      changed = false;
      for (const span of spans) {
        if (depthMap.has(span.spanId)) continue;
        if (span.parentSpanId && depthMap.has(span.parentSpanId)) {
          depthMap.set(span.spanId, depthMap.get(span.parentSpanId)! + 1);
          changed = true;
        }
      }
    }

    return spans.map((span) => ({
      span,
      depth: depthMap.get(span.spanId) ?? 0,
    }));
  }, [selectedTrace]);

  // -----------------------------------------------------------------------
  // Render
  // -----------------------------------------------------------------------

  if (loading) {
    return (
      <div className="flex h-64 items-center justify-center">
        <span className="text-xs text-text-muted">
          Initializing distributed tracing collector...
        </span>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Page header */}
      <div>
        <h1 className="text-xl font-bold tracking-tight text-text-primary">
          Distributed Tracing Waterfall
        </h1>
        <p className="mt-1 text-xs text-text-secondary">
          End-to-end trace visualization for the FizzBuzz evaluation pipeline.
          Each trace captures the full span tree from request ingress through
          blockchain commit and compliance verification.
        </p>
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-4 gap-4">
        {/* Trace list */}
        <Card className="xl:col-span-1">
          <CardHeader>
            <h2 className="text-xs font-semibold text-text-secondary uppercase tracking-wider">
              Recent Traces
            </h2>
            <p className="text-[10px] text-text-muted mt-0.5">
              {traces.length} traces collected
            </p>
          </CardHeader>
          <CardContent className="p-0">
            <div className="max-h-[600px] overflow-y-auto">
              {traces.map((trace) => {
                const isSelected = trace.traceId === selectedTraceId;
                return (
                  <button
                    key={trace.traceId}
                    type="button"
                    onClick={() => setSelectedTraceId(trace.traceId)}
                    className={`w-full text-left px-4 py-2.5 border-b border-border-subtle transition-colors ${
                      isSelected
                        ? "bg-surface-overlay"
                        : "hover:bg-panel-750 hover:bg-surface-raised/50"
                    }`}
                  >
                    <div className="flex items-center gap-2">
                      <span
                        className={`h-2 w-2 rounded-full shrink-0 ${
                          trace.hasError
                            ? STATUS_COLORS.error
                            : STATUS_COLORS.ok
                        }`}
                      />
                      <span className="text-xs font-mono text-text-secondary truncate">
                        {trace.traceId.slice(0, 16)}...
                      </span>
                    </div>
                    <div className="flex items-center justify-between mt-1 ml-4">
                      <span className="text-[10px] text-text-muted">
                        {trace.spans.length} spans
                      </span>
                      <span className="text-[10px] font-mono text-text-secondary">
                        {trace.totalDurationMs.toFixed(2)}ms
                      </span>
                    </div>
                    <div className="ml-4 mt-0.5">
                      <span className="text-[10px] text-text-muted">
                        {formatRelativeTime(trace.timestamp)}
                      </span>
                    </div>
                  </button>
                );
              })}
            </div>
          </CardContent>
        </Card>

        {/* Waterfall view + Span detail */}
        <div className="xl:col-span-3 space-y-4">
          {/* Waterfall */}
          <Card>
            <CardHeader>
              <div className="flex items-center justify-between">
                <div>
                  <h2 className="text-xs font-semibold text-text-secondary uppercase tracking-wider">
                    Span Waterfall
                  </h2>
                  {selectedTrace && (
                    <p className="text-[10px] text-text-muted mt-0.5 font-mono">
                      Trace {selectedTrace.traceId.slice(0, 16)} &mdash;{" "}
                      {selectedTrace.totalDurationMs.toFixed(2)}ms total
                    </p>
                  )}
                </div>
                {selectedTrace?.hasError && (
                  <span className="rounded bg-red-500/20 px-2 py-0.5 text-[10px] font-medium text-red-400 border border-red-500/30">
                    Contains Errors
                  </span>
                )}
              </div>
            </CardHeader>
            <CardContent>
              {selectedTrace ? (
                <div className="space-y-1">
                  {/* Scale bar */}
                  <div className="flex items-center justify-between text-[9px] text-text-muted font-mono mb-2 px-1">
                    <span>0ms</span>
                    <span>
                      {(selectedTrace.totalDurationMs / 4).toFixed(1)}ms
                    </span>
                    <span>
                      {(selectedTrace.totalDurationMs / 2).toFixed(1)}ms
                    </span>
                    <span>
                      {((selectedTrace.totalDurationMs * 3) / 4).toFixed(1)}ms
                    </span>
                    <span>{selectedTrace.totalDurationMs.toFixed(1)}ms</span>
                  </div>

                  {/* Spans */}
                  {spanTree.map(({ span, depth }) => {
                    const totalMs = selectedTrace.totalDurationMs || 1;
                    const leftPct = (span.startTimeMs / totalMs) * 100;
                    const widthPct = Math.max(
                      0.5,
                      (span.durationMs / totalMs) * 100,
                    );
                    const isSpanSelected = selectedSpan?.spanId === span.spanId;

                    return (
                      <button
                        key={span.spanId}
                        type="button"
                        onClick={() => setSelectedSpan(span)}
                        className={`w-full text-left rounded px-1 py-1.5 transition-colors group ${
                          isSpanSelected
                            ? "bg-surface-overlay ring-1 ring-panel-500"
                            : "hover:bg-panel-700/50"
                        }`}
                      >
                        <div className="flex items-center gap-2">
                          {/* Label area */}
                          <div
                            className="shrink-0 text-[10px] truncate"
                            style={{
                              width: "180px",
                              paddingLeft: `${depth * 16}px`,
                            }}
                          >
                            <span
                              className={`h-1.5 w-1.5 rounded-full inline-block mr-1 ${
                                span.status === "error"
                                  ? STATUS_COLORS.error
                                  : STATUS_COLORS.ok
                              }`}
                            />
                            <span className="text-text-secondary group-hover:text-text-primary">
                              {span.operationName}
                            </span>
                          </div>

                          {/* Bar area */}
                          <div className="flex-1 relative h-5 bg-surface-base rounded overflow-hidden">
                            <div
                              className={`absolute top-0.5 bottom-0.5 rounded ${
                                STATUS_BAR_COLORS[span.status]
                              } transition-all`}
                              style={{
                                left: `${leftPct}%`,
                                width: `${widthPct}%`,
                                minWidth: "4px",
                              }}
                            />
                          </div>

                          {/* Duration */}
                          <span className="shrink-0 text-[10px] font-mono text-text-secondary w-16 text-right">
                            {span.durationMs.toFixed(2)}ms
                          </span>
                        </div>
                      </button>
                    );
                  })}
                </div>
              ) : (
                <div className="flex h-48 items-center justify-center">
                  <span className="text-xs text-text-muted">
                    Select a trace to view the span waterfall
                  </span>
                </div>
              )}
            </CardContent>
          </Card>

          {/* Span detail panel */}
          <Card>
            <CardHeader>
              <h2 className="text-xs font-semibold text-text-secondary uppercase tracking-wider">
                Span Details
              </h2>
            </CardHeader>
            <CardContent>
              {selectedSpan ? (
                <div className="space-y-3">
                  {/* Summary row */}
                  <div className="flex flex-wrap gap-3 text-xs">
                    <span className="rounded bg-surface-base px-2 py-1 font-mono text-text-secondary">
                      {selectedSpan.operationName}
                    </span>
                    <span className="rounded bg-surface-base px-2 py-1 text-text-secondary">
                      {selectedSpan.serviceName}
                    </span>
                    <span
                      className={`rounded px-2 py-1 font-mono ${
                        selectedSpan.status === "error"
                          ? "bg-red-500/20 text-red-400"
                          : "bg-fizz-400/20 text-fizz-400"
                      }`}
                    >
                      {selectedSpan.status.toUpperCase()}
                    </span>
                    <span className="rounded bg-surface-base px-2 py-1 font-mono text-text-secondary">
                      {selectedSpan.durationMs.toFixed(3)}ms
                    </span>
                  </div>

                  {/* IDs */}
                  <div className="grid grid-cols-2 gap-2 text-[10px]">
                    <div>
                      <span className="text-text-muted">Span ID</span>
                      <p className="font-mono text-text-secondary mt-0.5">
                        {selectedSpan.spanId}
                      </p>
                    </div>
                    <div>
                      <span className="text-text-muted">Parent Span</span>
                      <p className="font-mono text-text-secondary mt-0.5">
                        {selectedSpan.parentSpanId ?? "— (root)"}
                      </p>
                    </div>
                  </div>

                  {/* Attributes table */}
                  <div>
                    <h3 className="text-[10px] text-text-muted uppercase tracking-wider mb-1.5">
                      Attributes
                    </h3>
                    <div className="rounded border border-border-subtle overflow-hidden">
                      <table className="w-full text-[10px]">
                        <thead>
                          <tr className="bg-surface-base">
                            <th className="text-left px-3 py-1.5 text-text-muted font-medium">
                              Key
                            </th>
                            <th className="text-left px-3 py-1.5 text-text-muted font-medium">
                              Value
                            </th>
                          </tr>
                        </thead>
                        <tbody>
                          {Object.entries(selectedSpan.attributes).map(
                            ([key, value]) => (
                              <tr
                                key={key}
                                className="border-t border-border-subtle"
                              >
                                <td className="px-3 py-1.5 font-mono text-text-secondary">
                                  {key}
                                </td>
                                <td className="px-3 py-1.5 font-mono text-text-secondary">
                                  {value}
                                </td>
                              </tr>
                            ),
                          )}
                        </tbody>
                      </table>
                    </div>
                  </div>
                </div>
              ) : (
                <div className="flex h-20 items-center justify-center">
                  <span className="text-xs text-text-muted">
                    Click a span in the waterfall to inspect its attributes
                  </span>
                </div>
              )}
            </CardContent>
          </Card>
        </div>
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
  return `${hours}h ago`;
}
