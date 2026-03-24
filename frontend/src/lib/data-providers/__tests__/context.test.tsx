import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { renderHook } from "@testing-library/react";
import type { ReactNode } from "react";

import { DataProvider, useDataProvider } from "../context";
import type { IDataProvider } from "../provider";

/**
 * Minimal mock provider implementing the IDataProvider interface.
 * Only stubs the methods invoked by these context-layer tests.
 */
function createMockProvider(overrides: Partial<IDataProvider> = {}): IDataProvider {
  return {
    name: "Mock Test Provider",
    evaluate: vi.fn().mockResolvedValue({ sessionId: "test", results: [], totalProcessingTimeMs: 0, strategy: "standard", evaluatedAt: new Date().toISOString() }),
    getSystemHealth: vi.fn().mockResolvedValue([]),
    getMetricsSummary: vi.fn().mockResolvedValue({ totalEvaluations: 0, evaluationsPerSecond: 0, cacheHitRate: 0, averageLatencyMs: 0, uptimeSeconds: 0, throughputHistory: [] }),
    getSLAStatus: vi.fn().mockResolvedValue({ availabilityPercent: 99.99, errorBudgetRemaining: 1, latencyP99Ms: 1, correctnessPercent: 100, activeIncidents: 0, onCallEngineer: "Test" }),
    getRecentEvaluations: vi.fn().mockResolvedValue([]),
    getConsensusStatus: vi.fn().mockResolvedValue({ leaderNode: "n1", ballotNumber: 1, consensusAchieved: true, clusterSize: 3, nodesAcknowledged: 3 }),
    getCostSummary: vi.fn().mockResolvedValue({ currentPeriodCost: 0, previousPeriodCost: 0, trend: "stable", costPerEvaluation: 0 }),
    getMetricTimeSeries: vi.fn().mockResolvedValue({ metricName: "test", dataPoints: [] }),
    listMetrics: vi.fn().mockResolvedValue([]),
    getHealthHistory: vi.fn().mockResolvedValue([]),
    getSLAHistory: vi.fn().mockResolvedValue([]),
    getIncidents: vi.fn().mockResolvedValue([]),
    getTraces: vi.fn().mockResolvedValue([]),
    getTrace: vi.fn().mockResolvedValue(null),
    getAlerts: vi.fn().mockResolvedValue([]),
    getComplianceFrameworks: vi.fn().mockResolvedValue([]),
    getComplianceFindings: vi.fn().mockResolvedValue([]),
    getAuditLog: vi.fn().mockResolvedValue([]),
    getClassificationDistribution: vi.fn().mockResolvedValue([]),
    getDivisorHeatmap: vi.fn().mockResolvedValue({ rows: [], divisors: [] }),
    getEvaluationTrend: vi.fn().mockResolvedValue({ period: "1h", points: [] }),
    getConfiguration: vi.fn().mockResolvedValue([]),
    updateConfigItem: vi.fn().mockResolvedValue({ success: true }),
    getFeatureFlags: vi.fn().mockResolvedValue([]),
    toggleFeatureFlag: vi.fn().mockResolvedValue({ success: true }),
    getAuditLogPaginated: vi.fn().mockResolvedValue({ totalCount: 0, page: 1, pageSize: 10, entries: [] }),
    getBlockchain: vi.fn().mockResolvedValue([]),
    getBlock: vi.fn().mockResolvedValue(null),
    getBlockchainStats: vi.fn().mockResolvedValue({ height: 0, totalTransactions: 0, averageMiningTimeMs: 0, currentDifficulty: 0, hashRate: 0, chainValid: true }),
    getQuantumCircuits: vi.fn().mockResolvedValue([]),
    runQuantumSimulation: vi.fn().mockResolvedValue({ circuit: {}, finalState: {}, measurementCounts: {}, shotsExecuted: 0, quantumAdvantageRatio: 0, quantumTimeMs: 0, classicalTimeMs: 0, simulatedAt: "" }),
    getQuantumState: vi.fn().mockResolvedValue({ amplitudes: [], probabilities: [], basisLabels: [] }),
    getChaosExperiments: vi.fn().mockResolvedValue([]),
    runChaosExperiment: vi.fn().mockResolvedValue({}),
    getGameDayScenarios: vi.fn().mockResolvedValue([]),
    getChaosMetrics: vi.fn().mockResolvedValue({ totalExperiments: 0, meanTimeToRecoveryMs: 0 }),
    runEvolution: vi.fn().mockResolvedValue({ runId: "", config: {}, generations: [], startedAt: "", completedAt: "", isComplete: true, bestChromosome: {} }),
    getEvolutionHistory: vi.fn().mockResolvedValue(null),
    getCurrentPopulation: vi.fn().mockResolvedValue(null),
    getClusterTopology: vi.fn().mockResolvedValue({ nodes: [], edges: [], leaderId: "" }),
    getElectionHistory: vi.fn().mockResolvedValue([]),
    simulatePartition: vi.fn().mockResolvedValue({ partitionCreated: false }),
    getTwinState: vi.fn().mockResolvedValue({ subsystems: [], overallDrift: 0 }),
    runProjection: vi.fn().mockResolvedValue({ metric: "", points: [] }),
    runWhatIfScenario: vi.fn().mockResolvedValue({ summary: "", impacts: [] }),
    getCostBreakdown: vi.fn().mockResolvedValue([]),
    getBudgetStatus: vi.fn().mockResolvedValue([]),
    getExchangeRateHistory: vi.fn().mockResolvedValue({ currentRate: 1, history: [] }),
    generateInvoice: vi.fn().mockResolvedValue({ invoiceId: "", period: "", lineItems: [], total: 0 }),
    getDailyCostTrend: vi.fn().mockResolvedValue([]),
    getCacheState: vi.fn().mockResolvedValue([]),
    getCacheStats: vi.fn().mockResolvedValue({ totalEntries: 0, hitRate: 0 }),
    getMESITransitions: vi.fn().mockResolvedValue([]),
    getCacheEulogies: vi.fn().mockResolvedValue([]),
    getFLClients: vi.fn().mockResolvedValue([]),
    getFLTrainingHistory: vi.fn().mockResolvedValue([]),
    getFLModelState: vi.fn().mockResolvedValue({ globalAccuracy: 0, privacyBudgetRemaining: 0, totalRounds: 0, convergenceRate: 0, weightDivergence: 0, totalPrivacyBudget: 0 }),
    startFLTrainingRound: vi.fn().mockResolvedValue(null),
    getStrata: vi.fn().mockResolvedValue([]),
    getArtifacts: vi.fn().mockResolvedValue([]),
    runBayesianReconstruction: vi.fn().mockResolvedValue({ artifactId: "", evidenceUpdates: [] }),
    generateForensicReport: vi.fn().mockResolvedValue({ reportId: "", findings: [] }),
    ...overrides,
  } as IDataProvider;
}

