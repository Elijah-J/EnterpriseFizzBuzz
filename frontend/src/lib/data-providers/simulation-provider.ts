import type { IDataProvider } from "./provider";
import type {
  EvaluationRequest,
  EvaluationSession,
  FizzBuzzResult,
  MatchedRule,
  SubsystemHealth,
  MetricsSummary,
  SLAStatus,
  ConsensusStatus,
  CostSummary,
  TimeSeriesData,
  MetricDefinition,
} from "./types";

/**
 * Generates a pseudo-random value from a Gaussian (normal) distribution
 * using the Box-Muller transform. Used to produce realistic processing
 * time jitter that mirrors production backend variance patterns.
 */
function gaussianRandom(mean: number, stddev: number): number {
  const u1 = Math.random();
  const u2 = Math.random();
  const z0 = Math.sqrt(-2.0 * Math.log(u1)) * Math.cos(2.0 * Math.PI * u2);
  return Math.max(0, mean + z0 * stddev);
}

/**
 * Generates a v4-compliant UUID for session identification.
 * Uses Math.random() — acceptable for simulation; production deployments
 * should use crypto.randomUUID().
 */
function generateSessionId(): string {
  return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, (c) => {
    const r = (Math.random() * 16) | 0;
    const v = c === "x" ? r : (r & 0x3) | 0x8;
    return v.toString(16);
  });
}

/**
 * Base processing time characteristics per strategy, in nanoseconds.
 * These values are calibrated to approximate real-world latency profiles
 * observed in production FizzBuzz evaluation clusters.
 */
const STRATEGY_TIMING: Record<string, { mean: number; stddev: number }> = {
  standard: { mean: 850, stddev: 120 },
  chain_of_responsibility: { mean: 1_400, stddev: 280 },
  machine_learning: { mean: 14_500, stddev: 3_200 },
  quantum: { mean: 42_000, stddev: 8_500 },
};

/**
 * Canonical list of infrastructure subsystems monitored by the platform.
 * Each subsystem maps to a real component in the Enterprise FizzBuzz
 * backend architecture.
 */
const SUBSYSTEM_NAMES = [
  "MESI Cache Coherence",
  "Blockchain Ledger",
  "Neural Network Inference",
  "RBAC Auth Provider",
  "SOX Compliance Engine",
  "GDPR Data Controller",
  "HIPAA Audit Logger",
  "Circuit Breaker Mesh",
  "Event Sourcing Store",
  "SLA Monitor",
  "Rate Limiter",
  "Service Mesh Proxy",
  "Raft Consensus Module",
  "Feature Flag Evaluator",
  "Webhook Dispatcher",
  "i18n Translation Service",
  "DI Container",
  "Chaos Engineering Agent",
  "FinOps Cost Tracker",
  "FizzSQL Query Engine",
  "FizzPM Package Registry",
  "FizzKube Pod Scheduler",
] as const;

/**
 * On-call rotation roster. Names are drawn from the Distinguished
 * Engineers who designed the Enterprise FizzBuzz Platform.
 */
const ON_CALL_ROSTER = [
  "Dr. Elara Modulus",
  "Prof. Byron Divisor",
  "Eng. Cassandra Remainder",
  "Arch. Dmitri Quotient",
  "SRE Jenkins McFizzface",
  "Dir. Priya Evaluator",
] as const;

/**
 * Paxos cluster node identifiers for the distributed evaluation fleet.
 */
const CLUSTER_NODES = [
  "fizz-eval-us-east-1a",
  "fizz-eval-us-west-2b",
  "fizz-eval-eu-west-1c",
  "fizz-eval-ap-south-1a",
  "fizz-eval-eu-central-1b",
] as const;

// ---------------------------------------------------------------------------
// Simulation state — maintained across calls to produce coherent time series
// ---------------------------------------------------------------------------

let throughputHistory: number[] = [];
let totalEvaluations = 847_293;
let uptimeSeconds = 2_592_000; // 30 days
let ballotNumber = 42;

