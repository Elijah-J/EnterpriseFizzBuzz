# PLAN.md — Compliance Center

## 1. Overview

The Enterprise FizzBuzz Platform operates under four regulatory frameworks: SOX (Sarbanes-Oxley Section 404 for financial integrity of FizzBuzz evaluation receipts), GDPR (General Data Protection Regulation for evaluation session data subject rights), HIPAA (Health Insurance Portability and Accountability Act, applicable because FizzBuzz outputs are classified as Protected Health Information under the platform's medical-grade evaluation tier), and FizzBuzz-ISO-27001 (the platform's proprietary information security management standard governing evaluation pipeline integrity).

The Compliance Center provides a unified operational view across all four frameworks. It surfaces the aggregate compliance posture score, per-framework control status, active findings requiring remediation, and a searchable audit trail. Without this page, compliance officers must cross-reference four separate dashboards — an unacceptable operational overhead for a platform processing mission-critical FizzBuzz evaluations at enterprise scale.

The page will be located at `/compliance` within the Operations Center, following the same data-provider architecture used by the Health Check Matrix and SLA Dashboard pages.

---

## 2. New Types

Add the following interfaces to `frontend/src/lib/data-providers/types.ts`:

```typescript
// ---------------------------------------------------------------------------
// Compliance Center types
// ---------------------------------------------------------------------------

/** Regulatory framework compliance status. */
export interface ComplianceFramework {
  /** Unique framework identifier (e.g., "SOX", "GDPR", "HIPAA", "FIZZBUZZ-ISO-27001"). */
  id: string;
  /** Full display name of the framework. */
  name: string;
  /** Current compliance score as a percentage (0-100). */
  complianceScore: number;
  /** Total number of controls defined under this framework. */
  totalControls: number;
  /** Number of controls currently passing validation. */
  passingControls: number;
  /** Number of controls that have failed their most recent assessment. */
  failingControls: number;
  /** Number of controls not yet assessed in the current audit cycle. */
  pendingControls: number;
  /** Overall framework status derived from control pass rates and finding severity. */
  status: "compliant" | "at-risk" | "non-compliant";
  /** ISO 8601 timestamp of the most recent audit run. */
  lastAuditDate: string;
  /** ISO 8601 timestamp of the next scheduled audit. */
  nextAuditDate: string;
  /** Number of open findings against this framework. */
  openFindings: number;
}

/** Severity classification for compliance findings. */
export type FindingSeverity = "critical" | "high" | "medium" | "low";

/** A compliance finding representing a control deficiency or policy violation. */
export interface ComplianceFinding {
  /** Unique finding identifier (e.g., "CF-2024-0847"). */
  id: string;
  /** Framework this finding is associated with. */
  frameworkId: string;
  /** Control identifier within the framework (e.g., "SOX-404.3", "GDPR-Art.17"). */
  controlId: string;
  /** Severity of the finding. */
  severity: FindingSeverity;
  /** Short title summarizing the finding. */
  title: string;
  /** Detailed description of the deficiency, its impact, and recommended remediation. */
  description: string;
  /** Current lifecycle status. */
  status: "open" | "in-progress" | "remediated" | "accepted-risk";
  /** ISO 8601 timestamp when the finding was identified. */
  identifiedAt: string;
  /** ISO 8601 timestamp of the remediation deadline, if applicable. */
  dueDate?: string;
  /** Engineer or team assigned to remediation. */
  assignee?: string;
}

/** An entry in the compliance audit log. */
export interface AuditEntry {
  /** Unique audit entry identifier. */
  id: string;
  /** ISO 8601 timestamp of the event. */
  timestamp: string;
  /** Category of audit action. */
  action: "audit-run" | "finding-created" | "finding-updated" | "control-assessed" | "policy-change" | "evidence-uploaded";
  /** Framework associated with this entry, if applicable. */
  frameworkId?: string;
  /** Principal who performed the action (user or automated system). */
  actor: string;
  /** Human-readable summary of the audit event. */
  description: string;
  /** Arbitrary metadata for drill-down. */
  metadata?: Record<string, string>;
}
```

---

## 3. DataProvider Extensions

Add three new methods to the `IDataProvider` interface in `frontend/src/lib/data-providers/provider.ts`:

