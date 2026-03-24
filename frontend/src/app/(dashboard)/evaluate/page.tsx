"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardFooter,
  CardHeader,
} from "@/components/ui/card";
import { ProgressBar } from "@/components/ui/progress-bar";
import { Reveal } from "@/components/ui/reveal";
import { Skeleton } from "@/components/ui/skeleton";
import type { EvaluationSession, FizzBuzzResult } from "@/lib/data-providers";
import { useDataProvider } from "@/lib/data-providers";
import {
  formatCSV,
  formatJSON,
  formatPlain,
  formatXML,
} from "@/lib/formatters";

// ---------------------------------------------------------------------------
// Strategy metadata
// ---------------------------------------------------------------------------

const STRATEGIES = [
  {
    value: "standard" as const,
    label: "Standard",
    description: "Direct modular arithmetic evaluation",
  },
  {
    value: "chain_of_responsibility" as const,
    label: "Chain of Responsibility",
    description: "Pattern-based rule chain with priority dispatch",
  },
  {
    value: "machine_learning" as const,
    label: "Machine Learning",
    description: "Neural network inference with backprop-trained weights",
  },
  {
    value: "quantum" as const,
    label: "Quantum",
    description: "Superposition-based evaluation via simulated qubits",
  },
];

type OutputFormat = "plain" | "json" | "xml" | "csv";

const FORMAT_LABELS: Record<OutputFormat, string> = {
  plain: "Plain",
  json: "JSON",
  xml: "XML",
  csv: "CSV",
};

// ---------------------------------------------------------------------------
// Classification → Tailwind class maps
// ---------------------------------------------------------------------------

const CELL_BG: Record<FizzBuzzResult["classification"], string> = {
  fizz: "bg-fizz-950 border-fizz-800 text-fizz-300",
  buzz: "bg-buzz-950 border-buzz-800 text-buzz-300",
  fizzbuzz: "bg-fizzbuzz-950 border-fizzbuzz-800 text-fizzbuzz-300",
  number: "bg-number-950 border-number-800 text-number-400",
};

const LABEL_COLOR: Record<FizzBuzzResult["classification"], string> = {
  fizz: "text-fizz-400",
  buzz: "text-buzz-400",
  fizzbuzz: "text-fizzbuzz-400",
  number: "text-number-500",
};

// ---------------------------------------------------------------------------
// Page component
// ---------------------------------------------------------------------------

