"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { Reveal } from "@/components/ui/reveal";
import { Skeleton } from "@/components/ui/skeleton";
import type {
  Artifact,
  BayesianReconstruction,
  EvidenceUpdate,
  ForensicReport,
  Stratum,
  StratumEpoch,
} from "@/lib/data-providers";
import { useDataProvider } from "@/lib/data-providers";

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

/** Human-readable epoch labels for display. */
const EPOCH_LABELS: Record<StratumEpoch, string> = {
  pre_fizzbuzz: "Pre-FizzBuzz Era",
  early_modulo: "Early Modulo Period",
  industrial_fizzbuzz: "Industrial FizzBuzz Age",
  digital_revolution: "Digital Revolution",
  modern_enterprise: "Modern Enterprise Era",
};

/** Condition badge styling. */
const CONDITION_STYLES: Record<string, { bg: string; text: string }> = {
  pristine: { bg: "bg-emerald-950", text: "text-emerald-400" },
  good: { bg: "bg-blue-950", text: "text-blue-400" },
  fair: { bg: "bg-amber-950", text: "text-amber-400" },
  poor: { bg: "bg-orange-950", text: "text-orange-400" },
  fragmentary: { bg: "bg-red-950", text: "text-red-400" },
};

/** Severity badge styling. */
const SEVERITY_STYLES: Record<string, { bg: string; text: string }> = {
  critical: { bg: "bg-red-950", text: "text-red-400" },
  major: { bg: "bg-orange-950", text: "text-orange-400" },
  minor: { bg: "bg-amber-950", text: "text-amber-400" },
  informational: { bg: "bg-blue-950", text: "text-blue-400" },
};

/** Significance badge styling. */
const SIGNIFICANCE_STYLES: Record<string, { bg: string; text: string }> = {
  exceptional: { bg: "bg-purple-950", text: "text-purple-400" },
  high: { bg: "bg-emerald-950", text: "text-emerald-400" },
  moderate: { bg: "bg-blue-950", text: "text-blue-400" },
  low: { bg: "bg-amber-950", text: "text-amber-400" },
  indeterminate: { bg: "bg-gray-950", text: "text-gray-400" },
};

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function formatAgeBP(years: number): string {
  if (years >= 1000) return `${(years / 1000).toFixed(1)}k BP`;
  return `${years} BP`;
}

function formatRelativeTime(isoString: string): string {
  const delta = Date.now() - new Date(isoString).getTime();
  if (delta < 0) return "just now";
  if (delta < 60_000) return `${Math.floor(delta / 1000)}s ago`;
  if (delta < 3_600_000) return `${Math.floor(delta / 60_000)}m ago`;
  if (delta < 86_400_000) return `${Math.floor(delta / 3_600_000)}h ago`;
  return `${Math.floor(delta / 86_400_000)}d ago`;
}

function confidenceColor(c: number): string {
  if (c >= 0.8) return "text-emerald-400";
  if (c >= 0.6) return "text-blue-400";
  if (c >= 0.4) return "text-amber-400";
  return "text-red-400";
}

function confidenceBgColor(c: number): string {
  if (c >= 0.8) return "bg-emerald-400";
  if (c >= 0.6) return "bg-blue-400";
  if (c >= 0.4) return "bg-amber-400";
  return "bg-red-400";
}

// ---------------------------------------------------------------------------
// Panel wrapper
// ---------------------------------------------------------------------------

function Panel({
  title,
  children,
  className = "",
}: {
  title: string;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <section
      className={`rounded-lg border border-border-subtle bg-surface-base ${className}`}
    >
      <div className="border-b border-border-subtle px-4 py-3">
        <h2 className="heading-section">{title}</h2>
      </div>
      <div className="p-4">{children}</div>
    </section>
  );
}

// ---------------------------------------------------------------------------
// Stratigraphy Cross-Section Viewer (SVG)
// ---------------------------------------------------------------------------

