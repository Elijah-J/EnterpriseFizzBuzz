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

// ---------------------------------------------------------------------------
// Blockchain Ledger types
// ---------------------------------------------------------------------------

/** A single FizzBuzz evaluation receipt recorded on-chain. */
export interface BlockTransaction {
  /** SHA-256 hash of the transaction payload. */
  hash: string;
  /** The input integer that was evaluated. */
  input: number;
  /** The computed output string (e.g., "Fizz", "Buzz", "FizzBuzz", or the number). */
  output: string;
  /** Semantic classification of the evaluation result. */
  classification: "fizz" | "buzz" | "fizzbuzz" | "number";
  /** ISO 8601 timestamp of the evaluation. */
  timestamp: string;
}

/**
 * A single block in the FizzBuzz blockchain, mirroring the Block dataclass
 * in the backend blockchain.py proof-of-work chain implementation.
 */
export interface Block {
  /** Block height (0-indexed, genesis block is 0). */
  index: number;
  /** SHA-256 hash of this block's contents (64 hex chars). */
  hash: string;
  /** SHA-256 hash of the previous block (64 hex chars). */
  previousHash: string;
  /** ISO 8601 timestamp of when this block was mined. */
  timestamp: string;
  /** Proof-of-work nonce discovered during mining. */
  nonce: number;
  /** Mining difficulty (number of leading zeros required in hash). */
  difficulty: number;
  /** FizzBuzz evaluation transactions included in this block. */
  transactions: BlockTransaction[];
  /** Wall-clock time spent mining this block, in milliseconds. */
  miningDurationMs: number;
}

/** Aggregate statistics for the blockchain ledger. */
export interface BlockchainStats {
  /** Current chain height (total number of blocks including genesis). */
  height: number;
  /** Total transactions across all blocks. */
  totalTransactions: number;
  /** Mean mining duration across all blocks, in milliseconds. */
  averageMiningTimeMs: number;
  /** Current proof-of-work difficulty level. */
  currentDifficulty: number;
  /** Estimated hash rate in hashes per second. */
  hashRate: number;
  /** Whether the full chain passes integrity validation. */
  chainValid: boolean;
}

// ---------------------------------------------------------------------------
// Quantum Circuit Workbench types
// ---------------------------------------------------------------------------

/** Supported quantum gate types matching the backend QuantumCircuit gate set. */
export type QuantumGateType = "H" | "X" | "Z" | "S" | "T" | "CNOT" | "CZ" | "SWAP" | "QFT" | "M";

/** A single gate placement within a quantum circuit. */
export interface QuantumGate {
  /** Gate type identifier matching the backend gate registry. */
  type: QuantumGateType;
  /** Primary target qubit index (0-indexed). */
  qubit: number;
  /** Control qubit index for two-qubit gates (CNOT, CZ, SWAP). Absent for single-qubit gates. */
  controlQubit?: number;
  /** Sequential position of this gate in the circuit's execution order. */
  step: number;
}

/** A named quantum circuit definition consisting of an ordered gate sequence. */
export interface QuantumCircuit {
  /** Unique circuit identifier. */
  id: string;
  /** Human-readable circuit name (e.g., "Shor-3 Divisibility Oracle"). */
  name: string;
  /** Extended description of the circuit's purpose and algorithmic basis. */
  description: string;
  /** Number of qubits in the circuit register. */
  numQubits: number;
  /** Ordered gate applications comprising the circuit. */
  gates: QuantumGate[];
  /** Number of classical measurement bits (typically equals numQubits). */
  numClassicalBits: number;
  /** Circuit depth (number of sequential gate steps). */
  depth: number;
}

/** A complex amplitude represented as a real/imaginary pair for JSON serialization. */
export interface ComplexAmplitude {
  /** Real component of the amplitude. */
  real: number;
  /** Imaginary component of the amplitude. */
  imag: number;
}

