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
}
