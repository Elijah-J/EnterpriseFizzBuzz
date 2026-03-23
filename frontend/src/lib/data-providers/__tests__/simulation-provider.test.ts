import { describe, it, expect, beforeEach } from "vitest";
import { SimulationProvider } from "../simulation-provider";

describe("SimulationProvider", () => {
  let provider: SimulationProvider;

  beforeEach(() => {
    provider = new SimulationProvider();
  });

  // ---------------------------------------------------------------------------
  // evaluate()
  // ---------------------------------------------------------------------------

  describe("evaluate()", () => {
    it("classifies multiples of 3 as Fizz", async () => {
      const session = await provider.evaluate({
        start: 3,
        end: 3,
        strategy: "standard",
      });

      expect(session.results).toHaveLength(1);
      expect(session.results[0].output).toBe("Fizz");
      expect(session.results[0].classification).toBe("fizz");
      expect(session.results[0].matchedRules).toEqual([
        { divisor: 3, label: "Fizz", priority: 1 },
      ]);
    });

    it("classifies multiples of 5 as Buzz", async () => {
      const session = await provider.evaluate({
        start: 5,
        end: 5,
        strategy: "standard",
      });

      expect(session.results).toHaveLength(1);
      expect(session.results[0].output).toBe("Buzz");
      expect(session.results[0].classification).toBe("buzz");
      expect(session.results[0].matchedRules).toEqual([
        { divisor: 5, label: "Buzz", priority: 2 },
      ]);
    });

    it("classifies multiples of 15 as FizzBuzz", async () => {
      const session = await provider.evaluate({
        start: 15,
        end: 15,
        strategy: "standard",
      });

      expect(session.results).toHaveLength(1);
      expect(session.results[0].output).toBe("FizzBuzz");
      expect(session.results[0].classification).toBe("fizzbuzz");
      expect(session.results[0].matchedRules).toHaveLength(2);
    });

    it("returns the number itself for non-multiples of 3 or 5", async () => {
      const session = await provider.evaluate({
        start: 7,
        end: 7,
        strategy: "standard",
      });

      expect(session.results).toHaveLength(1);
      expect(session.results[0].output).toBe("7");
      expect(session.results[0].classification).toBe("number");
      expect(session.results[0].matchedRules).toHaveLength(0);
    });

    it("evaluates a range of numbers with correct total count", async () => {
      const session = await provider.evaluate({
        start: 1,
        end: 20,
        strategy: "standard",
      });

      expect(session.results).toHaveLength(20);
    });

    it("includes session metadata", async () => {
      const session = await provider.evaluate({
        start: 1,
        end: 5,
        strategy: "chain_of_responsibility",
      });

      expect(session.sessionId).toMatch(
        /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/
      );
      expect(session.strategy).toBe("chain_of_responsibility");
      expect(session.evaluatedAt).toBeTruthy();
      expect(session.totalProcessingTimeMs).toBeGreaterThan(0);
    });

    it("records non-negative processing time for each result", async () => {
      const session = await provider.evaluate({
        start: 1,
        end: 10,
        strategy: "standard",
      });

      for (const result of session.results) {
        expect(result.processingTimeNs).toBeGreaterThanOrEqual(0);
      }
    });
  });

  // ---------------------------------------------------------------------------
  // getSystemHealth()
  // ---------------------------------------------------------------------------

  describe("getSystemHealth()", () => {
    it("returns an array of subsystem health records", async () => {
      const health = await provider.getSystemHealth();

      expect(Array.isArray(health)).toBe(true);
      expect(health.length).toBeGreaterThan(0);
    });

    it("includes required fields on each subsystem", async () => {
      const health = await provider.getSystemHealth();

      for (const subsystem of health) {
        expect(subsystem).toHaveProperty("name");
        expect(subsystem).toHaveProperty("status");
        expect(subsystem).toHaveProperty("lastChecked");
        expect(subsystem).toHaveProperty("responseTimeMs");
        expect(["up", "degraded", "down", "unknown"]).toContain(subsystem.status);
      }
    });

    it("contains known infrastructure subsystems", async () => {
      const health = await provider.getSystemHealth();
      const names = health.map((h) => h.name);

      expect(names).toContain("MESI Cache Coherence");
      expect(names).toContain("Blockchain Ledger");
      expect(names).toContain("Neural Network Inference");
    });
  });

  // ---------------------------------------------------------------------------
  // getMetricsSummary()
  // ---------------------------------------------------------------------------

  describe("getMetricsSummary()", () => {
    it("returns valid metrics with all required fields", async () => {
      const metrics = await provider.getMetricsSummary();

      expect(metrics.totalEvaluations).toBeGreaterThan(0);
      expect(metrics.evaluationsPerSecond).toBeGreaterThan(0);
      expect(metrics.cacheHitRate).toBeGreaterThanOrEqual(0);
      expect(metrics.cacheHitRate).toBeLessThanOrEqual(1);
      expect(metrics.averageLatencyMs).toBeGreaterThan(0);
      expect(metrics.uptimeSeconds).toBeGreaterThan(0);
    });

    it("returns throughput history as a non-empty array", async () => {
      const metrics = await provider.getMetricsSummary();

      expect(Array.isArray(metrics.throughputHistory)).toBe(true);
      expect(metrics.throughputHistory.length).toBeGreaterThan(0);
    });
  });

  // ---------------------------------------------------------------------------
  // getSLAStatus()
  // ---------------------------------------------------------------------------

  describe("getSLAStatus()", () => {
    it("returns valid SLA data with all required fields", async () => {
      const sla = await provider.getSLAStatus();

      expect(sla.availabilityPercent).toBeGreaterThanOrEqual(0);
      expect(sla.availabilityPercent).toBeLessThanOrEqual(100);
      expect(sla.errorBudgetRemaining).toBeGreaterThanOrEqual(0);
      expect(sla.errorBudgetRemaining).toBeLessThanOrEqual(1);
      expect(sla.latencyP99Ms).toBeGreaterThan(0);
      expect(sla.correctnessPercent).toBe(100);
      expect(typeof sla.activeIncidents).toBe("number");
      expect(typeof sla.onCallEngineer).toBe("string");
      expect(sla.onCallEngineer.length).toBeGreaterThan(0);
    });
  });
});
