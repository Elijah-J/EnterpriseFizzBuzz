import type { EvaluationRequest, EvaluationSession } from "./types";

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
}