function StratigraphyViewer({
  strata,
  selectedStratumId,
  onSelectStratum,
}: {
  strata: Stratum[];
  selectedStratumId: string | null;
  onSelectStratum: (id: string) => void;
}) {
  const svgWidth = 800;
  const svgHeight = 420;
  const marginTop = 30;
  const marginBottom = 20;
  const marginLeft = 120;
  const marginRight = 20;
  const layerHeight = (svgHeight - marginTop - marginBottom) / strata.length;

  return (
    <Panel title="Stratigraphy Cross-Section">
      <div className="overflow-x-auto">
        <svg
          viewBox={`0 0 ${svgWidth} ${svgHeight}`}
          className="w-full max-w-4xl"
          role="img"
          aria-label="Archaeological stratigraphy cross-section showing FizzBuzz geological layers"
        >
          {/* Surface line */}
          <line
            x1={marginLeft}
            y1={marginTop}
            x2={svgWidth - marginRight}
            y2={marginTop}
            stroke="#94a3b8"
            strokeWidth={2}
            strokeDasharray="6,3"
          />
          <text
            x={marginLeft - 8}
            y={marginTop + 4}
            textAnchor="end"
            fill="#94a3b8"
            fontSize={11}
          >
            Surface
          </text>

          {strata.map((stratum, i) => {
            const y = marginTop + i * layerHeight;
            const isSelected = stratum.id === selectedStratumId;

            return (
              <g
                key={stratum.id}
                className="cursor-pointer"
                onClick={() => onSelectStratum(stratum.id)}
                role="button"
                aria-label={`Select ${stratum.name}`}
              >
                {/* Stratum layer rectangle */}
                <rect
                  x={marginLeft}
                  y={y}
                  width={svgWidth - marginLeft - marginRight}
                  height={layerHeight}
                  fill={stratum.color}
                  opacity={isSelected ? 0.5 : 0.25}
                  stroke={isSelected ? "#ffffff" : stratum.color}
                  strokeWidth={isSelected ? 2 : 0.5}
                  rx={2}
                />

                {/* Artifact density indicators */}
                {Array.from({ length: stratum.artifactCount }).map((_, ai) => {
                  const ax =
                    marginLeft +
                    40 +
                    ai *
                      ((svgWidth - marginLeft - marginRight - 80) /
                        stratum.artifactCount);
                  const ay =
                    y +
                    layerHeight / 2 +
                    Math.sin(ai * 2.7) * layerHeight * 0.2;
                  return (
                    <circle
                      key={ai}
                      cx={ax}
                      cy={ay}
                      r={4}
                      fill={stratum.color}
                      opacity={0.8}
                      stroke="#ffffff"
                      strokeWidth={0.5}
                    />
                  );
                })}

                {/* Epoch label on the left */}
                <text
                  x={marginLeft - 8}
                  y={y + layerHeight / 2 + 4}
                  textAnchor="end"
                  fill={isSelected ? "#ffffff" : "#94a3b8"}
                  fontSize={10}
                  fontWeight={isSelected ? "bold" : "normal"}
                >
                  {formatAgeBP(stratum.ageBP)}
                </text>

                {/* Stratum name inside layer */}
                <text
                  x={marginLeft + 12}
                  y={y + layerHeight / 2 + 4}
                  fill="#e2e8f0"
                  fontSize={11}
                  fontWeight={isSelected ? "bold" : "normal"}
                >
                  {stratum.name}
                </text>

                {/* Artifact count badge */}
                <text
                  x={svgWidth - marginRight - 12}
                  y={y + layerHeight / 2 + 4}
                  textAnchor="end"
                  fill="#94a3b8"
                  fontSize={10}
                >
                  {stratum.artifactCount} artifact
                  {stratum.artifactCount !== 1 ? "s" : ""}
                </text>
              </g>
            );
          })}

          {/* Depth axis label */}
          <text
            x={12}
            y={svgHeight / 2}
            transform={`rotate(-90, 12, ${svgHeight / 2})`}
            fill="#64748b"
            fontSize={11}
            textAnchor="middle"
          >
            Depth (increasing)
          </text>
        </svg>
      </div>

      {/* Selected stratum detail */}
      {selectedStratumId &&
        (() => {
          const s = strata.find((st) => st.id === selectedStratumId);
          if (!s) return null;
          return (
            <div className="mt-4 rounded border border-border-subtle bg-surface-raised p-3 text-sm">
              <div className="flex items-center gap-3 mb-2">
                <span
                  className="inline-block h-3 w-3 rounded-full"
                  style={{ backgroundColor: s.color }}
                />
                <span className="font-semibold text-text-primary">
                  {s.name}
                </span>
                <span className="text-xs text-text-secondary">
                  {EPOCH_LABELS[s.epoch]}
                </span>
              </div>
              <p className="text-text-secondary text-xs leading-relaxed">
                {s.description}
              </p>
              <div className="mt-2 grid grid-cols-3 gap-4 text-xs">
                <div>
                  <span className="text-text-muted">Composition:</span>{" "}
                  <span className="text-text-secondary">{s.composition}</span>
                </div>
                <div>
                  <span className="text-text-muted">Age:</span>{" "}
                  <span className="text-text-secondary">
                    {formatAgeBP(s.ageBP)}
                  </span>
                </div>
                <div>
                  <span className="text-text-muted">Artifacts:</span>{" "}
                  <span className="text-text-secondary">{s.artifactCount}</span>
                </div>
              </div>
            </div>
          );
        })()}
    </Panel>
  );
}

