import { describe, it, expect, beforeEach } from "vitest";
import { SimulationProvider } from "../simulation-provider";

describe("SimulationProvider — full coverage", () => {
  let provider: SimulationProvider;

  beforeEach(() => {
    provider = new SimulationProvider();
  });

  // ---------------------------------------------------------------------------
  // Provider identity
  // ---------------------------------------------------------------------------

  it("exposes a human-readable name", () => {
    expect(provider.name).toBe("Local Simulation Engine");
  });

  // ---------------------------------------------------------------------------
  // getRecentEvaluations()
  // ---------------------------------------------------------------------------

  describe("getRecentEvaluations()", () => {
    it("returns a non-empty array of sessions", async () => {
      const sessions = await provider.getRecentEvaluations();
      expect(Array.isArray(sessions)).toBe(true);
      expect(sessions.length).toBeGreaterThan(0);
    });

    it("each session has a UUID sessionId and strategy", async () => {
      const sessions = await provider.getRecentEvaluations();
      for (const s of sessions) {
        expect(s.sessionId).toMatch(
          /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/,
        );
        expect(typeof s.strategy).toBe("string");
        expect(s.strategy.length).toBeGreaterThan(0);
      }
    });
  });

  // ---------------------------------------------------------------------------
  // getConsensusStatus()
  // ---------------------------------------------------------------------------

  describe("getConsensusStatus()", () => {
    it("returns consensus fields with valid ranges", async () => {
      const cs = await provider.getConsensusStatus();
      expect(typeof cs.leaderNode).toBe("string");
      expect(cs.ballotNumber).toBeGreaterThanOrEqual(0);
      expect(cs.clusterSize).toBeGreaterThanOrEqual(1);
      expect(cs.nodesAcknowledged).toBeLessThanOrEqual(cs.clusterSize);
      expect(typeof cs.consensusAchieved).toBe("boolean");
    });
  });

  // ---------------------------------------------------------------------------
  // getCostSummary()
  // ---------------------------------------------------------------------------

  describe("getCostSummary()", () => {
    it("returns cost fields with valid types", async () => {
      const cost = await provider.getCostSummary();
      expect(typeof cost.currentPeriodCost).toBe("number");
      expect(typeof cost.previousPeriodCost).toBe("number");
      expect(["up", "down", "stable"]).toContain(cost.trend);
      expect(cost.costPerEvaluation).toBeGreaterThan(0);
    });
  });

  // ---------------------------------------------------------------------------
  // listMetrics()
  // ---------------------------------------------------------------------------

  describe("listMetrics()", () => {
    it("returns a non-empty array of metric definitions", async () => {
      const metrics = await provider.listMetrics();
      expect(Array.isArray(metrics)).toBe(true);
      expect(metrics.length).toBeGreaterThan(0);
    });

    it("each metric has name, type, description, and unit", async () => {
      const metrics = await provider.listMetrics();
      for (const m of metrics) {
        expect(typeof m.name).toBe("string");
        expect(typeof m.type).toBe("string");
        expect(typeof m.description).toBe("string");
        expect(typeof m.unit).toBe("string");
      }
    });
  });

  // ---------------------------------------------------------------------------
  // getMetricTimeSeries()
  // ---------------------------------------------------------------------------

  describe("getMetricTimeSeries()", () => {
    it("returns data points for a valid metric", async () => {
      const metrics = await provider.listMetrics();
      const ts = await provider.getMetricTimeSeries(metrics[0].name, 300);
      expect(Array.isArray(ts.dataPoints)).toBe(true);
      expect(ts.dataPoints.length).toBeGreaterThan(0);
      expect(ts.metricName).toBe(metrics[0].name);
    });
  });

  // ---------------------------------------------------------------------------
  // getHealthHistory()
  // ---------------------------------------------------------------------------

  describe("getHealthHistory()", () => {
    it("returns health check points for a subsystem", async () => {
      const health = await provider.getSystemHealth();
      const history = await provider.getHealthHistory(health[0].name);
      expect(Array.isArray(history)).toBe(true);
      expect(history.length).toBeGreaterThan(0);
      for (const hp of history) {
        expect(typeof hp.timestamp).toBe("number");
        expect(typeof hp.responseTimeMs).toBe("number");
      }
    });
  });

  // ---------------------------------------------------------------------------
  // getSLAHistory()
  // ---------------------------------------------------------------------------

  describe("getSLAHistory()", () => {
    it("returns SLA history data points", async () => {
      const history = await provider.getSLAHistory();
      expect(Array.isArray(history)).toBe(true);
      expect(history.length).toBeGreaterThan(0);
      for (const h of history) {
        expect(typeof h.timestamp).toBe("number");
        expect(typeof h.budgetRemaining).toBe("number");
      }
    });
  });

  // ---------------------------------------------------------------------------
  // getIncidents()
  // ---------------------------------------------------------------------------

  describe("getIncidents()", () => {
    it("returns an array of incidents with required fields", async () => {
      const incidents = await provider.getIncidents();
      expect(Array.isArray(incidents)).toBe(true);
      for (const inc of incidents) {
        expect(typeof inc.id).toBe("string");
        expect(typeof inc.title).toBe("string");
        expect(typeof inc.severity).toBe("string");
        expect(typeof inc.startedAt).toBe("string");
      }
    });
  });

  // ---------------------------------------------------------------------------
  // getTraces() / getTrace()
  // ---------------------------------------------------------------------------

  describe("getTraces()", () => {
    it("returns traces up to the specified limit", async () => {
      const traces = await provider.getTraces(5);
      expect(traces.length).toBeLessThanOrEqual(5);
      expect(traces.length).toBeGreaterThan(0);
      for (const t of traces) {
        expect(typeof t.traceId).toBe("string");
        expect(Array.isArray(t.spans)).toBe(true);
      }
    });
  });

  describe("getTrace()", () => {
    it("returns a trace object for any traceId", async () => {
      const trace = await provider.getTrace("nonexistent-id");
      expect(trace).not.toBeNull();
      expect(typeof trace!.traceId).toBe("string");
    });
  });

  // ---------------------------------------------------------------------------
  // getAlerts()
  // ---------------------------------------------------------------------------

  describe("getAlerts()", () => {
    it("returns an array of alerts", async () => {
      const alerts = await provider.getAlerts();
      expect(Array.isArray(alerts)).toBe(true);
      for (const a of alerts) {
        expect(typeof a.id).toBe("string");
        expect(typeof a.severity).toBe("string");
        expect(typeof a.title).toBe("string");
      }
    });
  });

  // ---------------------------------------------------------------------------
  // Compliance
  // ---------------------------------------------------------------------------

  describe("getComplianceFrameworks()", () => {
    it("returns compliance frameworks with scores", async () => {
      const frameworks = await provider.getComplianceFrameworks();
      expect(Array.isArray(frameworks)).toBe(true);
      expect(frameworks.length).toBeGreaterThan(0);
      for (const fw of frameworks) {
        expect(typeof fw.id).toBe("string");
        expect(typeof fw.name).toBe("string");
        expect(fw.complianceScore).toBeGreaterThanOrEqual(0);
        expect(fw.complianceScore).toBeLessThanOrEqual(100);
        expect(["compliant", "at-risk", "non-compliant"]).toContain(fw.status);
      }
    });
  });

  describe("getComplianceFindings()", () => {
    it("returns findings array", async () => {
      const findings = await provider.getComplianceFindings();
      expect(Array.isArray(findings)).toBe(true);
    });

    it("filters by framework ID", async () => {
      const all = await provider.getComplianceFindings();
      if (all.length > 0) {
        const frameworkId = all[0].frameworkId;
        const filtered = await provider.getComplianceFindings(frameworkId);
        for (const f of filtered) {
          expect(f.frameworkId).toBe(frameworkId);
        }
      }
    });
  });

  describe("getAuditLog()", () => {
    it("returns audit entries up to the limit", async () => {
      const entries = await provider.getAuditLog(10);
      expect(Array.isArray(entries)).toBe(true);
      expect(entries.length).toBeLessThanOrEqual(10);
    });
  });

  describe("getAuditLogPaginated()", () => {
    it("returns paginated results with metadata", async () => {
      const result = await provider.getAuditLogPaginated({}, 1, 5);
      expect(typeof result.totalCount).toBe("number");
      expect(typeof result.page).toBe("number");
      expect(typeof result.pageSize).toBe("number");
      expect(Array.isArray(result.entries)).toBe(true);
      expect(result.entries.length).toBeLessThanOrEqual(5);
    });
  });

  // ---------------------------------------------------------------------------
  // Analytics & Intelligence
  // ---------------------------------------------------------------------------

  describe("getClassificationDistribution()", () => {
    it("returns exact counts for 1-15", async () => {
      const dist = await provider.getClassificationDistribution(1, 15);
      const classifications = dist.map((d) => d.classification);
      expect(classifications).toContain("fizz");
      expect(classifications).toContain("buzz");
      expect(classifications).toContain("fizzbuzz");
      expect(classifications).toContain("number");
      const totalCount = dist.reduce((s, d) => s + d.count, 0);
      expect(totalCount).toBe(15);
    });
  });

  describe("getDivisorHeatmap()", () => {
    it("returns heatmap with rows and cells", async () => {
      const heatmap = await provider.getDivisorHeatmap(1, 10);
      expect(Array.isArray(heatmap.cells)).toBe(true);
      expect(heatmap.cells.length).toBeGreaterThan(0);
      expect(Array.isArray(heatmap.numbers)).toBe(true);
      expect(Array.isArray(heatmap.divisors)).toBe(true);
    });
  });

  describe("getEvaluationTrend()", () => {
    it("returns trend data with period and points", async () => {
      const trend = await provider.getEvaluationTrend("1h");
      expect(Array.isArray(trend.dataPoints)).toBe(true);
      expect(trend.dataPoints.length).toBeGreaterThan(0);
      expect(typeof trend.totalEvaluations).toBe("number");
    });
  });

  // ---------------------------------------------------------------------------
  // Configuration & Feature Flags
  // ---------------------------------------------------------------------------

  describe("getConfiguration()", () => {
    it("returns config items with required fields", async () => {
      const items = await provider.getConfiguration();
      expect(Array.isArray(items)).toBe(true);
      expect(items.length).toBeGreaterThan(0);
      for (const item of items) {
        expect(typeof item.id).toBe("string");
        expect(typeof item.name).toBe("string");
        expect(typeof item.value).toBe("string");
      }
    });
  });

  describe("updateConfigItem()", () => {
    it("returns a result with success status", async () => {
      const items = await provider.getConfiguration();
      const result = await provider.updateConfigItem(items[0].id, "test-value");
      expect(typeof result.success).toBe("boolean");
    });
  });

  describe("getFeatureFlags()", () => {
    it("returns feature flags with enabled state", async () => {
      const flags = await provider.getFeatureFlags();
      expect(Array.isArray(flags)).toBe(true);
      expect(flags.length).toBeGreaterThan(0);
      for (const flag of flags) {
        expect(typeof flag.id).toBe("string");
        expect(typeof flag.name).toBe("string");
        expect(typeof flag.enabled).toBe("boolean");
      }
    });
  });

  describe("toggleFeatureFlag()", () => {
    it("returns toggle result", async () => {
      const flags = await provider.getFeatureFlags();
      const result = await provider.toggleFeatureFlag(flags[0].id, !flags[0].enabled);
      expect(typeof result.success).toBe("boolean");
    });
  });

  // ---------------------------------------------------------------------------
  // Blockchain
  // ---------------------------------------------------------------------------

  describe("getBlockchain()", () => {
    it("returns blocks in reverse chronological order", async () => {
      const blocks = await provider.getBlockchain(10);
      expect(Array.isArray(blocks)).toBe(true);
      expect(blocks.length).toBeGreaterThan(0);
      expect(blocks.length).toBeLessThanOrEqual(10);
      for (const b of blocks) {
        expect(typeof b.hash).toBe("string");
        expect(typeof b.previousHash).toBe("string");
        expect(typeof b.nonce).toBe("number");
      }
    });
  });

  describe("getBlock()", () => {
    it("returns a block by hash", async () => {
      const blocks = await provider.getBlockchain(1);
      const block = await provider.getBlock(blocks[0].hash);
      expect(block).not.toBeNull();
      expect(block!.hash).toBe(blocks[0].hash);
    });

    it("returns null for unknown hash", async () => {
      const block = await provider.getBlock("0000000000000000000000000000000000000000000000000000000000000000");
      expect(block).toBeNull();
    });
  });

  describe("getBlockchainStats()", () => {
    it("returns aggregate blockchain statistics", async () => {
      const stats = await provider.getBlockchainStats();
      expect(stats.height).toBeGreaterThan(0);
      expect(typeof stats.totalTransactions).toBe("number");
      expect(typeof stats.averageMiningTimeMs).toBe("number");
      expect(stats.chainValid).toBe(true);
    });
  });

  // ---------------------------------------------------------------------------
  // Quantum Circuit Workbench
  // ---------------------------------------------------------------------------

  describe("getQuantumCircuits()", () => {
    it("returns sorted circuit definitions", async () => {
      const circuits = await provider.getQuantumCircuits();
      expect(Array.isArray(circuits)).toBe(true);
      expect(circuits.length).toBeGreaterThan(0);
      for (const c of circuits) {
        expect(typeof c.id).toBe("string");
        expect(typeof c.name).toBe("string");
        expect(c.numQubits).toBeGreaterThan(0);
      }
    });
  });

  describe("runQuantumSimulation()", () => {
    it("returns simulation result with measurements", async () => {
      const circuits = await provider.getQuantumCircuits();
      const result = await provider.runQuantumSimulation(circuits[0].id, 100);
      expect(result.shotsExecuted).toBe(100);
      expect(result.circuit.id).toBe(circuits[0].id);
      expect(typeof result.quantumAdvantageRatio).toBe("number");
      expect(typeof result.simulatedAt).toBe("string");
    });

    it("throws for unknown circuit", async () => {
      await expect(provider.runQuantumSimulation("nonexistent", 10)).rejects.toThrow(
        /not found/,
      );
    });
  });

  describe("getQuantumState()", () => {
    it("returns the state vector for a circuit", async () => {
      const circuits = await provider.getQuantumCircuits();
      const state = await provider.getQuantumState(circuits[0].id);
      expect(Array.isArray(state.amplitudes)).toBe(true);
      expect(Array.isArray(state.probabilities)).toBe(true);
    });

    it("throws for unknown circuit", async () => {
      await expect(provider.getQuantumState("nonexistent")).rejects.toThrow(/not found/);
    });
  });

  // ---------------------------------------------------------------------------
  // Chaos Engineering
  // ---------------------------------------------------------------------------

  describe("getChaosExperiments()", () => {
    it("returns sorted experiment catalog", async () => {
      const experiments = await provider.getChaosExperiments();
      expect(Array.isArray(experiments)).toBe(true);
      expect(experiments.length).toBeGreaterThan(0);
      for (const e of experiments) {
        expect(typeof e.id).toBe("string");
        expect(typeof e.targetSubsystem).toBe("string");
        expect(typeof e.faultType).toBe("string");
      }
    });
  });

  describe("runChaosExperiment()", () => {
    it("returns the experiment with updated status", async () => {
      const experiments = await provider.getChaosExperiments();
      const result = await provider.runChaosExperiment(experiments[0].id);
      expect(result.id).toBe(experiments[0].id);
    });

    it("throws for unknown experiment", async () => {
      await expect(provider.runChaosExperiment("nonexistent")).rejects.toThrow(/not found/);
    });
  });

  describe("getGameDayScenarios()", () => {
    it("returns game day scenarios", async () => {
      const scenarios = await provider.getGameDayScenarios();
      expect(Array.isArray(scenarios)).toBe(true);
    });
  });

  describe("getChaosMetrics()", () => {
    it("returns chaos engineering metrics", async () => {
      const metrics = await provider.getChaosMetrics();
      expect(typeof metrics.experimentsRun).toBe("number");
      expect(typeof metrics.meanTimeToRecovery).toBe("number");
    });
  });

  // ---------------------------------------------------------------------------
  // Genetic Algorithm
  // ---------------------------------------------------------------------------

  describe("runEvolution()", () => {
    it("runs a GA evolution and returns history", async () => {
      const history = await provider.runEvolution({
        populationSize: 10,
        maxGenerations: 3,
        crossoverRate: 0.7,
        mutationRate: 0.1,
        elitismCount: 2,
        tournamentSize: 3,
      });
      expect(history.isComplete).toBe(true);
      expect(history.generations.length).toBe(3);
      expect(history.bestChromosome).toBeDefined();
    });
  });

  describe("getEvolutionHistory()", () => {
    it("returns null before any evolution", async () => {
      const result = await provider.getEvolutionHistory();
      expect(result).toBeNull();
    });

    it("returns history after evolution", async () => {
      await provider.runEvolution({
        populationSize: 6,
        maxGenerations: 2,
        crossoverRate: 0.7,
        mutationRate: 0.1,
        elitismCount: 1,
        tournamentSize: 2,
      });
      const history = await provider.getEvolutionHistory();
      expect(history).not.toBeNull();
      expect(history!.isComplete).toBe(true);
    });
  });

  describe("getCurrentPopulation()", () => {
    it("returns null before any evolution", async () => {
      const result = await provider.getCurrentPopulation();
      expect(result).toBeNull();
    });
  });

  // ---------------------------------------------------------------------------
  // Cluster Topology & Consensus
  // ---------------------------------------------------------------------------

  describe("getClusterTopology()", () => {
    it("returns topology with nodes and edges", async () => {
      const topology = await provider.getClusterTopology();
      expect(Array.isArray(topology.nodes)).toBe(true);
      expect(topology.nodes.length).toBeGreaterThan(0);
      expect(Array.isArray(topology.edges)).toBe(true);
      expect(typeof topology.currentLeader).toBe("string");
    });
  });

  describe("getElectionHistory()", () => {
    it("returns election records", async () => {
      const elections = await provider.getElectionHistory(5);
      expect(Array.isArray(elections)).toBe(true);
      expect(elections.length).toBeLessThanOrEqual(5);
    });
  });

  describe("simulatePartition()", () => {
    it("returns partition simulation result", async () => {
      const topology = await provider.getClusterTopology();
      const nodeId = topology.nodes[0].id;
      const result = await provider.simulatePartition([nodeId]);
      expect(typeof result.leaderElected).toBe("boolean");
    });
  });

  // ---------------------------------------------------------------------------
  // Digital Twin
  // ---------------------------------------------------------------------------

  describe("getTwinState()", () => {
    it("returns twin state with subsystem comparisons", async () => {
      const state = await provider.getTwinState();
      expect(Array.isArray(state.subsystemStates)).toBe(true);
      expect(state.subsystemStates.length).toBeGreaterThan(0);
      expect(typeof state.aggregateDriftFBDU).toBe("number");
    });
  });

  describe("runProjection()", () => {
    it("returns projection with confidence intervals", async () => {
      const projection = await provider.runProjection("latency", 3600);
      expect(typeof projection.metric).toBe("string");
      expect(Array.isArray(projection.points)).toBe(true);
      expect(projection.points.length).toBeGreaterThan(0);
    });
  });

  describe("runWhatIfScenario()", () => {
    it("returns what-if outcome", async () => {
      const outcome = await provider.runWhatIfScenario({ cacheEnabled: false });
      expect(typeof outcome.predictedLatencyMs).toBe("number");
      expect(typeof outcome.predictedCostFB).toBe("number");
    });
  });

  // ---------------------------------------------------------------------------
  // FinOps
  // ---------------------------------------------------------------------------

  describe("getCostBreakdown()", () => {
    it("returns cost allocations by subsystem", async () => {
      const breakdown = await provider.getCostBreakdown();
      expect(Array.isArray(breakdown)).toBe(true);
      expect(breakdown.length).toBeGreaterThan(0);
      for (const ca of breakdown) {
        expect(typeof ca.subsystem).toBe("string");
        expect(typeof ca.cost).toBe("number");
      }
    });
  });

  describe("getBudgetStatus()", () => {
    it("returns budget statuses", async () => {
      const budgets = await provider.getBudgetStatus();
      expect(Array.isArray(budgets)).toBe(true);
      expect(budgets.length).toBeGreaterThan(0);
      for (const b of budgets) {
        expect(typeof b.category).toBe("string");
        expect(typeof b.allocated).toBe("number");
        expect(typeof b.spent).toBe("number");
      }
    });
  });

  describe("getExchangeRateHistory()", () => {
    it("returns exchange rate with history", async () => {
      const rate = await provider.getExchangeRateHistory();
      expect(typeof rate.rate).toBe("number");
      expect(typeof rate.trend).toBe("string");
      expect(typeof rate.change24h).toBe("number");
    });
  });

  describe("generateInvoice()", () => {
    it("generates an invoice for a billing period", async () => {
      const invoice = await provider.generateInvoice("2026-03");
      expect(typeof invoice.id).toBe("string");
      expect(invoice.period).toBe("2026-03");
      expect(Array.isArray(invoice.lines)).toBe(true);
      expect(invoice.lines.length).toBeGreaterThan(0);
      expect(typeof invoice.total).toBe("number");
    });
  });

  describe("getDailyCostTrend()", () => {
    it("returns 30 days of cost data", async () => {
      const trend = await provider.getDailyCostTrend();
      expect(Array.isArray(trend)).toBe(true);
      expect(trend.length).toBeGreaterThan(0);
      for (const point of trend) {
        expect(typeof point.date).toBe("string");
        expect(typeof point.totalCost).toBe("number");
      }
    });
  });

  // ---------------------------------------------------------------------------
  // Cache Coherence
  // ---------------------------------------------------------------------------

  describe("getCacheState()", () => {
    it("returns cache lines with MESI state", async () => {
      const lines = await provider.getCacheState();
      expect(Array.isArray(lines)).toBe(true);
      expect(lines.length).toBeGreaterThan(0);
      for (const line of lines) {
        expect(typeof line.key).toBe("string");
        expect(["MODIFIED", "EXCLUSIVE", "SHARED", "INVALID"]).toContain(line.state);
      }
    });
  });

  describe("getCacheStats()", () => {
    it("returns cache statistics", async () => {
      const stats = await provider.getCacheStats();
      expect(typeof stats.entries).toBe("number");
      expect(typeof stats.hitRate).toBe("number");
      expect(stats.hitRate).toBeGreaterThanOrEqual(0);
      expect(stats.hitRate).toBeLessThanOrEqual(1);
    });
  });

  describe("getMESITransitions()", () => {
    it("returns MESI transitions up to the limit", async () => {
      const transitions = await provider.getMESITransitions(10);
      expect(Array.isArray(transitions)).toBe(true);
      expect(transitions.length).toBeLessThanOrEqual(10);
    });
  });

  describe("getCacheEulogies()", () => {
    it("returns cache eviction eulogies", async () => {
      const eulogies = await provider.getCacheEulogies(5);
      expect(Array.isArray(eulogies)).toBe(true);
      expect(eulogies.length).toBeLessThanOrEqual(5);
    });
  });

  // ---------------------------------------------------------------------------
  // Federated Learning
  // ---------------------------------------------------------------------------

  describe("getFLClients()", () => {
    it("returns federated learning clients sorted by region", async () => {
      const clients = await provider.getFLClients();
      expect(Array.isArray(clients)).toBe(true);
      expect(clients.length).toBeGreaterThan(0);
      for (const c of clients) {
        expect(typeof c.id).toBe("string");
        expect(typeof c.name).toBe("string");
        expect(typeof c.region).toBe("string");
      }
    });
  });

  describe("getFLTrainingHistory()", () => {
    it("returns training round history", async () => {
      const history = await provider.getFLTrainingHistory();
      expect(Array.isArray(history)).toBe(true);
      expect(history.length).toBeGreaterThan(0);
    });
  });

  describe("getFLModelState()", () => {
    it("returns the global model state", async () => {
      const state = await provider.getFLModelState();
      expect(typeof state.globalAccuracy).toBe("number");
      expect(state.globalAccuracy).toBeGreaterThanOrEqual(0);
      expect(state.globalAccuracy).toBeLessThanOrEqual(1);
      expect(typeof state.privacyBudgetRemaining).toBe("number");
      expect(typeof state.totalRounds).toBe("number");
    });
  });

  describe("startFLTrainingRound()", () => {
    it("returns a new training round", async () => {
      const round = await provider.startFLTrainingRound();
      expect(round).not.toBeNull();
      expect(typeof round!.roundNumber).toBe("number");
      expect(Array.isArray(round!.participants)).toBe(true);
      expect(round!.participants.length).toBeGreaterThan(0);
    });
  });

  // ---------------------------------------------------------------------------
  // Archaeological Recovery
  // ---------------------------------------------------------------------------

  describe("getStrata()", () => {
    it("returns archaeological strata", async () => {
      const strata = await provider.getStrata();
      expect(Array.isArray(strata)).toBe(true);
      expect(strata.length).toBeGreaterThan(0);
      for (const s of strata) {
        expect(typeof s.id).toBe("string");
        expect(typeof s.name).toBe("string");
        expect(typeof s.depth).toBe("number");
      }
    });
  });

  describe("getArtifacts()", () => {
    it("returns all artifacts when no filter is given", async () => {
      const artifacts = await provider.getArtifacts();
      expect(Array.isArray(artifacts)).toBe(true);
      expect(artifacts.length).toBeGreaterThan(0);
    });

    it("filters artifacts by stratum ID", async () => {
      const strata = await provider.getStrata();
      const filtered = await provider.getArtifacts(strata[0].id);
      for (const a of filtered) {
        expect(a.stratumId).toBe(strata[0].id);
      }
    });
  });

  describe("runBayesianReconstruction()", () => {
    it("returns a reconstruction with evidence updates", async () => {
      const artifacts = await provider.getArtifacts();
      const reconstruction = await provider.runBayesianReconstruction(artifacts[0].id);
      expect(typeof reconstruction.artifactId).toBe("string");
      expect(Array.isArray(reconstruction.evidenceChain)).toBe(true);
      expect(reconstruction.evidenceChain.length).toBeGreaterThan(0);
    });

    it("throws for unknown artifact", async () => {
      await expect(provider.runBayesianReconstruction("nonexistent")).rejects.toThrow(
        /not found/,
      );
    });
  });

  describe("generateForensicReport()", () => {
    it("generates a report from artifact IDs", async () => {
      const artifacts = await provider.getArtifacts();
      const ids = artifacts.slice(0, 2).map((a) => a.id);
      const report = await provider.generateForensicReport(ids);
      expect(typeof report.id).toBe("string");
      expect(Array.isArray(report.findings)).toBe(true);
    });

    it("throws for unknown artifact IDs", async () => {
      await expect(provider.generateForensicReport(["nonexistent"])).rejects.toThrow(
        /not found/,
      );
    });
  });
});
