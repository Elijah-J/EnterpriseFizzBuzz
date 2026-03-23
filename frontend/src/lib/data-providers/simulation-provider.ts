import type { IDataProvider } from "./provider";
import type {
  EvaluationRequest,
  EvaluationSession,
  FizzBuzzResult,
  MatchedRule,
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
 * Local simulation data provider for the Enterprise FizzBuzz Platform.
 *
 * Computes FizzBuzz evaluations entirely in TypeScript using modular
 * arithmetic. Generates realistic metadata including per-evaluation
 * processing times with Gaussian-distributed jitter, matched rule
 * annotations, and session identifiers suitable for audit correlation.
 *
 * This provider is intended for development, demonstration, and offline
 * operation. It produces results identical to the production backend
 * for the standard rule set (divisors 3 and 5).
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

    return {
      sessionId: generateSessionId(),
      results,
      totalProcessingTimeMs,
      strategy,
      evaluatedAt: new Date().toISOString(),
    };
  }
}