describe("DataProvider context", () => {
  it("provides the injected provider to child components", () => {
    const mockProvider = createMockProvider();

    function Consumer() {
      const p = useDataProvider();
      return <span data-testid="name">{p.name}</span>;
    }

    render(
      <DataProvider provider={mockProvider}>
        <Consumer />
      </DataProvider>,
    );

    expect(screen.getByTestId("name").textContent).toBe("Mock Test Provider");
  });

  it("defaults to SimulationProvider when no provider prop is given", () => {
    function Consumer() {
      const p = useDataProvider();
      return <span data-testid="name">{p.name}</span>;
    }

    render(
      <DataProvider>
        <Consumer />
      </DataProvider>,
    );

    expect(screen.getByTestId("name").textContent).toBe("Local Simulation Engine");
  });

  it("throws when useDataProvider is called outside DataProvider", () => {
    // Suppress React error boundary output
    const spy = vi.spyOn(console, "error").mockImplementation(() => {});

    expect(() => {
      renderHook(() => useDataProvider());
    }).toThrow(/useDataProvider must be used within a <DataProvider>/);

    spy.mockRestore();
  });

  it("memoises the provider instance across renders", () => {
    const mockProvider = createMockProvider();
    const instances: IDataProvider[] = [];

    function Collector() {
      const p = useDataProvider();
      instances.push(p);
      return null;
    }

    const { rerender } = render(
      <DataProvider provider={mockProvider}>
        <Collector />
      </DataProvider>,
    );

    rerender(
      <DataProvider provider={mockProvider}>
        <Collector />
      </DataProvider>,
    );

    expect(instances[0]).toBe(instances[1]);
  });

  it("provides a new instance when the provider prop changes", () => {
    const provider1 = createMockProvider({ name: "Provider A" } as Partial<IDataProvider>);
    const provider2 = createMockProvider({ name: "Provider B" } as Partial<IDataProvider>);
    const names: string[] = [];

    function Collector() {
      const p = useDataProvider();
      names.push(p.name);
      return null;
    }

    const { rerender } = render(
      <DataProvider provider={provider1}>
        <Collector />
      </DataProvider>,
    );

    rerender(
      <DataProvider provider={provider2}>
        <Collector />
      </DataProvider>,
    );

    expect(names).toContain("Provider A");
    expect(names).toContain("Provider B");
  });
});
