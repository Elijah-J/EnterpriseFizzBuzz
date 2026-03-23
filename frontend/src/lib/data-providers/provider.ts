import type {
  EvaluationRequest,
  EvaluationSession,
  SubsystemHealth,
  MetricsSummary,
  SLAStatus,
  ConsensusStatus,
  CostSummary,
  HealthCheckPoint,
  SLAHistoryPoint,
  Incident,
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
   * Retrieve historical health check data for a specific subsystem.
   * Returns the most recent ~20 data points for sparkline rendering
   * on the Health Check Matrix page.
   */
  getHealthHistory(subsystem: string): Promise<HealthCheckPoint[]>;

  /**
   * Retrieve the SLA error budget burn-down time series.
   * Returns data points showing budget depletion over the current
   * reporting window, used by the SLA Dashboard burn-down chart.
   */
  getSLAHistory(): Promise<SLAHistoryPoint[]>;

  /**
   * Retrieve recent incidents for the SLA incident timeline.
   * Returns incidents ordered by start time (most recent first)
   * with severity classification and resolution status.
   */
  getIncidents(): Promise<Incident[]>;
}