/** The quantum state vector after circuit execution, prior to measurement. */
export interface QuantumState {
  /** Complex amplitudes for each computational basis state |0...0> through |1...1>. */
  amplitudes: ComplexAmplitude[];
  /** Born-rule measurement probabilities for each basis state, derived from |amplitude|^2. */
  probabilities: number[];
  /** Number of qubits in the register. */
  numQubits: number;
  /** Basis state labels in ket notation (e.g., ["|00>", "|01>", "|10>", "|11>"]). */
  basisLabels: string[];
}

/** Results of executing a quantum circuit simulation over multiple measurement shots. */
export interface QuantumSimulationResult {
  /** The circuit that was executed. */
  circuit: QuantumCircuit;
  /** Final state vector after circuit execution (before measurement collapse). */
  finalState: QuantumState;
  /** Measurement outcome histogram: maps basis state label to observation count. */
  measurementCounts: Record<string, number>;
  /** Total number of measurement shots executed. */
  shotsExecuted: number;
  /** Ratio of quantum simulation wall-clock time to classical evaluation time.
   *  Values < 1.0 indicate quantum advantage. Values > 1.0 (the expected case
   *  for FizzBuzz) indicate classical superiority. */
  quantumAdvantageRatio: number;
  /** Wall-clock time for the quantum simulation in milliseconds. */
  quantumTimeMs: number;
  /** Wall-clock time for equivalent classical evaluation in milliseconds. */
  classicalTimeMs: number;
  /** ISO 8601 timestamp of simulation completion. */
  simulatedAt: string;
}

// ---------------------------------------------------------------------------
// Chaos Engineering types
// ---------------------------------------------------------------------------

/** Fault injection category matching the backend FaultType enum. */
export type FaultType =
  | "latency_injection"
  | "error_injection"
  | "resource_exhaustion"
  | "network_partition"
  | "cache_corruption"
  | "circuit_breaker_trip";

/** Execution status of a chaos experiment. */
export type ExperimentStatus = "pending" | "running" | "completed" | "failed" | "aborted";

/** Severity intensity level for fault injection (1-5). */
export type FaultIntensity = 1 | 2 | 3 | 4 | 5;

/** Result data captured after an experiment completes. */
export interface ExperimentResult {
  /** Number of evaluations affected by the injected fault. */
  evaluationsAffected: number;
  /** Number of evaluations that produced incorrect results. */
  corruptedResults: number;
  /** Time from fault injection to full recovery, in milliseconds. */
  recoveryTimeMs: number;
  /** Whether the circuit breaker triggered during the experiment. */
  circuitBreakerTripped: boolean;
  /** Peak error rate observed during the experiment window (0..1). */
  peakErrorRate: number;
  /** ISO 8601 timestamp of experiment completion. */
  completedAt: string;
}

/** A single chaos experiment targeting a specific subsystem with a defined fault type. */
export interface ChaosExperiment {
  /** Unique experiment identifier. */
  id: string;
  /** Human-readable experiment name. */
  name: string;
  /** Description of what this experiment tests and why. */
  description: string;
  /** Category of fault to inject. */
  faultType: FaultType;
  /** Infrastructure subsystem targeted by this experiment. */
  targetSubsystem: string;
  /** Fault severity intensity (1 = gentle breeze, 5 = apocalypse). */
  intensity: FaultIntensity;
  /** Current execution status. */
  status: ExperimentStatus;
  /** Estimated duration of the experiment in seconds. */
  estimatedDurationSec: number;
  /** Result data, populated after experiment completes. */
  results?: ExperimentResult;
  /** ISO 8601 timestamp of last execution, if ever run. */
  lastRunAt?: string;
}

/** Status of a Game Day scenario. */
export type GameDayStatus = "scheduled" | "in-progress" | "completed" | "failed";