/**
 * Local simulation data provider for the Enterprise FizzBuzz Platform.
 *
 * Computes FizzBuzz evaluations entirely in TypeScript using modular
 * arithmetic. Generates realistic metadata including per-evaluation
 * processing times with Gaussian-distributed jitter, matched rule
 * annotations, and session identifiers suitable for audit correlation.
 *
 * Dashboard telemetry methods produce statistically plausible simulated
 * data with controlled variance to ensure the Operations Center displays
 * realistic behavior without requiring a live backend.
 */
export class SimulationProvider implements IDataProvider {
  readonly name = "Local Simulation Engine";

  async evaluate(request: EvaluationRequest): Promise<EvaluationSession> {
    const { start, end, strategy } = request;
    const timing = STRATEGY_TIMING[strategy] ?? STRATEGY_TIMING.standard;
    const results: FizzBuzzResult[] = [];

    for (let n = start; n <= end; n++) {
      const matchedRules: MatchedRule[] = [];

      if (n % 3 === 0) {
        matchedRules.push({ divisor: 3, label: "Fizz", priority: 1 });
      }
      if (n % 5 === 0) {
        matchedRules.push({ divisor: 5, label: "Buzz", priority: 2 });
      }

      let output: string;
      let classification: FizzBuzzResult["classification"];

      if (matchedRules.length === 2) {
        output = "FizzBuzz";
        classification = "fizzbuzz";
      } else if (matchedRules.length === 1) {
        output = matchedRules[0].label;
        classification =
          matchedRules[0].label.toLowerCase() as FizzBuzzResult["classification"];
      } else {
        output = String(n);
        classification = "number";
      }

      const processingTimeNs = gaussianRandom(timing.mean, timing.stddev);

      results.push({
        number: n,
        output,
        classification,
        matchedRules,
        processingTimeNs,
      });
    }

    const totalProcessingTimeMs =
      results.reduce((sum, r) => sum + r.processingTimeNs, 0) / 1_000_000;

    totalEvaluations += results.length;

    return {
      sessionId: generateSessionId(),
      results,
      totalProcessingTimeMs,
      strategy,
      evaluatedAt: new Date().toISOString(),
    };
  }

  async getSystemHealth(): Promise<SubsystemHealth[]> {
    const now = new Date().toISOString();

    return SUBSYSTEM_NAMES.map((name, index) => {
      // Deterministically make 1-2 subsystems degraded, rarely one down
      const roll = Math.random();
      let status: SubsystemHealth["status"] = "up";
      if (roll > 0.95) {
        status = "down";
      } else if (roll > 0.88 || index === 1) {
        // Blockchain is chronically degraded — mining is expensive
        status = "degraded";
      }

      const baseLatency = 2 + index * 0.7;
      const responseTimeMs =
        status === "down"
          ? 0
          : gaussianRandom(
              baseLatency,
              status === "degraded" ? baseLatency * 0.8 : baseLatency * 0.15,
            );

      return {
        name,
        status,
        lastChecked: now,
        responseTimeMs: Math.round(responseTimeMs * 100) / 100,
      };
    });
  }

  async getMetricsSummary(): Promise<MetricsSummary> {
    // Advance simulated time
    uptimeSeconds += 2;
    totalEvaluations += Math.floor(gaussianRandom(340, 45));

    // Generate new throughput data point
    const newThroughput = gaussianRandom(1_247, 180);
    throughputHistory.push(Math.round(newThroughput));
    if (throughputHistory.length > 60) {
      throughputHistory = throughputHistory.slice(-60);
    }

    return {
      totalEvaluations,
      evaluationsPerSecond: Math.round(newThroughput * 10) / 10,
      cacheHitRate: Math.round(gaussianRandom(0.943, 0.012) * 1000) / 1000,
      averageLatencyMs: Math.round(gaussianRandom(1.2, 0.15) * 100) / 100,
      uptimeSeconds,
      throughputHistory: [...throughputHistory],
    };
  }

