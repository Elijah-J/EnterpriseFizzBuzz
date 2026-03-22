"""
Enterprise FizzBuzz Platform - Output Formatters Test Suite

Comprehensive tests for the four pillars of enterprise output serialization:
Plain Text, JSON, XML, and CSV. Because a FizzBuzz result that cannot be
rendered in at least four incompatible formats is a FizzBuzz result that
has failed to achieve true interoperability.

Every formatter implements the IFormatter interface, proving that even
the simplest string concatenation can be elevated to an abstract contract.
"""

from __future__ import annotations

import csv
import io
import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from enterprise_fizzbuzz.domain.interfaces import IFormatter
from enterprise_fizzbuzz.domain.models import (
    FizzBuzzResult,
    FizzBuzzSessionSummary,
    OutputFormat,
    RuleDefinition,
    RuleMatch,
)
from enterprise_fizzbuzz.infrastructure.formatters import (
    CsvFormatter,
    FormatterFactory,
    JsonFormatter,
    PlainTextFormatter,
    XmlFormatter,
)


# ============================================================
# Fixtures
# ============================================================


@pytest.fixture
def fizz_rule() -> RuleDefinition:
    """The sacred Fizz rule: divisor 3, priority 1."""
    return RuleDefinition(name="Fizz", divisor=3, label="Fizz", priority=1)


@pytest.fixture
def buzz_rule() -> RuleDefinition:
    """The sacred Buzz rule: divisor 5, priority 2."""
    return RuleDefinition(name="Buzz", divisor=5, label="Buzz", priority=2)


@pytest.fixture
def fizz_result(fizz_rule: RuleDefinition) -> FizzBuzzResult:
    """A result for number 3: the quintessential Fizz."""
    return FizzBuzzResult(
        number=3,
        output="Fizz",
        matched_rules=[RuleMatch(rule=fizz_rule, number=3)],
        processing_time_ns=42000,
        result_id="fizz-result-001",
        metadata={"strategy": "standard", "confidence": 1.0},
    )


@pytest.fixture
def buzz_result(buzz_rule: RuleDefinition) -> FizzBuzzResult:
    """A result for number 5: Buzz in its purest form."""
    return FizzBuzzResult(
        number=5,
        output="Buzz",
        matched_rules=[RuleMatch(rule=buzz_rule, number=5)],
        processing_time_ns=37000,
        result_id="buzz-result-001",
    )


@pytest.fixture
def fizzbuzz_result(fizz_rule: RuleDefinition, buzz_rule: RuleDefinition) -> FizzBuzzResult:
    """A result for number 15: the fabled FizzBuzz, matched by two rules."""
    return FizzBuzzResult(
        number=15,
        output="FizzBuzz",
        matched_rules=[
            RuleMatch(rule=fizz_rule, number=15),
            RuleMatch(rule=buzz_rule, number=15),
        ],
        processing_time_ns=99000,
        result_id="fizzbuzz-result-001",
    )


@pytest.fixture
def plain_result() -> FizzBuzzResult:
    """A result for number 7: no rules matched, just a lonely integer."""
    return FizzBuzzResult(
        number=7,
        output="7",
        matched_rules=[],
        processing_time_ns=10000,
        result_id="plain-result-001",
    )


@pytest.fixture
def batch_results(
    fizz_result: FizzBuzzResult,
    buzz_result: FizzBuzzResult,
    fizzbuzz_result: FizzBuzzResult,
    plain_result: FizzBuzzResult,
) -> list[FizzBuzzResult]:
    """A batch containing one of each classification. The four food groups."""
    return [plain_result, fizz_result, buzz_result, fizzbuzz_result]


@pytest.fixture
def session_summary() -> FizzBuzzSessionSummary:
    """A session summary with plausible enterprise-grade statistics."""
    return FizzBuzzSessionSummary(
        session_id="abcdef01-2345-6789-abcd-ef0123456789",
        total_numbers=100,
        fizz_count=27,
        buzz_count=14,
        fizzbuzz_count=6,
        plain_count=53,
        total_processing_time_ms=42.69,
    )


