import type {
  EvaluationRequest,
  EvaluationSession,
  SubsystemHealth,
  MetricsSummary,
  SLAStatus,
  ConsensusStatus,
  CostSummary,
  TimeSeriesData,
  MetricDefinition,
  ComplianceFramework,
  ComplianceFinding,
  AuditEntry,
  FindingSeverity,
} from "./types";

/**
 * Abstract data provider interface for FizzBuzz evaluation operations.
 *
 * All evaluation backends — simulation, REST API, gRPC, WebSocket stream —
 * must implement this interface to participate in the platform's evaluation
 * pipeline. The DataProvider abstraction enables seamless switching between
 * local simulation and production backend services without modifying
 * consumer components.
 */
export interface IDataProvider {
  /** Human-readable name of this provider for display in diagnostics panels. */
  readonly name: string;

  /**
   * Execute a FizzBuzz evaluation across the specified range using the
   * requested strategy. Returns a complete session with all results
   * and associated metadata.
   */
  evaluate(request: EvaluationRequest): Promise<EvaluationSession>;

  /**
   * Retrieve the current health status for all monitored infrastructure
   * subsystems. Used by the Health Matrix widget for real-time operational
   * awareness.
   */
  getSystemHealth(): Promise<SubsystemHealth[]>;

  /**
   * Retrieve aggregate evaluation pipeline metrics for the current
   * reporting window. Powers the throughput sparkline and KPI tiles.
   */
  getMetricsSummary(): Promise<MetricsSummary>;

  /**
   * Retrieve the current SLA compliance snapshot including availability,
   * error budget, latency percentiles, and incident status.
   */
  getSLAStatus(): Promise<SLAStatus>;

  /**
   * Retrieve recent evaluation sessions for the activity feed.
   * Returns the most recent sessions ordered by evaluation timestamp.
   */
  getRecentEvaluations(): Promise<EvaluationSession[]>;

  /**
   * Retrieve the current Paxos consensus state for the distributed
   * evaluation cluster. Used by the Consensus widget to display
   * leader election status and cluster health.
   */
  getConsensusStatus(): Promise<ConsensusStatus>;

  /**
   * Retrieve FizzBuck expenditure summary for FinOps reporting.
   * Used by the Cost widget to display current-period spend and trend.
   */
  getCostSummary(): Promise<CostSummary>;

  /**
   * Retrieve time series data for a named metric over the specified
   * duration. Used by the Real-Time Metrics Dashboard for detailed
   * metric visualization.
   *
   * @param metricName - Canonical metric name (e.g., "fizzbuzz_evaluations_total")
   * @param duration - Time window in seconds to retrieve data for
   */
  getMetricTimeSeries(metricName: string, duration: number): Promise<TimeSeriesData>;

  /**
   * List all metrics registered with the platform's telemetry subsystem.
   * Returns metric definitions including name, type, description, and unit.
   */
  listMetrics(): Promise<MetricDefinition[]>;

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
}
