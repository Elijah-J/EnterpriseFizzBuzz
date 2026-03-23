/**
 * Core domain types for the Enterprise FizzBuzz Evaluation Platform.
 *
 * These types define the canonical data model for FizzBuzz evaluation
 * sessions. All data providers must produce results conforming to these
 * interfaces to ensure interoperability across the evaluation pipeline.
 */

export interface MatchedRule {
  /** The divisor that triggered this rule (e.g., 3 for Fizz, 5 for Buzz). */
  divisor: number;
  /** The label emitted by the rule when triggered. */
  label: string;
  /** Execution priority — lower values are evaluated first. */
  priority: number;
}

export interface FizzBuzzResult {
  /** The input integer that was evaluated. */
  number: number;
  /** The computed output string (e.g., "Fizz", "Buzz", "FizzBuzz", or the number itself). */
  output: string;
  /** Semantic classification of the result for display and analytics. */
  classification: "fizz" | "buzz" | "fizzbuzz" | "number";
  /** Rules that matched during evaluation, ordered by priority. */
  matchedRules: MatchedRule[];
  /** Wall-clock processing time for this individual evaluation, in nanoseconds. */
  processingTimeNs: number;
}

export interface EvaluationRequest {
  /** Start of the evaluation range (inclusive). */
  start: number;
  /** End of the evaluation range (inclusive). */
  end: number;
  /** Evaluation strategy to apply. */
  strategy:
    | "standard"
    | "chain_of_responsibility"
    | "machine_learning"
    | "quantum";
}

export interface EvaluationSession {
  /** Unique session identifier for audit trail correlation. */
  sessionId: string;
  /** Ordered evaluation results for the requested range. */
  results: FizzBuzzResult[];
  /** Aggregate processing time across all evaluations, in milliseconds. */
  totalProcessingTimeMs: number;
  /** Strategy identifier that produced these results. */
  strategy: string;
  /** ISO 8601 timestamp of evaluation completion. */
  evaluatedAt: string;
}

// ---------------------------------------------------------------------------
// Dashboard telemetry types
// ---------------------------------------------------------------------------

/** Health status for an individual infrastructure subsystem. */
export interface SubsystemHealth {
  /** Display name of the subsystem (e.g., "MESI Cache Coherence"). */
  name: string;
  /** Current operational status. */
  status: "up" | "degraded" | "down" | "unknown";
  /** ISO 8601 timestamp of the most recent health check. */
  lastChecked: string;
  /** Round-trip response time of the health probe, in milliseconds. */
  responseTimeMs: number;
}

/** Aggregate evaluation pipeline metrics for the current reporting window. */
export interface MetricsSummary {
  /** Total evaluations executed since system boot. */
  totalEvaluations: number;
  /** Current sustained evaluation throughput. */
  evaluationsPerSecond: number;
  /** Cache hit ratio (0..1) across all MESI-coherent nodes. */
  cacheHitRate: number;
  /** Mean end-to-end evaluation latency, in milliseconds. */
  averageLatencyMs: number;
  /** Seconds elapsed since last system cold start. */
  uptimeSeconds: number;
  /** Last 60 throughput samples for sparkline rendering. */
  throughputHistory: number[];
}

/** Service Level Agreement compliance snapshot. */
export interface SLAStatus {
  /** Rolling availability percentage (target: 99.95%). */
  availabilityPercent: number;
  /** Remaining error budget as a fraction (0..1). */
  errorBudgetRemaining: number;
  /** 99th-percentile evaluation latency, in milliseconds. */
  latencyP99Ms: number;
  /** Percentage of evaluations returning mathematically correct results. */
  correctnessPercent: number;
  /** Number of currently active incidents. */
  activeIncidents: number;
  /** Name of the on-call engineer for the current rotation. */
  onCallEngineer: string;
}

/** Historical health check data point for sparkline rendering. */
export interface HealthCheckPoint {
  /** Unix timestamp in milliseconds. */
  timestamp: number;
  /** Operational status at time of check. */
  status: string;
  /** Response time recorded during this check, in milliseconds. */
  responseTimeMs: number;
}

/** SLA error budget burn-down data point. */
export interface SLAHistoryPoint {
  /** Unix timestamp in milliseconds. */
  timestamp: number;
  /** Remaining error budget as a percentage (0..100). */
  budgetRemaining: number;
}

/** Incident record for the SLA incident timeline. */
export interface Incident {
  /** Unique incident identifier. */
  id: string;
  /** Severity classification per the platform's incident taxonomy. */
  severity: "P1" | "P2" | "P3" | "P4";
  /** Brief incident title for timeline display. */
  title: string;
  /** Extended incident description with technical detail. */
  description: string;
  /** ISO 8601 timestamp of incident start. */
  startedAt: string;
  /** ISO 8601 timestamp of resolution, if resolved. */
  resolvedAt?: string;
  /** Total incident duration in milliseconds. */
  durationMs: number;
}

