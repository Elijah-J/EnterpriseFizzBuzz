import { describe, it, expect } from "vitest";

/**
 * Build smoke tests for the data provider module.
 *
 * These tests verify that all public exports resolve correctly at import time,
 * ensuring no broken re-exports, circular dependency chains, or missing module
 * paths interfere with bundle production. A failure here indicates a structural
 * packaging issue that would prevent the production build from completing.
 */
describe("Build smoke — data-providers barrel export", () => {
  it("exports SimulationProvider class", async () => {
    const mod = await import("../index");
    expect(mod.SimulationProvider).toBeDefined();
    expect(typeof mod.SimulationProvider).toBe("function");
  });

  it("exports DataProvider component", async () => {
    const mod = await import("../index");
    expect(mod.DataProvider).toBeDefined();
    expect(typeof mod.DataProvider).toBe("function");
  });

  it("exports useDataProvider hook", async () => {
    const mod = await import("../index");
    expect(mod.useDataProvider).toBeDefined();
    expect(typeof mod.useDataProvider).toBe("function");
  });

  it("SimulationProvider is instantiable", async () => {
    const { SimulationProvider } = await import("../index");
    const provider = new SimulationProvider();
    expect(provider.name).toBe("Local Simulation Engine");
  });

  it("SimulationProvider implements all IDataProvider methods", async () => {
    const { SimulationProvider } = await import("../index");
    const provider = new SimulationProvider();

    const expectedMethods = [
      "evaluate",
      "getSystemHealth",
      "getMetricsSummary",
      "getSLAStatus",
      "getRecentEvaluations",
      "getConsensusStatus",
      "getCostSummary",
      "getMetricTimeSeries",
      "listMetrics",
      "getHealthHistory",
      "getSLAHistory",
      "getIncidents",
      "getTraces",
      "getTrace",
      "getAlerts",
      "getComplianceFrameworks",
      "getComplianceFindings",
      "getAuditLog",
      "getClassificationDistribution",
      "getDivisorHeatmap",
      "getEvaluationTrend",
      "getConfiguration",
      "updateConfigItem",
      "getFeatureFlags",
      "toggleFeatureFlag",
      "getAuditLogPaginated",
      "getBlockchain",
      "getBlock",
      "getBlockchainStats",
      "getQuantumCircuits",
      "runQuantumSimulation",
      "getQuantumState",
      "getChaosExperiments",
      "runChaosExperiment",
      "getGameDayScenarios",
      "getChaosMetrics",
      "runEvolution",
      "getEvolutionHistory",
      "getCurrentPopulation",
      "getClusterTopology",
      "getElectionHistory",
      "simulatePartition",
      "getTwinState",
      "runProjection",
      "runWhatIfScenario",
      "getCostBreakdown",
      "getBudgetStatus",
      "getExchangeRateHistory",
      "generateInvoice",
      "getDailyCostTrend",
      "getCacheState",
      "getCacheStats",
      "getMESITransitions",
      "getCacheEulogies",
      "getFLClients",
      "getFLTrainingHistory",
      "getFLModelState",
      "startFLTrainingRound",
      "getStrata",
      "getArtifacts",
      "runBayesianReconstruction",
      "generateForensicReport",
    ];

    for (const method of expectedMethods) {
      expect(typeof (provider as Record<string, unknown>)[method]).toBe("function");
    }
  });
});

describe("Build smoke — type re-exports", () => {
  it("index barrel resolves without throwing", async () => {
    const mod = await import("../index");
    expect(mod).toBeDefined();
    expect(Object.keys(mod).length).toBeGreaterThan(0);
  });

  it("types module resolves without throwing", async () => {
    const mod = await import("../types");
    expect(mod).toBeDefined();
  });

  it("provider interface module resolves without throwing", async () => {
    const mod = await import("../provider");
    expect(mod).toBeDefined();
  });

  it("context module resolves without throwing", async () => {
    const mod = await import("../context");
    expect(mod).toBeDefined();
    expect(mod.DataProvider).toBeDefined();
    expect(mod.useDataProvider).toBeDefined();
  });
});