export default function EvaluateConsolePage() {
  const provider = useDataProvider();

  // Form state
  const [start, setStart] = useState(1);
  const [end, setEnd] = useState(100);
  const [strategy, setStrategy] = useState<
    "standard" | "chain_of_responsibility" | "machine_learning" | "quantum"
  >("standard");

  // Evaluation state
  const [session, setSession] = useState<EvaluationSession | null>(null);
  const [evaluating, setEvaluating] = useState(false);
  const [visibleCount, setVisibleCount] = useState(0);
  const [outputFormat, setOutputFormat] = useState<OutputFormat>("plain");
  const [evalStage, setEvalStage] = useState<string>("");
  const [evalProgress, setEvalProgress] = useState(0);
  const stageTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Validation
  const startValid = Number.isInteger(start) && start >= 1 && start <= 10_000;
  const endValid = Number.isInteger(end) && end >= 1 && end <= 10_000;
  const rangeValid = startValid && endValid && start < end;

  // ---------------------------------------------------------------------------
  // Execute evaluation
  // ---------------------------------------------------------------------------

  const handleEvaluate = useCallback(async () => {
    if (!rangeValid || evaluating) return;

    setEvaluating(true);
    setSession(null);
    setVisibleCount(0);
    setEvalStage("Initializing");
    setEvalProgress(10);

    try {
      // Simulate pipeline stage progression during evaluation
      stageTimer.current = setTimeout(() => {
        setEvalStage("Evaluating");
        setEvalProgress(40);
      }, 100);

      const result = await provider.evaluate({ start, end, strategy });

      setEvalStage("Formatting");
      setEvalProgress(80);

      setSession(result);

      // Brief pause before marking complete
      await new Promise((resolve) => setTimeout(resolve, 150));
      setEvalStage("Complete");
      setEvalProgress(100);

      // Animate results appearing one by one via CSS — we just need to
      // increment visibleCount on a timer so CSS transitions can fire.
      const total = result.results.length;
      let count = 0;
      const interval = setInterval(() => {
        count += 1;
        setVisibleCount(count);
        if (count >= total) clearInterval(interval);
      }, 30);
    } finally {
      setEvaluating(false);
      if (stageTimer.current) clearTimeout(stageTimer.current);
    }
  }, [provider, start, end, strategy, rangeValid, evaluating]);

  // ---------------------------------------------------------------------------
  // Computed analytics
  // ---------------------------------------------------------------------------

  const analytics = useMemo(() => {
    if (!session) return null;
    const results = session.results;
    return {
      total: results.length,
      fizz: results.filter((r) => r.classification === "fizz").length,
      buzz: results.filter((r) => r.classification === "buzz").length,
      fizzbuzz: results.filter((r) => r.classification === "fizzbuzz").length,
      number: results.filter((r) => r.classification === "number").length,
    };
  }, [session]);

  // ---------------------------------------------------------------------------
  // Formatted output
  // ---------------------------------------------------------------------------

  const formattedOutput = useMemo(() => {
    if (!session) return "";
    const formatters: Record<OutputFormat, (r: FizzBuzzResult[]) => string> = {
      plain: formatPlain,
      json: formatJSON,
      xml: formatXML,
      csv: formatCSV,
    };
    return formatters[outputFormat](session.results);
  }, [session, outputFormat]);

  // ---------------------------------------------------------------------------
  // Render
  // ---------------------------------------------------------------------------

  return (
    <div className="space-y-6">
      {/* Page header */}
      <Reveal>
        <div>
          <h1 className="heading-page">FizzBuzz Evaluation Console</h1>
          <p className="mt-1 text-sm text-text-secondary">
            Execute and inspect FizzBuzz evaluations across configurable ranges
            and strategies. All sessions are recorded for audit compliance.
          </p>
        </div>
      </Reveal>

      {/* ----------------------------------------------------------------- */}
      {/* Control Panel                                                      */}
      {/* ----------------------------------------------------------------- */}
      <Card>
        <CardHeader>
          <h2 className="heading-section">Evaluation Parameters</h2>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
            {/* Start */}
            <div>
              <label
                htmlFor="eval-start"
                className="block text-xs font-medium text-text-secondary mb-1"
              >
                Range Start
              </label>
              <input
                id="eval-start"
                type="number"
                min={1}
                max={10000}
                value={start}
                onChange={(e) => setStart(Number(e.target.value))}
                className={`w-full rounded border bg-surface-base px-3 py-2 text-sm text-text-primary focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-offset-surface-ground ${
                  startValid
                    ? "border-border-subtle focus:ring-fizzbuzz-500"
                    : "border-red-600 focus:ring-red-500"
                }`}
              />
              {!startValid && (
                <p className="mt-1 text-xs text-red-400">
                  Must be an integer between 1 and 10,000.
                </p>
              )}
            </div>

            {/* End */}
            <div>
              <label
                htmlFor="eval-end"
                className="block text-xs font-medium text-text-secondary mb-1"
              >
                Range End
              </label>
              <input
                id="eval-end"
                type="number"
                min={1}
                max={10000}
                value={end}
                onChange={(e) => setEnd(Number(e.target.value))}
                className={`w-full rounded border bg-surface-base px-3 py-2 text-sm text-text-primary focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-offset-surface-ground ${
                  endValid && (start < end || !startValid)
                    ? "border-border-subtle focus:ring-fizzbuzz-500"
                    : "border-red-600 focus:ring-red-500"
                }`}
              />
              {startValid && endValid && start >= end && (
                <p className="mt-1 text-xs text-red-400">
                  End must be greater than start.
                </p>
              )}
            </div>

            {/* Strategy */}
            <div>
              <label
                htmlFor="eval-strategy"
                className="block text-xs font-medium text-text-secondary mb-1"
              >
                Evaluation Strategy
              </label>
              <select
                id="eval-strategy"
                value={strategy}
                onChange={(e) => setStrategy(e.target.value as typeof strategy)}
                className="w-full rounded border border-border-subtle bg-surface-base px-3 py-2 text-sm text-text-primary focus:outline-none focus:ring-2 focus:ring-fizzbuzz-500 focus:ring-offset-2 focus:ring-offset-surface-ground"
              >
                {STRATEGIES.map((s) => (
                  <option key={s.value} value={s.value}>
                    {s.label}
                  </option>
                ))}
              </select>
              <p className="mt-1 text-xs text-text-muted">
                {STRATEGIES.find((s) => s.value === strategy)?.description}
              </p>
            </div>
          </div>
        </CardContent>
        <CardFooter>
          <Button
            onClick={handleEvaluate}
            disabled={!rangeValid || evaluating}
            size="md"
          >
            {evaluating ? "Evaluating..." : "Execute Evaluation"}
          </Button>
        </CardFooter>
      </Card>

      {/* ----------------------------------------------------------------- */}
      {/* Evaluation Progress                                                */}
      {/* ----------------------------------------------------------------- */}
      {evaluating && (
        <Card>
          <CardContent>
            <ProgressBar
              value={evalProgress}
              variant="determinate"
              label={evalStage}
              aria-label="Evaluation pipeline progress"
            />
            <p className="mt-2 text-[10px] text-text-muted">
              Initializing &rarr; Evaluating &rarr; Formatting &rarr; Complete
            </p>
          </CardContent>
        </Card>
      )}

      {/* ----------------------------------------------------------------- */}
      {/* Results Grid                                                       */}
      {/* ----------------------------------------------------------------- */}
      {session && (
        <Card>
          <CardHeader>
            <div className="flex items-center justify-between">
              <h2 className="heading-section">Evaluation Results</h2>
              <Badge variant="success">
                {session.results.length} evaluations
              </Badge>
            </div>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-5 gap-1.5 sm:grid-cols-8 md:grid-cols-10 lg:grid-cols-[repeat(15,minmax(0,1fr))]">
              {session.results.map((result, index) => (
                <div
                  key={result.number}
                  className={`flex flex-col items-center justify-center rounded border px-1 py-2 text-center transition-all duration-200 ${CELL_BG[result.classification]} ${
                    index < visibleCount
                      ? "opacity-100 scale-100"
                      : "opacity-0 scale-90"
                  }`}
                  title={`${result.number}: ${result.output} (${result.processingTimeNs.toFixed(0)}ns)`}
                >
                  <span
                    className={`text-[10px] font-mono ${LABEL_COLOR[result.classification]}`}
                  >
                    {result.output}
                  </span>
                  <span className="text-[9px] text-text-muted font-mono">
                    {result.number}
                  </span>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      {/* ----------------------------------------------------------------- */}
      {/* Metadata Panel                                                     */}
      {/* ----------------------------------------------------------------- */}
      {session && analytics && (
        <Card>
          <CardHeader>
            <h2 className="heading-section">Session Metadata</h2>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-4">
              <MetadataField
                label="Session ID"
                value={session.sessionId}
                mono
              />
              <MetadataField label="Strategy" value={session.strategy} />
              <MetadataField
                label="Total Processing Time"
                value={`${session.totalProcessingTimeMs.toFixed(6)} ms`}
                mono
              />
              <MetadataField
                label="Evaluated At"
                value={new Date(session.evaluatedAt).toLocaleString()}
              />
              <MetadataField
                label="Total Evaluations"
                value={String(analytics.total)}
              />
              <MetadataField
                label="Fizz Count"
                value={String(analytics.fizz)}
                className="text-fizz-400"
              />
              <MetadataField
                label="Buzz Count"
                value={String(analytics.buzz)}
                className="text-buzz-400"
              />
              <MetadataField
                label="FizzBuzz Count"
                value={String(analytics.fizzbuzz)}
                className="text-fizzbuzz-400"
              />
              <MetadataField
                label="Plain Number Count"
                value={String(analytics.number)}
                className="text-number-400"
              />
            </div>
          </CardContent>
        </Card>
      )}

      {/* ----------------------------------------------------------------- */}
      {/* Output Format Viewer                                               */}
      {/* ----------------------------------------------------------------- */}
      {session && (
        <Card>
          <CardHeader>
            <div className="flex items-center justify-between">
              <h2 className="heading-section">Output Format Viewer</h2>
              <div className="flex gap-1">
                {(Object.keys(FORMAT_LABELS) as OutputFormat[]).map((fmt) => (
                  <button
                    key={fmt}
                    type="button"
                    onClick={() => setOutputFormat(fmt)}
                    className={`rounded px-2.5 py-1 text-xs font-medium transition-colors ${
                      outputFormat === fmt
                        ? "bg-fizzbuzz-600 text-white"
                        : "bg-surface-overlay text-text-secondary hover:bg-surface-overlay hover:text-text-primary"
                    }`}
                  >
                    {FORMAT_LABELS[fmt]}
                  </button>
                ))}
              </div>
            </div>
          </CardHeader>
          <CardContent>
            <pre className="max-h-96 overflow-auto rounded border border-border-subtle bg-surface-base p-4 text-xs font-mono text-text-secondary leading-relaxed">
              {formattedOutput}
            </pre>
          </CardContent>
        </Card>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Metadata field helper
// ---------------------------------------------------------------------------

function MetadataField({
  label,
  value,
  mono,
  className,
}: {
  label: string;
  value: string;
  mono?: boolean;
  className?: string;
}) {
  return (
    <div>
      <p className="text-xs text-text-muted mb-0.5">{label}</p>
      <p
        className={`text-sm ${mono ? "font-mono" : ""} ${className ?? "text-text-primary"} truncate`}
        title={value}
      >
        {value}
      </p>
    </div>
  );
}
