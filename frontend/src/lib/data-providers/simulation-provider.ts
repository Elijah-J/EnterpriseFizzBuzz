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
  ComplianceFramework,
  ComplianceFinding,
  FindingSeverity,
  AuditEntry,
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

  async getComplianceFrameworks(): Promise<ComplianceFramework[]> {
    const now = Date.now();

    const frameworkProfiles = [
      { id: "SOX", name: "Sarbanes-Oxley Section 404", totalControls: 47, passRateMean: 0.95, passRateStddev: 0.01 },
      { id: "GDPR", name: "General Data Protection Regulation", totalControls: 38, passRateMean: 0.885, passRateStddev: 0.018 },
      { id: "HIPAA", name: "HIPAA Security Rule", totalControls: 54, passRateMean: 0.93, passRateStddev: 0.015 },
      { id: "FIZZBUZZ-ISO-27001", name: "FizzBuzz Information Security Standard", totalControls: 62, passRateMean: 0.98, passRateStddev: 0.01 },
    ];

    return frameworkProfiles.map((profile) => {
      const passRate = Math.max(0, Math.min(1, gaussianRandom(profile.passRateMean, profile.passRateStddev)));
      const passingControls = Math.round(profile.totalControls * passRate);
      const remainingAfterPass = profile.totalControls - passingControls;
      const pendingControls = Math.min(remainingAfterPass, Math.floor(Math.random() * 3));
      const failingControls = remainingAfterPass - pendingControls;
      const complianceScore = Math.round((passingControls / profile.totalControls) * 1000) / 10;

      let status: ComplianceFramework["status"] = "non-compliant";
      if (complianceScore >= 95) status = "compliant";
      else if (complianceScore >= 80) status = "at-risk";

      const lastAuditDaysAgo = Math.floor(Math.random() * 7);
      const nextAuditDays = 23 + Math.floor(Math.random() * 8);
      const openFindings = failingControls + Math.floor(Math.random() * 3);

      return {
        id: profile.id,
        name: profile.name,
        complianceScore,
        totalControls: profile.totalControls,
        passingControls,
        failingControls,
        pendingControls,
        status,
        lastAuditDate: new Date(now - lastAuditDaysAgo * 86_400_000).toISOString(),
        nextAuditDate: new Date(now + nextAuditDays * 86_400_000).toISOString(),
        openFindings,
      };
    });
  }

  async getComplianceFindings(frameworkId?: string, severity?: FindingSeverity): Promise<ComplianceFinding[]> {
    const findings: ComplianceFinding[] = COMPLIANCE_FINDINGS_SEED.map((seed, index) => {
      const daysAgo = Math.floor(Math.random() * 30) + 1;
      const dueDays = Math.floor(Math.random() * 14) + 7;
      const statuses: ComplianceFinding["status"][] = ["open", "in-progress", "remediated", "accepted-risk"];
      const status = statuses[Math.floor(Math.random() * statuses.length)];

      return {
        id: `CF-2024-${String(847 + index).padStart(4, "0")}`,
        frameworkId: seed.frameworkId,
        controlId: seed.controlId,
        severity: seed.severity,
        title: seed.title,
        description: seed.description,
        status,
        identifiedAt: new Date(Date.now() - daysAgo * 86_400_000).toISOString(),
        dueDate: status === "open" || status === "in-progress"
          ? new Date(Date.now() + dueDays * 86_400_000).toISOString()
          : undefined,
        assignee: ON_CALL_ROSTER[Math.floor(Math.random() * ON_CALL_ROSTER.length)],
      };
    });

    // Sort by severity (critical first), then by identifiedAt (most recent first)
    const severityOrder: Record<FindingSeverity, number> = { critical: 0, high: 1, medium: 2, low: 3 };
    findings.sort((a, b) => {
      const sevDiff = severityOrder[a.severity] - severityOrder[b.severity];
      if (sevDiff !== 0) return sevDiff;
      return new Date(b.identifiedAt).getTime() - new Date(a.identifiedAt).getTime();
    });

    // Apply filters
    let filtered = findings;
    if (frameworkId) {
      filtered = filtered.filter((f) => f.frameworkId === frameworkId);
    }
    if (severity) {
      filtered = filtered.filter((f) => f.severity === severity);
    }

    return filtered;
  }

  async getAuditLog(limit: number = 50): Promise<AuditEntry[]> {
    const entries: AuditEntry[] = [];
    const actions: AuditEntry["action"][] = [
      "audit-run", "finding-created", "finding-updated",
      "control-assessed", "policy-change", "evidence-uploaded",
    ];
    const automatedActors = [
      "Compliance Automation Engine",
      "SOX Continuous Monitor",
      "GDPR Data Controller",
      "HIPAA Audit Subsystem",
      "FizzBuzz-ISO Validator",
    ];
    const frameworkIds = ["SOX", "GDPR", "HIPAA", "FIZZBUZZ-ISO-27001"];

    const auditDescriptions: Record<AuditEntry["action"], string[]> = {
      "audit-run": [
        "Automated SOX Section 404 assessment completed — 45/47 controls passed",
        "Scheduled GDPR Article 32 security assessment completed — 34/38 controls passed",
        "HIPAA Security Rule quarterly assessment completed — 51/54 controls passed",
        "FizzBuzz-ISO-27001 continuous compliance scan completed — 61/62 controls passed",
      ],
      "finding-created": [
        "New critical finding created for HIPAA framework — PHI exposure in debug log",
        "New high finding created for SOX framework — segregation of duties violation",
        "New medium finding created for GDPR framework — consent record retention gap",
        "New low finding created for FIZZBUZZ-ISO-27001 — documentation update pending",
      ],
      "finding-updated": [
        "Finding CF-2024-0847 status changed from open to in-progress",
        "Finding CF-2024-0852 severity downgraded from high to medium after mitigation",
        "Finding CF-2024-0861 status changed to remediated — evidence uploaded",
        "Finding CF-2024-0855 assigned to Dr. Elara Modulus for remediation",
      ],
      "control-assessed": [
        "Control GDPR-Art.32.1 assessed as PASSING — encryption at rest verified",
        "Control SOX-404.3.7 assessed as FAILING — reconciliation gap detected",
        "Control HIPAA-164.312(a)(1) assessed as PASSING — access controls verified",
        "Control FIZZ-A.12.4.1 assessed as PASSING — audit logging operational",
      ],
      "policy-change": [
        "FizzBuzz-ISO-27001 password policy updated: minimum length increased to 128 characters",
        "SOX Section 404 retention policy extended to 10 years for evaluation receipts",
        "GDPR data subject access request SLA reduced from 30 to 15 business days",
        "HIPAA minimum necessary standard policy updated for ML training data access",
      ],
      "evidence-uploaded": [
        "SOX Section 404 evidence artifact uploaded: Q4 evaluation pipeline reconciliation report",
        "GDPR Article 30 processing activities register updated for Q1 reporting period",
        "HIPAA risk assessment evidence uploaded: annual penetration test results",
        "FizzBuzz-ISO-27001 management review minutes uploaded for March review cycle",
      ],
    };

    for (let i = 0; i < limit; i++) {
      const action = actions[Math.floor(Math.random() * actions.length)];
      const hoursAgo = Math.random() * 168; // 7 days in hours
      const isAutomated = Math.random() > 0.35;
      const actor = isAutomated
        ? automatedActors[Math.floor(Math.random() * automatedActors.length)]
        : ON_CALL_ROSTER[Math.floor(Math.random() * ON_CALL_ROSTER.length)];
      const descriptions = auditDescriptions[action];
      const description = descriptions[Math.floor(Math.random() * descriptions.length)];

      entries.push({
        id: `AE-${String(10000 + i).padStart(5, "0")}`,
        timestamp: new Date(Date.now() - hoursAgo * 3_600_000).toISOString(),
        action,
        frameworkId: frameworkIds[Math.floor(Math.random() * frameworkIds.length)],
        actor,
        description,
      });
    }

    // Sort by timestamp, most recent first
    entries.sort((a, b) => new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime());

    return entries;
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

// ---------------------------------------------------------------------------
// Compliance findings seed data — realistic control deficiencies distributed
// across the four regulatory frameworks
// ---------------------------------------------------------------------------

const COMPLIANCE_FINDINGS_SEED: {
  frameworkId: string;
  controlId: string;
  severity: FindingSeverity;
  title: string;
  description: string;
}[] = [
  // Critical findings (2)
  {
    frameworkId: "HIPAA",
    controlId: "HIPAA-164.312(a)(1)",
    severity: "critical",
    title: "HIPAA-protected FizzBuzz results exposed in debug log",
    description:
      "The evaluation pipeline debug logger was found to emit Protected Health Information (PHI) — specifically, FizzBuzz evaluation results classified under the medical-grade tier — to the application's standard output stream without redaction. This constitutes a potential breach under HIPAA Security Rule Section 164.312(a)(1) requiring access controls for electronic PHI. Immediate remediation requires disabling verbose debug output in production and implementing PHI-aware log scrubbing in the middleware pipeline.",
  },
  {
    frameworkId: "SOX",
    controlId: "SOX-404.3.7",
    severity: "critical",
    title: "Blockchain audit receipt chain broken for 3 evaluation batches",
    description:
      "The immutable evaluation ledger shows a gap of three consecutive blocks where audit receipt hashes do not chain correctly due to a race condition in the concurrent mining subsystem. This breaks the Sarbanes-Oxley Section 404 requirement for complete and verifiable financial evaluation records. Root cause analysis indicates the Raft consensus module failed to serialize block commits during a leader election event. Remediation requires replaying the affected evaluation sessions and re-mining the corrected blocks.",
  },
  // High findings (5)
  {
    frameworkId: "GDPR",
    controlId: "GDPR-Art.17.2",
    severity: "high",
    title: "GDPR right-to-erasure SLA exceeded for 12 sessions",
    description:
      "Twelve data subject erasure requests under GDPR Article 17 (Right to Erasure) have exceeded the platform's 72-hour processing SLA. The evaluation session data for these subjects remains in the event sourcing store pending a compaction cycle that was deferred due to high evaluation throughput. The GDPR Data Controller subsystem must prioritize these erasure operations to avoid regulatory exposure.",
  },
  {
    frameworkId: "SOX",
    controlId: "SOX-404.5.2",
    severity: "high",
    title: "SOX segregation of duties violation in rule engine configuration",
    description:
      "A single operator was found to have both configured the FizzBuzz rule engine parameters and approved the resulting evaluation batch without independent review. This violates the Sarbanes-Oxley Section 404 segregation of duties control requiring that rule configuration changes undergo peer review before activation in the production evaluation pipeline.",
  },
  {
    frameworkId: "HIPAA",
    controlId: "HIPAA-164.308(a)(5)",
    severity: "high",
    title: "HIPAA access review for ML training data not completed",
    description:
      "The quarterly access review for personnel with access to the machine learning training dataset — which contains PHI-classified FizzBuzz evaluation results — was not completed within the required review window. HIPAA Section 164.308(a)(5) mandates periodic access reviews to ensure minimum necessary access principles are maintained.",
  },
  {
    frameworkId: "FIZZBUZZ-ISO-27001",
    controlId: "FIZZ-A.9.4.3",
    severity: "high",
    title: "Service account credentials not rotated within policy window",
    description:
      "Three service accounts used by the evaluation pipeline have credentials that exceed the FizzBuzz-ISO-27001 maximum credential age policy of 90 days. Control A.9.4.3 requires automated credential rotation for all non-human identities accessing the evaluation infrastructure.",
  },
  {
    frameworkId: "GDPR",
    controlId: "GDPR-Art.35.1",
    severity: "high",
    title: "Data Protection Impact Assessment pending for quantum strategy",
    description:
      "The quantum evaluation strategy was deployed to production without a completed Data Protection Impact Assessment (DPIA) as required by GDPR Article 35. The quantum strategy processes evaluation requests using a fundamentally different computational model which may alter the risk profile for data subjects whose evaluation sessions are processed through this path.",
  },
  // Medium findings (7)
  {
    frameworkId: "FIZZBUZZ-ISO-27001",
    controlId: "FIZZ-A.12.4.1",
    severity: "medium",
    title: "FizzBuzz-ISO-27001 key rotation overdue by 48 hours",
    description:
      "The platform's TLS certificate rotation for inter-service communication exceeded the FizzBuzz-ISO-27001 control A.12.4.1 rotation schedule by 48 hours. The delay was caused by a backlog in the secrets vault key derivation pipeline. No security incident resulted, but the policy deviation has been logged for the next audit cycle.",
  },
  {
    frameworkId: "HIPAA",
    controlId: "HIPAA-164.312(e)(1)",
    severity: "medium",
    title: "Transmission security gap in cache replication channel",
    description:
      "The MESI cache coherence replication channel between evaluation nodes was found to use TLS 1.2 rather than the required TLS 1.3 for transmission of PHI-classified cache entries. While TLS 1.2 remains cryptographically secure, HIPAA Section 164.312(e)(1) and the platform's transmission security policy mandate TLS 1.3 for all PHI data in transit.",
  },
  {
    frameworkId: "SOX",
    controlId: "SOX-404.2.4",
    severity: "medium",
    title: "Evaluation receipt reconciliation delayed by 6 hours",
    description:
      "The automated reconciliation process that verifies evaluation receipts against the blockchain ledger experienced a 6-hour delay due to elevated block mining times during a proof-of-work difficulty adjustment. SOX control 404.2.4 requires reconciliation within 4 hours of batch completion.",
  },
  {
    frameworkId: "GDPR",
    controlId: "GDPR-Art.30.1",
    severity: "medium",
    title: "Processing activities register incomplete for federated learning",
    description:
      "The GDPR Article 30 record of processing activities does not include the federated learning subsystem's data processing operations. All processing activities involving personal data must be documented in the register to maintain compliance with the accountability principle.",
  },
  {
    frameworkId: "FIZZBUZZ-ISO-27001",
    controlId: "FIZZ-A.14.2.8",
    severity: "medium",
    title: "System testing evidence gap for chaos engineering module",
    description:
      "The chaos engineering agent's latest deployment did not include system testing evidence artifacts as required by FizzBuzz-ISO-27001 control A.14.2.8. Testing was performed but the results were not captured in the compliance evidence repository.",
  },
  {
    frameworkId: "HIPAA",
    controlId: "HIPAA-164.308(a)(1)",
    severity: "medium",
    title: "Risk analysis not updated after infrastructure topology change",
    description:
      "The platform's HIPAA risk analysis document was not updated following the addition of two new evaluation cluster nodes in the ap-south-1 region. Section 164.308(a)(1) requires the risk analysis to reflect the current infrastructure topology.",
  },
  {
    frameworkId: "SOX",
    controlId: "SOX-404.6.1",
    severity: "medium",
    title: "Change management approval retroactively applied",
    description:
      "A configuration change to the rate limiter thresholds was applied to the production environment 2 hours before the change advisory board approval was recorded. While the change was ultimately approved, the retroactive approval violates SOX control 404.6.1 requiring pre-implementation authorization.",
  },
  // Low findings (6)
  {
    frameworkId: "SOX",
    controlId: "SOX-404.1.2",
    severity: "low",
    title: "SOX audit trail timestamp precision reduced to seconds",
    description:
      "The audit trail for SOX-governed evaluation receipt operations is recording timestamps with second-level precision instead of the nanosecond precision specified in the audit trail format standard. While second-level precision is sufficient for regulatory purposes, the deviation from the platform's internal specification has been flagged for correction.",
  },
  {
    frameworkId: "GDPR",
    controlId: "GDPR-Art.25.1",
    severity: "low",
    title: "GDPR privacy impact assessment pending for quantum strategy",
    description:
      "A supplementary privacy impact assessment for the quantum evaluation strategy's handling of evaluation session metadata has not been completed. The primary DPIA covers the core evaluation path but the quantum-specific metadata enrichment requires separate analysis under GDPR Article 25 (Data Protection by Design).",
  },
  {
    frameworkId: "FIZZBUZZ-ISO-27001",
    controlId: "FIZZ-A.7.2.2",
    severity: "low",
    title: "Security awareness training completion rate at 94%",
    description:
      "The quarterly FizzBuzz-ISO-27001 security awareness training completion rate is 94%, below the 100% target set by control A.7.2.2. Three engineers have pending completions with extensions granted due to on-call rotation conflicts.",
  },
  {
    frameworkId: "HIPAA",
    controlId: "HIPAA-164.310(d)(1)",
    severity: "low",
    title: "Device inventory reconciliation pending for evaluation nodes",
    description:
      "The HIPAA device and media controls inventory has not been reconciled following the latest evaluation cluster scaling event. Two new nodes were provisioned but their hardware asset tags have not been recorded in the device inventory system.",
  },
  {
    frameworkId: "SOX",
    controlId: "SOX-404.7.3",
    severity: "low",
    title: "Monitoring alert threshold documentation not updated",
    description:
      "The SOX monitoring controls documentation does not reflect the updated alert thresholds deployed in the most recent SLA monitor configuration change. The operational thresholds are correctly configured but the compliance documentation is out of sync.",
  },
  {
    frameworkId: "GDPR",
    controlId: "GDPR-Art.12.3",
    severity: "low",
    title: "Data subject notification template uses outdated branding",
    description:
      "The automated data subject notification templates used for GDPR Article 12 transparency communications reference the previous platform version identifier. The templates are functionally correct and contain all required information but should be updated to reflect the current platform version for consistency.",
  },
];