@pytest.fixture
def session_summary_with_errors() -> FizzBuzzSessionSummary:
    """A session summary that has seen better days."""
    return FizzBuzzSessionSummary(
        session_id="deadbeef-dead-beef-dead-beefdeadbeef",
        total_numbers=50,
        fizz_count=10,
        buzz_count=5,
        fizzbuzz_count=3,
        plain_count=32,
        total_processing_time_ms=100.0,
        errors=["Blockchain consensus failure", "Neural network existential crisis"],
    )


# ============================================================
# PlainTextFormatter Tests
# ============================================================


class TestPlainTextFormatter:
    """Tests for the formatter that outputs text like a civilized human.

    No angle brackets, no curly braces, no delimiters — just raw,
    unadorned FizzBuzz truth printed to the console.
    """

    def test_implements_iformatter(self):
        """The plain text formatter honors the sacred IFormatter contract."""
        assert isinstance(PlainTextFormatter(), IFormatter)

    def test_get_format_type_returns_plain(self):
        """It knows what it is: PLAIN."""
        assert PlainTextFormatter().get_format_type() == OutputFormat.PLAIN

    def test_format_single_fizz(self, fizz_result: FizzBuzzResult):
        """Formatting a Fizz result returns the string 'Fizz'. Groundbreaking."""
        assert PlainTextFormatter().format_result(fizz_result) == "Fizz"

    def test_format_single_buzz(self, buzz_result: FizzBuzzResult):
        """Formatting a Buzz result returns 'Buzz'."""
        assert PlainTextFormatter().format_result(buzz_result) == "Buzz"

    def test_format_single_fizzbuzz(self, fizzbuzz_result: FizzBuzzResult):
        """The coveted FizzBuzz, rendered in plain text glory."""
        assert PlainTextFormatter().format_result(fizzbuzz_result) == "FizzBuzz"

    def test_format_plain_number(self, plain_result: FizzBuzzResult):
        """A plain number is simply itself. No frills, no labels."""
        assert PlainTextFormatter().format_result(plain_result) == "7"

    def test_format_batch(self, batch_results: list[FizzBuzzResult]):
        """Batch formatting joins results with newlines, one per line."""
        fmt = PlainTextFormatter()
        output = fmt.format_results(batch_results)
        lines = output.split("\n")
        assert len(lines) == 4
        assert lines[0] == "7"
        assert lines[1] == "Fizz"
        assert lines[2] == "Buzz"
        assert lines[3] == "FizzBuzz"

    def test_format_empty_batch(self):
        """An empty batch produces an empty string. The void gazes back."""
        assert PlainTextFormatter().format_results([]) == ""

    def test_format_summary(self, session_summary: FizzBuzzSessionSummary):
        """The summary contains all the statistics a manager could want."""
        fmt = PlainTextFormatter()
        output = fmt.format_summary(session_summary)
        assert "FizzBuzz Session Summary" in output
        assert "Total Numbers: 100" in output
        assert "Fizz:          27" in output
        assert "Buzz:          14" in output
        assert "FizzBuzz:      6" in output
        assert "Plain:         53" in output
        assert "42.69ms" in output
        assert session_summary.session_id[:8] in output

    def test_format_summary_with_errors(self, session_summary_with_errors: FizzBuzzSessionSummary):
        """When errors exist, they are dutifully listed for postmortem review."""
        fmt = PlainTextFormatter()
        output = fmt.format_summary(session_summary_with_errors)
        assert "Errors: 2" in output
        assert "Blockchain consensus failure" in output
        assert "Neural network existential crisis" in output

    def test_format_summary_without_errors(self, session_summary: FizzBuzzSessionSummary):
        """A clean session does not boast about the absence of errors."""
        fmt = PlainTextFormatter()
        output = fmt.format_summary(session_summary)
        assert "Errors" not in output


# ============================================================
# JsonFormatter Tests
# ============================================================


