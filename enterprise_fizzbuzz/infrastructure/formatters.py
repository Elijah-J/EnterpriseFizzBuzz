"""
Enterprise FizzBuzz Platform - Output Formatters Module

Provides pluggable output formatting in Plain Text, JSON, XML,
and CSV formats for maximum interoperability with downstream systems.
"""

from __future__ import annotations

import json
import logging
from typing import Optional

from enterprise_fizzbuzz.domain.interfaces import IFormatter
from enterprise_fizzbuzz.domain.models import FizzBuzzResult, FizzBuzzSessionSummary, OutputFormat

logger = logging.getLogger(__name__)


class PlainTextFormatter(IFormatter):
    """Formats FizzBuzz results as plain text.

    The simplest formatter, producing human-readable output.
    """

    def format_result(self, result: FizzBuzzResult) -> str:
        return result.output

    def format_results(self, results: list[FizzBuzzResult]) -> str:
        return "\n".join(self.format_result(r) for r in results)

    def format_summary(self, summary: FizzBuzzSessionSummary) -> str:
        lines = [
            "",
            "=" * 50,
            "  FizzBuzz Session Summary",
            "=" * 50,
            f"  Session ID:    {summary.session_id[:8]}...",
            f"  Total Numbers: {summary.total_numbers}",
            f"  Fizz:          {summary.fizz_count}",
            f"  Buzz:          {summary.buzz_count}",
            f"  FizzBuzz:      {summary.fizzbuzz_count}",
            f"  Plain:         {summary.plain_count}",
            f"  Processing:    {summary.total_processing_time_ms:.2f}ms",
            f"  Throughput:    {summary.numbers_per_second:.0f} numbers/sec",
            "=" * 50,
        ]
        if summary.errors:
            lines.append(f"  Errors: {len(summary.errors)}")
            for err in summary.errors:
                lines.append(f"    - {err}")
            lines.append("=" * 50)
        return "\n".join(lines)

    def get_format_type(self) -> OutputFormat:
        return OutputFormat.PLAIN


class JsonFormatter(IFormatter):
    """Formats FizzBuzz results as JSON.

    Produces structured JSON output suitable for API responses
    and integration with modern web architectures.
    """

    def __init__(self, indent: int = 2, include_metadata: bool = False) -> None:
        self._indent = indent
        self._include_metadata = include_metadata

    def format_result(self, result: FizzBuzzResult) -> str:
        data: dict = {
            "number": result.number,
            "output": result.output,
            "result_id": result.result_id,
            "matched_rules": [
                {
                    "name": m.rule.name,
                    "divisor": m.rule.divisor,
                    "label": m.rule.label,
                }
                for m in result.matched_rules
            ],
        }
        if self._include_metadata:
            data["metadata"] = result.metadata
            data["processing_time_ns"] = result.processing_time_ns
        return json.dumps(data, indent=self._indent)

    def format_results(self, results: list[FizzBuzzResult]) -> str:
        data = {
            "results": [json.loads(self.format_result(r)) for r in results],
            "count": len(results),
        }
        return json.dumps(data, indent=self._indent)

    def format_summary(self, summary: FizzBuzzSessionSummary) -> str:
        data = {
            "session_id": summary.session_id,
            "total_numbers": summary.total_numbers,
            "fizz_count": summary.fizz_count,
            "buzz_count": summary.buzz_count,
            "fizzbuzz_count": summary.fizzbuzz_count,
            "plain_count": summary.plain_count,
            "processing_time_ms": summary.total_processing_time_ms,
            "numbers_per_second": summary.numbers_per_second,
            "errors": summary.errors,
        }
        return json.dumps(data, indent=self._indent)

    def get_format_type(self) -> OutputFormat:
        return OutputFormat.JSON


