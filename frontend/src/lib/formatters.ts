import type { FizzBuzzResult } from "./data-providers/types";

/**
 * Output format renderers for FizzBuzz evaluation results.
 *
 * Each formatter produces a string representation of the evaluation
 * result set in the specified wire format. These formatters support
 * the Output Format Viewer panel in the Evaluation Console, enabling
 * operators to preview data in the format required by downstream
 * consumers before export.
 */

/** Plain text — one result per line, number and output separated by a colon. */
export function formatPlain(results: FizzBuzzResult[]): string {
  return results.map((r) => `${r.number}: ${r.output}`).join("\n");
}

/** JSON — array of evaluation result objects with full metadata. */
export function formatJSON(results: FizzBuzzResult[]): string {
  const payload = results.map((r) => ({
    number: r.number,
    output: r.output,
    classification: r.classification,
    matchedRules: r.matchedRules,
    processingTimeNs: r.processingTimeNs,
  }));
  return JSON.stringify(payload, null, 2);
}

/** XML — structured document with evaluation elements and rule sub-elements. */
export function formatXML(results: FizzBuzzResult[]): string {
  const lines: string[] = [
    '<?xml version="1.0" encoding="UTF-8"?>',
    "<EvaluationResults>",
  ];

  for (const r of results) {
    lines.push(`  <Result number="${r.number}" classification="${r.classification}">`);
    lines.push(`    <Output>${escapeXml(r.output)}</Output>`);
    lines.push(`    <ProcessingTimeNs>${r.processingTimeNs.toFixed(0)}</ProcessingTimeNs>`);
    if (r.matchedRules.length > 0) {
      lines.push("    <MatchedRules>");
      for (const rule of r.matchedRules) {
        lines.push(
          `      <Rule divisor="${rule.divisor}" label="${escapeXml(rule.label)}" priority="${rule.priority}" />`,
        );
      }
      lines.push("    </MatchedRules>");
    }
    lines.push("  </Result>");
  }

  lines.push("</EvaluationResults>");
  return lines.join("\n");
}

/** CSV — comma-separated values with header row. */
export function formatCSV(results: FizzBuzzResult[]): string {
  const header = "number,output,classification,matchedRules,processingTimeNs";
  const rows = results.map((r) => {
    const rules = r.matchedRules
      .map((rule) => `${rule.label}(/${rule.divisor})`)
      .join(";");
    return `${r.number},${csvEscape(r.output)},${r.classification},${csvEscape(rules)},${r.processingTimeNs.toFixed(0)}`;
  });
  return [header, ...rows].join("\n");
}

function escapeXml(s: string): string {
  return s
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function csvEscape(s: string): string {
  if (s.includes(",") || s.includes('"') || s.includes("\n")) {
    return `"${s.replace(/"/g, '""')}"`;
  }
  return s;
}