class TestJsonFormatter:
    """Tests for the JSON formatter.

    Every output must be valid JSON, parseable by any standards-compliant
    JSON parser. If the output isn't valid JSON, it's just a string with
    delusions of structure.
    """

    def test_implements_iformatter(self):
        """The JSON formatter implements IFormatter because abstraction."""
        assert isinstance(JsonFormatter(), IFormatter)

    def test_get_format_type_returns_json(self):
        """It returns OutputFormat.JSON. REST APIs everywhere rejoice."""
        assert JsonFormatter().get_format_type() == OutputFormat.JSON

    def test_format_single_result_is_valid_json(self, fizz_result: FizzBuzzResult):
        """The formatted output must parse as valid JSON."""
        output = JsonFormatter().format_result(fizz_result)
        data = json.loads(output)
        assert isinstance(data, dict)

    def test_format_single_result_structure(self, fizz_result: FizzBuzzResult):
        """The JSON object contains number, output, result_id, and matched_rules."""
        data = json.loads(JsonFormatter().format_result(fizz_result))
        assert data["number"] == 3
        assert data["output"] == "Fizz"
        assert data["result_id"] == "fizz-result-001"
        assert len(data["matched_rules"]) == 1
        assert data["matched_rules"][0]["name"] == "Fizz"
        assert data["matched_rules"][0]["divisor"] == 3
        assert data["matched_rules"][0]["label"] == "Fizz"

    def test_format_plain_number_has_empty_rules(self, plain_result: FizzBuzzResult):
        """A plain number has an empty matched_rules array. Zero matches, zero glory."""
        data = json.loads(JsonFormatter().format_result(plain_result))
        assert data["matched_rules"] == []
        assert data["output"] == "7"

    def test_format_fizzbuzz_has_two_rules(self, fizzbuzz_result: FizzBuzzResult):
        """FizzBuzz matches two rules: the whole point of the enterprise."""
        data = json.loads(JsonFormatter().format_result(fizzbuzz_result))
        assert len(data["matched_rules"]) == 2
        rule_names = {r["name"] for r in data["matched_rules"]}
        assert rule_names == {"Fizz", "Buzz"}

    def test_metadata_excluded_by_default(self, fizz_result: FizzBuzzResult):
        """Metadata is not included unless explicitly requested."""
        data = json.loads(JsonFormatter().format_result(fizz_result))
        assert "metadata" not in data
        assert "processing_time_ns" not in data

    def test_metadata_included_when_requested(self, fizz_result: FizzBuzzResult):
        """With include_metadata=True, the full telemetry payload appears."""
        fmt = JsonFormatter(include_metadata=True)
        data = json.loads(fmt.format_result(fizz_result))
        assert data["metadata"] == {"strategy": "standard", "confidence": 1.0}
        assert data["processing_time_ns"] == 42000

    def test_custom_indent(self, fizz_result: FizzBuzzResult):
        """Custom indentation is respected. Some prefer 4 spaces; they are wrong."""
        fmt = JsonFormatter(indent=4)
        output = fmt.format_result(fizz_result)
        # 4-space indent means lines should start with 4 spaces
        assert "    " in output
        json.loads(output)  # Still valid JSON

    def test_format_batch_is_valid_json(self, batch_results: list[FizzBuzzResult]):
        """Batch output is a valid JSON object with results array and count."""
        output = JsonFormatter().format_results(batch_results)
        data = json.loads(output)
        assert data["count"] == 4
        assert len(data["results"]) == 4

    def test_format_batch_preserves_order(self, batch_results: list[FizzBuzzResult]):
        """Results appear in the same order they were provided."""
        data = json.loads(JsonFormatter().format_results(batch_results))
        numbers = [r["number"] for r in data["results"]]
        assert numbers == [7, 3, 5, 15]

    def test_format_empty_batch(self):
        """An empty batch produces a valid JSON object with count 0."""
        data = json.loads(JsonFormatter().format_results([]))
        assert data["count"] == 0
        assert data["results"] == []

    def test_format_summary_is_valid_json(self, session_summary: FizzBuzzSessionSummary):
        """The session summary serializes to valid JSON with all fields."""
        output = JsonFormatter().format_summary(session_summary)
        data = json.loads(output)
        assert data["session_id"] == session_summary.session_id
        assert data["total_numbers"] == 100
        assert data["fizz_count"] == 27
        assert data["buzz_count"] == 14
        assert data["fizzbuzz_count"] == 6
        assert data["plain_count"] == 53
        assert data["processing_time_ms"] == pytest.approx(42.69)
        assert data["errors"] == []

    def test_format_summary_with_errors(self, session_summary_with_errors: FizzBuzzSessionSummary):
        """Errors are serialized as a JSON array of strings."""
        data = json.loads(JsonFormatter().format_summary(session_summary_with_errors))
        assert len(data["errors"]) == 2
        assert "Blockchain consensus failure" in data["errors"]


