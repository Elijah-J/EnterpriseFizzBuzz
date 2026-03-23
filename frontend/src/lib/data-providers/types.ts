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
