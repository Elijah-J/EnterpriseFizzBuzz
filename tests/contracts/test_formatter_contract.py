"""
Enterprise FizzBuzz Platform - Formatter Contract Tests

Defines the behavioral contract for all IFormatter implementations.
Whether you're rendering FizzBuzz results as plain text, JSON, XML,
or CSV, the contract insists on the same fundamental guarantees:
format_result returns a string, format_results returns a string,
format_summary returns a string, and get_format_type returns an
OutputFormat. Revolutionary stuff.

The FormatterContractTests mixin ensures that swapping formatters
is a safe operation — because if your JSON formatter suddenly starts
emitting YAML, the downstream SOAP service from 2003 will be very upset.
"""

from __future__ import annotations

import sys
from abc import abstractmethod
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from enterprise_fizzbuzz.domain.interfaces import IFormatter
from enterprise_fizzbuzz.domain.models import (
    FizzBuzzResult,
    FizzBuzzSessionSummary,
    OutputFormat,
    RuleDefinition,
    RuleMatch,
)


def _make_result(number: int, output: str, label: str | None = None) -> FizzBuzzResult:
    """Construct a FizzBuzzResult for formatter testing.

    Produces results with enough fidelity to exercise serialization logic
    without requiring an actual evaluation pipeline. Because formatters
    should not need a running neural network to render the word 'Fizz'.
    """
    matched_rules = []
    if label is not None:
        divisor = {"Fizz": 3, "Buzz": 5}.get(label, 1)
        rule = RuleDefinition(name=f"{label}Rule", divisor=divisor, label=label, priority=1)
        matched_rules.append(RuleMatch(rule=rule, number=number))
    return FizzBuzzResult(
        number=number,
        output=output,
        matched_rules=matched_rules,
        processing_time_ns=42000,
        result_id=f"fmt-{number:04d}",
        metadata={"formatter_test": True},
    )


def _make_summary() -> FizzBuzzSessionSummary:
    """Produce a session summary for formatter contract verification.

    The numbers are entirely fictional but statistically plausible
    for a FizzBuzz session, which is more than can be said for most
    enterprise KPI dashboards.
    """
    return FizzBuzzSessionSummary(
        session_id="contract-summary-session",
        total_numbers=15,
        fizz_count=4,
        buzz_count=2,
        fizzbuzz_count=1,
        plain_count=8,
        total_processing_time_ms=3.14,
    )


class FormatterContractTests:
    """Mixin defining the behavioral contract for IFormatter.

    Every formatter — whether it produces angle brackets, curly braces,
    commas, or plain English — must satisfy these tests. The contract
    is intentionally minimal: we verify types and non-emptiness, not
    specific serialization details, because those are the formatter's
    creative prerogative.

    Subclasses must implement create_formatter() and expected_format_type().
    """

    @abstractmethod
    def create_formatter(self) -> IFormatter:
        """Provide a fresh formatter instance for testing."""
        ...

    @abstractmethod
    def expected_format_type(self) -> OutputFormat:
        """Return the OutputFormat this formatter should declare."""
        ...

    def test_is_iformatter(self) -> None:
        """The implementation must actually implement IFormatter."""
        fmt = self.create_formatter()
        assert isinstance(fmt, IFormatter), (
            f"{type(fmt).__name__} does not implement IFormatter. "
            f"A formatter that doesn't implement the formatter interface "
            f"is just a function with delusions of grandeur."
        )

    def test_format_result_returns_string(self) -> None:
        """format_result must return a string, because bytes would be uncivilized."""
        fmt = self.create_formatter()
        result = _make_result(3, "Fizz", label="Fizz")
        output = fmt.format_result(result)
        assert isinstance(output, str)
        assert len(output) > 0, "format_result returned an empty string. Silence is not a format."

    def test_format_result_contains_output(self) -> None:
        """The formatted string should contain the result's output value."""
        fmt = self.create_formatter()
        result = _make_result(3, "Fizz", label="Fizz")
        output = fmt.format_result(result)
        assert "Fizz" in output or "3" in output, (
            "format_result produced output that doesn't mention 'Fizz' or '3'. "
            "The formatter appears to be formatting something else entirely."
        )

    def test_format_results_returns_string(self) -> None:
        """format_results must return a string for a collection of results."""
        fmt = self.create_formatter()
        results = [
            _make_result(3, "Fizz", label="Fizz"),
            _make_result(5, "Buzz", label="Buzz"),
            _make_result(7, "7"),
        ]
        output = fmt.format_results(results)
        assert isinstance(output, str)
        assert len(output) > 0

    def test_format_results_empty_list(self) -> None:
        """format_results should handle an empty list without exploding."""
        fmt = self.create_formatter()
        output = fmt.format_results([])
        assert isinstance(output, str)

    def test_format_summary_returns_string(self) -> None:
        """format_summary must return a string representation of the summary."""
        fmt = self.create_formatter()
        summary = _make_summary()
        output = fmt.format_summary(summary)
        assert isinstance(output, str)
        assert len(output) > 0

    def test_get_format_type_returns_output_format(self) -> None:
        """get_format_type must return an OutputFormat enum member."""
        fmt = self.create_formatter()
        fmt_type = fmt.get_format_type()
        assert isinstance(fmt_type, OutputFormat), (
            f"get_format_type() returned {type(fmt_type).__name__} instead of "
            f"OutputFormat. The formatter doesn't know what format it is. "
            f"This is an existential crisis, not a type error."
        )

    def test_get_format_type_matches_expected(self) -> None:
        """The declared format type must match what we expect."""
        fmt = self.create_formatter()
        assert fmt.get_format_type() == self.expected_format_type(), (
            f"Formatter declares itself as {fmt.get_format_type()} but was "
            f"expected to be {self.expected_format_type()}. Identity fraud."
        )


class TestPlainTextFormatterContract(FormatterContractTests):
    """Contract compliance for PlainTextFormatter.

    The formatter that just returns result.output. The least amount
    of work possible while still technically qualifying as formatting.
    """

    def create_formatter(self) -> IFormatter:
        from enterprise_fizzbuzz.infrastructure.formatters import PlainTextFormatter
        return PlainTextFormatter()

    def expected_format_type(self) -> OutputFormat:
        return OutputFormat.PLAIN


class TestJsonFormatterContract(FormatterContractTests):
    """Contract compliance for JsonFormatter.

    Because every FizzBuzz result deserves to be wrapped in curly braces
    and transmitted over HTTP with a Content-Type header.
    """

    def create_formatter(self) -> IFormatter:
        from enterprise_fizzbuzz.infrastructure.formatters import JsonFormatter
        return JsonFormatter()

    def expected_format_type(self) -> OutputFormat:
        return OutputFormat.JSON


class TestXmlFormatterContract(FormatterContractTests):
    """Contract compliance for XmlFormatter.

    For enterprises that haven't yet received the memo about JSON.
    The angle brackets provide a comforting sense of verbosity.
    """

    def create_formatter(self) -> IFormatter:
        from enterprise_fizzbuzz.infrastructure.formatters import XmlFormatter
        return XmlFormatter()

    def expected_format_type(self) -> OutputFormat:
        return OutputFormat.XML


class TestCsvFormatterContract(FormatterContractTests):
    """Contract compliance for CsvFormatter.

    For when your FizzBuzz results need to be imported into Excel
    and turned into a pivot table for the quarterly board meeting.
    """

    def create_formatter(self) -> IFormatter:
        from enterprise_fizzbuzz.infrastructure.formatters import CsvFormatter
        return CsvFormatter()

    def expected_format_type(self) -> OutputFormat:
        return OutputFormat.CSV