# ============================================================
# XmlFormatter Tests
# ============================================================


class TestXmlFormatter:
    """Tests for the XML formatter.

    For those enterprise environments still running SOAP services
    circa 2003, this formatter produces well-formed XML that would
    make any WS-* specification committee weep with pride.
    """

    def test_implements_iformatter(self):
        """The XML formatter implements IFormatter. The ceremony continues."""
        assert isinstance(XmlFormatter(), IFormatter)

    def test_get_format_type_returns_xml(self):
        """It returns OutputFormat.XML, as the WSDL demands."""
        assert XmlFormatter().get_format_type() == OutputFormat.XML

    def test_format_single_result_is_valid_xml(self, fizz_result: FizzBuzzResult):
        """The single result output parses as well-formed XML."""
        output = XmlFormatter().format_result(fizz_result)
        root = ET.fromstring(output)
        assert root.tag == "result"

    def test_format_single_result_structure(self, fizz_result: FizzBuzzResult):
        """The XML contains number, output, and matchedRules elements."""
        root = ET.fromstring(XmlFormatter().format_result(fizz_result))
        assert root.attrib["id"] == "fizz-result-001"
        assert root.find("number").text == "3"
        assert root.find("output").text == "Fizz"
        rules = root.find("matchedRules").findall("rule")
        assert len(rules) == 1
        assert rules[0].attrib["name"] == "Fizz"
        assert rules[0].attrib["divisor"] == "3"
        assert rules[0].attrib["label"] == "Fizz"

    def test_format_plain_number_xml(self, plain_result: FizzBuzzResult):
        """A plain number has an empty matchedRules element. XML's equivalent of silence."""
        root = ET.fromstring(XmlFormatter().format_result(plain_result))
        assert root.find("output").text == "7"
        rules = root.find("matchedRules").findall("rule")
        assert len(rules) == 0

    def test_format_fizzbuzz_has_two_rule_elements(self, fizzbuzz_result: FizzBuzzResult):
        """FizzBuzz produces two <rule> elements under matchedRules."""
        root = ET.fromstring(XmlFormatter().format_result(fizzbuzz_result))
        rules = root.find("matchedRules").findall("rule")
        assert len(rules) == 2

    def test_format_batch_is_valid_xml(self, batch_results: list[FizzBuzzResult]):
        """Batch output is well-formed XML with an XML declaration."""
        output = XmlFormatter().format_results(batch_results)
        assert output.startswith('<?xml version="1.0"')
        root = ET.fromstring(output)
        assert root.tag == "fizzBuzzResults"

    def test_format_batch_count_attribute(self, batch_results: list[FizzBuzzResult]):
        """The root element carries a count attribute matching the number of results."""
        root = ET.fromstring(XmlFormatter().format_results(batch_results))
        assert root.attrib["count"] == "4"
        assert len(root.findall(".//result")) == 4

    def test_format_empty_batch_is_valid_xml(self):
        """An empty batch still produces valid XML. The schema must not be violated."""
        output = XmlFormatter().format_results([])
        root = ET.fromstring(output)
        assert root.attrib["count"] == "0"
        assert len(root.findall("result")) == 0

    def test_format_summary_is_valid_xml(self, session_summary: FizzBuzzSessionSummary):
        """The session summary is valid XML with all statistics as child elements."""
        output = XmlFormatter().format_summary(session_summary)
        root = ET.fromstring(output)
        assert root.tag == "sessionSummary"
        assert root.find("sessionId").text == session_summary.session_id
        assert root.find("totalNumbers").text == "100"
        assert root.find("fizzCount").text == "27"
        assert root.find("buzzCount").text == "14"
        assert root.find("fizzBuzzCount").text == "6"
        assert root.find("plainCount").text == "53"

    def test_format_summary_has_xml_declaration(self, session_summary: FizzBuzzSessionSummary):
        """The summary output begins with a proper XML declaration."""
        output = XmlFormatter().format_summary(session_summary)
        assert output.startswith('<?xml version="1.0" encoding="UTF-8"?>')