/** Paxos consensus state for the distributed evaluation cluster. */
export interface ConsensusStatus {
  /** Node ID of the current Paxos leader. */
  leaderNode: string;
  /** Current ballot number in the Paxos protocol. */
  ballotNumber: number;
  /** Whether consensus has been achieved for the current epoch. */
  consensusAchieved: boolean;
  /** Total number of nodes participating in the cluster. */
  clusterSize: number;
  /** Number of nodes that have acknowledged the current leader. */
  nodesAcknowledged: number;
}

// ---------------------------------------------------------------------------
// Time series metrics types
// ---------------------------------------------------------------------------

/** A single data point in a metric time series. */
export interface TimeSeriesDataPoint {
  /** Unix timestamp in milliseconds. */
  timestamp: number;
  /** Observed metric value at this timestamp. */
  value: number;
}

/** Time series data for a named metric over a requested duration. */
export interface TimeSeriesData {
  /** Canonical metric name (e.g., "fizzbuzz_evaluations_total"). */
  metricName: string;
  /** Ordered data points for the requested time window. */
  dataPoints: TimeSeriesDataPoint[];
  /** Unit of measurement (e.g., "count", "seconds", "bytes", "percent"). */
  unit: string;
}

/** Descriptor for a registered platform metric. */
export interface MetricDefinition {
  /** Canonical metric name matching Prometheus naming conventions. */
  name: string;
  /** Metric type per OpenMetrics specification. */
  type: "counter" | "gauge" | "histogram";
  /** Human-readable description of what this metric measures. */
  description: string;
  /** Unit of measurement. */
  unit: string;
}

/** FizzBuck financial expenditure summary for FinOps reporting. */
export interface CostSummary {
  /** Current-period FizzBuck expenditure. */
  currentPeriodCost: number;
  /** Previous-period FizzBuck expenditure for trend comparison. */
  previousPeriodCost: number;
  /** Cost trend direction derived from period-over-period comparison. */
  trend: "up" | "down" | "stable";
  /** Cost per individual evaluation in FizzBucks. */
  costPerEvaluation: number;
}

// ---------------------------------------------------------------------------
// Distributed tracing types
// ---------------------------------------------------------------------------

/** A single span within a distributed trace. */
export interface TraceSpan {
  /** Unique identifier for this span. */
  spanId: string;
  /** Trace identifier linking all spans in a single evaluation path. */
  traceId: string;
  /** Parent span identifier, absent for root spans. */
  parentSpanId?: string;
  /** Operation being performed (e.g., "ValidationMiddleware"). */
  operationName: string;
  /** Service or subsystem that owns this span. */
  serviceName: string;
  /** Start time relative to the trace origin, in milliseconds. */
  startTimeMs: number;
  /** Wall-clock duration of the span, in milliseconds. */
  durationMs: number;
  /** Outcome of the span execution. */
  status: "ok" | "error";
  /** Arbitrary key-value metadata attached to the span for diagnostics. */
  attributes: Record<string, string>;
}

/** A complete distributed trace representing a single FizzBuzz evaluation path. */
export interface Trace {
  /** Unique identifier for this trace. */
  traceId: string;
  /** Span ID of the root span in this trace. */
  rootSpan: string;
  /** All spans that compose this trace, ordered by start time. */
  spans: TraceSpan[];
  /** Total end-to-end duration of the trace, in milliseconds. */
  totalDurationMs: number;
  /** ISO 8601 timestamp of trace collection. */
  timestamp: string;
  /** Whether any span in this trace has an error status. */
  hasError: boolean;
}

// ---------------------------------------------------------------------------
// Alert management types
// ---------------------------------------------------------------------------

/** An operational alert generated by the FizzBuzz monitoring subsystem. */
export interface Alert {
  /** Unique alert identifier. */
  id: string;
  /** Alert severity level determining escalation priority. */
  severity: "critical" | "warning" | "info";
  /** Infrastructure subsystem that originated this alert. */
  subsystem: string;
  /** Short summary of the alert condition. */
  title: string;
  /** Detailed description of the alert condition and potential impact. */
  description: string;
  /** ISO 8601 timestamp when the alert condition was first detected. */
  firedAt: string;
  /** Whether an operator has acknowledged this alert. */
  acknowledged: boolean;
  /** Whether this alert has been silenced to suppress notifications. */
  silenced: boolean;
}

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

// ---------------------------------------------------------------------------
// Analytics & Intelligence types
// ---------------------------------------------------------------------------

/** Classification count and proportion for a single FizzBuzz output category. */
export interface ClassificationDistribution {
  /** The classification category. */
  classification: "fizz" | "buzz" | "fizzbuzz" | "number";
  /** Absolute count of integers in this category within the range. */
  count: number;
  /** Proportion of total range (0..1). */
  proportion: number;
  /** Exact fraction representation (e.g., "4/15") for display. */
  fraction: string;
  /** Design token CSS color variable for this classification. */
  color: string;
}

