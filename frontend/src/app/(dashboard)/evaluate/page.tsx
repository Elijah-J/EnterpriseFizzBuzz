"use client";

import { useCallback, useMemo, useState } from "react";
import { Card, CardContent, CardFooter, CardHeader } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { useDataProvider } from "@/lib/data-providers";
import type { EvaluationSession, FizzBuzzResult } from "@/lib/data-providers";
import { formatPlain, formatJSON, formatXML, formatCSV } from "@/lib/formatters";

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

    try {
      const result = await provider.evaluate({ start, end, strategy });
      setSession(result);

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
      <div>
        <h1 className="text-2xl font-bold tracking-tight text-panel-50">
          FizzBuzz Evaluation Console
        </h1>
        <p className="mt-1 text-sm text-panel-400">
          Execute and inspect FizzBuzz evaluations across configurable ranges
          and strategies. All sessions are recorded for audit compliance.
        </p>
      </div>

      {/* ----------------------------------------------------------------- */}
      {/* Control Panel                                                      */}
      {/* ----------------------------------------------------------------- */}
      <Card>
        <CardHeader>
          <h2 className="text-sm font-semibold text-panel-100">
            Evaluation Parameters
          </h2>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
            {/* Start */}
            <div>
              <label
                htmlFor="eval-start"
                className="block text-xs font-medium text-panel-400 mb-1"
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
                className={`w-full rounded border bg-panel-900 px-3 py-2 text-sm text-panel-50 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-offset-panel-950 ${
                  startValid
                    ? "border-panel-700 focus:ring-fizzbuzz-500"
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
                className="block text-xs font-medium text-panel-400 mb-1"
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
                className={`w-full rounded border bg-panel-900 px-3 py-2 text-sm text-panel-50 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-offset-panel-950 ${
                  endValid && (start < end || !startValid)
                    ? "border-panel-700 focus:ring-fizzbuzz-500"
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
                className="block text-xs font-medium text-panel-400 mb-1"
              >
                Evaluation Strategy
              </label>
              <select
                id="eval-strategy"
                value={strategy}
                onChange={(e) => setStrategy(e.target.value as typeof strategy)}
                className="w-full rounded border border-panel-700 bg-panel-900 px-3 py-2 text-sm text-panel-50 focus:outline-none focus:ring-2 focus:ring-fizzbuzz-500 focus:ring-offset-2 focus:ring-offset-panel-950"
              >
                {STRATEGIES.map((s) => (
                  <option key={s.value} value={s.value}>
                    {s.label}
                  </option>
                ))}
              </select>
              <p className="mt-1 text-xs text-panel-500">
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
      {/* Results Grid                                                       */}
      {/* ----------------------------------------------------------------- */}
      {session && (
        <Card>
          <CardHeader>
            <div className="flex items-center justify-between">
              <h2 className="text-sm font-semibold text-panel-100">
                Evaluation Results
              </h2>
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
                  <span className={`text-[10px] font-mono ${LABEL_COLOR[result.classification]}`}>
                    {result.output}
                  </span>
                  <span className="text-[9px] text-panel-500 font-mono">
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
            <h2 className="text-sm font-semibold text-panel-100">
              Session Metadata
            </h2>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-4">
              <MetadataField label="Session ID" value={session.sessionId} mono />
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
              <h2 className="text-sm font-semibold text-panel-100">
                Output Format Viewer
              </h2>
              <div className="flex gap-1">
                {(Object.keys(FORMAT_LABELS) as OutputFormat[]).map((fmt) => (
                  <button
                    key={fmt}
                    type="button"
                    onClick={() => setOutputFormat(fmt)}
                    className={`rounded px-2.5 py-1 text-xs font-medium transition-colors ${
                      outputFormat === fmt
                        ? "bg-fizzbuzz-600 text-white"
                        : "bg-panel-700 text-panel-300 hover:bg-panel-600 hover:text-panel-100"
                    }`}
                  >
                    {FORMAT_LABELS[fmt]}
                  </button>
                ))}
              </div>
            </div>
          </CardHeader>
          <CardContent>
            <pre className="max-h-96 overflow-auto rounded border border-panel-700 bg-panel-900 p-4 text-xs font-mono text-panel-300 leading-relaxed">
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
      <p className="text-xs text-panel-500 mb-0.5">{label}</p>
      <p
        className={`text-sm ${mono ? "font-mono" : ""} ${className ?? "text-panel-100"} truncate`}
        title={value}
      >
        {value}
      </p>
    </div>
  );
}