# ============================================================
# CsvFormatter Tests
# ============================================================


class TestCsvFormatter:
    """Tests for the CSV formatter.

    For importing FizzBuzz results into enterprise spreadsheet solutions,
    pivot tables, and business intelligence dashboards where executives
    can finally see the data they've been missing: how many numbers
    between 1 and 100 are divisible by 3.
    """

    def test_implements_iformatter(self):
        """The CSV formatter implements IFormatter. Every interface must be satisfied."""
        assert isinstance(CsvFormatter(), IFormatter)

    def test_get_format_type_returns_csv(self):
        """It returns OutputFormat.CSV, ready for Excel."""
        assert CsvFormatter().get_format_type() == OutputFormat.CSV

    def test_format_single_result(self, fizz_result: FizzBuzzResult):
        """A single result is a comma-separated line: number, output, rules, id."""
        output = CsvFormatter().format_result(fizz_result)
        assert output == "3,Fizz,Fizz,fizz-result-001"

    def test_format_plain_number_shows_none_for_rules(self, plain_result: FizzBuzzResult):
        """When no rules matched, the rules field shows 'none'."""
        output = CsvFormatter().format_result(plain_result)
        assert output == "7,7,none,plain-result-001"

    def test_format_fizzbuzz_pipes_rule_names(self, fizzbuzz_result: FizzBuzzResult):
        """Multiple matched rules are pipe-delimited within the rules field."""
        output = CsvFormatter().format_result(fizzbuzz_result)
        parts = output.split(",")
        assert parts[0] == "15"
        assert parts[1] == "FizzBuzz"
        assert "Fizz" in parts[2]
        assert "Buzz" in parts[2]
        assert "|" in parts[2]

    def test_format_batch_has_header(self, batch_results: list[FizzBuzzResult]):
        """Batch output starts with a header row: number,output,matched_rules,result_id."""
        output = CsvFormatter().format_results(batch_results)
        lines = output.split("\n")
        assert lines[0] == "number,output,matched_rules,result_id"

    def test_format_batch_row_count(self, batch_results: list[FizzBuzzResult]):
        """Batch output has one header row plus one data row per result."""
        output = CsvFormatter().format_results(batch_results)
        lines = output.split("\n")
        assert len(lines) == 5  # 1 header + 4 data rows

    def test_format_empty_batch_has_only_header(self):
        """An empty batch produces just the header row. An empty spreadsheet is still a spreadsheet."""
        output = CsvFormatter().format_results([])
        assert output == "number,output,matched_rules,result_id"

    def test_format_batch_is_parseable_csv(self, batch_results: list[FizzBuzzResult]):
        """The batch output can be parsed by Python's csv module."""
        output = CsvFormatter().format_results(batch_results)
        reader = csv.reader(io.StringIO(output))
        rows = list(reader)
        assert rows[0] == ["number", "output", "matched_rules", "result_id"]
        assert len(rows) == 5

    def test_format_summary_is_metric_value_pairs(self, session_summary: FizzBuzzSessionSummary):
        """The summary is a two-column CSV: metric,value."""
        output = CsvFormatter().format_summary(session_summary)
        reader = csv.reader(io.StringIO(output))
        rows = list(reader)
        assert rows[0] == ["metric", "value"]
        # Convert to dict for easy assertion
        metrics = {row[0]: row[1] for row in rows[1:]}
        assert metrics["session_id"] == session_summary.session_id
        assert metrics["total_numbers"] == "100"
        assert metrics["fizz_count"] == "27"
        assert metrics["buzz_count"] == "14"
        assert metrics["fizzbuzz_count"] == "6"
        assert metrics["plain_count"] == "53"


# ============================================================
# FormatterFactory Tests
# ============================================================


