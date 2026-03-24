"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { MetricGauge } from "@/components/charts/metric-gauge";
import { Accordion } from "@/components/ui/accordion";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { Reveal } from "@/components/ui/reveal";
import { Skeleton } from "@/components/ui/skeleton";
import { StatGroup } from "@/components/ui/stat-group";
import { Tabs } from "@/components/ui/tabs";
import type {
  AuditEntry,
  ComplianceFinding,
  ComplianceFramework,
  FindingSeverity,
} from "@/lib/data-providers";
import { useDataProvider } from "@/lib/data-providers";

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const REFRESH_INTERVAL_MS = 10_000;

const FRAMEWORK_OPTIONS = [
  { label: "All", value: "" },
  { label: "SOX", value: "SOX" },
  { label: "GDPR", value: "GDPR" },
  { label: "HIPAA", value: "HIPAA" },
  { label: "FizzBuzz-ISO-27001", value: "FIZZBUZZ-ISO-27001" },
] as const;

const SEVERITY_OPTIONS = [
  { label: "All", value: "" },
  { label: "Critical", value: "critical" },
  { label: "High", value: "high" },
  { label: "Medium", value: "medium" },
  { label: "Low", value: "low" },
] as const;

const STATUS_OPTIONS = [
  { label: "All", value: "" },
  { label: "Open", value: "open" },
  { label: "In Progress", value: "in-progress" },
  { label: "Remediated", value: "remediated" },
  { label: "Accepted Risk", value: "accepted-risk" },
] as const;

const ACTION_OPTIONS = [
  { label: "All", value: "" },
  { label: "Audit Run", value: "audit-run" },
  { label: "Finding Created", value: "finding-created" },
  { label: "Finding Updated", value: "finding-updated" },
  { label: "Control Assessed", value: "control-assessed" },
  { label: "Policy Change", value: "policy-change" },
  { label: "Evidence Uploaded", value: "evidence-uploaded" },
] as const;

const SEVERITY_BADGE_VARIANT: Record<
  FindingSeverity,
  "error" | "warning" | "info" | "success"