/** A multi-phase Game Day scenario grouping related experiments. */
export interface GameDayScenario {
  /** Unique scenario identifier. */
  id: string;
  /** Scenario name (e.g., "Modulo Meltdown"). */
  name: string;
  /** Description of what this Game Day validates. */
  description: string;
  /** Ordered list of experiment IDs executed during this scenario. */
  experiments: string[];
  /** Current scenario status. */
  status: GameDayStatus;
  /** ISO 8601 timestamp when the scenario was started, if applicable. */
  startedAt?: string;
  /** ISO 8601 timestamp when the scenario completed, if applicable. */
  completedAt?: string;
  /** Number of phases in the scenario. */
  totalPhases: number;
  /** Index of the currently executing phase (0-based), if in progress. */
  currentPhase?: number;
}

// ---------------------------------------------------------------------------
// Consensus & Cluster Topology types
// ---------------------------------------------------------------------------

/** Role of a node within the Paxos consensus cluster. */
export type ClusterNodeRole = "leader" | "follower" | "candidate" | "observer";

/** Operational status of a cluster node. */
export type ClusterNodeStatus = "healthy" | "degraded" | "unreachable" | "partitioned";

/** A single node in the distributed FizzBuzz evaluation cluster. */
export interface ClusterNode {
  /** Unique node identifier (e.g., "fizz-eval-us-east-1a"). */
  id: string;
  /** Current role in the Paxos protocol. */
  role: ClusterNodeRole;
  /** Operational status based on heartbeat and health probe results. */
  status: ClusterNodeStatus;
  /** Deployment region for geographic topology rendering. */
  region: string;
  /** ISO 8601 timestamp of the most recent heartbeat received from this node. */
  lastHeartbeat: string;
  /** Highest ballot number this node has participated in. */
  ballotNumber: number;
  /** Index of the last committed log entry on this node. */
  logIndex: number;
}

/** An edge connecting two nodes in the cluster topology graph. */
export interface ClusterEdge {
  /** Source node identifier. */
  from: string;
  /** Target node identifier. */
  to: string;
  /** Round-trip latency between the two nodes, in milliseconds. */
  latencyMs: number;
  /** Whether this link is currently healthy. */
  healthy: boolean;
}

/** A completed or in-progress leader election event. */
export interface LeaderElection {
  /** Paxos term number for this election. */
  term: number;
  /** Node ID of the candidate that initiated the election. */
  candidateId: string;
  /** Number of votes received by the candidate. */
  votes: number;
  /** Total number of votes possible (cluster size). */
  totalVoters: number;
  /** ISO 8601 timestamp when the election was initiated. */
  startedAt: string;
  /** ISO 8601 timestamp when the election concluded, if resolved. */
  resolvedAt?: string;
  /** Election outcome. */
  outcome: "elected" | "rejected" | "timed-out" | "in-progress";
}

/** Paxos protocol message phase. */
export type PaxosMessageType = "prepare" | "promise" | "accept" | "accepted";

/** A single Paxos protocol message exchanged between cluster nodes. */
export interface PaxosMessage {
  /** Message identifier for deduplication. */
  id: string;
  /** Phase of the Paxos protocol this message belongs to. */
  type: PaxosMessageType;
  /** Sending node identifier. */
  from: string;
  /** Receiving node identifier. */
  to: string;
  /** Ballot number associated with this message. */
  ballotNumber: number;
  /** ISO 8601 timestamp of message transmission. */
  timestamp: string;
}

/** Complete cluster topology snapshot including nodes, edges, and leadership state. */
export interface ClusterTopology {
  /** All nodes in the cluster. */
  nodes: ClusterNode[];
  /** All edges (connections) between nodes. */
  edges: ClusterEdge[];
  /** Node ID of the current elected leader. */
  currentLeader: string;
  /** Current Paxos term number. */
  currentTerm: number;
}

/** Result of a simulated network partition. */
export interface PartitionSimulationResult {
  /** Whether a new leader was elected after the partition. */
  leaderElected: boolean;
  /** Node ID of the new leader, if elected. */
  newLeader?: string;
  /** New term number after the partition, if an election occurred. */
  newTerm?: number;
  /** Updated cluster topology reflecting the partition state. */
  topology: ClusterTopology;
  /** Paxos messages generated during the re-election, if any. */
  messages: PaxosMessage[];
  /** Human-readable explanation of what happened. */
  summary: string;
}