class XmlFormatter(IFormatter):
    """Formats FizzBuzz results as XML.

    For those enterprise environments that still require XML
    interoperability with legacy SOAP services circa 2003.
    """

    def format_result(self, result: FizzBuzzResult) -> str:
        rules_xml = ""
        for m in result.matched_rules:
            rules_xml += (
                f"    <rule name=\"{m.rule.name}\" "
                f"divisor=\"{m.rule.divisor}\" "
                f"label=\"{m.rule.label}\" />\n"
            )
        return (
            f"<result id=\"{result.result_id}\">\n"
            f"  <number>{result.number}</number>\n"
            f"  <output>{result.output}</output>\n"
            f"  <matchedRules>\n{rules_xml}  </matchedRules>\n"
            f"</result>"
        )

    def format_results(self, results: list[FizzBuzzResult]) -> str:
        inner = "\n".join(f"  {self.format_result(r)}" for r in results)
        return (
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            f"<fizzBuzzResults count=\"{len(results)}\">\n"
            f"{inner}\n"
            f"</fizzBuzzResults>"
        )

    def format_summary(self, summary: FizzBuzzSessionSummary) -> str:
        return (
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            "<sessionSummary>\n"
            f"  <sessionId>{summary.session_id}</sessionId>\n"
            f"  <totalNumbers>{summary.total_numbers}</totalNumbers>\n"
            f"  <fizzCount>{summary.fizz_count}</fizzCount>\n"
            f"  <buzzCount>{summary.buzz_count}</buzzCount>\n"
            f"  <fizzBuzzCount>{summary.fizzbuzz_count}</fizzBuzzCount>\n"
            f"  <plainCount>{summary.plain_count}</plainCount>\n"
            f"  <processingTimeMs>{summary.total_processing_time_ms:.2f}"
            f"</processingTimeMs>\n"
            f"  <numbersPerSecond>{summary.numbers_per_second:.0f}"
            f"</numbersPerSecond>\n"
            "</sessionSummary>"
        )

    def get_format_type(self) -> OutputFormat:
        return OutputFormat.XML


class CsvFormatter(IFormatter):
    """Formats FizzBuzz results as CSV.

    For importing into enterprise spreadsheet solutions and
    business intelligence dashboards.
    """

    def format_result(self, result: FizzBuzzResult) -> str:
        rules = "|".join(m.rule.name for m in result.matched_rules) or "none"
        return f"{result.number},{result.output},{rules},{result.result_id}"

    def format_results(self, results: list[FizzBuzzResult]) -> str:
        header = "number,output,matched_rules,result_id"
        rows = [self.format_result(r) for r in results]
        return "\n".join([header] + rows)

    def format_summary(self, summary: FizzBuzzSessionSummary) -> str:
        return (
            "metric,value\n"
            f"session_id,{summary.session_id}\n"
            f"total_numbers,{summary.total_numbers}\n"
            f"fizz_count,{summary.fizz_count}\n"
            f"buzz_count,{summary.buzz_count}\n"
            f"fizzbuzz_count,{summary.fizzbuzz_count}\n"
            f"plain_count,{summary.plain_count}\n"
            f"processing_time_ms,{summary.total_processing_time_ms:.2f}\n"
            f"numbers_per_second,{summary.numbers_per_second:.0f}"
        )

    def get_format_type(self) -> OutputFormat:
        return OutputFormat.CSV


class FormatterFactory:
    """Factory for creating the appropriate formatter based on output format."""

    _formatters: dict[OutputFormat, type[IFormatter]] = {
        OutputFormat.PLAIN: PlainTextFormatter,
        OutputFormat.JSON: JsonFormatter,
        OutputFormat.XML: XmlFormatter,
        OutputFormat.CSV: CsvFormatter,
    }

    @classmethod
    def create(
        cls, format_type: OutputFormat, **kwargs: object
    ) -> IFormatter:
        formatter_class = cls._formatters.get(format_type, PlainTextFormatter)
        return formatter_class(**kwargs) if kwargs else formatter_class()