> = {
  critical: "error",
  high: "warning",
  medium: "info",
  low: "success",
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

const FRAMEWORK_STATUS_VARIANT: Record<
  ComplianceFramework["status"],
  "success" | "warning" | "error"
> = {
  compliant: "success",
  "at-risk": "warning",
  "non-compliant": "error",
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
// Inline Components
// ---------------------------------------------------------------------------

function ComplianceProgressBar({
  passing,
  failing,
  pending,
  total,
}: {
  passing: number;
  failing: number;
  pending: number;
  total: number;
}) {
  const passPct = (passing / total) * 100;
  const failPct = (failing / total) * 100;
  const pendPct = (pending / total) * 100;

  return (
    <div className="flex h-2 w-full overflow-hidden rounded-full bg-surface-overlay">
      <div
        className="bg-fizz-500 transition-all duration-300"
        style={{ width: `${passPct}%` }}
      />
      <div
        className="bg-red-500 transition-all duration-300"
        style={{ width: `${failPct}%` }}
      />
      <div
        className="bg-panel-500 transition-all duration-300"
        style={{ width: `${pendPct}%` }}
      />
    </div>
  );
}

function FindingRow({ finding }: { finding: ComplianceFinding }) {
  const [expanded, setExpanded] = useState(false);

  return (
    <>
      <tr
        className="border-b border-border-subtle hover:bg-surface-raised/50 cursor-pointer transition-colors"
        onClick={() => setExpanded(!expanded)}
      >
        <td className="px-3 py-2 text-xs font-mono text-text-secondary">
          {finding.id}
        </td>
        <td className="px-3 py-2">
          <Badge variant={SEVERITY_BADGE_VARIANT[finding.severity]}>
            {finding.severity}
          </Badge>
        </td>
        <td className="px-3 py-2 text-xs text-text-secondary">
          {finding.frameworkId}
        </td>
        <td className="px-3 py-2 text-xs font-mono text-text-secondary">
          {finding.controlId}
        </td>
        <td className="px-3 py-2 text-xs text-text-secondary max-w-[200px] truncate">
          {finding.title}
        </td>
        <td className="px-3 py-2 text-xs">
          <span
            className={`rounded px-1.5 py-0.5 text-[10px] font-medium ${
              finding.status === "open"
                ? "bg-red-950 text-red-400"
                : finding.status === "in-progress"
                  ? "bg-amber-950 text-amber-400"
                  : finding.status === "remediated"
                    ? "bg-fizz-950 text-fizz-400"
                    : "bg-surface-overlay text-text-secondary"
            }`}
          >
            {finding.status}
          </span>
        </td>
        <td className="px-3 py-2 text-xs text-text-secondary">
          {finding.assignee ?? "-"}
        </td>
        <td className="px-3 py-2 text-xs text-text-muted">
          {finding.dueDate ? relativeTime(finding.dueDate) : "-"}
        </td>
      </tr>
      {expanded && (
        <tr className="border-b border-border-subtle bg-surface-raised/30">
          <td colSpan={8} className="px-6 py-3">
            <p className="text-xs text-text-secondary leading-relaxed">
              {finding.description}
            </p>
            <div className="mt-2 flex gap-4 text-[10px] text-text-muted">
              <span>
                Identified:{" "}
                {new Date(finding.identifiedAt).toLocaleDateString()}
              </span>
              {finding.dueDate && (
                <span>
                  Due: {new Date(finding.dueDate).toLocaleDateString()}
                </span>
              )}
            </div>
          </td>
        </tr>
      )}
    </>
  );
}

// ---------------------------------------------------------------------------
// Page Component
// ---------------------------------------------------------------------------

export default function ComplianceCenterPage() {
  const provider = useDataProvider();

  // Data state
  const [frameworks, setFrameworks] = useState<ComplianceFramework[]>([]);
  const [findings, setFindings] = useState<ComplianceFinding[]>([]);
  const [auditLog, setAuditLog] = useState<AuditEntry[]>([]);

  // Findings filter state
  const [findingFrameworkFilter, setFindingFrameworkFilter] = useState("");
  const [findingSeverityFilter, setFindingSeverityFilter] = useState("");
  const [findingStatusFilter, setFindingStatusFilter] = useState("");

  // Audit log filter state
  const [auditSearchQuery, setAuditSearchQuery] = useState("");
  const [auditActionFilter, setAuditActionFilter] = useState("");

  // -----------------------------------------------------------------------
  // Data fetching
  // -----------------------------------------------------------------------

  const fetchData = useCallback(async () => {
    const [frameworkData, findingData, auditData] = await Promise.all([
      provider.getComplianceFrameworks(),
      provider.getComplianceFindings(
        findingFrameworkFilter || undefined,
        (findingSeverityFilter as FindingSeverity) || undefined,
      ),
      provider.getAuditLog(50),
    ]);
    setFrameworks(frameworkData);
    setFindings(findingData);
    setAuditLog(auditData);
  }, [provider, findingFrameworkFilter, findingSeverityFilter]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  useEffect(() => {
    const timer = setInterval(fetchData, REFRESH_INTERVAL_MS);
    return () => clearInterval(timer);
  }, [fetchData]);

  // -----------------------------------------------------------------------
  // Derived state
  // -----------------------------------------------------------------------

  const aggregateScore = useMemo(() => {
    if (frameworks.length === 0) return 0;
    const totalControls = frameworks.reduce((s, f) => s + f.totalControls, 0);
    const totalPassing = frameworks.reduce((s, f) => s + f.passingControls, 0);
    return totalControls > 0
      ? Math.round((totalPassing / totalControls) * 1000) / 10
      : 0;
  }, [frameworks]);

  const aggregateStatus = useMemo(() => {
    if (aggregateScore >= 95) return "COMPLIANT";
    if (aggregateScore >= 80) return "AT RISK";
    return "NON-COMPLIANT";
  }, [aggregateScore]);

  const aggregateStatusVariant = useMemo(() => {
    if (aggregateScore >= 95) return "success" as const;
    if (aggregateScore >= 80) return "warning" as const;
    return "error" as const;
  }, [aggregateScore]);

  const totalControls = useMemo(
    () => frameworks.reduce((s, f) => s + f.totalControls, 0),
    [frameworks],
  );
  const totalPassing = useMemo(
    () => frameworks.reduce((s, f) => s + f.passingControls, 0),
    [frameworks],
  );
  const totalFailing = useMemo(
    () => frameworks.reduce((s, f) => s + f.failingControls, 0),
    [frameworks],
  );
  const totalOpenFindings = useMemo(
    () => frameworks.reduce((s, f) => s + f.openFindings, 0),
    [frameworks],
  );

  const filteredFindings = useMemo(() => {
    let result = findings;
    if (findingStatusFilter) {
      result = result.filter((f) => f.status === findingStatusFilter);
    }
    return result;
  }, [findings, findingStatusFilter]);

  const filteredAuditLog = useMemo(() => {
    let result = auditLog;
    if (auditActionFilter) {
      result = result.filter((e) => e.action === auditActionFilter);
    }
    if (auditSearchQuery) {
      const q = auditSearchQuery.toLowerCase();
      result = result.filter((e) => e.description.toLowerCase().includes(q));
    }
    return result;
  }, [auditLog, auditActionFilter, auditSearchQuery]);

  // -----------------------------------------------------------------------
  // Render
  // -----------------------------------------------------------------------

  return (
    <div className="space-y-6">
      {/* Page header */}
      <div>
        <h1 className="text-xl font-bold tracking-tight text-text-primary">
          Compliance Center
        </h1>
        <p className="mt-1 text-xs text-text-secondary">
          Unified regulatory compliance monitoring across SOX, GDPR, HIPAA, and
          FizzBuzz-ISO-27001 frameworks. Control assessments, findings, and
          audit trails are consolidated for cross-framework operational
          visibility.
        </p>
      </div>

      {/* Compliance KPI Summary */}
      <StatGroup
        items={[
          { label: "Score", value: `${aggregateScore.toFixed(1)}%`, trend: { direction: aggregateScore >= 90 ? "up" as const : "down" as const, label: aggregateScore >= 90 ? "Compliant" : "Action Required" } },
          { label: "Controls", value: String(totalControls) },
          { label: "Passing", value: String(totalPassing), trend: { direction: "up" as const, label: `${totalControls > 0 ? ((totalPassing / totalControls) * 100).toFixed(0) : 0}%` } },
          { label: "Failing", value: String(totalFailing) },
          { label: "Open Findings", value: String(totalOpenFindings) },
        ]}
        className="rounded-lg border border-border-subtle bg-surface-raised px-4 py-3"
      />

      {/* Section 5.1: Overall Compliance Score */}
      <Card>
        <CardContent>
          <div className="flex flex-col md:flex-row items-center gap-6 py-2">
            {/* Gauge */}
            <div className="flex flex-col items-center gap-2">
              <MetricGauge
                value={aggregateScore}
                size={140}
                label="Aggregate Compliance"
              />
              <Badge variant={aggregateStatusVariant}>{aggregateStatus}</Badge>
            </div>

            {/* KPI tiles */}
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4 flex-1">
              <div className="rounded-lg border border-border-subtle bg-surface-raised p-3 text-center">
                <p className="text-[10px] text-text-muted uppercase tracking-wider">
                  Total Controls
                </p>
                <p className="text-2xl font-mono font-semibold text-text-primary mt-1">
                  {totalControls}
                </p>
              </div>
              <div className="rounded-lg border border-border-subtle bg-surface-raised p-3 text-center">
                <p className="text-[10px] text-text-muted uppercase tracking-wider">
                  Passing
                </p>
                <p className="text-2xl font-mono font-semibold text-fizz-400 mt-1">
                  {totalPassing}
                </p>
              </div>
              <div className="rounded-lg border border-border-subtle bg-surface-raised p-3 text-center">
                <p className="text-[10px] text-text-muted uppercase tracking-wider">
                  Failing
                </p>
                <p className="text-2xl font-mono font-semibold text-red-400 mt-1">
                  {totalFailing}
                </p>
              </div>
              <div className="rounded-lg border border-border-subtle bg-surface-raised p-3 text-center">
                <p className="text-[10px] text-text-muted uppercase tracking-wider">
                  Open Findings
                </p>
                <p className="text-2xl font-mono font-semibold text-amber-400 mt-1">
                  {totalOpenFindings}
                </p>
              </div>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Section 5.2: Framework Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-4">
        {frameworks.map((fw) => (
          <Card key={fw.id}>
            <CardHeader>
              <div className="flex items-center justify-between gap-2">
                <h2 className="text-sm font-semibold text-text-primary truncate">
                  {fw.name}
                </h2>
                <Badge variant={FRAMEWORK_STATUS_VARIANT[fw.status]}>
                  {fw.status}
                </Badge>
              </div>
            </CardHeader>
            <CardContent>
              <div className="space-y-3">
                {/* Score gauge */}
                <div className="flex justify-center">
                  <MetricGauge
                    value={fw.complianceScore}
                    size={80}
                    strokeWidth={6}
                  />
                </div>

                {/* Control breakdown */}
                <div>
                  <div className="flex items-center justify-between text-[10px] text-text-secondary mb-1">
                    <span>
                      {fw.passingControls}/{fw.totalControls} controls passing
                    </span>
                  </div>
                  <ComplianceProgressBar
                    passing={fw.passingControls}
                    failing={fw.failingControls}
                    pending={fw.pendingControls}
                    total={fw.totalControls}
                  />
                </div>

                {/* Audit dates */}
                <div className="text-[10px] text-text-muted space-y-0.5">
                  <p>Last audit: {relativeTime(fw.lastAuditDate)}</p>
                  <p>Next audit: {relativeTime(fw.nextAuditDate)}</p>
                </div>

                {/* Open findings */}
                <p className="text-xs text-amber-400 font-medium">
                  {fw.openFindings} open finding
                  {fw.openFindings !== 1 ? "s" : ""}
                </p>
              </div>
            </CardContent>
          </Card>
        ))}
      </div>

      {/* Section 5.3: Findings Table */}
      <Card>
        <CardHeader>
          <h2 className="heading-section">Compliance Findings</h2>
        </CardHeader>
        <CardContent>
          {/* Filter controls */}
          <div className="flex flex-wrap gap-3 mb-4">
            <select
              value={findingFrameworkFilter}
              onChange={(e) => setFindingFrameworkFilter(e.target.value)}
              className="rounded border border-border-default bg-surface-raised px-2 py-1 text-xs text-text-secondary outline-none"
            >
              {FRAMEWORK_OPTIONS.map((opt) => (
                <option key={opt.value} value={opt.value}>
                  {opt.label}
                </option>
              ))}
            </select>
            <select
              value={findingSeverityFilter}
              onChange={(e) => setFindingSeverityFilter(e.target.value)}
              className="rounded border border-border-default bg-surface-raised px-2 py-1 text-xs text-text-secondary outline-none"
            >
              {SEVERITY_OPTIONS.map((opt) => (
                <option key={opt.value} value={opt.value}>
                  {opt.label}
                </option>
              ))}
            </select>
            <select
              value={findingStatusFilter}
              onChange={(e) => setFindingStatusFilter(e.target.value)}
              className="rounded border border-border-default bg-surface-raised px-2 py-1 text-xs text-text-secondary outline-none"
            >
              {STATUS_OPTIONS.map((opt) => (
                <option key={opt.value} value={opt.value}>
                  {opt.label}
                </option>
              ))}
            </select>
          </div>

          {/* Table */}
          <div className="overflow-x-auto">
            <table className="w-full text-left">
              <thead>
                <tr className="border-b border-border-default text-[10px] text-text-muted uppercase tracking-wider">
                  <th className="px-3 py-2 font-medium">ID</th>
                  <th className="px-3 py-2 font-medium">Severity</th>
                  <th className="px-3 py-2 font-medium">Framework</th>
                  <th className="px-3 py-2 font-medium">Control</th>
                  <th className="px-3 py-2 font-medium">Title</th>
                  <th className="px-3 py-2 font-medium">Status</th>
                  <th className="px-3 py-2 font-medium">Assignee</th>
                  <th className="px-3 py-2 font-medium">Due Date</th>
                </tr>
              </thead>
              <tbody>
                {filteredFindings.map((finding) => (
                  <FindingRow key={finding.id} finding={finding} />
                ))}
                {filteredFindings.length === 0 && (
                  <tr>
                    <td
                      colSpan={8}
                      className="px-3 py-6 text-center text-xs text-text-muted"
                    >
                      No findings match the current filters
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>

      {/* Section 5.4: Audit Log */}
      <Card>
        <CardHeader>
          <h2 className="heading-section">Compliance Audit Log</h2>
        </CardHeader>
        <CardContent>
          {/* Filter controls */}
          <div className="flex flex-wrap gap-3 mb-4">
            <input
              type="text"
              value={auditSearchQuery}
              onChange={(e) => setAuditSearchQuery(e.target.value)}
              placeholder="Search audit log..."
              className="rounded border border-border-default bg-surface-raised px-2 py-1 text-xs text-text-secondary placeholder-panel-500 outline-none min-w-[200px]"
            />
            <select
              value={auditActionFilter}
              onChange={(e) => setAuditActionFilter(e.target.value)}
              className="rounded border border-border-default bg-surface-raised px-2 py-1 text-xs text-text-secondary outline-none"
            >
              {ACTION_OPTIONS.map((opt) => (
                <option key={opt.value} value={opt.value}>
                  {opt.label}
                </option>
              ))}
            </select>
          </div>

          {/* Table */}
          <div className="overflow-x-auto">
            <table className="w-full text-left">
              <thead>
                <tr className="border-b border-border-default text-[10px] text-text-muted uppercase tracking-wider">
                  <th className="px-3 py-2 font-medium">Timestamp</th>
                  <th className="px-3 py-2 font-medium">Action</th>
                  <th className="px-3 py-2 font-medium">Framework</th>
                  <th className="px-3 py-2 font-medium">Actor</th>
                  <th className="px-3 py-2 font-medium">Description</th>
                </tr>
              </thead>
              <tbody>
                {filteredAuditLog.map((entry) => (
                  <tr
                    key={entry.id}
                    className="border-b border-border-subtle hover:bg-surface-raised/50 transition-colors"
                  >
                    <td
                      className="px-3 py-2 text-xs text-text-secondary whitespace-nowrap"
                      title={entry.timestamp}
                    >
                      {relativeTime(entry.timestamp)}
                    </td>
                    <td className="px-3 py-2">
                      <Badge variant={ACTION_BADGE_VARIANT[entry.action]}>
                        {entry.action}
                      </Badge>
                    </td>
                    <td className="px-3 py-2 text-xs text-text-secondary">
                      {entry.frameworkId ?? "-"}
                    </td>
                    <td className="px-3 py-2 text-xs text-text-secondary whitespace-nowrap">
                      {entry.actor}
                    </td>
                    <td className="px-3 py-2 text-xs text-text-secondary">
                      {entry.description}
                    </td>
                  </tr>
                ))}
                {filteredAuditLog.length === 0 && (
                  <tr>
                    <td
                      colSpan={5}
                      className="px-3 py-6 text-center text-xs text-text-muted"
                    >
                      No audit entries match the current filters
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>

      {/* Refresh footer */}
      <p className="text-center text-[10px] text-text-muted">
        Auto-refreshing every 10 seconds
      </p>
    </div>
  );
}
