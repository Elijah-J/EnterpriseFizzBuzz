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
  HealthCheckPoint,
  SLAHistoryPoint,
  Incident,
  Trace,
  Alert,
  ComplianceFramework,
  ComplianceFinding,
  AuditEntry,
  FindingSeverity,
  ClassificationDistribution,
  HeatmapData,
  EvaluationTrend,
  ConfigCategory,
  ConfigItem,
  ConfigUpdateResult,
  FeatureFlag,
  FeatureFlagToggleResult,
  AuditLogFilter,
  PaginatedAuditLog,
  AuditLogSortField,
  Block,
  BlockchainStats,
  QuantumCircuit,
  QuantumSimulationResult,
  QuantumState,
  ChaosExperiment,
  GameDayScenario,
  ChaosMetrics,
  GAConfig,
  GAEvolutionHistory,
  GAPopulation,
  ClusterTopology,
  LeaderElection,
  PartitionSimulationResult,
  TwinState,
  TwinProjection,
  WhatIfOutcome,
  CostAllocation,
  BudgetStatus,
  FizzBuckExchangeRate,
  Invoice,
  DailyCostPoint,
  CacheLine,
  CacheStats,
  MESITransition,
  CacheEulogy,
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

  /**
   * Retrieve recent distributed traces from the evaluation pipeline.
   * Each trace captures the full span tree of a single FizzBuzz evaluation
   * including middleware, cache, rule engine, and blockchain commit stages.
   *
   * @param limit - Maximum number of traces to return (default: 25)
   */
  getTraces(limit?: number): Promise<Trace[]>;

  /**
   * Retrieve a single trace by its trace identifier. Returns null if the
   * trace has been evicted from the retention window.
   */
  getTrace(traceId: string): Promise<Trace | null>;

  /**
   * Retrieve all active alerts from the platform monitoring subsystem.
   * Alerts are returned in severity-descending, time-descending order.
   */
  getAlerts(): Promise<Alert[]>;

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

  /**
   * Compute the classification distribution for a given integer range.
   * Returns exact counts, proportions, and simplified fractions for each
   * FizzBuzz classification category.
   *
   * @param start - Start of range (inclusive)
   * @param end - End of range (inclusive)
   */
  getClassificationDistribution(start: number, end: number): Promise<ClassificationDistribution[]>;

  /**
   * Generate a divisibility heatmap for a range of numbers against a set
   * of divisors. Used to visualize modular arithmetic patterns that
   * underpin the FizzBuzz classification engine.
   *
   * @param start - Start of range (inclusive)
   * @param end - End of range (inclusive)
   * @param divisors - Divisors to test (default: [2, 3, 4, 5, 6, 7, 8, 9, 10, 15])
   */
  getDivisorHeatmap(start: number, end: number, divisors?: number[]): Promise<HeatmapData>;

  /**
   * Retrieve evaluation volume trend data for the specified period.
   * Returns time-bucketed evaluation counts with per-classification breakdown.
   *
   * @param period - Time period: "1h", "6h", "24h", "7d"
   */
  getEvaluationTrend(period: string): Promise<EvaluationTrend>;

  /**
   * Retrieve all platform configuration items, optionally filtered by category.
   * Returns items sorted by category, then by name.
   */
  getConfiguration(category?: ConfigCategory): Promise<ConfigItem[]>;

  /**
   * Submit a configuration change. The change is validated server-side
   * against type constraints and business rules before acceptance.
   */
  updateConfigItem(itemId: string, newValue: string): Promise<ConfigUpdateResult>;

  /**
   * Retrieve all registered feature flags with current state and rollout
   * configuration. Returns flags sorted by lifecycle stage, then by name.
   */
  getFeatureFlags(): Promise<FeatureFlag[]>;

  /**
   * Toggle a feature flag's enabled state or update its rollout percentage.
   * Returns the updated flag state after server-side validation.
   */
  toggleFeatureFlag(flagId: string, enabled: boolean, rolloutPercentage?: number): Promise<FeatureFlagToggleResult>;

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

  /**
   * Retrieve the most recent blocks from the blockchain ledger.
   * Returns blocks in reverse chronological order (newest first).
   *
   * @param limit - Maximum number of blocks to return (default: 50)
   */
  getBlockchain(limit?: number): Promise<Block[]>;

  /**
   * Retrieve a single block by its SHA-256 hash. Returns null if no block
   * with the given hash exists in the chain.
   */
  getBlock(hash: string): Promise<Block | null>;

  /**
   * Retrieve aggregate blockchain statistics including chain height,
   * transaction volume, mining performance, and integrity status.
   */
  getBlockchainStats(): Promise<BlockchainStats>;

  /**
   * Retrieve all pre-built quantum circuits available for simulation.
   * Returns circuits ordered by qubit count ascending, then alphabetically.
   */
  getQuantumCircuits(): Promise<QuantumCircuit[]>;

  /**
   * Execute a quantum simulation of the specified circuit for the given
   * number of measurement shots. Returns the final state vector,
   * measurement histogram, and Quantum Advantage Ratio.
   *
   * @param circuitId - Identifier of the circuit to simulate
   * @param shots - Number of measurement repetitions (default: 1024)
   */
  runQuantumSimulation(circuitId: string, shots: number): Promise<QuantumSimulationResult>;

  /**
   * Retrieve the current state vector for a circuit without performing
   * measurement. Used for state visualization before collapsing the
   * superposition.
   *
   * @param circuitId - Identifier of the circuit to inspect
   */
  getQuantumState(circuitId: string): Promise<QuantumState>;

  /**
   * Retrieve the catalog of available chaos experiments.
   * Returns all experiments ordered by target subsystem, then by fault type.
   */
  getChaosExperiments(): Promise<ChaosExperiment[]>;

  /**
   * Execute a chaos experiment by its identifier. Returns the updated
   * experiment with status transitioned to "running". Poll via
   * getChaosExperiments() to observe completion.
   */
  runChaosExperiment(experimentId: string): Promise<ChaosExperiment>;

  /**
   * Retrieve all Game Day scenarios with current status and phase progress.
   */
  getGameDayScenarios(): Promise<GameDayScenario[]>;

  /**
   * Retrieve aggregate chaos engineering metrics for the control plane
   * summary bar and MTTR trend chart.
   */
  getChaosMetrics(): Promise<ChaosMetrics>;

  /**
   * Launch a genetic algorithm evolution run with the specified configuration.
   * Returns the complete evolution history once the run completes. The GA
   * explores the FizzBuzz rule space via tournament selection, single-point
   * crossover, and multi-operator mutation to discover optimal divisor/label
   * combinations.
   */
  runEvolution(config: GAConfig): Promise<GAEvolutionHistory>;

  /**
   * Retrieve the most recent evolution run history, or null if no evolution
   * has been executed in the current session.
   */
  getEvolutionHistory(): Promise<GAEvolutionHistory | null>;

  /**
   * Retrieve the current (latest-generation) population from the most
   * recent evolution run. Returns null if no evolution has been executed.
   */
  getCurrentPopulation(): Promise<GAPopulation | null>;

  /**
   * Retrieve the current cluster topology including all nodes, inter-node
   * connections, and leadership state. Used by the Consensus page for
   * topology graph rendering.
   */
  getClusterTopology(): Promise<ClusterTopology>;

  /**
   * Retrieve the history of leader elections in the Paxos cluster.
   * Returns the most recent elections ordered by term (descending).
   *
   * @param limit - Maximum number of elections to return (default: 20)
   */
  getElectionHistory(limit?: number): Promise<LeaderElection[]>;

  /**
   * Simulate a network partition by isolating the specified nodes from
   * the rest of the cluster. Returns the resulting topology state after
   * the cluster responds to the partition (potential re-election).
   *
   * @param nodeIds - Node identifiers to isolate behind the partition
   */
  simulatePartition(nodeIds: string[]): Promise<PartitionSimulationResult>;

  /**
   * Retrieve the current digital twin state including per-subsystem
   * live-vs-twin comparison, sync status, and aggregate drift.
   */
  getTwinState(): Promise<TwinState>;

  /**
   * Run a Monte Carlo projection for a named metric over the specified
   * horizon. Returns a fan chart dataset with confidence intervals.
   *
   * @param metric - Metric identifier (e.g., "latency", "throughput", "cost", "failure_rate")
   * @param horizonSeconds - How far into the future to project
   */
  runProjection(metric: string, horizonSeconds: number): Promise<TwinProjection>;

  /**
   * Execute a what-if scenario by applying parameter overrides to the
   * twin model and returning the projected outcome.
   *
   * @param overrides - Parameter key-value overrides to apply
   */
  runWhatIfScenario(overrides: Record<string, string | number | boolean>): Promise<WhatIfOutcome>;

  /**
   * Retrieve the current FizzBuck cost allocation breakdown across all
   * infrastructure subsystems. Used by the FinOps cost treemap for
   * spend attribution and chargeback analysis.
   */
  getCostBreakdown(): Promise<CostAllocation[]>;

  /**
   * Retrieve budget status for all budget categories in the current
   * reporting period. Powers the budget health progress bars and
   * overrun alerting.
   */
  getBudgetStatus(): Promise<BudgetStatus[]>;

  /**
   * Retrieve the current FizzBuck exchange rate with 24-hour history.
   * Used by the exchange rate ticker widget for real-time rate display
   * and trend visualization.
   */
  getExchangeRateHistory(): Promise<FizzBuckExchangeRate>;

  /**
   * Generate a FizzBuck invoice for the specified billing period.
   * Computes line items from subsystem usage telemetry, applies
   * FBVAT, and returns the complete invoice document.
   *
   * @param period - Billing period in YYYY-MM format (e.g., "2026-03")
   */
  generateInvoice(period: string): Promise<Invoice>;

  /**
   * Retrieve daily cost trend data for the last 30 days. Used by the
   * cost trend line chart for spend pattern analysis and anomaly detection.
   */
  getDailyCostTrend(): Promise<DailyCostPoint[]>;

  /**
   * Retrieve all current cache lines with their MESI coherence state
   * and access metadata. Used by the Cache Coherence Visualizer for
   * the live cache inventory table.
   */
  getCacheState(): Promise<CacheLine[]>;

  /**
   * Retrieve aggregate cache statistics including hit/miss rates,
   * eviction count, MESI state distribution, and capacity utilization.
   */
  getCacheStats(): Promise<CacheStats>;

  /**
   * Retrieve the most recent MESI state transitions from the coherence
   * protocol event log. Used by the state machine diagram to highlight
   * active transitions and by the transition log table.
   *
   * @param limit - Maximum number of transitions to return (default: 50)
   */
  getMESITransitions(limit?: number): Promise<MESITransition[]>;

  /**
   * Retrieve the most recent eviction eulogies. Each eulogy commemorates
   * a cache entry that was evicted from the cache with full ceremony.
   *
   * @param limit - Maximum number of eulogies to return (default: 20)
   */
  getCacheEulogies(limit?: number): Promise<CacheEulogy[]>;
}