/** Aggregate chaos engineering metrics for the control plane summary bar. */
export interface ChaosMetrics {
  /** Total number of experiments executed since system initialization. */
  experimentsRun: number;
  /** Mean time to recovery across all completed experiments, in milliseconds. */
  meanTimeToRecovery: number;
  /** Overall platform resilience score (0-100) derived from experiment outcomes. */
  resilienceScore: number;
  /** Total number of faults successfully injected. */
  faultsInjected: number;
  /** Number of experiments currently in running state. */
  activeExperiments: number;
  /** Timestamp of the most recent experiment execution. */
  lastExperimentAt?: string;
  /** Historical MTTR data points for trend chart rendering. */
  mttrHistory: { timestamp: number; mttrMs: number }[];
}

// ---------------------------------------------------------------------------
// Genetic Algorithm Observatory types
// ---------------------------------------------------------------------------

/** A single FizzBuzz rule encoded as a gene — the atomic unit of FizzBuzz heredity. */
export interface GAGene {
  /** The divisor to test against (e.g., 3, 5, 7). */
  divisor: number;
  /** The string label emitted when the rule matches (e.g., "Fizz"). */
  label: string;
  /** Evaluation priority (lower = higher priority). */
  priority: number;
}

/** Multi-objective fitness score for a chromosome, matching the backend FitnessScore dataclass. */
export interface GAFitnessScore {
  /** How well the rules match canonical FizzBuzz output (0-1). */
  accuracy: number;
  /** Fraction of numbers in 1-100 that receive at least one label (0-1). */
  coverage: number;
  /** Number of unique labels, normalized (0-1). */
  distinctness: number;
  /** Average phonetic quality of labels (0-1). */
  phoneticHarmony: number;
  /** Preference for small/prime divisors (0-1). */
  mathematicalElegance: number;
  /** Weighted combination of all components (0-1). */
  overall: number;
}

/** A complete FizzBuzz rule set encoded as a chromosome. */
export interface GAChromosome {
  /** Unique identifier for tracking lineage. */
  chromosomeId: string;
  /** The list of genes (rules) in this chromosome. */
  genes: GAGene[];
  /** The generation in which this chromosome was created. */
  generation: number;
  /** The most recently computed fitness score. */
  fitness: GAFitnessScore;
  /** IDs of the parent chromosomes (empty for initial population). */
  parentIds: string[];
  /** Per-number correctness for the range 1-100: true if this chromosome produces the correct output. */
  correctnessMap: boolean[];
}

/** A snapshot of the population at a single generation. */
export interface GAPopulation {
  /** Zero-indexed generation number. */
  generation: number;
  /** All chromosomes in this generation. */
  chromosomes: GAChromosome[];
  /** Best fitness score in this generation. */
  bestFitness: number;
  /** Mean fitness across the population. */
  averageFitness: number;
  /** Worst fitness in this generation. */
  worstFitness: number;
  /** Shannon diversity index measuring genetic diversity (0 = monoculture, higher = diverse). */
  diversityIndex: number;
}

/** Complete history of an evolution run across all generations. */
export interface GAEvolutionHistory {
  /** Unique identifier for this evolution run. */
  runId: string;
  /** Configuration used for this run. */
  config: GAConfig;
  /** Population snapshots for each generation. */
  generations: GAPopulation[];
  /** ISO 8601 timestamp of run initiation. */
  startedAt: string;
  /** ISO 8601 timestamp of run completion. */
  completedAt?: string;
  /** Whether the run has finished (converged or hit max generations). */
  isComplete: boolean;
  /** The best chromosome discovered across all generations. */
  bestChromosome: GAChromosome;
}