/** A single cell in the divisibility heatmap grid. */
export interface HeatmapCell {
  /** The integer being tested. */
  number: number;
  /** The divisor being tested against. */
  divisor: number;
  /** Whether the number is evenly divisible by the divisor. */
  divisible: boolean;
  /** The remainder (number % divisor). */
  remainder: number;
}

/** Complete heatmap dataset for a range of numbers and divisors. */
export interface HeatmapData {
  /** All cells in the heatmap grid, ordered row-major (by number, then by divisor). */
  cells: HeatmapCell[];
  /** The numbers (rows) included in the heatmap. */
  numbers: number[];
  /** The divisors (columns) tested. */
  divisors: number[];
}

/** A single data point in the evaluation volume trend. */
export interface EvaluationTrendPoint {
  /** Unix timestamp in milliseconds. */
  timestamp: number;
  /** Total number of evaluations in this time bucket. */
  count: number;
  /** Evaluations classified as Fizz in this bucket. */
  fizz: number;
  /** Evaluations classified as Buzz in this bucket. */
  buzz: number;
  /** Evaluations classified as FizzBuzz in this bucket. */
  fizzbuzz: number;
  /** Evaluations classified as plain numbers in this bucket. */
  plain: number;
}

/** Evaluation volume trend over a time period. */
export interface EvaluationTrend {
  /** Ordered data points for the requested period. */
  dataPoints: EvaluationTrendPoint[];
  /** Total evaluations across the entire trend period. */
  totalEvaluations: number;
  /** The time bucket size in seconds (e.g., 3600 for hourly). */
  bucketSizeSeconds: number;
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
}

// ---------------------------------------------------------------------------
// Configuration Management types
// ---------------------------------------------------------------------------

/** Top-level category for grouping related configuration items. */
export type ConfigCategory =
  | "evaluation"
  | "cache"
  | "compliance"
  | "chaos"
  | "blockchain"
  | "ml"
  | "feature_flags"
  | "rate_limiting"
  | "sla"
  | "service_mesh"
  | "observability"
  | "persistence";

/** The primitive type of a configuration value, determining the input widget rendered. */
export type ConfigValueType = "string" | "number" | "boolean" | "enum";

/** A single configurable parameter of the platform. */
export interface ConfigItem {
  /** Stable machine identifier (e.g., "cache.eviction_policy"). */
  id: string;
  /** Human-readable display name. */
  name: string;
  /** Current effective value (always serialized as string). */
  value: string;
  /** Data type governing the editor widget. */
  type: ConfigValueType;
  /** For enum types, the set of allowed values. */
  enumValues?: string[];
  /** For number types, optional minimum value. */
  min?: number;
  /** For number types, optional maximum value. */
  max?: number;
  /** Short description of what this parameter controls. */
  description: string;
  /** Factory default value. */
  defaultValue: string;
  /** Category this item belongs to. */
  category: ConfigCategory;
  /** Whether this parameter requires a platform restart to take effect. */
  requiresRestart: boolean;
  /** ISO 8601 timestamp of the last modification, if ever changed from default. */
  lastModifiedAt?: string;
  /** Principal who last modified this value. */
  lastModifiedBy?: string;
}

/** Lifecycle state of a feature flag. */
export type FeatureFlagLifecycle = "development" | "testing" | "canary" | "ga" | "deprecated";

/** A feature flag governing progressive rollout of platform capabilities. */
export interface FeatureFlag {
  /** Unique flag identifier (e.g., "wuzz_rule_experimental"). */
  id: string;
  /** Human-readable flag name. */
  name: string;
  /** Extended description of the capability gated by this flag. */
  description: string;
  /** Whether the flag is currently enabled. */
  enabled: boolean;
  /** Percentage of evaluations receiving the flagged behavior (0-100). */
  rolloutPercentage: number;
  /** Current lifecycle state. */
  lifecycle: FeatureFlagLifecycle;
  /** ISO 8601 timestamp of the last state change. */
  lastToggledAt: string;
  /** Principal who last toggled this flag. */
  lastToggledBy: string;
}

/** Result of a configuration update operation. */
export interface ConfigUpdateResult {
  /** Whether the update was accepted. */
  success: boolean;
  /** Reason for rejection, if applicable. */
  error?: string;
  /** The updated configuration item. */
  item?: ConfigItem;
}

/** Result of a feature flag toggle operation. */
export interface FeatureFlagToggleResult {
  /** Whether the toggle was accepted. */
  success: boolean;
  /** Reason for rejection, if applicable. */
  error?: string;
  /** The updated feature flag. */
  flag?: FeatureFlag;
}

/** Filter criteria for paginated audit log queries. */
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

/** Paginated response for audit log queries. */
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

/** Sortable fields for audit log table columns. */
export type AuditLogSortField = "timestamp" | "severity" | "action" | "actor" | "outcome" | "subsystem";