// ---------------------------------------------------------------------------
// Artifact Catalog
// ---------------------------------------------------------------------------

function ArtifactCatalog({
  artifacts,
  selectedIds,
  onToggleSelect,
  onRunReconstruction,
  reconstructionLoading,
}: {
  artifacts: Artifact[];
  selectedIds: Set<string>;
  onToggleSelect: (id: string) => void;
  onRunReconstruction: (id: string) => void;
  reconstructionLoading: string | null;
}) {
  return (
    <Panel title={`Artifact Catalog (${artifacts.length} recovered)`}>
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {artifacts.map((artifact) => {
          const cStyle =
            CONDITION_STYLES[artifact.condition] ?? CONDITION_STYLES.fair;
          const isSelected = selectedIds.has(artifact.id);
          return (
            <div
              key={artifact.id}
              className={`rounded border p-3 transition-colors ${isSelected ? "border-fizzbuzz-400 bg-surface-raised" : "border-border-subtle bg-surface-raised/50 hover:border-border-default"}`}
            >
              <div className="flex items-start justify-between gap-2">
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    <input
                      type="checkbox"
                      checked={isSelected}
                      onChange={() => onToggleSelect(artifact.id)}
                      className="h-3.5 w-3.5 rounded border-border-default bg-surface-raised text-fizzbuzz-400"
                      aria-label={`Select ${artifact.name}`}
                    />
                    <h3 className="text-xs font-semibold text-text-primary truncate">
                      {artifact.name}
                    </h3>
                  </div>
                  <p className="mt-0.5 text-xs text-text-muted">
                    {artifact.id}
                  </p>
                </div>
                <div className="flex flex-col items-end gap-1">
                  <span
                    className={`inline-flex items-center rounded px-1.5 py-0.5 text-xs font-medium ${cStyle.bg} ${cStyle.text}`}
                  >
                    {artifact.condition}
                  </span>
                </div>
              </div>

              {/* Confidence bar */}
              <div className="mt-2">
                <div className="flex items-center justify-between text-xs">
                  <span className="text-text-muted">Confidence</span>
                  <span className={confidenceColor(artifact.confidence)}>
                    {(artifact.confidence * 100).toFixed(0)}%
                  </span>
                </div>
                <div className="mt-0.5 h-1.5 w-full rounded-full bg-surface-overlay">
                  <div
                    className={`h-full rounded-full ${confidenceBgColor(artifact.confidence)}`}
                    style={{ width: `${artifact.confidence * 100}%` }}
                  />
                </div>
              </div>

              <p className="mt-2 text-xs text-text-secondary line-clamp-2">
                {artifact.description}
              </p>

              <div className="mt-2 flex items-center justify-between text-xs text-text-muted">
                <span>{artifact.type.replace(/_/g, " ")}</span>
                <span>{formatAgeBP(artifact.estimatedAgeBP)}</span>
              </div>

              <button
                onClick={() => onRunReconstruction(artifact.id)}
                disabled={reconstructionLoading === artifact.id}
                className="mt-2 w-full rounded border border-border-default bg-surface-overlay px-2 py-1 text-xs text-text-secondary hover:bg-surface-overlay hover:text-text-primary transition-colors disabled:opacity-50"
              >
                {reconstructionLoading === artifact.id
                  ? "Reconstructing..."
                  : "Run Bayesian Reconstruction"}
              </button>
            </div>
          );
        })}
      </div>
    </Panel>
  );
}

