# PLAN: Audit Log Page

## Overview

The Enterprise FizzBuzz Platform requires a dedicated Audit Log page (`/audit`) that provides a comprehensive, enterprise-grade audit trail viewer. While the Compliance Center already includes an inline audit log section (limited to 50 entries with basic action/search filtering), the platform's regulatory obligations demand a full-featured audit interface with server-style pagination, advanced multi-dimensional filtering, timeline visualization, and data export capabilities.

This page is critical for SOX Section 302/404 certification, GDPR Article 30 record-keeping, and HIPAA Security Rule audit trail requirements. The existing inline view on the Compliance page is insufficient for forensic investigation, incident correlation, and regulatory evidence production.

## 1. Type Enrichment

The existing `AuditEntry` interface in `types.ts` covers basic fields (id, timestamp, action, frameworkId, actor, description, metadata). The dedicated audit page requires additional dimensions for filtering, correlation, and forensic analysis.

### New fields to add to `AuditEntry`

```typescript
/** Severity/importance level of the audit event. */
severity: "critical" | "high" | "medium" | "low" | "info";
/** Outcome of the audited operation. */
outcome: "success" | "failure" | "denied" | "error";
/** Session correlation identifier linking related audit events. */
sessionCorrelationId: string;
/** Source IP address or service identifier of the initiator. */
sourceIp: string;
/** Subsystem that generated this audit event. */
subsystem: string;
/** Evaluation session ID, if this event is associated with a specific evaluation. */
evaluationSessionId?: string;
```

### New type: `AuditLogFilter`

```typescript
export interface AuditLogFilter {
  /** ISO 8601 start of date range (inclusive). */
  dateFrom?: string;
  /** ISO 8601 end of date range (inclusive). */
  dateTo?: string;
  /** Filter by one or more action types. */
  actions?: AuditEntry["action"][];
  /** Free-text search across actor, description, and metadata values. */
  searchQuery?: string;
  /** Filter by outcome. */
  outcome?: AuditEntry["outcome"];
  /** Filter by severity. */
  severity?: AuditEntry["severity"];
  /** Filter by framework ID. */
  frameworkId?: string;
  /** Filter by subsystem. */
  subsystem?: string;
  /** Filter by actor (exact match). */
  actor?: string;
}
```

### New type: `PaginatedAuditLog`

```typescript
export interface PaginatedAuditLog {
  /** Audit entries for the current page. */
  entries: AuditEntry[];
  /** Total number of entries matching the current filters. */
  totalCount: number;
  /** Current page number (1-indexed). */
  page: number;
  /** Number of entries per page. */
  pageSize: number;
  /** Total number of pages. */
  totalPages: number;
}
```

### New type: `AuditLogSortField`

```typescript
export type AuditLogSortField = "timestamp" | "severity" | "action" | "actor" | "outcome" | "subsystem";
```

## 2. DataProvider Interface Extension

Add one new method to `IDataProvider` in `provider.ts`:

```typescript
/**
 * Retrieve paginated audit log entries with server-side filtering and sorting.
 * Supports multi-dimensional filtering for forensic investigation and
 * regulatory evidence production.
 *
 * @param filters - Filter criteria to apply
 * @param page - Page number (1-indexed)
 * @param pageSize - Entries per page
 * @param sortField - Field to sort by (default: "timestamp")
 * @param sortDirection - Sort direction (default: "desc")
 */
getAuditLogPaginated(
  filters: AuditLogFilter,
  page: number,
  pageSize: number,
  sortField?: AuditLogSortField,
  sortDirection?: "asc" | "desc",
): Promise<PaginatedAuditLog>;
```

The existing `getAuditLog(limit?)` method remains unchanged for backward compatibility with the Compliance Center page.

## 3. SimulationProvider Implementation

Generate **250 audit entries** with the following diversity requirements:

- **Timestamps**: Distributed across a 7-day window with realistic clustering (more events during business hours, periodic spikes around automated scan windows)
- **Actions**: All 6 action types represented with weighted distribution: `control-assessed` (30%), `audit-run` (15%), `finding-created` (15%), `finding-updated` (15%), `evidence-uploaded` (15%), `policy-change` (10%)
- **Actors**: Mix of automated systems (65%) and human operators from the existing `ON_CALL_ROSTER` (35%)
- **Severity**: Weighted distribution: `info` (40%), `low` (25%), `medium` (20%), `high` (10%), `critical` (5%)
- **Outcomes**: Weighted: `success` (75%), `failure` (10%), `denied` (10%), `error` (5%)
- **Source IPs**: Pool of 15-20 internal RFC 1918 addresses (10.0.x.x, 172.16.x.x) plus service mesh identifiers (e.g., `svc://compliance-engine`, `svc://cache-coherence`)
- **Subsystems**: `compliance-engine`, `cache-subsystem`, `rule-engine`, `blockchain-ledger`, `auth-service`, `ml-pipeline`, `consensus-cluster`, `chaos-controller`, `rate-limiter`, `service-mesh`
- **Session correlation**: Groups of 2-5 entries share the same `sessionCorrelationId` to simulate related operations (e.g., an audit run that creates findings)
- **Metadata**: Populated with 1-3 key-value pairs appropriate to the action type