  async getSLAStatus(): Promise<SLAStatus> {
    const availability = Math.min(
      100,
      Math.round(gaussianRandom(99.97, 0.008) * 10000) / 10000,
    );

    // Error budget: how much of the allowed downtime remains
    // At 99.95% target, 0.05% is the total budget
    const usedBudget = Math.max(0, 100 - availability) / 0.05;
    const errorBudgetRemaining = Math.max(
      0,
      Math.min(1, 1 - usedBudget + gaussianRandom(0.08, 0.02)),
    );

    return {
      availabilityPercent: availability,
      errorBudgetRemaining: Math.round(errorBudgetRemaining * 10000) / 10000,
      latencyP99Ms: Math.round(gaussianRandom(4.7, 0.6) * 100) / 100,
      correctnessPercent: 100, // FizzBuzz is deterministic — correctness is absolute
      activeIncidents: Math.random() > 0.85 ? 1 : 0,
      onCallEngineer:
        ON_CALL_ROSTER[Math.floor(Date.now() / 86_400_000) % ON_CALL_ROSTER.length],
    };
  }

  async getRecentEvaluations(): Promise<EvaluationSession[]> {
    const sessions: EvaluationSession[] = [];
    const strategies = ["standard", "chain_of_responsibility", "machine_learning", "quantum"];

    for (let i = 0; i < 5; i++) {
      const strategy = strategies[Math.floor(Math.random() * strategies.length)];
      const start = Math.floor(Math.random() * 900) + 1;
      const end = start + Math.floor(Math.random() * 100) + 10;

      sessions.push({
        sessionId: generateSessionId(),
        results: [], // Lightweight — no full results for the feed
        totalProcessingTimeMs: gaussianRandom(0.08, 0.02),
        strategy,
        evaluatedAt: new Date(
          Date.now() - i * Math.floor(gaussianRandom(60_000, 15_000)),
        ).toISOString(),
      });
    }

    return sessions;
  }

  async getConsensusStatus(): Promise<ConsensusStatus> {
    // Leader is stable most of the time, occasionally an election occurs
    const electionInProgress = Math.random() > 0.92;
    ballotNumber += electionInProgress ? 1 : 0;

    const leaderIndex = ballotNumber % CLUSTER_NODES.length;
    const nodesAcknowledged = electionInProgress
      ? Math.floor(Math.random() * 3) + 1
      : CLUSTER_NODES.length;

    return {
      leaderNode: CLUSTER_NODES[leaderIndex],
      ballotNumber,
      consensusAchieved: !electionInProgress,
      clusterSize: CLUSTER_NODES.length,
      nodesAcknowledged,
    };
  }

  async getCostSummary(): Promise<CostSummary> {
    const currentCost = Math.round(gaussianRandom(42.73, 3.5) * 100) / 100;
    const previousCost = Math.round(gaussianRandom(39.21, 3.5) * 100) / 100;

    const diff = currentCost - previousCost;
    let trend: CostSummary["trend"] = "stable";
    if (diff > 1.5) trend = "up";
    else if (diff < -1.5) trend = "down";

    return {
      currentPeriodCost: currentCost,
      previousPeriodCost: previousCost,
      trend,
      costPerEvaluation:
        Math.round(gaussianRandom(0.0000503, 0.000005) * 10_000_000) / 10_000_000,
    };
  }

  async listMetrics(): Promise<MetricDefinition[]> {
    return METRIC_DEFINITIONS;
  }

