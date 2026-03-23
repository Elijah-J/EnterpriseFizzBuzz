/**
 * Core domain types for the Enterprise FizzBuzz Evaluation Platform.
 *
 * These types define the canonical data model for FizzBuzz evaluation
 * sessions. All data providers must produce results conforming to these
 * interfaces to ensure interoperability across the evaluation pipeline.
 */

export interface MatchedRule {
  /** The divisor that triggered this rule (e.g., 3 for Fizz, 5 for Buzz). */
  divisor: number;
  /** The label emitted by the rule when triggered. */
  label: string;
  /** Execution priority — lower values are evaluated first. */
  priority: number;
}

export interface FizzBuzzResult {
  /** The input integer that was evaluated. */
  number: number;
  /** The computed output string (e.g., "Fizz", "Buzz", "FizzBuzz", or the number itself). */
  output: string;
  /** Semantic classification of the result for display and analytics. */
  classification: "fizz" | "buzz" | "fizzbuzz" | "number";
  /** Rules that matched during evaluation, ordered by priority. */
  matchedRules: MatchedRule[];
  /** Wall-clock processing time for this individual evaluation, in nanoseconds. */
  processingTimeNs: number;
}

export interface EvaluationRequest {
  /** Start of the evaluation range (inclusive). */
  start: number;
  /** End of the evaluation range (inclusive). */
  end: number;
  /** Evaluation strategy to apply. */
  strategy:
    | "standard"
    | "chain_of_responsibility"
    | "machine_learning"
    | "quantum";
}

export interface EvaluationSession {
  /** Unique session identifier for audit trail correlation. */
  sessionId: string;
  /** Ordered evaluation results for the requested range. */
  results: FizzBuzzResult[];
  /** Aggregate processing time across all evaluations, in milliseconds. */
  totalProcessingTimeMs: number;
  /** Strategy identifier that produced these results. */
  strategy: string;
  /** ISO 8601 timestamp of evaluation completion. */
  evaluatedAt: string;
}