Filtering, sorting, and pagination are performed in-memory against the pre-generated dataset. The dataset is generated once on first call and cached for the provider instance lifetime.

## 4. Page Layout

### 4.1 Page Header

- Title: "Audit Log"
- Subtitle describing the purpose of the centralized audit trail
- Entry count badge showing total entries matching current filters (e.g., "1,247 entries")

### 4.2 Filter Bar

A horizontally scrollable filter bar with the following controls:

| Control | Type | Notes |
|---|---|---|
| Date range | Two date inputs (from/to) | Default: last 7 days |
| Action type | Multi-select dropdown | All 6 action types as checkboxes |
| Actor | Text input with autocomplete | Searches across actor names |
| Severity | Single-select dropdown | critical / high / medium / low / info / All |
| Outcome | Single-select dropdown | success / failure / denied / error / All |
| Framework | Single-select dropdown | SOX / GDPR / HIPAA / FIZZBUZZ-ISO-27001 / All |
| Subsystem | Single-select dropdown | All 10 subsystems + All |
| Search | Text input | Free-text search across description and metadata |
| Clear filters | Button | Resets all filters to defaults |

### 4.3 View Toggle

A toggle between two views:

- **Table View** (default): Sortable data table
- **Timeline View**: Vertical chronological timeline

### 4.4 Audit Entry Table (Table View)

Sortable columns:

| Column | Width | Sortable | Notes |
|---|---|---|---|
| Timestamp | 140px | Yes | ISO 8601 with relative time tooltip |
| Severity | 80px | Yes | Color-coded badge |
| Action | 120px | Yes | Badge with action-specific color |
| Actor | 140px | Yes | Truncated with tooltip |
| Subsystem | 130px | Yes | Monospace font |
| Outcome | 80px | Yes | Color-coded: green=success, red=failure, amber=denied, gray=error |
| Framework | 100px | No | Short framework ID |
| Description | flex | No | Truncated, full text in expandable row |

**Expandable detail rows**: Clicking a row expands it to show:
- Full description text
- All metadata key-value pairs in a definition list
- Session correlation ID (clickable to filter by that session)
- Source IP address
- Evaluation session ID (if present, linked)
- Exact timestamp in ISO 8601 and local timezone

### 4.5 Timeline View

A vertical timeline with:
- Time axis on the left (grouped by day, then by hour)
- Colored dots by severity (critical=red, high=amber, medium=blue, low=green, info=gray)
- Each node shows: timestamp, action badge, actor, truncated description
- Clicking a node expands inline detail identical to the table's expandable row
- Correlated entries (same `sessionCorrelationId`) are connected by a subtle line

### 4.6 Export Controls

Two export buttons in the page header area:
- **Export CSV**: Downloads all entries matching current filters as CSV (not just current page)
- **Export JSON**: Downloads all entries matching current filters as JSON array

Both exports include all fields including metadata (metadata serialized as JSON string in CSV).

### 4.7 Pagination Controls

Bottom of the table:
- Page size selector: 25, 50, 100, 250
- Page navigation: First, Previous, page numbers, Next, Last
- Entry range indicator: "Showing 51-100 of 247 entries"

### 4.8 Real-Time Mode Toggle

A toggle switch in the header bar:
- When enabled: polls every 5 seconds, auto-prepends new entries to the top of the table, shows a subtle animation on new rows
- When disabled: static view, manual refresh only
- Default: disabled
- Visual indicator: pulsing dot when active

## 5. Sidebar Navigation Update

In `layout.tsx`, the "Audit Log" sidebar item currently has no `href`. Update it to link to `/audit`:

```tsx
<a
  href="/audit"
  className="block rounded px-2 py-1.5 hover:bg-panel-800 transition-colors"
>
  Audit Log
</a>
```

## 6. Files to Create/Modify

### Files to modify

| File | Changes |
|---|---|
| `frontend/src/lib/data-providers/types.ts` | Add `severity`, `outcome`, `sessionCorrelationId`, `sourceIp`, `subsystem`, `evaluationSessionId` fields to `AuditEntry`. Add `AuditLogFilter`, `PaginatedAuditLog`, `AuditLogSortField` types. |
| `frontend/src/lib/data-providers/provider.ts` | Add `getAuditLogPaginated()` method to `IDataProvider`. Import new types. |
| `frontend/src/lib/data-providers/simulation-provider.ts` | Implement `getAuditLogPaginated()` with 250-entry dataset generation, in-memory filtering/sorting/pagination. Update existing `getAuditLog()` to populate new fields for backward compatibility. |
| `frontend/src/lib/data-providers/index.ts` | Re-export new types (`AuditLogFilter`, `PaginatedAuditLog`, `AuditLogSortField`). |
| `frontend/src/app/layout.tsx` | Add `href="/audit"` to the Audit Log sidebar link. |

### Files to create

| File | Purpose |
|---|---|
| `frontend/src/app/(dashboard)/audit/page.tsx` | Main Audit Log page component with all sections described above (filter bar, table view, timeline view, export, pagination, real-time toggle). Single-file page component following the established pattern in the codebase. |
