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
  HealthCheckPoint,
  SLAHistoryPoint,
  Incident,
  Trace,
  TraceSpan,
  Alert,
  ComplianceFramework,
  ComplianceFinding,
  FindingSeverity,
  AuditEntry,
  ClassificationDistribution,
  HeatmapData,
  HeatmapCell,
  EvaluationTrend,
  EvaluationTrendPoint,
  ConfigCategory,
  ConfigItem,
  ConfigUpdateResult,
  FeatureFlag,
  FeatureFlagToggleResult,
  AuditLogFilter,
  PaginatedAuditLog,
  AuditLogSortField,
  QuantumCircuit,
  QuantumGate,
  QuantumState,
  QuantumSimulationResult,
  ComplexAmplitude,
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
 * Computes the greatest common divisor of two non-negative integers
 * using the Euclidean algorithm. Used by the analytics subsystem for
 * exact fraction simplification in classification distribution reports.
 */
function gcd(a: number, b: number): number {
  a = Math.abs(a);
  b = Math.abs(b);
  while (b !== 0) {
    const t = b;
    b = a % b;
    a = t;
  }
  return a;
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

/**
 * Catalog of realistic incident titles drawn from actual subsystem
 * failure modes observed in the Enterprise FizzBuzz production fleet.
 */
const INCIDENT_CATALOG: { title: string; description: string; severity: Incident["severity"] }[] = [
  {
    title: "Cache coherence protocol entered INVALID state on 3 entries",
    description: "MESI protocol violation detected during concurrent Fizz evaluation. Three cache lines transitioned to INVALID without corresponding bus invalidation signals. Forced full cache flush on affected nodes.",
    severity: "P2",
  },
  {
    title: "ML engine confidence dropped below threshold for numbers >50",
    description: "Neural network inference confidence fell to 0.34 for inputs exceeding 50. Root cause traced to weight decay in the modulo-3 detection layer. Emergency retraining initiated with augmented training corpus.",
    severity: "P3",
  },
  {
    title: "Blockchain fork detected: 2 competing chains at block height 847",
    description: "Network partition caused by aggressive mining difficulty adjustment. Two nodes produced valid blocks within the same epoch. Longest-chain resolution protocol activated; losing fork contained 3 FizzBuzz evaluation records requiring replay.",
    severity: "P1",
  },
  {
    title: "SOX compliance audit flagged missing FizzBuzz evaluation receipt",
    description: "Automated SOX Section 404 scan identified evaluation session fb-9e2a1d that completed without generating a signed audit receipt. Manual review confirmed the evaluation produced correct results; receipt generation was blocked by a full audit queue.",
    severity: "P3",
  },
  {
    title: "Rate limiter rejected legitimate evaluation batch from staging",
    description: "Token bucket rate limiter on the staging endpoint rejected a batch of 500 evaluations due to burst capacity misconfiguration. Rate limit was set to 100 req/s; staging harness sends at 250 req/s during smoke tests.",
    severity: "P4",
  },
  {
    title: "Raft consensus leader election timeout exceeded 5s threshold",
    description: "Leader node fizz-eval-us-east-1a became unresponsive during garbage collection pause. Follower nodes initiated election but quorum was not achieved within the 5-second timeout due to cross-region latency. Manual leader assignment required.",
    severity: "P2",
  },
  {
    title: "GDPR data deletion request timed out for evaluation session batch",
    description: "Right-to-erasure request for 47 evaluation sessions exceeded the 72-hour SLA. Root cause: blockchain immutability layer blocked deletion of on-chain evaluation hashes. Legal team consulted; redaction markers applied as compensating control.",
    severity: "P3",
  },
  {
    title: "Webhook dispatcher queue depth exceeded 10,000 pending events",
    description: "Downstream webhook consumer experienced a 12-minute outage, causing event queue backpressure. Circuit breaker tripped at 10,000 queued events, dropping subsequent webhook deliveries. 342 evaluation notifications lost.",
    severity: "P2",
  },
  {
    title: "FizzKube pod scheduler assigned Buzz workload to Fizz-only node",
    description: "Affinity rule misconfiguration in the pod scheduler allowed a Buzz-class evaluation to be scheduled on a node reserved for Fizz-only workloads. Resource contention caused 23ms latency spike on co-located Fizz evaluations.",
    severity: "P4",
  },
  {
    title: "i18n translation service returned Klingon for English locale request",
    description: "Translation cache corruption caused locale fallback chain to resolve en-US to tlh (Klingon). 147 evaluation results displayed as 'vIH' instead of 'Fizz' for approximately 90 seconds before cache invalidation.",
    severity: "P3",
  },
];

// ---------------------------------------------------------------------------
// Audit log dataset generation constants
// ---------------------------------------------------------------------------

/**
 * Source IP pool for audit event attribution. Comprises RFC 1918 internal
 * addresses from platform infrastructure subnets and service mesh identifiers
 * for automated subsystem-to-subsystem communication.
 */
const AUDIT_SOURCE_IPS = [
  "10.0.1.12", "10.0.1.34", "10.0.1.56", "10.0.2.10", "10.0.2.78",
  "10.0.3.15", "10.0.3.42", "172.16.0.5", "172.16.0.18", "172.16.1.3",
  "172.16.1.22", "172.16.2.8", "172.16.2.41",
  "svc://compliance-engine", "svc://cache-coherence", "svc://rule-engine",
  "svc://blockchain-ledger", "svc://ml-pipeline", "svc://consensus-cluster",
] as const;

/**
 * Subsystem identifiers that generate audit events. Each maps to a
 * real infrastructure component in the Enterprise FizzBuzz backend.
 */
const AUDIT_SUBSYSTEMS = [
  "compliance-engine", "cache-subsystem", "rule-engine", "blockchain-ledger",
  "auth-service", "ml-pipeline", "consensus-cluster", "chaos-controller",
  "rate-limiter", "service-mesh",
] as const;

/**
 * Automated service principals that generate the majority of audit events.
 * These represent the platform's continuous compliance monitoring and
 * automated assessment pipelines.
 */
const AUTOMATED_AUDIT_ACTORS = [
  "Compliance Automation Engine",
  "SOX Continuous Monitor",
  "GDPR Data Controller",
  "HIPAA Audit Subsystem",
  "FizzBuzz-ISO Validator",
  "Cache Coherence Watchdog",
  "Blockchain Integrity Verifier",
  "ML Model Governance Agent",
  "Chaos Engineering Orchestrator",
  "Rate Limit Policy Enforcer",
] as const;

/**
 * Descriptive templates for each audit action type. Metadata key-value
 * pairs are generated alongside each description to provide drill-down
 * context for forensic investigation.
 */
const AUDIT_DESCRIPTIONS: Record<AuditEntry["action"], { text: string; metadata: Record<string, string> }[]> = {
  "control-assessed": [
    { text: "Control GDPR-Art.32.1 assessed as PASSING — encryption at rest verified", metadata: { controlId: "GDPR-Art.32.1", result: "pass", duration: "1.24s" } },
    { text: "Control SOX-404.3.7 assessed as FAILING — reconciliation gap detected", metadata: { controlId: "SOX-404.3.7", result: "fail", gapDays: "3" } },
    { text: "Control HIPAA-164.312(a)(1) assessed as PASSING — access controls verified", metadata: { controlId: "HIPAA-164.312(a)(1)", result: "pass" } },
    { text: "Control FIZZ-A.12.4.1 assessed as PASSING — audit logging operational", metadata: { controlId: "FIZZ-A.12.4.1", result: "pass", logRetentionDays: "365" } },
    { text: "Control SOX-302.1.2 assessed as PASSING — CEO certification current", metadata: { controlId: "SOX-302.1.2", result: "pass" } },
    { text: "Control GDPR-Art.17.3 assessed as FAILING — erasure backlog exceeds SLA", metadata: { controlId: "GDPR-Art.17.3", result: "fail", backlogCount: "47" } },
    { text: "Control HIPAA-164.308(a)(5) assessed as PASSING — security awareness training current", metadata: { controlId: "HIPAA-164.308(a)(5)", result: "pass", completionRate: "98.7%" } },
    { text: "Control FIZZ-A.9.2.3 assessed as PASSING — privilege escalation review completed", metadata: { controlId: "FIZZ-A.9.2.3", result: "pass" } },
  ],
  "audit-run": [
    { text: "Automated SOX Section 404 assessment completed — 45/47 controls passed", metadata: { framework: "SOX", passed: "45", total: "47" } },
    { text: "Scheduled GDPR Article 32 security assessment completed — 34/38 controls passed", metadata: { framework: "GDPR", passed: "34", total: "38" } },
    { text: "HIPAA Security Rule quarterly assessment completed — 51/54 controls passed", metadata: { framework: "HIPAA", passed: "51", total: "54" } },
    { text: "FizzBuzz-ISO-27001 continuous compliance scan completed — 61/62 controls passed", metadata: { framework: "FIZZBUZZ-ISO-27001", passed: "61", total: "62" } },
  ],
  "finding-created": [
    { text: "New critical finding created for HIPAA framework — PHI exposure in debug log", metadata: { findingId: "CF-2024-0912", severity: "critical" } },
    { text: "New high finding created for SOX framework — segregation of duties violation", metadata: { findingId: "CF-2024-0913", severity: "high" } },
    { text: "New medium finding created for GDPR framework — consent record retention gap", metadata: { findingId: "CF-2024-0914", severity: "medium" } },
    { text: "New low finding created for FIZZBUZZ-ISO-27001 — documentation update pending", metadata: { findingId: "CF-2024-0915", severity: "low" } },
  ],
  "finding-updated": [
    { text: "Finding CF-2024-0847 status changed from open to in-progress", metadata: { findingId: "CF-2024-0847", oldStatus: "open", newStatus: "in-progress" } },
    { text: "Finding CF-2024-0852 severity downgraded from high to medium after mitigation", metadata: { findingId: "CF-2024-0852", oldSeverity: "high", newSeverity: "medium" } },
    { text: "Finding CF-2024-0861 status changed to remediated — evidence uploaded", metadata: { findingId: "CF-2024-0861", newStatus: "remediated" } },
    { text: "Finding CF-2024-0855 assigned to Dr. Elara Modulus for remediation", metadata: { findingId: "CF-2024-0855", assignee: "Dr. Elara Modulus" } },
  ],
  "evidence-uploaded": [
    { text: "SOX Section 404 evidence artifact uploaded: Q4 evaluation pipeline reconciliation report", metadata: { artifactType: "reconciliation-report", quarter: "Q4" } },
    { text: "GDPR Article 30 processing activities register updated for Q1 reporting period", metadata: { artifactType: "processing-register", period: "Q1" } },
    { text: "HIPAA risk assessment evidence uploaded: annual penetration test results", metadata: { artifactType: "pentest-results", scope: "full-platform" } },
    { text: "FizzBuzz-ISO-27001 management review minutes uploaded for March review cycle", metadata: { artifactType: "review-minutes", month: "March" } },
  ],
  "policy-change": [
    { text: "FizzBuzz-ISO-27001 password policy updated: minimum length increased to 128 characters", metadata: { policy: "password-complexity", field: "minLength", oldValue: "64", newValue: "128" } },
    { text: "SOX Section 404 retention policy extended to 10 years for evaluation receipts", metadata: { policy: "data-retention", oldYears: "7", newYears: "10" } },
    { text: "GDPR data subject access request SLA reduced from 30 to 15 business days", metadata: { policy: "dsar-sla", oldDays: "30", newDays: "15" } },
    { text: "HIPAA minimum necessary standard policy updated for ML training data access", metadata: { policy: "minimum-necessary", scope: "ml-training" } },
  ],
};

/**
 * Weighted random selection utility. Picks an index from a weight array
 * using cumulative distribution sampling.
 */
function weightedRandomIndex(weights: number[]): number {
  const total = weights.reduce((s, w) => s + w, 0);
  let r = Math.random() * total;
  for (let i = 0; i < weights.length; i++) {
    r -= weights[i];
    if (r <= 0) return i;
  }
  return weights.length - 1;
}

/**
 * Generates the canonical 250-entry audit dataset. The dataset is generated
 * deterministically on first invocation and cached for the provider instance
 * lifetime. Entries span a 7-day window with realistic temporal clustering.
 */
function generateAuditDataset(): AuditEntry[] {
  const entries: AuditEntry[] = [];
  const now = Date.now();
  const sevenDaysMs = 7 * 24 * 3_600_000;

  const actions: AuditEntry["action"][] = [
    "control-assessed", "audit-run", "finding-created",
    "finding-updated", "evidence-uploaded", "policy-change",
  ];
  const actionWeights = [30, 15, 15, 15, 15, 10];

  const severities: AuditEntry["severity"][] = ["info", "low", "medium", "high", "critical"];
  const severityWeights = [40, 25, 20, 10, 5];

  const outcomes: AuditEntry["outcome"][] = ["success", "failure", "denied", "error"];
  const outcomeWeights = [75, 10, 10, 5];

  const frameworkIds = ["SOX", "GDPR", "HIPAA", "FIZZBUZZ-ISO-27001"];

  // Generate session correlation groups: 50-125 groups of 2-5 entries each
  const sessionGroups: { id: string; indices: number[] }[] = [];
  let idx = 0;
  while (idx < 250) {
    const groupSize = 2 + Math.floor(Math.random() * 4); // 2-5
    const sessionId = generateSessionId();
    const indices: number[] = [];
    for (let j = 0; j < groupSize && idx < 250; j++, idx++) {
      indices.push(idx);
    }
    sessionGroups.push({ id: sessionId, indices });
  }

  // Build a lookup from entry index to session ID
  const sessionMap = new Map<number, string>();
  for (const group of sessionGroups) {
    for (const i of group.indices) {
      sessionMap.set(i, group.id);
    }
  }

  for (let i = 0; i < 250; i++) {
    const action = actions[weightedRandomIndex(actionWeights)];
    const severity = severities[weightedRandomIndex(severityWeights)];
    const outcome = outcomes[weightedRandomIndex(outcomeWeights)];

    // Timestamp distribution: business hours clustering with periodic spikes
    // Generate hour-of-day with business-hour bias
    const dayOffset = Math.floor(Math.random() * 7);
    const hourRoll = Math.random();
    let hour: number;
    if (hourRoll < 0.7) {
      // 70% during business hours (8-18)
      hour = 8 + Math.floor(Math.random() * 10);
    } else if (hourRoll < 0.85) {
      // 15% during automated scan windows (2-4 AM)
      hour = 2 + Math.floor(Math.random() * 2);
    } else {
      // 15% other hours
      hour = Math.floor(Math.random() * 24);
    }
    const minute = Math.floor(Math.random() * 60);
    const second = Math.floor(Math.random() * 60);
    const timestampMs = now - dayOffset * 86_400_000 - (24 - hour) * 3_600_000 - (60 - minute) * 60_000 - second * 1_000;

    const isAutomated = Math.random() < 0.65;
    const actor = isAutomated
      ? AUTOMATED_AUDIT_ACTORS[Math.floor(Math.random() * AUTOMATED_AUDIT_ACTORS.length)]
      : ON_CALL_ROSTER[Math.floor(Math.random() * ON_CALL_ROSTER.length)];

    const descEntry = AUDIT_DESCRIPTIONS[action][Math.floor(Math.random() * AUDIT_DESCRIPTIONS[action].length)];
    const sourceIp = AUDIT_SOURCE_IPS[Math.floor(Math.random() * AUDIT_SOURCE_IPS.length)];
    const subsystem = AUDIT_SUBSYSTEMS[Math.floor(Math.random() * AUDIT_SUBSYSTEMS.length)];
    const frameworkId = frameworkIds[Math.floor(Math.random() * frameworkIds.length)];

    const hasEvalSession = Math.random() < 0.3;

    entries.push({
      id: `AE-${String(10000 + i).padStart(5, "0")}`,
      timestamp: new Date(timestampMs).toISOString(),
      action,
      frameworkId,
      actor,
      description: descEntry.text,
      metadata: { ...descEntry.metadata },
      severity,
      outcome,
      sessionCorrelationId: sessionMap.get(i)!,
      sourceIp,
      subsystem,
      evaluationSessionId: hasEvalSession ? `eval-${generateSessionId().slice(0, 8)}` : undefined,
    });
  }

  // Sort by timestamp descending (most recent first)
  entries.sort((a, b) => new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime());

  return entries;
}

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
// ---------------------------------------------------------------------------
// Quantum circuit definitions — pre-built circuits for FizzBuzz evaluation
// ---------------------------------------------------------------------------

const QUANTUM_CIRCUITS: QuantumCircuit[] = [
  {
    id: "bell-fizzbuzz",
    name: "Bell State Entanglement Probe",
    description:
      "Prepares a Bell state |00> + |11> to test qubit entanglement fidelity. Serves as a calibration circuit for the quantum evaluation pipeline — if the Bell state is impure, all subsequent FizzBuzz evaluations are suspect.",
    numQubits: 2,
    gates: [
      { type: "H", qubit: 0, step: 0 },
      { type: "CNOT", qubit: 1, controlQubit: 0, step: 1 },
      { type: "M", qubit: 0, step: 2 },
      { type: "M", qubit: 1, step: 2 },
    ],
    numClassicalBits: 2,
    depth: 3,
  },
  {
    id: "shor-3",
    name: "Shor-3 Divisibility Oracle",
    description:
      "Simplified Shor's period-finding circuit for modular exponentiation base-a mod 3. Applies Hadamard superposition on counting register, controlled modular multiplication, and inverse QFT to extract the period r=2, confirming divisibility by 3.",
    numQubits: 4,
    gates: [
      { type: "H", qubit: 0, step: 0 },
      { type: "H", qubit: 1, step: 0 },
      { type: "CNOT", qubit: 2, controlQubit: 1, step: 1 },
      { type: "CNOT", qubit: 3, controlQubit: 0, step: 2 },
      { type: "H", qubit: 0, step: 3 },
      { type: "CNOT", qubit: 1, controlQubit: 0, step: 4 },
      { type: "H", qubit: 1, step: 5 },
      { type: "M", qubit: 0, step: 6 },
      { type: "M", qubit: 1, step: 6 },
      { type: "M", qubit: 2, step: 6 },
      { type: "M", qubit: 3, step: 6 },
    ],
    numClassicalBits: 4,
    depth: 7,
  },
  {
    id: "shor-5",
    name: "Shor-5 Divisibility Oracle",
    description:
      "Period-finding circuit targeting divisor 5. Uses a 4-qubit register to find the period of a^x mod 5. The QFT resolves the period r=4, enabling factorization of the Buzz divisor.",
    numQubits: 4,
    gates: [
      { type: "H", qubit: 0, step: 0 },
      { type: "H", qubit: 1, step: 0 },
      { type: "CNOT", qubit: 2, controlQubit: 0, step: 1 },
      { type: "CNOT", qubit: 3, controlQubit: 1, step: 2 },
      { type: "S", qubit: 2, step: 3 },
      { type: "T", qubit: 3, step: 3 },
      { type: "H", qubit: 0, step: 4 },
      { type: "CNOT", qubit: 1, controlQubit: 0, step: 5 },
      { type: "H", qubit: 1, step: 6 },
      { type: "M", qubit: 0, step: 7 },
      { type: "M", qubit: 1, step: 7 },
      { type: "M", qubit: 2, step: 7 },
      { type: "M", qubit: 3, step: 7 },
    ],
    numClassicalBits: 4,
    depth: 8,
  },
  {
    id: "grover-fizzbuzz",
    name: "Grover FizzBuzz Search",
    description:
      "Grover's search algorithm with an oracle marking states divisible by 15 (FizzBuzz). Applies sqrt(N) Grover iterations to amplify the probability of measuring a FizzBuzz-classified integer.",
    numQubits: 5,
    gates: [
      // Initial superposition
      { type: "H", qubit: 0, step: 0 },
      { type: "H", qubit: 1, step: 0 },
      { type: "H", qubit: 2, step: 0 },
      { type: "H", qubit: 3, step: 0 },
      { type: "X", qubit: 4, step: 1 },
      { type: "H", qubit: 4, step: 2 },
      // Oracle
      { type: "CNOT", qubit: 4, controlQubit: 0, step: 3 },
      { type: "CNOT", qubit: 4, controlQubit: 1, step: 4 },
      { type: "CNOT", qubit: 4, controlQubit: 2, step: 5 },
      { type: "CNOT", qubit: 4, controlQubit: 3, step: 6 },
      // Diffusion operator
      { type: "H", qubit: 0, step: 7 },
      { type: "H", qubit: 1, step: 7 },
      { type: "H", qubit: 2, step: 7 },
      { type: "H", qubit: 3, step: 7 },
      { type: "X", qubit: 0, step: 8 },
      { type: "X", qubit: 1, step: 8 },
      { type: "X", qubit: 2, step: 8 },
      { type: "X", qubit: 3, step: 8 },
      { type: "H", qubit: 3, step: 9 },
      { type: "CNOT", qubit: 3, controlQubit: 0, step: 10 },
      { type: "CNOT", qubit: 3, controlQubit: 1, step: 11 },
      { type: "CNOT", qubit: 3, controlQubit: 2, step: 12 },
      { type: "H", qubit: 3, step: 13 },
      { type: "X", qubit: 0, step: 14 },
      { type: "X", qubit: 1, step: 14 },
      { type: "X", qubit: 2, step: 14 },
      { type: "X", qubit: 3, step: 14 },
      { type: "H", qubit: 0, step: 15 },
      { type: "H", qubit: 1, step: 15 },
      { type: "H", qubit: 2, step: 15 },
      { type: "H", qubit: 3, step: 15 },
      // Measurement
      { type: "M", qubit: 0, step: 16 },
      { type: "M", qubit: 1, step: 16 },
      { type: "M", qubit: 2, step: 16 },
      { type: "M", qubit: 3, step: 16 },
      { type: "M", qubit: 4, step: 16 },
    ],
    numClassicalBits: 5,
    depth: 17,
  },
];

/**
 * Pre-computed quantum state vectors for each circuit. These represent
 * the ideal state-vector output of the circuit simulation prior to
 * measurement collapse.
 */
function buildQuantumState(circuitId: string): QuantumState {
  switch (circuitId) {
    case "bell-fizzbuzz": {
      // Bell state: |00> + |11> with equal superposition
      const amplitudes: ComplexAmplitude[] = [
        { real: Math.SQRT1_2, imag: 0 },
        { real: 0, imag: 0 },
        { real: 0, imag: 0 },
        { real: Math.SQRT1_2, imag: 0 },
      ];
      return {
        amplitudes,
        probabilities: [0.5, 0, 0, 0.5],
        numQubits: 2,
        basisLabels: ["|00>", "|01>", "|10>", "|11>"],
      };
    }
    case "shor-3": {
      // Period r=2 encoded: peaked at |00> and |10> in counting register
      const amp = Math.SQRT1_2;
      const amplitudes: ComplexAmplitude[] = Array.from({ length: 16 }, (_, i) => {
        // States |0000> (0) and |1000> (8) are peaked
        if (i === 0) return { real: amp * 0.9, imag: amp * 0.1 };
        if (i === 8) return { real: amp * 0.85, imag: -amp * 0.15 };
        return { real: 0.02, imag: 0.01 };
      });
      const probabilities = amplitudes.map((a) => a.real * a.real + a.imag * a.imag);
      // Normalize
      const total = probabilities.reduce((s, p) => s + p, 0);
      const normalizedProbs = probabilities.map((p) => p / total);
      return {
        amplitudes,
        probabilities: normalizedProbs,
        numQubits: 4,
        basisLabels: Array.from({ length: 16 }, (_, i) =>
          "|" + i.toString(2).padStart(4, "0") + ">",
        ),
      };
    }
    case "shor-5": {
      // Period r=4: peaked at |0000> (0) and |0100> (4) representing 1/4 fractions
      const amp = Math.SQRT1_2;
      const amplitudes: ComplexAmplitude[] = Array.from({ length: 16 }, (_, i) => {
        if (i === 0) return { real: amp * 0.88, imag: amp * 0.12 };
        if (i === 4) return { real: amp * 0.82, imag: -amp * 0.18 };
        return { real: 0.025, imag: 0.015 };
      });
      const probabilities = amplitudes.map((a) => a.real * a.real + a.imag * a.imag);
      const total = probabilities.reduce((s, p) => s + p, 0);
      const normalizedProbs = probabilities.map((p) => p / total);
      return {
        amplitudes,
        probabilities: normalizedProbs,
        numQubits: 4,
        basisLabels: Array.from({ length: 16 }, (_, i) =>
          "|" + i.toString(2).padStart(4, "0") + ">",
        ),
      };
    }
    case "grover-fizzbuzz": {
      // Grover amplification: multiples of 15 within 5-qubit range (0-31)
      // States 0 and 15 (|01111>) are amplified
      const N = 32;
      const amplitudes: ComplexAmplitude[] = Array.from({ length: N }, (_, i) => {
        const isMultOf15 = i > 0 && i % 15 === 0; // state 15 and 30
        if (i === 0) return { real: 0.08, imag: 0.01 }; // |00000> — not a FizzBuzz
        if (isMultOf15) return { real: 0.55, imag: 0.12 }; // Amplified by Grover
        return { real: 0.12, imag: -0.03 }; // Background uniform amplitude
      });
      const probabilities = amplitudes.map((a) => a.real * a.real + a.imag * a.imag);
      const total = probabilities.reduce((s, p) => s + p, 0);
      const normalizedProbs = probabilities.map((p) => p / total);
      return {
        amplitudes,
        probabilities: normalizedProbs,
        numQubits: 5,
        basisLabels: Array.from({ length: N }, (_, i) =>
          "|" + i.toString(2).padStart(5, "0") + ">",
        ),
      };
    }
    default:
      throw new Error(`Unknown circuit: ${circuitId}`);
  }
}

/**
 * Samples measurement outcomes from a probability distribution using
 * weighted random selection with quantum shot noise simulation.
 */
function sampleMeasurements(
  probabilities: number[],
  basisLabels: string[],
  shots: number,
): Record<string, number> {
  // Build cumulative distribution
  const cdf: number[] = [];
  let cumulative = 0;
  for (const p of probabilities) {
    cumulative += p;
    cdf.push(cumulative);
  }

  // Sample from the distribution
  const counts: Record<string, number> = {};
  for (let i = 0; i < shots; i++) {
    const r = Math.random();
    let idx = 0;
    while (idx < cdf.length - 1 && r > cdf[idx]) {
      idx++;
    }
    const label = basisLabels[idx];
    counts[label] = (counts[label] ?? 0) + 1;
  }

  // Add Gaussian shot noise (stddev = 2% of expected count per state)
  for (let i = 0; i < basisLabels.length; i++) {
    const label = basisLabels[i];
    const expected = probabilities[i] * shots;
    if (expected > 0 && counts[label] !== undefined) {
      const noise = gaussianRandom(0, expected * 0.02);
      counts[label] = Math.max(0, Math.round(counts[label] + noise));
    }
  }

  return counts;
}

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

  /**
   * Cached audit dataset. Generated on first access and reused across all
   * audit log queries for the provider instance lifetime, ensuring consistent
   * pagination and filtering behavior.
   */
  private auditDatasetCache: AuditEntry[] | null = null;

  private getAuditDataset(): AuditEntry[] {
    if (!this.auditDatasetCache) {
      this.auditDatasetCache = generateAuditDataset();
    }
    return this.auditDatasetCache;
  }

  async getAuditLog(limit: number = 50): Promise<AuditEntry[]> {
    const dataset = this.getAuditDataset();
    return dataset.slice(0, limit);
  }

  async getAuditLogPaginated(
    filters: AuditLogFilter,
    page: number,
    pageSize: number,
    sortField: AuditLogSortField = "timestamp",
    sortDirection: "asc" | "desc" = "desc",
  ): Promise<PaginatedAuditLog> {
    let entries = [...this.getAuditDataset()];

    // Apply filters
    if (filters.dateFrom) {
      const from = new Date(filters.dateFrom).getTime();
      entries = entries.filter((e) => new Date(e.timestamp).getTime() >= from);
    }
    if (filters.dateTo) {
      const to = new Date(filters.dateTo).getTime();
      entries = entries.filter((e) => new Date(e.timestamp).getTime() <= to);
    }
    if (filters.actions && filters.actions.length > 0) {
      entries = entries.filter((e) => filters.actions!.includes(e.action));
    }
    if (filters.outcome) {
      entries = entries.filter((e) => e.outcome === filters.outcome);
    }
    if (filters.severity) {
      entries = entries.filter((e) => e.severity === filters.severity);
    }
    if (filters.frameworkId) {
      entries = entries.filter((e) => e.frameworkId === filters.frameworkId);
    }
    if (filters.subsystem) {
      entries = entries.filter((e) => e.subsystem === filters.subsystem);
    }
    if (filters.actor) {
      entries = entries.filter((e) => e.actor === filters.actor);
    }
    if (filters.searchQuery) {
      const query = filters.searchQuery.toLowerCase();
      entries = entries.filter((e) => {
        if (e.actor.toLowerCase().includes(query)) return true;
        if (e.description.toLowerCase().includes(query)) return true;
        if (e.metadata) {
          for (const val of Object.values(e.metadata)) {
            if (val.toLowerCase().includes(query)) return true;
          }
        }
        return false;
      });
    }

    // Apply sorting
    const severityOrder: Record<string, number> = { critical: 0, high: 1, medium: 2, low: 3, info: 4 };
    const outcomeOrder: Record<string, number> = { error: 0, failure: 1, denied: 2, success: 3 };
    const direction = sortDirection === "asc" ? 1 : -1;

    entries.sort((a, b) => {
      let cmp = 0;
      switch (sortField) {
        case "timestamp":
          cmp = new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime();
          break;
        case "severity":
          cmp = (severityOrder[a.severity] ?? 5) - (severityOrder[b.severity] ?? 5);
          break;
        case "outcome":
          cmp = (outcomeOrder[a.outcome] ?? 5) - (outcomeOrder[b.outcome] ?? 5);
          break;
        case "action":
          cmp = a.action.localeCompare(b.action);
          break;
        case "actor":
          cmp = a.actor.localeCompare(b.actor);
          break;
        case "subsystem":
          cmp = a.subsystem.localeCompare(b.subsystem);
          break;
      }
      return cmp * direction;
    });

    const totalCount = entries.length;
    const totalPages = Math.max(1, Math.ceil(totalCount / pageSize));
    const clampedPage = Math.max(1, Math.min(page, totalPages));
    const startIdx = (clampedPage - 1) * pageSize;
    const pageEntries = entries.slice(startIdx, startIdx + pageSize);

    return {
      entries: pageEntries,
      totalCount,
      page: clampedPage,
      pageSize,
      totalPages,
    };
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

  async getHealthHistory(subsystem: string): Promise<HealthCheckPoint[]> {
    const now = Date.now();
    const points: HealthCheckPoint[] = [];
    const subsystemIndex = SUBSYSTEM_NAMES.indexOf(subsystem as typeof SUBSYSTEM_NAMES[number]);
    const baseLatency = 2 + Math.max(0, subsystemIndex) * 0.7;

    for (let i = 19; i >= 0; i--) {
      const timestamp = now - i * 5_000; // 5-second intervals
      const roll = Math.random();
      let status: string = "up";
      if (roll > 0.97) {
        status = "down";
      } else if (roll > 0.90) {
        status = "degraded";
      }

      const responseTimeMs =
        status === "down"
          ? 0
          : gaussianRandom(
              baseLatency,
              status === "degraded" ? baseLatency * 0.8 : baseLatency * 0.15,
            );

      points.push({
        timestamp,
        status,
        responseTimeMs: Math.round(responseTimeMs * 100) / 100,
      });
    }

    return points;
  }

  async getSLAHistory(): Promise<SLAHistoryPoint[]> {
    const now = Date.now();
    const points: SLAHistoryPoint[] = [];
    let budget = 100;

    for (let i = 59; i >= 0; i--) {
      const timestamp = now - i * 60_000; // 1-minute intervals over 1 hour
      // Budget decreases slightly over time with occasional larger drops
      const drop = Math.random() > 0.85 ? gaussianRandom(1.2, 0.4) : gaussianRandom(0.08, 0.03);
      budget = Math.max(0, budget - Math.abs(drop));

      points.push({
        timestamp,
        budgetRemaining: Math.round(budget * 100) / 100,
      });
    }

    return points;
  }

  async getIncidents(): Promise<Incident[]> {
    const now = Date.now();
    // Deterministically select 6-8 incidents from the catalog
    const count = 6 + Math.floor(Math.random() * 3);
    const incidents: Incident[] = [];

    for (let i = 0; i < count && i < INCIDENT_CATALOG.length; i++) {
      const template = INCIDENT_CATALOG[i];
      const startedAt = now - (i + 1) * Math.floor(gaussianRandom(3_600_000, 900_000));
      const durationMs = Math.floor(gaussianRandom(1_800_000, 600_000));
      const resolved = Math.random() > 0.2; // 80% resolved

      incidents.push({
        id: `INC-${(1000 + i).toString()}`,
        severity: template.severity,
        title: template.title,
        description: template.description,
        startedAt: new Date(startedAt).toISOString(),
        resolvedAt: resolved ? new Date(startedAt + durationMs).toISOString() : undefined,
        durationMs: resolved ? durationMs : now - startedAt,
      });
    }

    return incidents;
  }

  // -------------------------------------------------------------------------
  // Distributed tracing
  // -------------------------------------------------------------------------

  async getTraces(limit = 25): Promise<Trace[]> {
    const traces: Trace[] = [];
    const count = Math.min(limit, 30);

    for (let i = 0; i < count; i++) {
      traces.push(generateTrace(Date.now() - i * Math.floor(gaussianRandom(2_000, 800))));
    }

    return traces;
  }

  async getTrace(traceId: string): Promise<Trace | null> {
    // In simulation mode, generate a deterministic trace seeded by the ID
    const traces = await this.getTraces(30);
    return traces.find((t) => t.traceId === traceId) ?? generateTrace(Date.now());
  }

  // -------------------------------------------------------------------------
  // Alert management
  // -------------------------------------------------------------------------

  async getAlerts(): Promise<Alert[]> {
    return generateAlerts();
  }

  // -------------------------------------------------------------------------
  // Analytics & Intelligence
  // -------------------------------------------------------------------------

  async getClassificationDistribution(
    start: number,
    end: number,
  ): Promise<ClassificationDistribution[]> {
    const counts: Record<string, number> = {
      fizz: 0,
      buzz: 0,
      fizzbuzz: 0,
      number: 0,
    };

    for (let n = start; n <= end; n++) {
      if (n % 15 === 0) {
        counts.fizzbuzz++;
      } else if (n % 3 === 0) {
        counts.fizz++;
      } else if (n % 5 === 0) {
        counts.buzz++;
      } else {
        counts.number++;
      }
    }

    const total = end - start + 1;

    const colorMap: Record<string, string> = {
      fizz: "var(--fizz-400)",
      buzz: "var(--buzz-400)",
      fizzbuzz: "var(--fizzbuzz-400)",
      number: "var(--number-400)",
    };

    return (["fizz", "buzz", "fizzbuzz", "number"] as const).map(
      (classification) => {
        const count = counts[classification];
        const proportion = total > 0 ? count / total : 0;
        const divisor = gcd(count, total);
        const fraction =
          total > 0 && divisor > 0
            ? `${count / divisor}/${total / divisor}`
            : "0/1";

        return {
          classification,
          count,
          proportion,
          fraction,
          color: colorMap[classification],
        };
      },
    );
  }

  async getDivisorHeatmap(
    start: number,
    end: number,
    divisors: number[] = [2, 3, 4, 5, 6, 7, 8, 9, 10, 15],
  ): Promise<HeatmapData> {
    const rangeSize = end - start + 1;
    let numbers: number[];

    if (rangeSize > 50) {
      // Sample evenly across the range to produce exactly 50 entries
      numbers = [];
      for (let i = 0; i < 50; i++) {
        numbers.push(start + Math.round((i / 49) * (rangeSize - 1)));
      }
    } else {
      numbers = [];
      for (let n = start; n <= end; n++) {
        numbers.push(n);
      }
    }

    const cells: HeatmapCell[] = [];
    for (const num of numbers) {
      for (const div of divisors) {
        cells.push({
          number: num,
          divisor: div,
          divisible: num % div === 0,
          remainder: num % div,
        });
      }
    }

    return { cells, numbers, divisors };
  }

  async getEvaluationTrend(period: string): Promise<EvaluationTrend> {
    const periodConfig: Record<string, { buckets: number; bucketSize: number }> = {
      "1h": { buckets: 12, bucketSize: 300 },
      "6h": { buckets: 24, bucketSize: 900 },
      "24h": { buckets: 24, bucketSize: 3600 },
      "7d": { buckets: 28, bucketSize: 21600 },
    };

    const config = periodConfig[period] ?? periodConfig["24h"];
    const now = Date.now();
    const dataPoints: EvaluationTrendPoint[] = [];
    let totalEvals = 0;

    for (let i = config.buckets - 1; i >= 0; i--) {
      const timestamp = now - i * config.bucketSize * 1000;
      const count = Math.max(1, Math.round(gaussianRandom(150, 40)));

      const fbCount = Math.max(0, Math.round(count * (1 / 15) + gaussianRandom(0, 2)));
      const fizzCount = Math.max(0, Math.round(count * (4 / 15) + gaussianRandom(0, 3)));
      const buzzCount = Math.max(0, Math.round(count * (2 / 15) + gaussianRandom(0, 2)));
      const plain = Math.max(0, count - fbCount - fizzCount - buzzCount);

      dataPoints.push({
        timestamp,
        count,
        fizz: fizzCount,
        buzz: buzzCount,
        fizzbuzz: fbCount,
        plain,
      });

      totalEvals += count;
    }

    return {
      dataPoints,
      totalEvaluations: totalEvals,
      bucketSizeSeconds: config.bucketSize,
    };
  }

  async getConfiguration(category?: ConfigCategory): Promise<ConfigItem[]> {
    let items = [...configurationItems];
    if (category) {
      items = items.filter((item) => item.category === category);
    }
    items.sort((a, b) => {
      const catCmp = a.category.localeCompare(b.category);
      if (catCmp !== 0) return catCmp;
      return a.name.localeCompare(b.name);
    });
    return items;
  }

  async updateConfigItem(itemId: string, newValue: string): Promise<ConfigUpdateResult> {
    const item = configurationItems.find((i) => i.id === itemId);
    if (!item) {
      return { success: false, error: `Configuration item "${itemId}" not found.` };
    }

    // Type validation
    if (item.type === "number") {
      const num = Number(newValue);
      if (isNaN(num)) {
        return { success: false, error: `Value "${newValue}" is not a valid number.` };
      }
      if (item.min !== undefined && num < item.min) {
        return { success: false, error: `Value ${num} is below minimum ${item.min}.` };
      }
      if (item.max !== undefined && num > item.max) {
        return { success: false, error: `Value ${num} exceeds maximum ${item.max}.` };
      }
    }

    if (item.type === "boolean" && newValue !== "true" && newValue !== "false") {
      return { success: false, error: `Value "${newValue}" is not a valid boolean.` };
    }

    if (item.type === "enum" && item.enumValues && !item.enumValues.includes(newValue)) {
      return {
        success: false,
        error: `Value "${newValue}" is not in allowed values: ${item.enumValues.join(", ")}.`,
      };
    }

    item.value = newValue;
    item.lastModifiedAt = new Date().toISOString();
    item.lastModifiedBy = "platform-admin";

    return { success: true, item: { ...item } };
  }

  async getFeatureFlags(): Promise<FeatureFlag[]> {
    const lifecycleOrder: Record<string, number> = {
      development: 0,
      testing: 1,
      canary: 2,
      ga: 3,
      deprecated: 4,
    };
    return [...featureFlagItems].sort((a, b) => {
      const lcCmp = (lifecycleOrder[a.lifecycle] ?? 99) - (lifecycleOrder[b.lifecycle] ?? 99);
      if (lcCmp !== 0) return lcCmp;
      return a.name.localeCompare(b.name);
    });
  }

  async toggleFeatureFlag(
    flagId: string,
    enabled: boolean,
    rolloutPercentage?: number,
  ): Promise<FeatureFlagToggleResult> {
    const flag = featureFlagItems.find((f) => f.id === flagId);
    if (!flag) {
      return { success: false, error: `Feature flag "${flagId}" not found.` };
    }

    if (rolloutPercentage !== undefined && (rolloutPercentage < 0 || rolloutPercentage > 100)) {
      return { success: false, error: `Rollout percentage must be between 0 and 100.` };
    }

    flag.enabled = enabled;
    if (rolloutPercentage !== undefined) {
      flag.rolloutPercentage = rolloutPercentage;
    }
    flag.lastToggledAt = new Date().toISOString();
    flag.lastToggledBy = "platform-admin";

    return { success: true, flag: { ...flag } };
  }

  // -------------------------------------------------------------------------
  // Quantum Circuit Workbench
  // -------------------------------------------------------------------------

  async getQuantumCircuits(): Promise<QuantumCircuit[]> {
    return [...QUANTUM_CIRCUITS].sort((a, b) => {
      const qubitCmp = a.numQubits - b.numQubits;
      if (qubitCmp !== 0) return qubitCmp;
      return a.name.localeCompare(b.name);
    });
  }

  async runQuantumSimulation(
    circuitId: string,
    shots: number,
  ): Promise<QuantumSimulationResult> {
    const circuit = QUANTUM_CIRCUITS.find((c) => c.id === circuitId);
    if (!circuit) {
      throw new Error(`Quantum circuit "${circuitId}" not found in the circuit registry.`);
    }

    const state = buildQuantumState(circuitId);
    const measurementCounts = sampleMeasurements(
      state.probabilities,
      state.basisLabels,
      shots,
    );

    // Classical evaluation: a single modulo operation per shot
    const classicalTimeMs = 0.001 * shots;
    // Quantum simulation: state-vector simulation is computationally expensive
    const quantumTimeMs = 50 + gaussianRandom(shots * 0.2, shots * 0.05);
    const quantumAdvantageRatio = quantumTimeMs / classicalTimeMs;

    return {
      circuit,
      finalState: state,
      measurementCounts,
      shotsExecuted: shots,
      quantumAdvantageRatio: Math.round(quantumAdvantageRatio * 10) / 10,
      quantumTimeMs: Math.round(quantumTimeMs * 100) / 100,
      classicalTimeMs: Math.round(classicalTimeMs * 1000) / 1000,
      simulatedAt: new Date().toISOString(),
    };
  }

  async getQuantumState(circuitId: string): Promise<QuantumState> {
    const circuit = QUANTUM_CIRCUITS.find((c) => c.id === circuitId);
    if (!circuit) {
      throw new Error(`Quantum circuit "${circuitId}" not found in the circuit registry.`);
    }
    return buildQuantumState(circuitId);
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
// Trace generation — models the FizzBuzz evaluation pipeline
// ---------------------------------------------------------------------------

/**
 * Pipeline stage descriptors for trace span generation. Each stage represents
 * a real subsystem in the Enterprise FizzBuzz evaluation pipeline, with
 * timing parameters calibrated from production profiling data.
 */
const PIPELINE_STAGES: Array<{
  operation: string;
  service: string;
  meanMs: number;
  stddevMs: number;
  /** Probability this stage produces an error span. */
  errorRate: number;
  /** If true, a cache hit may short-circuit remaining stages. */
  cacheGate?: boolean;
  attributes: Record<string, string>;
}> = [
  {
    operation: "ValidationMiddleware",
    service: "middleware-pipeline",
    meanMs: 0.1,
    stddevMs: 0.03,
    errorRate: 0.02,
    attributes: {
      "middleware.type": "validation",
      "validation.schema": "FizzBuzzEvaluationRequest/v3",
      "validation.strict_mode": "true",
    },
  },
  {
    operation: "CacheCheck",
    service: "mesi-cache",
    meanMs: 0.2,
    stddevMs: 0.05,
    errorRate: 0.01,
    cacheGate: true,
    attributes: {
      "cache.protocol": "MESI",
      "cache.coherence_domain": "us-east-1",
      "cache.tier": "L1",
    },
  },
  {
    operation: "RuleEngine.evaluate",
    service: "rule-engine",
    meanMs: 0.5,
    stddevMs: 0.12,
    errorRate: 0.03,
    attributes: {
      "engine.strategy": "chain_of_responsibility",
      "engine.rule_count": "7",
      "engine.parallel": "false",
    },
  },
  {
    operation: "BlockchainCommit",
    service: "blockchain-ledger",
    meanMs: 5.0,
    stddevMs: 1.8,
    errorRate: 0.05,
    attributes: {
      "blockchain.consensus": "proof_of_work",
      "blockchain.difficulty": "4",
      "blockchain.pending_txns": String(Math.floor(Math.random() * 12) + 1),
    },
  },
  {
    operation: "ComplianceCheck",
    service: "compliance-engine",
    meanMs: 0.3,
    stddevMs: 0.08,
    errorRate: 0.01,
    attributes: {
      "compliance.frameworks": "SOX,GDPR,HIPAA",
      "compliance.audit_level": "full",
      "compliance.region": "us-east-1",
    },
  },
  {
    operation: "FormatterPipeline",
    service: "formatter",
    meanMs: 0.1,
    stddevMs: 0.02,
    errorRate: 0.005,
    attributes: {
      "formatter.output_format": "plain",
      "formatter.locale": "en-US",
      "formatter.encoding": "UTF-8",
    },
  },
];

function generateTrace(baseTimestamp: number): Trace {
  const traceId = generateSessionId().replace(/-/g, "");
  const rootSpanId = generateSessionId().split("-")[0];
  const spans: TraceSpan[] = [];
  let hasError = false;
  let cursor = 0;

  // Determine if this is a cache hit (skip stages after CacheCheck)
  const isCacheHit = Math.random() < 0.35;

  // Root span — "evaluate"
  const rootStart = 0;

  for (let i = 0; i < PIPELINE_STAGES.length; i++) {
    const stage = PIPELINE_STAGES[i];
    const spanId = generateSessionId().split("-")[0] + i.toString(16);
    const duration = Math.max(0.01, gaussianRandom(stage.meanMs, stage.stddevMs));
    const startTime = cursor;
    cursor += duration + gaussianRandom(0.02, 0.005);

    const isError = Math.random() < stage.errorRate;
    if (isError) hasError = true;

    const attributes = { ...stage.attributes };
    if (stage.cacheGate && isCacheHit) {
      attributes["cache.result"] = "HIT";
      attributes["cache.ttl_remaining_ms"] = String(Math.floor(Math.random() * 30000));
    } else if (stage.cacheGate) {
      attributes["cache.result"] = "MISS";
    }

    spans.push({
      spanId,
      traceId,
      parentSpanId: rootSpanId,
      operationName: stage.operation,
      serviceName: stage.service,
      startTimeMs: Math.round(startTime * 1000) / 1000,
      durationMs: Math.round(duration * 1000) / 1000,
      status: isError ? "error" : "ok",
      attributes,
    });

    // Cache hit: stop processing after CacheCheck
    if (stage.cacheGate && isCacheHit) break;
  }

  const totalDuration = cursor;

  // Insert root span at the beginning
  spans.unshift({
    spanId: rootSpanId,
    traceId,
    operationName: "evaluate",
    serviceName: "fizzbuzz-platform",
    startTimeMs: 0,
    durationMs: Math.round(totalDuration * 1000) / 1000,
    status: hasError ? "error" : "ok",
    attributes: {
      "fizzbuzz.input": String(Math.floor(Math.random() * 1000) + 1),
      "fizzbuzz.strategy": "chain_of_responsibility",
      "fizzbuzz.cache_hit": String(isCacheHit),
    },
  });

  return {
    traceId,
    rootSpan: rootSpanId,
    spans,
    totalDurationMs: Math.round(totalDuration * 1000) / 1000,
    timestamp: new Date(baseTimestamp).toISOString(),
    hasError,
  };
}

// ---------------------------------------------------------------------------
// Alert generation
// ---------------------------------------------------------------------------

const ALERT_TEMPLATES: Array<{
  severity: Alert["severity"];
  subsystem: string;
  title: string;
  description: string;
}> = [
  {
    severity: "critical",
    subsystem: "Blockchain Ledger",
    title: "Block mining latency exceeds SLA threshold",
    description:
      "Proof-of-work mining duration has exceeded the 10-second SLA threshold for 3 consecutive blocks. Current average: 14.2s. Evaluation commits are queueing. Immediate investigation required.",
  },
  {
    severity: "critical",
    subsystem: "MESI Cache Coherence",
    title: "Cache coherence violation detected",
    description:
      "Node fizz-eval-eu-west-1c reported a Modified state for cache line 0x3F while fizz-eval-us-east-1a holds Exclusive. MESI protocol invariant violated. Data integrity at risk.",
  },
  {
    severity: "warning",
    subsystem: "Neural Network Inference",
    title: "ML confidence score below acceptable threshold",
    description:
      "The FizzBuzz neural network classifier softmax confidence has dropped to 87.3%, below the 90% operational threshold. Model retraining may be required.",
  },
  {
    severity: "warning",
    subsystem: "Circuit Breaker Mesh",
    title: "Circuit breaker OPEN for blockchain-ledger endpoint",
    description:
      "The circuit breaker for the blockchain-ledger service has tripped to OPEN state after 5 consecutive timeouts. Requests are being short-circuited with fallback responses.",
  },
  {
    severity: "warning",
    subsystem: "Rate Limiter",
    title: "Rate limit approaching for evaluation API",
    description:
      "Current request rate (1,847 req/s) is at 92% of the configured rate limit ceiling (2,000 req/s). Consider scaling horizontally or adjusting the limit.",
  },
  {
    severity: "info",
    subsystem: "Raft Consensus Module",
    title: "Leader election completed successfully",
    description:
      "Raft leader election for term 43 completed in 127ms. New leader: fizz-eval-us-west-2b. All 5 nodes acknowledged. No evaluation interruption observed.",
  },
  {
    severity: "info",
    subsystem: "Feature Flag Evaluator",
    title: "Feature flag 'quantum-strategy-v2' enabled in production",
    description:
      "The quantum-strategy-v2 feature flag has been activated for 100% of traffic. Previous rollout: 25%. Monitor evaluation correctness metrics closely.",
  },
  {
    severity: "info",
    subsystem: "FizzPM Package Registry",
    title: "Dependency audit completed — 0 critical vulnerabilities",
    description:
      "Scheduled dependency audit scanned 847 packages across 12 dependency trees. No critical or high-severity vulnerabilities detected. 2 moderate advisories noted.",
  },
  {
    severity: "warning",
    subsystem: "SOX Compliance Engine",
    title: "Audit log rotation approaching retention limit",
    description:
      "SOX audit log partition fizzbuzz-audit-2026-Q1 is at 89% capacity. Automated rotation will trigger at 95%. Ensure archival pipeline is operational.",
  },
  {
    severity: "critical",
    subsystem: "SLA Monitor",
    title: "Error budget burn rate exceeds safe threshold",
    description:
      "Current error budget burn rate of 4.2x exceeds the 1.0x safe threshold. At this rate, the monthly error budget will be exhausted in 2.3 days. Incident response protocol recommended.",
  },
];

function generateAlerts(): Alert[] {
  // Select 5-10 alerts from the template pool
  const count = Math.floor(Math.random() * 6) + 5;
  const shuffled = [...ALERT_TEMPLATES].sort(() => Math.random() - 0.5);
  const selected = shuffled.slice(0, count);

  return selected.map((template, i) => ({
    id: `alert-${generateSessionId().split("-")[0]}`,
    severity: template.severity,
    subsystem: template.subsystem,
    title: template.title,
    description: template.description,
    firedAt: new Date(Date.now() - i * Math.floor(gaussianRandom(300_000, 120_000))).toISOString(),
    acknowledged: Math.random() < 0.2,
    silenced: Math.random() < 0.1,
  }));
}

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

// ---------------------------------------------------------------------------
// Configuration items — derived from the platform's 80+ CLI flags
// ---------------------------------------------------------------------------

const configurationItems: ConfigItem[] = [
  // Evaluation (5)
  { id: "evaluation.strategy", name: "Evaluation Strategy", value: "standard", type: "enum", enumValues: ["standard", "chain_of_responsibility", "parallel_async", "machine_learning"], description: "Primary rule evaluation strategy", defaultValue: "standard", category: "evaluation", requiresRestart: true },
  { id: "evaluation.range_start", name: "Default Range Start", value: "1", type: "number", min: 1, max: 1_000_000, description: "Default start of evaluation range", defaultValue: "1", category: "evaluation", requiresRestart: false },
  { id: "evaluation.range_end", name: "Default Range End", value: "100", type: "number", min: 1, max: 1_000_000, description: "Default end of evaluation range", defaultValue: "100", category: "evaluation", requiresRestart: false },
  { id: "evaluation.output_format", name: "Output Format", value: "plain", type: "enum", enumValues: ["plain", "json", "xml", "csv"], description: "Serialization format for evaluation results", defaultValue: "plain", category: "evaluation", requiresRestart: false },
  { id: "evaluation.locale", name: "Locale", value: "en", type: "enum", enumValues: ["en", "de", "fr", "ja", "tlh", "sjn", "qya"], description: "Internationalized output locale", defaultValue: "en", category: "evaluation", requiresRestart: false },
  // Cache (5)
  { id: "cache.enabled", name: "Cache Enabled", value: "false", type: "boolean", description: "Enable MESI-coherent caching layer", defaultValue: "false", category: "cache", requiresRestart: true },
  { id: "cache.eviction_policy", name: "Eviction Policy", value: "lru", type: "enum", enumValues: ["lru", "lfu", "fifo", "dramatic_random"], description: "Cache eviction algorithm", defaultValue: "lru", category: "cache", requiresRestart: false },
  { id: "cache.max_entries", name: "Max Cache Entries", value: "1024", type: "number", min: 1, max: 1_000_000, description: "Maximum entries before eviction triggers", defaultValue: "1024", category: "cache", requiresRestart: false },
  { id: "cache.warm_on_start", name: "Warm on Start", value: "false", type: "boolean", description: "Pre-populate cache during boot sequence", defaultValue: "false", category: "cache", requiresRestart: true },
  { id: "cache.ttl_seconds", name: "TTL (seconds)", value: "3600", type: "number", min: 1, max: 86_400, description: "Time-to-live for cached evaluation results", defaultValue: "3600", category: "cache", requiresRestart: false },
  // Compliance (5)
  { id: "compliance.enabled", name: "Compliance Framework Enabled", value: "false", type: "boolean", description: "Enable SOX/GDPR/HIPAA compliance subsystem", defaultValue: "false", category: "compliance", requiresRestart: true },
  { id: "compliance.sox_audit", name: "SOX Audit Trail", value: "true", type: "boolean", description: "Emit segregation-of-duties audit entries", defaultValue: "true", category: "compliance", requiresRestart: false },
  { id: "compliance.gdpr_erasure_enabled", name: "GDPR Right-to-Erasure", value: "true", type: "boolean", description: "Honor GDPR Art. 17 erasure requests", defaultValue: "true", category: "compliance", requiresRestart: false },
  { id: "compliance.hipaa_encryption", name: "HIPAA PHI Encryption", value: "true", type: "boolean", description: "Encrypt PHI data at rest and in transit", defaultValue: "true", category: "compliance", requiresRestart: true },
  { id: "compliance.audit_retention_days", name: "Audit Retention (days)", value: "2555", type: "number", min: 30, max: 36_500, description: "Minimum retention period for compliance records", defaultValue: "2555", category: "compliance", requiresRestart: false },
  // Chaos Engineering (5)
  { id: "chaos.enabled", name: "Chaos Engineering Enabled", value: "false", type: "boolean", description: "Enable fault injection subsystem", defaultValue: "false", category: "chaos", requiresRestart: true },
  { id: "chaos.severity_level", name: "Severity Level", value: "1", type: "enum", enumValues: ["1", "2", "3", "4", "5"], description: "Chaos fault severity (1=gentle, 5=apocalypse)", defaultValue: "1", category: "chaos", requiresRestart: false },
  { id: "chaos.gameday_scenario", name: "Game Day Scenario", value: "total_chaos", type: "enum", enumValues: ["modulo_meltdown", "confidence_crisis", "slow_burn", "total_chaos"], description: "Default Game Day scenario", defaultValue: "total_chaos", category: "chaos", requiresRestart: false },
  { id: "chaos.auto_postmortem", name: "Auto Post-Mortem", value: "true", type: "boolean", description: "Automatically generate incident reports", defaultValue: "true", category: "chaos", requiresRestart: false },
  { id: "chaos.blast_radius_percent", name: "Blast Radius (%)", value: "25", type: "number", min: 0, max: 100, description: "Percentage of evaluations subject to fault injection", defaultValue: "25", category: "chaos", requiresRestart: false },
  // Blockchain (4)
  { id: "blockchain.enabled", name: "Blockchain Ledger Enabled", value: "false", type: "boolean", description: "Enable immutable audit ledger", defaultValue: "false", category: "blockchain", requiresRestart: true },
  { id: "blockchain.mining_difficulty", name: "Mining Difficulty", value: "2", type: "number", min: 1, max: 32, description: "Proof-of-work hash prefix zeros required", defaultValue: "2", category: "blockchain", requiresRestart: false },
  { id: "blockchain.consensus_algorithm", name: "Consensus Algorithm", value: "pow", type: "enum", enumValues: ["pow", "pos", "poa"], description: "Block validation consensus mechanism", defaultValue: "pow", category: "blockchain", requiresRestart: true },
  { id: "blockchain.block_size_limit", name: "Block Size Limit", value: "100", type: "number", min: 1, max: 10_000, description: "Maximum evaluation results per block", defaultValue: "100", category: "blockchain", requiresRestart: false },
  // ML (5)
  { id: "ml.enabled", name: "ML Engine Enabled", value: "false", type: "boolean", description: "Enable neural network evaluation strategy", defaultValue: "false", category: "ml", requiresRestart: true },
  { id: "ml.learning_rate", name: "Learning Rate", value: "0.001", type: "number", min: 0.0001, max: 1, description: "Gradient descent step size", defaultValue: "0.001", category: "ml", requiresRestart: false },
  { id: "ml.hidden_layers", name: "Hidden Layer Count", value: "3", type: "number", min: 1, max: 100, description: "Neural network depth", defaultValue: "3", category: "ml", requiresRestart: true },
  { id: "ml.epochs", name: "Training Epochs", value: "100", type: "number", min: 1, max: 100_000, description: "Complete passes through training data", defaultValue: "100", category: "ml", requiresRestart: false },
  { id: "ml.confidence_threshold", name: "Confidence Threshold", value: "0.85", type: "number", min: 0, max: 1, description: "Minimum prediction confidence for acceptance", defaultValue: "0.85", category: "ml", requiresRestart: false },
  // Rate Limiting (5)
  { id: "rate_limiting.enabled", name: "Rate Limiting Enabled", value: "false", type: "boolean", description: "Enable evaluation rate governance", defaultValue: "false", category: "rate_limiting", requiresRestart: true },
  { id: "rate_limiting.rpm", name: "Max Evaluations/min", value: "1000", type: "number", min: 1, max: 1_000_000, description: "Requests-per-minute ceiling", defaultValue: "1000", category: "rate_limiting", requiresRestart: false },
  { id: "rate_limiting.algorithm", name: "Algorithm", value: "token_bucket", type: "enum", enumValues: ["token_bucket", "sliding_window", "fixed_window"], description: "Rate limiting algorithm", defaultValue: "token_bucket", category: "rate_limiting", requiresRestart: false },
  { id: "rate_limiting.burst_multiplier", name: "Burst Multiplier", value: "2", type: "number", min: 1, max: 100, description: "Allowed burst factor over sustained rate", defaultValue: "2", category: "rate_limiting", requiresRestart: false },
  { id: "rate_limiting.quota_enabled", name: "Quota Tracking", value: "true", type: "boolean", description: "Enable per-tenant quota accounting", defaultValue: "true", category: "rate_limiting", requiresRestart: false },
  // SLA (5)
  { id: "sla.enabled", name: "SLA Monitoring Enabled", value: "false", type: "boolean", description: "Enable SLO/SLA monitoring subsystem", defaultValue: "false", category: "sla", requiresRestart: true },
  { id: "sla.availability_target", name: "Availability Target (%)", value: "99.95", type: "number", min: 0, max: 100, description: "Target availability percentage", defaultValue: "99.95", category: "sla", requiresRestart: false },
  { id: "sla.latency_p99_target_ms", name: "P99 Latency Target (ms)", value: "50", type: "number", min: 1, max: 10_000, description: "99th-percentile latency SLO threshold", defaultValue: "50", category: "sla", requiresRestart: false },
  { id: "sla.error_budget_window_days", name: "Error Budget Window (days)", value: "30", type: "number", min: 1, max: 365, description: "Rolling window for error budget calculation", defaultValue: "30", category: "sla", requiresRestart: false },
  { id: "sla.auto_escalation", name: "Auto Escalation", value: "true", type: "boolean", description: "Automatically page on-call for SLO breach", defaultValue: "true", category: "sla", requiresRestart: false },
  // Service Mesh (3)
  { id: "service_mesh.enabled", name: "Service Mesh Enabled", value: "false", type: "boolean", description: "Decompose FizzBuzz into 7 microservices", defaultValue: "false", category: "service_mesh", requiresRestart: true },
  { id: "service_mesh.latency_injection", name: "Latency Injection", value: "false", type: "boolean", description: "Inject simulated network latency between services", defaultValue: "false", category: "service_mesh", requiresRestart: false },
  { id: "service_mesh.packet_loss", name: "Packet Loss Simulation", value: "false", type: "boolean", description: "Simulate packet loss between mesh services", defaultValue: "false", category: "service_mesh", requiresRestart: false },
  // Observability (4)
  { id: "observability.tracing", name: "Distributed Tracing", value: "false", type: "boolean", description: "Enable OpenTelemetry distributed tracing", defaultValue: "false", category: "observability", requiresRestart: true },
  { id: "observability.metrics", name: "Prometheus Metrics", value: "false", type: "boolean", description: "Enable Prometheus-style metrics collection", defaultValue: "false", category: "observability", requiresRestart: true },
  { id: "observability.webhooks", name: "Webhook Notifications", value: "false", type: "boolean", description: "Enable event-driven webhook telemetry", defaultValue: "false", category: "observability", requiresRestart: false },
  { id: "observability.hot_reload", name: "Config Hot-Reload", value: "false", type: "boolean", description: "Enable Raft-consensus configuration hot-reload", defaultValue: "false", category: "observability", requiresRestart: true },
  // Persistence (4)
  { id: "persistence.backend", name: "Storage Backend", value: "in_memory", type: "enum", enumValues: ["in_memory", "sqlite", "filesystem"], description: "Result persistence repository backend", defaultValue: "in_memory", category: "persistence", requiresRestart: true },
  { id: "persistence.db_path", name: "SQLite Database Path", value: "fizzbuzz.db", type: "string", description: "Path to SQLite database file", defaultValue: "fizzbuzz.db", category: "persistence", requiresRestart: true },
  { id: "persistence.results_dir", name: "Results Directory", value: "./results", type: "string", description: "Filesystem persistence output directory", defaultValue: "./results", category: "persistence", requiresRestart: true },
  { id: "persistence.event_sourcing", name: "Event Sourcing", value: "false", type: "boolean", description: "Enable CQRS event-sourced persistence", defaultValue: "false", category: "persistence", requiresRestart: true },
];

// ---------------------------------------------------------------------------
// Feature flags — progressive rollout controls for platform capabilities
// ---------------------------------------------------------------------------

const featureFlagItems: FeatureFlag[] = [
  { id: "wuzz_rule_experimental", name: "Wuzz Rule (Experimental)", description: "Adds \"Wuzz\" output for numbers divisible by 7", enabled: false, rolloutPercentage: 0, lifecycle: "development", lastToggledAt: new Date(Date.now() - 86_400_000 * 3).toISOString(), lastToggledBy: "Dr. Elara Modulus" },
  { id: "quantum_strategy", name: "Quantum Evaluation Strategy", description: "Route eligible evaluations through quantum circuit simulator", enabled: true, rolloutPercentage: 15, lifecycle: "canary", lastToggledAt: new Date(Date.now() - 7_200_000).toISOString(), lastToggledBy: "platform-admin" },
  { id: "ml_confidence_override", name: "ML Confidence Override", description: "Allow ML strategy to override low-confidence predictions with fallback", enabled: true, rolloutPercentage: 100, lifecycle: "ga", lastToggledAt: new Date(Date.now() - 86_400_000 * 14).toISOString(), lastToggledBy: "Prof. Byron Divisor" },
  { id: "blockchain_async_mining", name: "Async Block Mining", description: "Mine blocks asynchronously to reduce evaluation latency", enabled: false, rolloutPercentage: 0, lifecycle: "testing", lastToggledAt: new Date(Date.now() - 86_400_000).toISOString(), lastToggledBy: "Eng. Cassandra Remainder" },
  { id: "cache_predictive_warm", name: "Predictive Cache Warming", description: "Use access pattern analysis to pre-warm cache entries", enabled: true, rolloutPercentage: 50, lifecycle: "canary", lastToggledAt: new Date(Date.now() - 3_600_000 * 5).toISOString(), lastToggledBy: "platform-admin" },
  { id: "gdpr_enhanced_erasure", name: "Enhanced GDPR Erasure", description: "Extended erasure covering backup and replica stores", enabled: true, rolloutPercentage: 100, lifecycle: "ga", lastToggledAt: new Date(Date.now() - 86_400_000 * 30).toISOString(), lastToggledBy: "Arch. Dmitri Quotient" },
  { id: "chaos_adaptive_severity", name: "Adaptive Chaos Severity", description: "Dynamically adjust chaos severity based on system health", enabled: false, rolloutPercentage: 0, lifecycle: "development", lastToggledAt: new Date(Date.now() - 86_400_000 * 2).toISOString(), lastToggledBy: "SRE Jenkins McFizzface" },
  { id: "federated_aggregation", name: "Federated Model Aggregation", description: "Enable FedAvg aggregation across distributed training nodes", enabled: true, rolloutPercentage: 25, lifecycle: "testing", lastToggledAt: new Date(Date.now() - 86_400_000 * 5).toISOString(), lastToggledBy: "Dir. Priya Evaluator" },
  { id: "genetic_crossover_v2", name: "Genetic Algorithm Crossover v2", description: "Replaced by uniform crossover in v3 engine", enabled: false, rolloutPercentage: 0, lifecycle: "deprecated", lastToggledAt: new Date(Date.now() - 86_400_000 * 60).toISOString(), lastToggledBy: "Prof. Byron Divisor" },
  { id: "dark_launch_fizzdap", name: "FizzDAP Dark Launch", description: "Shadow-route evaluations to FizzDAP debug adapter protocol", enabled: true, rolloutPercentage: 10, lifecycle: "canary", lastToggledAt: new Date(Date.now() - 3_600_000 * 8).toISOString(), lastToggledBy: "platform-admin" },
];
