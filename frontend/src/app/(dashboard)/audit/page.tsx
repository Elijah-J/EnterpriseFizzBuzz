"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { Pagination } from "@/components/ui/pagination";
import { Reveal } from "@/components/ui/reveal";
import { Skeleton } from "@/components/ui/skeleton";
import type {
  AuditEntry,
  AuditLogFilter,
  AuditLogSortField,
  PaginatedAuditLog,
} from "@/lib/data-providers";
import { useDataProvider } from "@/lib/data-providers";

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const DEFAULT_PAGE_SIZE = 25;
const REALTIME_POLL_INTERVAL_MS = 5_000;

const ACTION_OPTIONS: { label: string; value: AuditEntry["action"] }[] = [
  { label: "Audit Run", value: "audit-run" },
  { label: "Finding Created", value: "finding-created" },
  { label: "Finding Updated", value: "finding-updated" },
  { label: "Control Assessed", value: "control-assessed" },
  { label: "Policy Change", value: "policy-change" },
  { label: "Evidence Uploaded", value: "evidence-uploaded" },
];

const SEVERITY_OPTIONS = [
  { label: "All", value: "" },
  { label: "Critical", value: "critical" },
  { label: "High", value: "high" },
  { label: "Medium", value: "medium" },
  { label: "Low", value: "low" },
  { label: "Info", value: "info" },
] as const;

const OUTCOME_OPTIONS = [
  { label: "All", value: "" },
  { label: "Success", value: "success" },
  { label: "Failure", value: "failure" },
  { label: "Denied", value: "denied" },
  { label: "Error", value: "error" },
] as const;

const FRAMEWORK_OPTIONS = [
  { label: "All", value: "" },
  { label: "SOX", value: "SOX" },
  { label: "GDPR", value: "GDPR" },
  { label: "HIPAA", value: "HIPAA" },
  { label: "FizzBuzz-ISO-27001", value: "FIZZBUZZ-ISO-27001" },
] as const;

const SUBSYSTEM_OPTIONS = [
  { label: "All", value: "" },
  { label: "compliance-engine", value: "compliance-engine" },
  { label: "cache-subsystem", value: "cache-subsystem" },
  { label: "rule-engine", value: "rule-engine" },
  { label: "blockchain-ledger", value: "blockchain-ledger" },
  { label: "auth-service", value: "auth-service" },
  { label: "ml-pipeline", value: "ml-pipeline" },
  { label: "consensus-cluster", value: "consensus-cluster" },
  { label: "chaos-controller", value: "chaos-controller" },
  { label: "rate-limiter", value: "rate-limiter" },
  { label: "service-mesh", value: "service-mesh" },
] as const;

const PAGE_SIZE_OPTIONS = [25, 50, 100, 250] as const;

const SEVERITY_BADGE_VARIANT: Record<
  AuditEntry["severity"],
  "error" | "warning" | "info" | "success"
> = {
  critical: "error",
  high: "warning",
  medium: "info",
  low: "success",
  info: "info",
};

const ACTION_BADGE_VARIANT: Record<
  AuditEntry["action"],
  "error" | "warning" | "info" | "success"
> = {
  "audit-run": "info",
  "finding-created": "error",
  "finding-updated": "warning",
  "control-assessed": "success",
  "policy-change": "warning",
  "evidence-uploaded": "info",
};

const OUTCOME_COLORS: Record<AuditEntry["outcome"], string> = {
  success: "bg-fizz-950 text-fizz-400",
  failure: "bg-red-950 text-red-400",
  denied: "bg-amber-950 text-amber-400",
  error: "bg-surface-overlay text-text-secondary",
};