```typescript
/**
 * Retrieve compliance status for all regulatory frameworks.
 * Returns framework-level compliance scores, control counts,
 * and audit scheduling information.
 */
getComplianceFrameworks(): Promise<ComplianceFramework[]>;

/**
 * Retrieve compliance findings, optionally filtered by framework
 * and/or severity. Returns findings ordered by severity (critical first),
 * then by identification date (most recent first).
 */
getComplianceFindings(frameworkId?: string, severity?: FindingSeverity): Promise<ComplianceFinding[]>;

/**
 * Retrieve the compliance audit log. Returns audit entries ordered
 * by timestamp (most recent first).
 *
 * @param limit - Maximum number of entries to return (default: 50)
 */
getAuditLog(limit?: number): Promise<AuditEntry[]>;
```

Update the import in `provider.ts` to include `ComplianceFramework`, `ComplianceFinding`, `AuditEntry`, and `FindingSeverity` from `./types`.

Update the re-exports in `frontend/src/lib/data-providers/index.ts` to include the new types.

---

## 4. SimulationProvider Data

Implement the three new methods in `SimulationProvider` (`frontend/src/lib/data-providers/simulation-provider.ts`):

### 4.1 `getComplianceFrameworks()`

Generate four frameworks with the following profiles:

| Framework | ID | Total Controls | Typical Pass Rate | Typical Status |
|---|---|---|---|---|
| Sarbanes-Oxley Section 404 | SOX | 47 | 93-97% | compliant or at-risk |
| General Data Protection Regulation | GDPR | 38 | 85-92% | at-risk |
| HIPAA Security Rule | HIPAA | 54 | 90-96% | compliant or at-risk |
| FizzBuzz Information Security Standard | FIZZBUZZ-ISO-27001 | 62 | 96-100% | compliant |

Each call should apply small Gaussian jitter to passing/failing counts (within bounds) so the dashboard reflects realistic drift. `lastAuditDate` should be within the last 7 days. `nextAuditDate` should be 23-30 days in the future. `openFindings` should be derived from the failing controls count plus a small random offset.

### 4.2 `getComplianceFindings()`

Generate 15-25 findings distributed across the four frameworks. Include:

- 1-2 critical findings (e.g., "Blockchain audit receipt chain broken for 3 evaluation batches", "HIPAA-protected FizzBuzz results exposed in debug log")
- 3-5 high findings (e.g., "GDPR right-to-erasure SLA exceeded for 12 sessions", "SOX segregation of duties violation in rule engine configuration")
- 5-8 medium findings (e.g., "FizzBuzz-ISO-27001 key rotation overdue by 48 hours", "HIPAA access review for ML training data not completed")
- 4-6 low findings (e.g., "SOX audit trail timestamp precision reduced to seconds", "GDPR privacy impact assessment pending for quantum strategy")

Findings should have realistic `controlId` values (e.g., "SOX-404.3.7", "GDPR-Art.17.2", "HIPAA-164.312(a)(1)", "FIZZ-A.12.4.1"). Assignees should be drawn from the existing `ON_CALL_ROSTER`. Support filtering by `frameworkId` and `severity` parameters.

### 4.3 `getAuditLog()`

Generate 50 audit log entries spanning the last 7 days with a mix of action types:

- `audit-run`: "Automated SOX Section 404 assessment completed — 45/47 controls passed"
- `finding-created`: "New critical finding CF-2024-0912 created for HIPAA framework"
- `finding-updated`: "Finding CF-2024-0847 status changed from open to in-progress"
- `control-assessed`: "Control GDPR-Art.32.1 assessed as PASSING — encryption at rest verified"
- `policy-change`: "FizzBuzz-ISO-27001 password policy updated: minimum length increased to 128 characters"
- `evidence-uploaded`: "SOX Section 404 evidence artifact uploaded: Q4 evaluation pipeline reconciliation report"

Actors should include both automated systems ("Compliance Automation Engine", "SOX Continuous Monitor", "GDPR Data Controller") and human operators from the on-call roster.

---

## 5. Page Layout

Route: `/compliance` (file: `frontend/src/app/(dashboard)/compliance/page.tsx`)

### 5.1 Overall Compliance Score

A prominent hero section at the top containing:
- A large `MetricGauge` (size=140) showing the weighted average compliance score across all frameworks.
- Adjacent KPI tiles: "Total Controls" count, "Passing" count (green), "Failing" count (red), "Open Findings" count.
- A status label: "COMPLIANT", "AT RISK", or "NON-COMPLIANT" derived from the aggregate score thresholds (>=95 = compliant, >=80 = at-risk, <80 = non-compliant).

Use a `Card` wrapper. Layout: gauge on the left, KPI tiles in a row on the right.