  async getMetricTimeSeries(
    metricName: string,
    duration: number,
  ): Promise<TimeSeriesData> {
    const definition = METRIC_DEFINITIONS.find((m) => m.name === metricName);
    const unit = definition?.unit ?? "unknown";
    const type = definition?.type ?? "gauge";

    const now = Date.now();
    // Generate one data point per second, capped at 600 for performance
    const pointCount = Math.min(duration, 600);
    const intervalMs = (duration * 1000) / pointCount;

    const config = METRIC_SIMULATION_CONFIG[metricName] ?? {
      baseline: 50,
      noise: 5,
      trend: 0,
      spikeProbability: 0.02,
      spikeMultiplier: 3,
    };

    const dataPoints: { timestamp: number; value: number }[] = [];
    let cumulativeValue = config.baseline;

    for (let i = 0; i < pointCount; i++) {
      const timestamp = now - (pointCount - 1 - i) * intervalMs;
      const progress = i / pointCount;

      // Base value with trend
      let value = config.baseline + config.trend * progress * pointCount;

      // Add Gaussian noise
      value += gaussianRandom(0, config.noise) - config.noise;

      // Occasional spikes — these represent real production anomalies
      if (Math.random() < config.spikeProbability) {
        value *= config.spikeMultiplier;
      }

      // Counters are monotonically increasing
      if (type === "counter") {
        cumulativeValue += Math.abs(value - config.baseline) + config.baseline * 0.01;
        value = Math.round(cumulativeValue);
      } else {
        // Gauges and histograms can fluctuate but should not go negative
        value = Math.max(0, value);
      }

      dataPoints.push({
        timestamp: Math.round(timestamp),
        value: Math.round(value * 1000) / 1000,
      });
    }

    return {
      metricName,
      dataPoints,
      unit,
    };
  }
}

// ---------------------------------------------------------------------------
// Metric registry — canonical list of all platform telemetry signals
// ---------------------------------------------------------------------------

const METRIC_DEFINITIONS: MetricDefinition[] = [
  {
    name: "fizzbuzz_evaluations_total",
    type: "counter",
    description:
      "Total number of FizzBuzz evaluations executed across all strategies since system boot.",
    unit: "count",
  },
  {
    name: "fizzbuzz_evaluation_duration_seconds",
    type: "histogram",
    description:
      "Distribution of end-to-end evaluation latency including rule matching, caching, and serialization overhead.",
    unit: "seconds",
  },
  {
    name: "cache_hit_ratio",
    type: "gauge",
    description:
      "Fraction of evaluation requests served from the MESI-coherent L1/L2 cache hierarchy without backend recomputation.",
    unit: "percent",
  },
  {
    name: "cache_entries_total",
    type: "gauge",
    description:
      "Current number of entries resident in the distributed cache across all coherence domains.",
    unit: "count",
  },
  {
    name: "blockchain_block_height",
    type: "counter",
    description:
      "Current block height of the FizzBuzz immutable evaluation ledger. Monotonically increasing under normal operation.",
    unit: "count",
  },
  {
    name: "blockchain_mining_duration_ms",
    type: "histogram",
    description:
      "Distribution of proof-of-work mining times for new evaluation record blocks.",
    unit: "milliseconds",
  },
  {
    name: "ml_inference_confidence",
    type: "gauge",
    description:
      "Mean softmax confidence score from the neural network FizzBuzz classifier across recent inference batches.",
    unit: "percent",
  },
  {
    name: "circuit_breaker_trips_total",
    type: "counter",
    description:
      "Cumulative count of circuit breaker state transitions to the OPEN state across all service mesh endpoints.",
    unit: "count",
  },
  {
    name: "paxos_leader_elections_total",
    type: "counter",
    description:
      "Total number of Paxos leader elections triggered by the distributed consensus subsystem.",
    unit: "count",
  },
  {
    name: "sla_error_budget_remaining",
    type: "gauge",
    description:
      "Remaining error budget as a percentage of the 30-day rolling window. Burns down as SLA violations occur.",
    unit: "percent",
  },
  {
    name: "http_requests_total",
    type: "counter",
    description:
      "Total HTTP requests received by the FizzBuzz evaluation API across all endpoints and methods.",
    unit: "count",
  },
  {
    name: "memory_usage_bytes",
    type: "gauge",
    description:
      "Current resident set size of the FizzBuzz evaluation process including all subsystem allocations.",
    unit: "bytes",
  },
  {
    name: "quantum_qubit_decoherence_rate",
    type: "gauge",
    description:
      "Rate of quantum decoherence events per second in the simulated qubit register used for quantum strategy evaluations.",
    unit: "events/s",
  },
  {
    name: "compliance_audit_score",
    type: "gauge",
    description:
      "Composite compliance score across SOX, GDPR, and HIPAA audit frameworks. 100 indicates full regulatory compliance.",
    unit: "percent",
  },
  {
    name: "fizzbucks_spent_total",
    type: "counter",
    description:
      "Cumulative FizzBuck expenditure across all cost centers since the beginning of the current fiscal period.",
    unit: "FizzBucks",
  },
];