/** Configuration parameters for an evolution run. */
export interface GAConfig {
  /** Number of chromosomes per generation. */
  populationSize: number;
  /** Probability of gene mutation per chromosome per generation (0-1). */
  mutationRate: number;
  /** Probability of crossover between selected parents (0-1). */
  crossoverRate: number;
  /** Number of top chromosomes preserved unchanged into the next generation. */
  elitismCount: number;
  /** Maximum number of generations before termination. */
  maxGenerations: number;
}

// ---------------------------------------------------------------------------
// Digital Twin Situation Room types
// ---------------------------------------------------------------------------

/** Per-subsystem comparison between live platform telemetry and twin model prediction. */
export interface TwinSubsystemState {
  /** Subsystem name matching SubsystemHealth.name. */
  name: string;
  /** Current live platform value for the primary metric. */
  liveValue: number;
  /** Digital twin's predicted value for the same metric. */
  twinValue: number;
  /** Unit of the metric (e.g., "ms", "eval/s", "FB$"). */
  unit: string;
  /** Drift between live and twin as a signed percentage. */
  driftPercent: number;
  /** Whether the subsystem is enabled in the twin model. */
  enabled: boolean;
}

/** Complete digital twin state including synchronization health and aggregate drift. */
export interface TwinState {
  /** Per-subsystem comparison between live platform and twin model. */
  subsystemStates: TwinSubsystemState[];
  /** Overall synchronization health of the twin. */
  syncStatus: "synchronized" | "drifting" | "desynchronized";
  /** ISO 8601 timestamp of last successful state sync. */
  lastSyncAt: string;
  /** Aggregate drift in FizzBuck Divergence Units (FBDUs). */
  aggregateDriftFBDU: number;
  /** Number of Monte Carlo simulations backing the current model. */
  simulationCount: number;
  /** Twin model construction timestamp. */
  modelBuiltAt: string;
}

/** A single data point in a Monte Carlo projection fan chart. */
export interface TwinProjectionPoint {
  /** Unix timestamp in milliseconds. */
  timestamp: number;
  /** Predicted mean value at this time step. */
  mean: number;
  /** Lower bound of the 90% confidence interval. */
  ci90Lower: number;
  /** Upper bound of the 90% confidence interval. */
  ci90Upper: number;
  /** Lower bound of the 50% confidence interval. */
  ci50Lower: number;
  /** Upper bound of the 50% confidence interval. */
  ci50Upper: number;
}

/** Monte Carlo projection dataset for a single metric over a specified horizon. */
export interface TwinProjection {
  /** Metric being projected. */
  metric: string;
  /** Human-readable metric label. */
  metricLabel: string;
  /** Unit of the projected metric. */
  unit: string;
  /** Projection horizon in seconds. */
  horizonSeconds: number;
  /** Number of Monte Carlo simulations used. */
  simulationCount: number;
  /** Ordered projection data points (fan chart data). */
  points: TwinProjectionPoint[];
}

/** Parameter overrides and projected impact for a what-if analysis scenario. */
export interface WhatIfScenario {
  /** Unique scenario identifier. */
  id: string;
  /** Human-readable scenario name. */
  name: string;
  /** Description of what this scenario tests. */
  description: string;
  /** Parameter overrides applied to the twin model. */
  parameterOverrides: Record<string, string | number | boolean>;
  /** Projected outcome after applying the overrides. */
  projectedOutcome: WhatIfOutcome;
}

/** Projected platform metrics after applying what-if parameter overrides. */
export interface WhatIfOutcome {
  /** Predicted mean evaluation latency in ms. */
  predictedLatencyMs: number;
  /** Predicted cost per evaluation in FizzBucks. */
  predictedCostFB: number;
  /** Predicted failure rate (0..1). */
  predictedFailureRate: number;
  /** Predicted throughput in evaluations per second. */
  predictedThroughput: number;
  /** Change vs current baseline as signed percentages. */
  latencyChangePercent: number;
  costChangePercent: number;
  failureRateChangePercent: number;
  throughputChangePercent: number;
}