const SEVERITY_DOT_COLORS: Record<AuditEntry["severity"], string> = {
  critical: "bg-red-500",
  high: "bg-amber-500",
  medium: "bg-buzz-500",
  low: "bg-fizz-500",
  info: "bg-panel-400",
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

function formatTimestamp(isoString: string): string {
  const d = new Date(isoString);
  return d
    .toISOString()
    .replace("T", " ")
    .replace(/\.\d{3}Z$/, "Z");
}

function formatLocalTimestamp(isoString: string): string {
  const d = new Date(isoString);
  return d.toLocaleString();
}

function getDefaultDateFrom(): string {
  const d = new Date();
  d.setDate(d.getDate() - 7);
  return d.toISOString().slice(0, 10);
}

function getDefaultDateTo(): string {
  return new Date().toISOString().slice(0, 10);
}

function escapeCsvField(value: string): string {
  if (value.includes(",") || value.includes('"') || value.includes("\n")) {
    return `"${value.replace(/"/g, '""')}"`;
  }
  return value;
}

// ---------------------------------------------------------------------------
// Inline Components
// ---------------------------------------------------------------------------

function SortableHeader({
  label,
  field,
  currentField,
  currentDirection,
  onSort,
  width,
}: {
  label: string;
  field: AuditLogSortField;
  currentField: AuditLogSortField;
  currentDirection: "asc" | "desc";
  onSort: (field: AuditLogSortField) => void;
  width: string;
}) {
  const isActive = currentField === field;
  return (
    <th
      className={`px-3 py-2 text-left text-xs font-medium uppercase tracking-wider cursor-pointer select-none hover:text-text-primary transition-colors ${
        isActive ? "text-fizzbuzz-400" : "text-text-secondary"
      }`}
      style={{ width }}
      onClick={() => onSort(field)}
    >
      <span className="inline-flex items-center gap-1">
        {label}
        {isActive && (
          <span className="text-[10px]">
            {currentDirection === "asc" ? "\u25B2" : "\u25BC"}
          </span>
        )}
      </span>
    </th>
  );
}

function AuditEntryRow({
  entry,
  expanded,
  onToggle,
  onFilterBySession,
}: {
  entry: AuditEntry;
  expanded: boolean;
  onToggle: () => void;
  onFilterBySession: (sessionId: string) => void;
}) {
  return (
    <>
      <tr
        className="border-b border-border-subtle hover:bg-surface-raised/50 cursor-pointer transition-colors"
        onClick={onToggle}
      >
        <td
          className="px-3 py-2 text-xs font-mono text-text-secondary"
          title={`${formatTimestamp(entry.timestamp)}\n${formatLocalTimestamp(entry.timestamp)}`}
        >
          {relativeTime(entry.timestamp)}
        </td>
        <td className="px-3 py-2">
          <Badge variant={SEVERITY_BADGE_VARIANT[entry.severity]}>
            {entry.severity}
          </Badge>
        </td>
        <td className="px-3 py-2">
          <Badge variant={ACTION_BADGE_VARIANT[entry.action]}>
            {entry.action}
          </Badge>
        </td>
        <td
          className="px-3 py-2 text-xs text-text-secondary max-w-[140px] truncate"
          title={entry.actor}
        >
          {entry.actor}
        </td>
        <td className="px-3 py-2 text-xs font-mono text-text-secondary">
          {entry.subsystem}
        </td>
        <td className="px-3 py-2">
          <span
            className={`inline-flex items-center rounded-full px-2 py-0.5 text-[10px] font-medium ${OUTCOME_COLORS[entry.outcome]}`}
          >
            {entry.outcome}
          </span>
        </td>
        <td className="px-3 py-2 text-xs text-text-secondary">
          {entry.frameworkId}
        </td>
        <td
          className="px-3 py-2 text-xs text-text-secondary max-w-[250px] truncate"
          title={entry.description}
        >
          {entry.description}
        </td>
      </tr>
      {expanded && (
        <tr className="border-b border-border-subtle bg-surface-raised/30">
          <td colSpan={8} className="px-6 py-4">
            <div className="grid grid-cols-2 gap-4 text-xs">
              <div>
                <h4 className="text-text-secondary uppercase tracking-wider text-[10px] mb-2 font-medium">
                  Description
                </h4>
                <p className="text-text-secondary">{entry.description}</p>
              </div>
              <div>
                <h4 className="text-text-secondary uppercase tracking-wider text-[10px] mb-2 font-medium">
                  Details
                </h4>
                <dl className="space-y-1">
                  <div className="flex gap-2">
                    <dt className="text-text-muted min-w-[140px]">
                      Session Correlation ID
                    </dt>
                    <dd>
                      <button
                        className="text-fizzbuzz-400 hover:underline font-mono text-[11px]"
                        onClick={(e) => {
                          e.stopPropagation();
                          onFilterBySession(entry.sessionCorrelationId);
                        }}
                      >
                        {entry.sessionCorrelationId}
                      </button>
                    </dd>
                  </div>
                  <div className="flex gap-2">
                    <dt className="text-text-muted min-w-[140px]">Source IP</dt>
                    <dd className="text-text-secondary font-mono">
                      {entry.sourceIp}
                    </dd>
                  </div>
                  <div className="flex gap-2">
                    <dt className="text-text-muted min-w-[140px]">
                      Timestamp (ISO 8601)
                    </dt>
                    <dd className="text-text-secondary font-mono">
                      {formatTimestamp(entry.timestamp)}
                    </dd>
                  </div>
                  <div className="flex gap-2">
                    <dt className="text-text-muted min-w-[140px]">
                      Timestamp (local)
                    </dt>
                    <dd className="text-text-secondary font-mono">
                      {formatLocalTimestamp(entry.timestamp)}
                    </dd>
                  </div>
                  {entry.evaluationSessionId && (
                    <div className="flex gap-2">
                      <dt className="text-text-muted min-w-[140px]">
                        Evaluation Session
                      </dt>
                      <dd className="text-fizzbuzz-400 font-mono text-[11px]">
                        {entry.evaluationSessionId}
                      </dd>
                    </div>
                  )}
                </dl>
              </div>
              {entry.metadata && Object.keys(entry.metadata).length > 0 && (
                <div className="col-span-2">
                  <h4 className="text-text-secondary uppercase tracking-wider text-[10px] mb-2 font-medium">
                    Metadata
                  </h4>
                  <dl className="grid grid-cols-3 gap-x-4 gap-y-1">
                    {Object.entries(entry.metadata).map(([key, value]) => (
                      <div key={key} className="flex gap-2">
                        <dt className="text-text-muted font-mono">{key}</dt>
                        <dd className="text-text-secondary">{value}</dd>
                      </div>
                    ))}
                  </dl>
                </div>
              )}
            </div>
          </td>
        </tr>
      )}
    </>
  );
}

function TimelineNode({
  entry,
  expanded,
  onToggle,
  onFilterBySession,
  showDayHeader,
  dayLabel,
}: {
  entry: AuditEntry;
  expanded: boolean;
  onToggle: () => void;
  onFilterBySession: (sessionId: string) => void;
  showDayHeader: boolean;
  dayLabel: string;
}) {
  return (
    <>
      {showDayHeader && (
        <div className="flex items-center gap-3 py-2">
          <span className="text-xs font-semibold text-text-secondary uppercase tracking-wider">
            {dayLabel}
          </span>
          <div className="flex-1 border-t border-border-subtle" />
        </div>
      )}
      <div
        className="flex gap-3 py-2 cursor-pointer hover:bg-surface-raised/30 rounded px-2 transition-colors"
        onClick={onToggle}
      >
        {/* Timeline dot and line */}
        <div className="flex flex-col items-center w-4 pt-1">
          <div
            className={`w-3 h-3 rounded-full flex-shrink-0 ${SEVERITY_DOT_COLORS[entry.severity]}`}
          />
          <div className="w-px flex-1 bg-surface-overlay mt-1" />
        </div>
        {/* Content */}
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 text-xs">
            <span className="text-text-secondary font-mono">
              {new Date(entry.timestamp).toLocaleTimeString()}
            </span>
            <Badge variant={ACTION_BADGE_VARIANT[entry.action]}>
              {entry.action}
            </Badge>
            <span className="text-text-secondary truncate">{entry.actor}</span>
          </div>
          <p className="text-xs text-text-secondary mt-0.5 truncate">
            {entry.description}
          </p>
          {expanded && (
            <div className="mt-3 p-3 rounded bg-surface-raised/50 border border-border-subtle">
              <div className="grid grid-cols-2 gap-4 text-xs">
                <div>
                  <p className="text-text-secondary mb-2">
                    {entry.description}
                  </p>
                  <dl className="space-y-1">
                    <div className="flex gap-2">
                      <dt className="text-text-muted min-w-[120px]">
                        Severity
                      </dt>
                      <dd>
                        <Badge variant={SEVERITY_BADGE_VARIANT[entry.severity]}>
                          {entry.severity}
                        </Badge>
                      </dd>
                    </div>
                    <div className="flex gap-2">
                      <dt className="text-text-muted min-w-[120px]">Outcome</dt>
                      <dd>
                        <span
                          className={`inline-flex items-center rounded-full px-2 py-0.5 text-[10px] font-medium ${OUTCOME_COLORS[entry.outcome]}`}
                        >
                          {entry.outcome}
                        </span>
                      </dd>
                    </div>
                    <div className="flex gap-2">
                      <dt className="text-text-muted min-w-[120px]">
                        Subsystem
                      </dt>
                      <dd className="text-text-secondary font-mono">
                        {entry.subsystem}
                      </dd>
                    </div>
                    <div className="flex gap-2">
                      <dt className="text-text-muted min-w-[120px]">
                        Framework
                      </dt>
                      <dd className="text-text-secondary">
                        {entry.frameworkId}
                      </dd>
                    </div>
                    <div className="flex gap-2">
                      <dt className="text-text-muted min-w-[120px]">
                        Source IP
                      </dt>
                      <dd className="text-text-secondary font-mono">
                        {entry.sourceIp}
                      </dd>
                    </div>
                    <div className="flex gap-2">
                      <dt className="text-text-muted min-w-[120px]">
                        Session ID
                      </dt>
                      <dd>
                        <button
                          className="text-fizzbuzz-400 hover:underline font-mono text-[11px]"
                          onClick={(e) => {
                            e.stopPropagation();
                            onFilterBySession(entry.sessionCorrelationId);
                          }}
                        >
                          {entry.sessionCorrelationId}
                        </button>
                      </dd>
                    </div>
                    {entry.evaluationSessionId && (
                      <div className="flex gap-2">
                        <dt className="text-text-muted min-w-[120px]">
                          Eval Session
                        </dt>
                        <dd className="text-fizzbuzz-400 font-mono text-[11px]">
                          {entry.evaluationSessionId}
                        </dd>
                      </div>
                    )}
                  </dl>
                </div>
                {entry.metadata && Object.keys(entry.metadata).length > 0 && (
                  <div>
                    <h4 className="text-text-secondary uppercase tracking-wider text-[10px] mb-2 font-medium">
                      Metadata
                    </h4>
                    <dl className="space-y-1">
                      {Object.entries(entry.metadata).map(([key, value]) => (
                        <div key={key} className="flex gap-2">
                          <dt className="text-text-muted font-mono">{key}</dt>
                          <dd className="text-text-secondary">{value}</dd>
                        </div>
                      ))}
                    </dl>
                  </div>
                )}
              </div>
            </div>
          )}
        </div>
      </div>
    </>
  );
}

function PaginationControls({
  page,
  totalPages,
  pageSize,
  totalCount,
  onPageChange,
  onPageSizeChange,
}: {
  page: number;
  totalPages: number;
  pageSize: number;
  totalCount: number;
  onPageChange: (page: number) => void;
  onPageSizeChange: (size: number) => void;
}) {
  const startEntry = (page - 1) * pageSize + 1;
  const endEntry = Math.min(page * pageSize, totalCount);

  return (
    <div className="flex items-center justify-between px-3 py-3 border-t border-border-subtle">
      <div className="flex items-center gap-2 text-xs text-text-secondary">
        <span>Rows per page:</span>
        <select
          value={pageSize}
          onChange={(e) => onPageSizeChange(Number(e.target.value))}
          className="bg-surface-raised border border-border-default rounded px-2 py-1 text-xs text-text-secondary"
        >
          {PAGE_SIZE_OPTIONS.map((size) => (
            <option key={size} value={size}>
              {size}
            </option>
          ))}
        </select>
      </div>

      <span className="text-xs text-text-secondary">
        Showing {startEntry}-{endEntry} of {totalCount.toLocaleString()} entries
      </span>

      <Pagination
        total={totalCount}
        current={page}
        onPageChange={onPageChange}
        pageSize={pageSize}
      />
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main Page Component
// ---------------------------------------------------------------------------

export default function AuditLogPage() {
  const provider = useDataProvider();

  // ---------------------------------------------------------------------------
  // State
  // ---------------------------------------------------------------------------

  const [data, setData] = useState<PaginatedAuditLog | null>(null);
  const [loading, setLoading] = useState(true);
  const [viewMode, setViewMode] = useState<"table" | "timeline">("table");
  const [expandedRows, setExpandedRows] = useState<Set<string>>(new Set());
  const [realTimeEnabled, setRealTimeEnabled] = useState(false);
  const [newEntryIds, setNewEntryIds] = useState<Set<string>>(new Set());
  const previousEntryIdsRef = useRef<Set<string>>(new Set());

  // Filters
  const [dateFrom, setDateFrom] = useState(getDefaultDateFrom);
  const [dateTo, setDateTo] = useState(getDefaultDateTo);
  const [selectedActions, setSelectedActions] = useState<
    AuditEntry["action"][]
  >([]);
  const [actorFilter, setActorFilter] = useState("");
  const [severityFilter, setSeverityFilter] = useState("");
  const [outcomeFilter, setOutcomeFilter] = useState("");
  const [frameworkFilter, setFrameworkFilter] = useState("");
  const [subsystemFilter, setSubsystemFilter] = useState("");
  const [searchQuery, setSearchQuery] = useState("");

  // Pagination & sorting
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(DEFAULT_PAGE_SIZE);
  const [sortField, setSortField] = useState<AuditLogSortField>("timestamp");
  const [sortDirection, setSortDirection] = useState<"asc" | "desc">("desc");

  // Action dropdown
  const [actionDropdownOpen, setActionDropdownOpen] = useState(false);

  // ---------------------------------------------------------------------------
  // Derived filter object
  // ---------------------------------------------------------------------------

  const filters: AuditLogFilter = useMemo(
    () => ({
      dateFrom: dateFrom ? new Date(dateFrom).toISOString() : undefined,
      dateTo: dateTo
        ? new Date(dateTo + "T23:59:59.999Z").toISOString()
        : undefined,
      actions: selectedActions.length > 0 ? selectedActions : undefined,
      searchQuery: searchQuery || undefined,
      outcome: (outcomeFilter as AuditEntry["outcome"]) || undefined,
      severity: (severityFilter as AuditEntry["severity"]) || undefined,
      frameworkId: frameworkFilter || undefined,
      subsystem: subsystemFilter || undefined,
      actor: actorFilter || undefined,
    }),
    [
      dateFrom,
      dateTo,
      selectedActions,
      searchQuery,
      outcomeFilter,
      severityFilter,
      frameworkFilter,
      subsystemFilter,
      actorFilter,
    ],
  );

  // ---------------------------------------------------------------------------
  // Data fetching
  // ---------------------------------------------------------------------------

  const fetchData = useCallback(async () => {
    try {
      const result = await provider.getAuditLogPaginated(
        filters,
        page,
        pageSize,
        sortField,
        sortDirection,
      );

      // Track new entries for real-time animation
      if (realTimeEnabled && data) {
        const currentIds = new Set(result.entries.map((e) => e.id));
        const freshIds = new Set<string>();
        for (const id of currentIds) {
          if (!previousEntryIdsRef.current.has(id)) {
            freshIds.add(id);
          }
        }
        if (freshIds.size > 0) {
          setNewEntryIds(freshIds);
          setTimeout(() => setNewEntryIds(new Set()), 2000);
        }
        previousEntryIdsRef.current = currentIds;
      } else {
        previousEntryIdsRef.current = new Set(result.entries.map((e) => e.id));
      }

      setData(result);
    } finally {
      setLoading(false);
    }
  }, [
    provider,
    filters,
    page,
    pageSize,
    sortField,
    sortDirection,
    realTimeEnabled,
    data,
  ]);

  useEffect(() => {
    setLoading(true);
    fetchData();
  }, [filters, page, pageSize, sortField, sortDirection]);

  // Real-time polling
  useEffect(() => {
    if (!realTimeEnabled) return;
    const interval = setInterval(fetchData, REALTIME_POLL_INTERVAL_MS);
    return () => clearInterval(interval);
  }, [realTimeEnabled, fetchData]);

  // ---------------------------------------------------------------------------
  // Handlers
  // ---------------------------------------------------------------------------

  const handleSort = useCallback(
    (field: AuditLogSortField) => {
      if (field === sortField) {
        setSortDirection((d) => (d === "asc" ? "desc" : "asc"));
      } else {
        setSortField(field);
        setSortDirection("desc");
      }
      setPage(1);
    },
    [sortField],
  );

  const handlePageSizeChange = useCallback((size: number) => {
    setPageSize(size);
    setPage(1);
  }, []);

  const toggleRowExpansion = useCallback((id: string) => {
    setExpandedRows((prev) => {
      const next = new Set(prev);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
      }
      return next;
    });
  }, []);

  const handleFilterBySession = useCallback((sessionId: string) => {
    setSearchQuery(sessionId);
    setPage(1);
  }, []);

  const handleToggleAction = useCallback((action: AuditEntry["action"]) => {
    setSelectedActions((prev) => {
      if (prev.includes(action)) {
        return prev.filter((a) => a !== action);
      }
      return [...prev, action];
    });
    setPage(1);
  }, []);

  const clearFilters = useCallback(() => {
    setDateFrom(getDefaultDateFrom());
    setDateTo(getDefaultDateTo());
    setSelectedActions([]);
    setActorFilter("");
    setSeverityFilter("");
    setOutcomeFilter("");
    setFrameworkFilter("");
    setSubsystemFilter("");
    setSearchQuery("");
    setPage(1);
  }, []);

  // ---------------------------------------------------------------------------
  // Export handlers
  // ---------------------------------------------------------------------------

  const exportAll = useCallback(
    async (format: "csv" | "json") => {
      // Fetch all entries matching current filters (no pagination)
      const all = await provider.getAuditLogPaginated(
        filters,
        1,
        10000,
        sortField,
        sortDirection,
      );

      let content: string;
      let mimeType: string;
      let filename: string;

      if (format === "csv") {
        const headers = [
          "id",
          "timestamp",
          "action",
          "severity",
          "outcome",
          "actor",
          "subsystem",
          "frameworkId",
          "description",
          "sourceIp",
          "sessionCorrelationId",
          "evaluationSessionId",
          "metadata",
        ];
        const rows = all.entries.map((e) =>
          [
            e.id,
            e.timestamp,
            e.action,
            e.severity,
            e.outcome,
            e.actor,
            e.subsystem,
            e.frameworkId ?? "",
            e.description,
            e.sourceIp,
            e.sessionCorrelationId,
            e.evaluationSessionId ?? "",
            e.metadata ? JSON.stringify(e.metadata) : "",
          ]
            .map(escapeCsvField)
            .join(","),
        );
        content = [headers.join(","), ...rows].join("\n");
        mimeType = "text/csv";
        filename = `audit-log-export-${new Date().toISOString().slice(0, 10)}.csv`;
      } else {
        content = JSON.stringify(all.entries, null, 2);
        mimeType = "application/json";
        filename = `audit-log-export-${new Date().toISOString().slice(0, 10)}.json`;
      }

      const blob = new Blob([content], { type: mimeType });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    },
    [provider, filters, sortField, sortDirection],
  );

  // ---------------------------------------------------------------------------
  // Timeline grouping
  // ---------------------------------------------------------------------------

  const timelineGroups = useMemo(() => {
    if (!data) return [];
    const groups: { label: string; entries: AuditEntry[] }[] = [];
    let currentDay = "";

    for (const entry of data.entries) {
      const day = new Date(entry.timestamp).toLocaleDateString("en-US", {
        weekday: "long",
        year: "numeric",
        month: "long",
        day: "numeric",
      });
      if (day !== currentDay) {
        currentDay = day;
        groups.push({ label: day, entries: [] });
      }
      groups[groups.length - 1].entries.push(entry);
    }

    return groups;
  }, [data]);

  // ---------------------------------------------------------------------------
  // Render
  // ---------------------------------------------------------------------------

  return (
    <div className="space-y-6">
      {/* Page Header */}
      <div className="flex items-start justify-between">
        <div>
          <div className="flex items-center gap-3">
            <h1 className="heading-page">Audit Log</h1>
            {data && (
              <span className="inline-flex items-center rounded-full bg-surface-raised border border-border-default px-2.5 py-0.5 text-xs font-medium text-text-secondary">
                {data.totalCount.toLocaleString()} entries
              </span>
            )}
          </div>
          <p className="text-sm text-text-secondary mt-1">
            Centralized audit trail for SOX Section 302/404, GDPR Article 30,
            and HIPAA Security Rule compliance. Supports forensic investigation,
            incident correlation, and regulatory evidence production.
          </p>
        </div>
        <div className="flex items-center gap-2">
          {/* Real-time toggle */}
          <div className="flex items-center gap-2 mr-4">
            <button
              onClick={() => setRealTimeEnabled(!realTimeEnabled)}
              className={`relative inline-flex h-5 w-9 items-center rounded-full transition-colors ${
                realTimeEnabled ? "bg-fizzbuzz-600" : "bg-panel-600"
              }`}
            >
              <span
                className={`inline-block h-3.5 w-3.5 transform rounded-full bg-white transition-transform ${
                  realTimeEnabled ? "translate-x-4" : "translate-x-0.5"
                }`}
              />
            </button>
            <span className="text-xs text-text-secondary flex items-center gap-1.5">
              {realTimeEnabled && (
                <span className="h-2 w-2 rounded-full bg-fizzbuzz-400 animate-pulse" />
              )}
              Real-time
            </span>
          </div>

          {/* Export buttons */}
          <button
            onClick={() => exportAll("csv")}
            className="px-3 py-1.5 text-xs rounded bg-surface-raised border border-border-default text-text-secondary hover:bg-surface-overlay transition-colors"
          >
            Export CSV
          </button>
          <button
            onClick={() => exportAll("json")}
            className="px-3 py-1.5 text-xs rounded bg-surface-raised border border-border-default text-text-secondary hover:bg-surface-overlay transition-colors"
          >
            Export JSON
          </button>
        </div>
      </div>

      {/* Filter Bar */}
      <Card>
        <CardContent className="py-3">
          <div className="flex flex-wrap items-end gap-3">
            {/* Date range */}
            <div className="flex flex-col gap-1">
              <label className="text-[10px] text-text-muted uppercase tracking-wider">
                From
              </label>
              <input
                type="date"
                value={dateFrom}
                onChange={(e) => {
                  setDateFrom(e.target.value);
                  setPage(1);
                }}
                className="bg-surface-raised border border-border-default rounded px-2 py-1 text-xs text-text-secondary w-[130px]"
              />
            </div>
            <div className="flex flex-col gap-1">
              <label className="text-[10px] text-text-muted uppercase tracking-wider">
                To
              </label>
              <input
                type="date"
                value={dateTo}
                onChange={(e) => {
                  setDateTo(e.target.value);
                  setPage(1);
                }}
                className="bg-surface-raised border border-border-default rounded px-2 py-1 text-xs text-text-secondary w-[130px]"
              />
            </div>

            {/* Action type multi-select */}
            <div className="flex flex-col gap-1 relative">
              <label className="text-[10px] text-text-muted uppercase tracking-wider">
                Action
              </label>
              <button
                className="bg-surface-raised border border-border-default rounded px-2 py-1 text-xs text-text-secondary w-[160px] text-left"
                onClick={() => setActionDropdownOpen(!actionDropdownOpen)}
              >
                {selectedActions.length === 0
                  ? "All actions"
                  : `${selectedActions.length} selected`}
              </button>
              {actionDropdownOpen && (
                <div className="absolute top-full left-0 mt-1 z-50 bg-surface-raised border border-border-default rounded shadow-lg py-1 w-[200px]">
                  {ACTION_OPTIONS.map((opt) => (
                    <label
                      key={opt.value}
                      className="flex items-center gap-2 px-3 py-1 hover:bg-surface-overlay cursor-pointer text-xs text-text-secondary"
                    >
                      <input
                        type="checkbox"
                        checked={selectedActions.includes(opt.value)}
                        onChange={() => handleToggleAction(opt.value)}
                        className="rounded"
                      />
                      {opt.label}
                    </label>
                  ))}
                </div>
              )}
            </div>

            {/* Actor */}
            <div className="flex flex-col gap-1">
              <label className="text-[10px] text-text-muted uppercase tracking-wider">
                Actor
              </label>
              <input
                type="text"
                value={actorFilter}
                onChange={(e) => {
                  setActorFilter(e.target.value);
                  setPage(1);
                }}
                placeholder="Filter by actor"
                className="bg-surface-raised border border-border-default rounded px-2 py-1 text-xs text-text-secondary w-[140px]"
              />
            </div>

            {/* Severity */}
            <div className="flex flex-col gap-1">
              <label className="text-[10px] text-text-muted uppercase tracking-wider">
                Severity
              </label>
              <select
                value={severityFilter}
                onChange={(e) => {
                  setSeverityFilter(e.target.value);
                  setPage(1);
                }}
                className="bg-surface-raised border border-border-default rounded px-2 py-1 text-xs text-text-secondary w-[100px]"
              >
                {SEVERITY_OPTIONS.map((opt) => (
                  <option key={opt.value} value={opt.value}>
                    {opt.label}
                  </option>
                ))}
              </select>
            </div>

            {/* Outcome */}
            <div className="flex flex-col gap-1">
              <label className="text-[10px] text-text-muted uppercase tracking-wider">
                Outcome
              </label>
              <select
                value={outcomeFilter}
                onChange={(e) => {
                  setOutcomeFilter(e.target.value);
                  setPage(1);
                }}
                className="bg-surface-raised border border-border-default rounded px-2 py-1 text-xs text-text-secondary w-[100px]"
              >
                {OUTCOME_OPTIONS.map((opt) => (
                  <option key={opt.value} value={opt.value}>
                    {opt.label}
                  </option>
                ))}
              </select>
            </div>

            {/* Framework */}
            <div className="flex flex-col gap-1">
              <label className="text-[10px] text-text-muted uppercase tracking-wider">
                Framework
              </label>
              <select
                value={frameworkFilter}
                onChange={(e) => {
                  setFrameworkFilter(e.target.value);
                  setPage(1);
                }}
                className="bg-surface-raised border border-border-default rounded px-2 py-1 text-xs text-text-secondary w-[160px]"
              >
                {FRAMEWORK_OPTIONS.map((opt) => (
                  <option key={opt.value} value={opt.value}>
                    {opt.label}
                  </option>
                ))}
              </select>
            </div>

            {/* Subsystem */}
            <div className="flex flex-col gap-1">
              <label className="text-[10px] text-text-muted uppercase tracking-wider">
                Subsystem
              </label>
              <select
                value={subsystemFilter}
                onChange={(e) => {
                  setSubsystemFilter(e.target.value);
                  setPage(1);
                }}
                className="bg-surface-raised border border-border-default rounded px-2 py-1 text-xs text-text-secondary w-[160px]"
              >
                {SUBSYSTEM_OPTIONS.map((opt) => (
                  <option key={opt.value} value={opt.value}>
                    {opt.label}
                  </option>
                ))}
              </select>
            </div>

            {/* Search */}
            <div className="flex flex-col gap-1">
              <label className="text-[10px] text-text-muted uppercase tracking-wider">
                Search
              </label>
              <input
                type="text"
                value={searchQuery}
                onChange={(e) => {
                  setSearchQuery(e.target.value);
                  setPage(1);
                }}
                placeholder="Search descriptions..."
                className="bg-surface-raised border border-border-default rounded px-2 py-1 text-xs text-text-secondary w-[160px]"
              />
            </div>

            {/* Clear filters */}
            <button
              onClick={clearFilters}
              className="px-3 py-1 text-xs rounded bg-surface-overlay text-text-secondary hover:bg-panel-600 transition-colors"
            >
              Clear filters
            </button>
          </div>
        </CardContent>
      </Card>

      {/* View Toggle */}
      <div className="flex items-center gap-1 bg-surface-raised rounded-lg p-0.5 w-fit">
        <button
          onClick={() => setViewMode("table")}
          className={`px-3 py-1 text-xs rounded-md transition-colors ${
            viewMode === "table"
              ? "bg-surface-overlay text-text-primary"
              : "text-text-secondary hover:text-text-secondary"
          }`}
        >
          Table View
        </button>
        <button
          onClick={() => setViewMode("timeline")}
          className={`px-3 py-1 text-xs rounded-md transition-colors ${
            viewMode === "timeline"
              ? "bg-surface-overlay text-text-primary"
              : "text-text-secondary hover:text-text-secondary"
          }`}
        >
          Timeline View
        </button>
      </div>

      {/* Main Content */}
      {loading && !data ? (
        <Card>
          <CardContent className="py-12 text-center">
            <p className="text-sm text-text-secondary">Loading audit log...</p>
          </CardContent>
        </Card>
      ) : data && viewMode === "table" ? (
        <Card>
          <div className="overflow-x-auto">
            <table className="w-full text-left">
              <thead className="border-b border-border-subtle bg-surface-raised/50">
                <tr>
                  <SortableHeader
                    label="Timestamp"
                    field="timestamp"
                    currentField={sortField}
                    currentDirection={sortDirection}
                    onSort={handleSort}
                    width="140px"
                  />
                  <SortableHeader
                    label="Severity"
                    field="severity"
                    currentField={sortField}
                    currentDirection={sortDirection}
                    onSort={handleSort}
                    width="80px"
                  />
                  <SortableHeader
                    label="Action"
                    field="action"
                    currentField={sortField}
                    currentDirection={sortDirection}
                    onSort={handleSort}
                    width="120px"
                  />
                  <SortableHeader
                    label="Actor"
                    field="actor"
                    currentField={sortField}
                    currentDirection={sortDirection}
                    onSort={handleSort}
                    width="140px"
                  />
                  <SortableHeader
                    label="Subsystem"
                    field="subsystem"
                    currentField={sortField}
                    currentDirection={sortDirection}
                    onSort={handleSort}
                    width="130px"
                  />
                  <SortableHeader
                    label="Outcome"
                    field="outcome"
                    currentField={sortField}
                    currentDirection={sortDirection}
                    onSort={handleSort}
                    width="80px"
                  />
                  <th
                    className="px-3 py-2 text-left text-xs font-medium uppercase tracking-wider text-text-secondary"
                    style={{ width: "100px" }}
                  >
                    Framework
                  </th>
                  <th className="px-3 py-2 text-left text-xs font-medium uppercase tracking-wider text-text-secondary">
                    Description
                  </th>
                </tr>
              </thead>
              <tbody>
                {data.entries.map((entry) => (
                  <AuditEntryRow
                    key={entry.id}
                    entry={entry}
                    expanded={expandedRows.has(entry.id)}
                    onToggle={() => toggleRowExpansion(entry.id)}
                    onFilterBySession={handleFilterBySession}
                  />
                ))}
                {data.entries.length === 0 && (
                  <tr>
                    <td
                      colSpan={8}
                      className="px-3 py-12 text-center text-sm text-text-secondary"
                    >
                      No audit entries match the current filters.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
          <PaginationControls
            page={data.page}
            totalPages={data.totalPages}
            pageSize={data.pageSize}
            totalCount={data.totalCount}
            onPageChange={setPage}
            onPageSizeChange={handlePageSizeChange}
          />
        </Card>
      ) : data && viewMode === "timeline" ? (
        <Card>
          <CardContent className="py-4">
            <div className="space-y-0">
              {timelineGroups.map((group, gIdx) =>
                group.entries.map((entry, eIdx) => (
                  <TimelineNode
                    key={entry.id}
                    entry={entry}
                    expanded={expandedRows.has(entry.id)}
                    onToggle={() => toggleRowExpansion(entry.id)}
                    onFilterBySession={handleFilterBySession}
                    showDayHeader={eIdx === 0}
                    dayLabel={group.label}
                  />
                )),
              )}
              {data.entries.length === 0 && (
                <p className="text-sm text-text-secondary text-center py-12">
                  No audit entries match the current filters.
                </p>
              )}
            </div>
          </CardContent>
          <PaginationControls
            page={data.page}
            totalPages={data.totalPages}
            pageSize={data.pageSize}
            totalCount={data.totalCount}
            onPageChange={setPage}
            onPageSizeChange={handlePageSizeChange}
          />
        </Card>
      ) : null}
    </div>
  );
}