/**
 * Per-metric simulation parameters. Each metric has a characteristic
 * baseline, noise profile, trend direction, and anomaly probability
 * calibrated to approximate production telemetry patterns.
 */
const METRIC_SIMULATION_CONFIG: Record<
  string,
  {
    baseline: number;
    noise: number;
    trend: number;
    spikeProbability: number;
    spikeMultiplier: number;
  }
> = {
  fizzbuzz_evaluations_total: {
    baseline: 342,
    noise: 28,
    trend: 0.15,
    spikeProbability: 0.01,
    spikeMultiplier: 2.5,
  },
  fizzbuzz_evaluation_duration_seconds: {
    baseline: 0.0012,
    noise: 0.0003,
    trend: 0,
    spikeProbability: 0.03,
    spikeMultiplier: 4,
  },
  cache_hit_ratio: {
    baseline: 94.3,
    noise: 1.2,
    trend: 0.02,
    spikeProbability: 0.02,
    spikeMultiplier: 0.7,
  },
  cache_entries_total: {
    baseline: 48_721,
    noise: 340,
    trend: 0.8,
    spikeProbability: 0.005,
    spikeMultiplier: 1.3,
  },
  blockchain_block_height: {
    baseline: 12,
    noise: 3,
    trend: 0.05,
    spikeProbability: 0.01,
    spikeMultiplier: 2,
  },
  blockchain_mining_duration_ms: {
    baseline: 847,
    noise: 190,
    trend: 0,
    spikeProbability: 0.04,
    spikeMultiplier: 3.5,
  },
  ml_inference_confidence: {
    baseline: 97.2,
    noise: 0.8,
    trend: 0.01,
    spikeProbability: 0.02,
    spikeMultiplier: 0.92,
  },
  circuit_breaker_trips_total: {
    baseline: 3,
    noise: 1.5,
    trend: 0,
    spikeProbability: 0.05,
    spikeMultiplier: 5,
  },
  paxos_leader_elections_total: {
    baseline: 1,
    noise: 0.8,
    trend: 0,
    spikeProbability: 0.08,
    spikeMultiplier: 4,
  },
  sla_error_budget_remaining: {
    baseline: 73.4,
    noise: 0.5,
    trend: -0.03,
    spikeProbability: 0.02,
    spikeMultiplier: 0.85,
  },
  http_requests_total: {
    baseline: 1_247,
    noise: 180,
    trend: 0.2,
    spikeProbability: 0.015,
    spikeMultiplier: 3,
  },
  memory_usage_bytes: {
    baseline: 524_288_000,
    noise: 12_000_000,
    trend: 0.5,
    spikeProbability: 0.01,
    spikeMultiplier: 1.4,
  },
  quantum_qubit_decoherence_rate: {
    baseline: 0.042,
    noise: 0.008,
    trend: 0,
    spikeProbability: 0.06,
    spikeMultiplier: 5,
  },
  compliance_audit_score: {
    baseline: 98.7,
    noise: 0.3,
    trend: 0.005,
    spikeProbability: 0.01,
    spikeMultiplier: 0.95,
  },
  fizzbucks_spent_total: {
    baseline: 42.7,
    noise: 3.5,
    trend: 0.1,
    spikeProbability: 0.02,
    spikeMultiplier: 2.5,
  },
};