// ---------------------------------------------------------------------------
// Bayesian Reconstruction Panel
// ---------------------------------------------------------------------------

function BayesianReconstructionPanel({
  reconstruction,
}: {
  reconstruction: BayesianReconstruction;
}) {
  const artifact = reconstruction.artifactId;
  return (
    <Panel title={`Bayesian Reconstruction: ${artifact}`}>
      {/* Evidence chain visualization */}
      <div className="mb-4">
        <h3 className="heading-section">Evidence Chain</h3>
        <div className="space-y-2">
          {reconstruction.evidenceChain.map((update, i) => (
            <EvidenceChainStep
              key={i}
              update={update}
              stepNumber={i + 1}
              isLast={i === reconstruction.evidenceChain.length - 1}
            />
          ))}
        </div>
      </div>

      {/* Reconstructed parameters */}
      <div className="mb-4">
        <h3 className="heading-section">Reconstructed Parameters</h3>
        <div className="grid grid-cols-2 gap-2">
          {Object.entries(reconstruction.reconstructedParameters).map(
            ([key, value]) => (
              <div
                key={key}
                className="rounded border border-border-subtle bg-surface-raised px-3 py-2"
              >
                <div className="text-xs text-text-muted">{key}</div>
                <div className="text-sm text-text-primary">{value}</div>
              </div>
            ),
          )}
        </div>
      </div>

      {/* Conclusion */}
      <div className="rounded border border-border-subtle bg-surface-raised p-3">
        <h3 className="heading-section">Conclusion</h3>
        <p className="text-xs text-text-secondary leading-relaxed">
          {reconstruction.conclusion}
        </p>
        <div className="mt-2 flex items-center gap-2">
          <span className="text-xs text-text-muted">Final Posterior:</span>
          <span
            className={`text-sm font-semibold ${confidenceColor(reconstruction.finalPosterior)}`}
          >
            {(reconstruction.finalPosterior * 100).toFixed(1)}%
          </span>
        </div>
      </div>
    </Panel>
  );
}