class TestFormatterFactory:
    """Tests for the factory that creates formatters.

    Because you can't just instantiate a class directly in enterprise
    software. You need an intermediary. A factory. A ceremony.
    """

    def test_create_plain_formatter(self):
        """The factory creates a PlainTextFormatter for OutputFormat.PLAIN."""
        fmt = FormatterFactory.create(OutputFormat.PLAIN)
        assert isinstance(fmt, PlainTextFormatter)

    def test_create_json_formatter(self):
        """The factory creates a JsonFormatter for OutputFormat.JSON."""
        fmt = FormatterFactory.create(OutputFormat.JSON)
        assert isinstance(fmt, JsonFormatter)

    def test_create_xml_formatter(self):
        """The factory creates an XmlFormatter for OutputFormat.XML."""
        fmt = FormatterFactory.create(OutputFormat.XML)
        assert isinstance(fmt, XmlFormatter)

    def test_create_csv_formatter(self):
        """The factory creates a CsvFormatter for OutputFormat.CSV."""
        fmt = FormatterFactory.create(OutputFormat.CSV)
        assert isinstance(fmt, CsvFormatter)

    def test_all_formatters_implement_iformatter(self):
        """Every formatter the factory creates implements IFormatter."""
        for format_type in OutputFormat:
            fmt = FormatterFactory.create(format_type)
            assert isinstance(fmt, IFormatter), (
                f"Formatter for {format_type} does not implement IFormatter"
            )

    def test_json_formatter_accepts_kwargs(self):
        """The factory passes kwargs through to the formatter constructor."""
        fmt = FormatterFactory.create(OutputFormat.JSON, indent=4, include_metadata=True)
        assert isinstance(fmt, JsonFormatter)
        assert fmt._indent == 4
        assert fmt._include_metadata is True

    def test_factory_returns_correct_format_types(self):
        """Each created formatter reports the correct format type via get_format_type()."""
        for format_type in OutputFormat:
            fmt = FormatterFactory.create(format_type)
            assert fmt.get_format_type() == format_type


# ============================================================
# Cross-Formatter Edge Case Tests
# ============================================================


class TestFormatterEdgeCases:
    """Edge cases that apply across all formatters.

    The edge of the enterprise is where bugs hide. These tests
    probe the dark corners that integration tests never reach.
    """

    @pytest.fixture(params=[PlainTextFormatter, JsonFormatter, XmlFormatter, CsvFormatter])
    def formatter(self, request) -> IFormatter:
        """Parametrized fixture yielding one of each formatter type."""
        return request.param()

    def test_single_result_returns_string(self, formatter: IFormatter, fizz_result: FizzBuzzResult):
        """Every formatter returns a string from format_result."""
        output = formatter.format_result(fizz_result)
        assert isinstance(output, str)
        assert len(output) > 0

    def test_batch_results_returns_string(self, formatter: IFormatter, batch_results: list[FizzBuzzResult]):
        """Every formatter returns a string from format_results."""
        output = formatter.format_results(batch_results)
        assert isinstance(output, str)
        assert len(output) > 0

    def test_summary_returns_string(self, formatter: IFormatter, session_summary: FizzBuzzSessionSummary):
        """Every formatter returns a string from format_summary."""
        output = formatter.format_summary(session_summary)
        assert isinstance(output, str)
        assert len(output) > 0

    def test_single_item_batch(self, formatter: IFormatter, fizz_result: FizzBuzzResult):
        """A batch with a single result should still produce valid output."""
        output = formatter.format_results([fizz_result])
        assert isinstance(output, str)
        assert len(output) > 0

    def test_result_with_metadata(self, formatter: IFormatter):
        """A result carrying metadata doesn't cause formatting failures."""
        result = FizzBuzzResult(
            number=42,
            output="42",
            matched_rules=[],
            processing_time_ns=1,
            result_id="meta-test-001",
            metadata={"ml_confidence": 0.999, "strategy": "neural_network", "epochs": 1000},
        )
        output = formatter.format_result(result)
        assert isinstance(output, str)

    def test_zero_processing_time_summary(self, formatter: IFormatter):
        """A summary with zero processing time yields infinite throughput without crashing."""
        summary = FizzBuzzSessionSummary(
            session_id="zero-time-session",
            total_numbers=10,
            total_processing_time_ms=0.0,
        )
        output = formatter.format_summary(summary)
        assert isinstance(output, str)