### 5.2 Framework Cards

A 4-column responsive grid (`grid-cols-1 md:grid-cols-2 xl:grid-cols-4`) with one `Card` per framework:
- **Header**: Framework name + status `Badge` ("compliant" = success, "at-risk" = warning, "non-compliant" = error).
- **Score**: A smaller `MetricGauge` (size=80) showing the framework compliance percentage.
- **Control breakdown**: Text line showing "X/Y controls passing" with a simple CSS progress bar (green portion = passing, red portion = failing, gray portion = pending).
- **Audit dates**: "Last audit: 3 days ago" / "Next audit: in 25 days" in muted text.
- **Open findings**: "N open findings" count, colored by severity of the worst open finding.

### 5.3 Findings Table

A `Card` containing a filterable table of compliance findings:

**Filter controls** (above the table):
- Framework dropdown: All / SOX / GDPR / HIPAA / FizzBuzz-ISO-27001
- Severity dropdown: All / Critical / High / Medium / Low
- Status dropdown: All / Open / In Progress / Remediated / Accepted Risk

**Table columns**:
| ID | Severity | Framework | Control | Title | Status | Assignee | Due Date |
|---|---|---|---|---|---|---|---|

- Severity column uses colored `Badge` components (critical=error, high=warning, medium=info, low=success).
- Rows are expandable (click to reveal full description and remediation details).
- Default sort: severity descending, then identifiedAt descending.

### 5.4 Audit Log

A `Card` containing a searchable, filterable table of audit entries:

**Controls**:
- Text search input filtering on description text.
- Action type dropdown filter: All / Audit Run / Finding Created / Finding Updated / Control Assessed / Policy Change / Evidence Uploaded.

**Table columns**:
| Timestamp | Action | Framework | Actor | Description |
|---|---|---|---|---|

- Action column uses a colored `Badge` per action type.
- Timestamps displayed as relative time ("2h ago") with full ISO tooltip on hover.
- Most recent entries first.

### 5.5 Refresh Behavior

Auto-refresh every 10 seconds (compliance data is less volatile than real-time metrics). Show "Auto-refreshing every 10 seconds" footer text consistent with other pages.

---

## 6. Component Breakdown

### New Components

1. **`frontend/src/app/(dashboard)/compliance/page.tsx`** — Main Compliance Center page component. Contains all sections described above. Follows the same `"use client"` + `useDataProvider()` + `useCallback`/`useEffect` refresh pattern as the Health and SLA pages.

### Reused Components

- `@/components/ui/card` (`Card`, `CardContent`, `CardHeader`) — Section wrappers.
- `@/components/ui/badge` (`Badge`) — Status and severity badges.
- `@/components/charts/metric-gauge` (`MetricGauge`) — Overall compliance score and per-framework score gauges.

### Inline Components (defined within the page file, following the pattern set by Health and SLA pages)

- **`ComplianceProgressBar`** — A simple horizontal bar showing passing/failing/pending control proportions. CSS-only, no SVG required.
- **`FindingRow`** — Expandable table row component for the findings table.
- **`relativeTime()`** — Reuse the same relative time formatting helper as the Health page (define locally, as per existing convention of no shared utility files).

---

## 7. Sidebar Update

In `frontend/src/app/layout.tsx`, the "Platform" section already contains a non-linked "Compliance" list item (line 111). Update it to include an `<a href="/compliance">` link, matching the pattern used by "Metrics", "Traces", and "Alerts" links.

---

## 8. Files to Create/Modify

### Create

| File | Purpose |
|---|---|
| `frontend/src/app/(dashboard)/compliance/page.tsx` | Compliance Center page |

### Modify

| File | Changes |
|---|---|
| `frontend/src/lib/data-providers/types.ts` | Add `ComplianceFramework`, `ComplianceFinding`, `AuditEntry`, `FindingSeverity` types |
| `frontend/src/lib/data-providers/provider.ts` | Add `getComplianceFrameworks()`, `getComplianceFindings()`, `getAuditLog()` to `IDataProvider` |
| `frontend/src/lib/data-providers/simulation-provider.ts` | Implement the three new methods with realistic simulated data |
| `frontend/src/lib/data-providers/index.ts` | Re-export `ComplianceFramework`, `ComplianceFinding`, `AuditEntry`, `FindingSeverity` |
| `frontend/src/app/layout.tsx` | Add `<a href="/compliance">` link to the existing Compliance sidebar item |