function EvidenceChainStep({
  update,
  stepNumber,
  isLast,
}: {
  update: EvidenceUpdate;
  stepNumber: number;
  isLast: boolean;
}) {
  return (
    <div className="flex gap-3">
      {/* Connector line */}
      <div className="flex flex-col items-center">
        <div
          className={`flex h-6 w-6 items-center justify-center rounded-full border text-xs font-medium ${confidenceColor(update.posteriorProbability)} border-border-default`}
        >
          {stepNumber}
        </div>
        {!isLast && <div className="h-full w-px bg-surface-overlay" />}
      </div>

      {/* Content */}
      <div className="flex-1 pb-3">
        <div className="flex items-center justify-between">
          <span className="text-xs font-semibold text-text-primary">
            {update.source}
          </span>
          <span className="text-xs text-text-muted">
            LR: {update.likelihoodRatio.toFixed(2)}
          </span>
        </div>
        <p className="mt-0.5 text-xs text-text-secondary">
          {update.description}
        </p>
        <div className="mt-1 flex items-center gap-4 text-xs">
          <span className="text-text-muted">
            Prior:{" "}
            <span className="text-text-secondary">
              {(update.priorProbability * 100).toFixed(1)}%
            </span>
          </span>
          <span className="text-text-muted">&rarr;</span>
          <span className="text-text-muted">
            Posterior:{" "}
            <span className={confidenceColor(update.posteriorProbability)}>
              {(update.posteriorProbability * 100).toFixed(1)}%
            </span>
          </span>
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Forensic Report Display
// ---------------------------------------------------------------------------

function ForensicReportDisplay({ report }: { report: ForensicReport }) {
  const sigStyle =
    SIGNIFICANCE_STYLES[report.significanceRating] ??
    SIGNIFICANCE_STYLES.moderate;

  return (
    <Panel title={`Forensic Report ${report.id}`}>
      {/* Header */}
      <div className="mb-4 flex items-center justify-between">
        <div>
          <span className="text-xs text-text-muted">Generated: </span>
          <span className="text-xs text-text-secondary">
            {new Date(report.generatedAt).toLocaleString()}
          </span>
        </div>
        <span
          className={`inline-flex items-center rounded px-2 py-0.5 text-xs font-medium ${sigStyle.bg} ${sigStyle.text}`}
        >
          {report.significanceRating} significance
        </span>
      </div>

      {/* Summary */}
      <div className="mb-4 rounded border border-border-subtle bg-surface-raised p-3">
        <h3 className="heading-section">Executive Summary</h3>
        <p className="text-xs text-text-secondary leading-relaxed">
          {report.summary}
        </p>
      </div>

      {/* Findings */}
      <div className="mb-4">
        <h3 className="heading-section">Findings ({report.findings.length})</h3>
        <div className="space-y-2">
          {report.findings.map((finding, i) => {
            const sevStyle =
              SEVERITY_STYLES[finding.severity] ??
              SEVERITY_STYLES.informational;
            return (
              <div
                key={i}
                className="rounded border border-border-subtle bg-surface-raised p-3"
              >
                <div className="flex items-center gap-2 mb-1">
                  <span
                    className={`inline-flex items-center rounded px-1.5 py-0.5 text-xs font-medium ${sevStyle.bg} ${sevStyle.text}`}
                  >
                    {finding.severity}
                  </span>
                  <span className="text-xs font-semibold text-text-primary">
                    {finding.title}
                  </span>
                  <span className="ml-auto text-xs text-text-muted">
                    {finding.category}
                  </span>
                </div>
                <p className="text-xs text-text-secondary leading-relaxed">
                  {finding.description}
                </p>
                <div className="mt-1 flex items-center gap-1 text-xs text-text-muted">
                  <span>Confidence:</span>
                  <span className={confidenceColor(finding.confidence)}>
                    {(finding.confidence * 100).toFixed(0)}%
                  </span>
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* Recommendations */}
      <div>
        <h3 className="heading-section">Recommendations</h3>
        <ul className="space-y-1">
          {report.recommendations.map((rec, i) => (
            <li key={i} className="flex gap-2 text-xs text-text-secondary">
              <span className="text-text-muted shrink-0">{i + 1}.</span>
              {rec}
            </li>
          ))}
        </ul>
      </div>
    </Panel>
  );
}

// ---------------------------------------------------------------------------
// Recovery Timeline
// ---------------------------------------------------------------------------

function RecoveryTimeline({ artifacts }: { artifacts: Artifact[] }) {
  const sorted = useMemo(
    () =>
      [...artifacts].sort(
        (a, b) =>
          new Date(b.recoveredAt).getTime() - new Date(a.recoveredAt).getTime(),
      ),
    [artifacts],
  );

  return (
    <Panel title="Recovery Timeline">
      <div className="space-y-2">
        {sorted.map((artifact, i) => {
          const cStyle =
            CONDITION_STYLES[artifact.condition] ?? CONDITION_STYLES.fair;
          return (
            <div key={artifact.id} className="flex gap-3">
              <div className="flex flex-col items-center">
                <div
                  className={`h-2.5 w-2.5 rounded-full ${confidenceBgColor(artifact.confidence)}`}
                />
                {i < sorted.length - 1 && (
                  <div className="h-full w-px bg-surface-overlay" />
                )}
              </div>
              <div className="flex-1 pb-3">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-semibold text-text-primary">
                    {artifact.name}
                  </span>
                  <span className="text-xs text-text-muted">
                    {formatRelativeTime(artifact.recoveredAt)}
                  </span>
                </div>
                <div className="mt-0.5 flex items-center gap-2 text-xs text-text-secondary">
                  <span>{artifact.id}</span>
                  <span className={`${cStyle.text}`}>{artifact.condition}</span>
                  <span className={confidenceColor(artifact.confidence)}>
                    {(artifact.confidence * 100).toFixed(0)}%
                  </span>
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </Panel>
  );
}

// ---------------------------------------------------------------------------
// Main Page Component
// ---------------------------------------------------------------------------

export default function ArchaeologyPage() {
  const provider = useDataProvider();

  const [strata, setStrata] = useState<Stratum[]>([]);
  const [artifacts, setArtifacts] = useState<Artifact[]>([]);
  const [selectedStratumId, setSelectedStratumId] = useState<string | null>(
    null,
  );
  const [selectedArtifactIds, setSelectedArtifactIds] = useState<Set<string>>(
    new Set(),
  );
  const [reconstruction, setReconstruction] =
    useState<BayesianReconstruction | null>(null);
  const [reconstructionLoading, setReconstructionLoading] = useState<
    string | null
  >(null);
  const [forensicReport, setForensicReport] = useState<ForensicReport | null>(
    null,
  );
  const [reportLoading, setReportLoading] = useState(false);
  const [loading, setLoading] = useState(true);

  // Initial data load
  useEffect(() => {
    let cancelled = false;
    async function load() {
      const [strataData, artifactData] = await Promise.all([
        provider.getStrata(),
        provider.getArtifacts(),
      ]);
      if (!cancelled) {
        setStrata(strataData);
        setArtifacts(artifactData);
        setLoading(false);
      }
    }
    load();
    return () => {
      cancelled = true;
    };
  }, [provider]);

  // Filter artifacts by selected stratum
  const filteredArtifacts = useMemo(() => {
    if (!selectedStratumId) return artifacts;
    return artifacts.filter((a) => a.stratumId === selectedStratumId);
  }, [artifacts, selectedStratumId]);

  const handleStratumSelect = useCallback((id: string) => {
    setSelectedStratumId((prev) => (prev === id ? null : id));
  }, []);

  const handleToggleArtifact = useCallback((id: string) => {
    setSelectedArtifactIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }, []);

  const handleRunReconstruction = useCallback(
    async (artifactId: string) => {
      setReconstructionLoading(artifactId);
      try {
        const result = await provider.runBayesianReconstruction(artifactId);
        setReconstruction(result);
      } finally {
        setReconstructionLoading(null);
      }
    },
    [provider],
  );

  const handleGenerateReport = useCallback(async () => {
    if (selectedArtifactIds.size === 0) return;
    setReportLoading(true);
    try {
      const result = await provider.generateForensicReport(
        Array.from(selectedArtifactIds),
      );
      setForensicReport(result);
    } finally {
      setReportLoading(false);
    }
  }, [provider, selectedArtifactIds]);

  if (loading) {
    return (
      <div className="flex h-64 items-center justify-center">
        <div className="text-sm text-text-secondary">
          Initializing archaeological recovery subsystem...
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Page header */}
      <Reveal>
        <div>
          <h1 className="heading-page">Archaeological Recovery Console</h1>
          <p className="mt-1 text-sm text-text-secondary">
            Systematic excavation and forensic analysis of the FizzBuzz
            geological record. Artifacts are cataloged per ICFA standards with
            Bayesian reconstruction for provenance verification.
          </p>
        </div>
      </Reveal>

      {/* Summary stats */}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-5">
        <div className="rounded-lg border border-border-subtle bg-surface-base px-4 py-3">
          <div className="text-xs text-text-muted">Strata Identified</div>
          <div className="mt-1 text-lg font-bold text-text-primary">
            {strata.length}
          </div>
        </div>
        <div className="rounded-lg border border-border-subtle bg-surface-base px-4 py-3">
          <div className="text-xs text-text-muted">Artifacts Recovered</div>
          <div className="mt-1 text-lg font-bold text-text-primary">
            {artifacts.length}
          </div>
        </div>
        <div className="rounded-lg border border-border-subtle bg-surface-base px-4 py-3">
          <div className="text-xs text-text-muted">Mean Confidence</div>
          <div
            className={`mt-1 text-lg font-bold ${confidenceColor(artifacts.reduce((s, a) => s + a.confidence, 0) / artifacts.length)}`}
          >
            {(
              (artifacts.reduce((s, a) => s + a.confidence, 0) /
                artifacts.length) *
              100
            ).toFixed(1)}
            %
          </div>
        </div>
        <div className="rounded-lg border border-border-subtle bg-surface-base px-4 py-3">
          <div className="text-xs text-text-muted">Oldest Artifact</div>
          <div className="mt-1 text-lg font-bold text-text-primary">
            {formatAgeBP(Math.max(...artifacts.map((a) => a.estimatedAgeBP)))}
          </div>
        </div>
        <div className="rounded-lg border border-border-subtle bg-surface-base px-4 py-3">
          <div className="text-xs text-text-muted">Epochs Covered</div>
          <div className="mt-1 text-lg font-bold text-text-primary">
            {new Set(strata.map((s) => s.epoch)).size}
          </div>
        </div>
      </div>

      {/* Stratigraphy cross-section */}
      <StratigraphyViewer
        strata={strata}
        selectedStratumId={selectedStratumId}
        onSelectStratum={handleStratumSelect}
      />

      {/* Artifact catalog + Report button */}
      <div>
        {selectedArtifactIds.size > 0 && (
          <div className="mb-3 flex items-center justify-between rounded border border-border-subtle bg-surface-raised px-4 py-2">
            <span className="text-xs text-text-secondary">
              {selectedArtifactIds.size} artifact
              {selectedArtifactIds.size !== 1 ? "s" : ""} selected for forensic
              analysis
            </span>
            <button
              onClick={handleGenerateReport}
              disabled={reportLoading}
              className="rounded bg-fizzbuzz-600 px-3 py-1 text-xs font-medium text-white hover:bg-fizzbuzz-500 transition-colors disabled:opacity-50"
            >
              {reportLoading
                ? "Generating Report..."
                : "Generate Forensic Report"}
            </button>
          </div>
        )}
        <ArtifactCatalog
          artifacts={filteredArtifacts}
          selectedIds={selectedArtifactIds}
          onToggleSelect={handleToggleArtifact}
          onRunReconstruction={handleRunReconstruction}
          reconstructionLoading={reconstructionLoading}
        />
      </div>

      {/* Bayesian reconstruction panel */}
      {reconstruction && (
        <BayesianReconstructionPanel reconstruction={reconstruction} />
      )}

      {/* Forensic report */}
      {forensicReport && <ForensicReportDisplay report={forensicReport} />}

      {/* Recovery timeline */}
      <RecoveryTimeline artifacts={artifacts} />
    </div>
  );
}
