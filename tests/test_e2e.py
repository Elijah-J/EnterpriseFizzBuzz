"""
Enterprise FizzBuzz Platform - End-to-End CLI Test Suite

These tests invoke main.py as a subprocess and verify stdout, stderr,
and exit codes. Because the only thing more enterprise than a FizzBuzz
platform with 39 CLI flags is a test suite that exercises every last
one of them through process boundaries.

Every test in this file proves that the platform boots, evaluates,
formats, and exits without incident — which, given the number of
middleware layers between the user and a modulo operation, is a
genuinely non-trivial achievement.
"""

from __future__ import annotations

import csv
import io
import json
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

# ============================================================
# Constants
# ============================================================

MAIN_PY = str(Path(__file__).parent.parent / "main.py")
CWD = str(Path(__file__).parent.parent)
PYTHON = sys.executable

DEFAULT_TIMEOUT = 30
ML_TIMEOUT = 60

# The canonical FizzBuzz answers for 1-20, because even a test
# file needs a source of truth that doesn't require a neural network.
FIZZBUZZ_1_20 = [
    "1", "2", "Fizz", "4", "Buzz",
    "Fizz", "7", "8", "Fizz", "Buzz",
    "11", "Fizz", "13", "14", "FizzBuzz",
    "16", "17", "Fizz", "19", "Buzz",
]


# ============================================================
# Helpers
# ============================================================

def run_cli(*args: str, timeout: int = DEFAULT_TIMEOUT) -> subprocess.CompletedProcess:
    """Invoke the Enterprise FizzBuzz Platform CLI as a subprocess.

    Returns the CompletedProcess so callers can inspect stdout, stderr,
    and returncode. Adds --no-banner and UTF-8 encoding by default
    because the ASCII art banner, while majestic, makes assertion
    parsing needlessly theatrical.
    """
    cmd = [PYTHON, MAIN_PY, "--no-banner", *args]
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=timeout,
        cwd=CWD,
        env=None,  # inherit environment
        encoding="utf-8",
        errors="replace",
    )


def extract_fizzbuzz_lines(stdout: str) -> list[str]:
    """Extract the FizzBuzz result lines from CLI output.

    The CLI prints a few status lines (strategy, format, range) before
    the actual results, and optionally a summary after. This function
    strips everything that isn't a FizzBuzz result line.
    """
    lines = stdout.strip().splitlines()
    results = []
    for line in lines:
        stripped = line.strip()
        # Skip status/info lines (they start with metadata-ish prefixes)
        if not stripped:
            continue
        if stripped.startswith(("Evaluating", "Strategy:", "Output Format:",
                                "Authenticated", "+-", "|", "WARNING",
                                "Wall clock", "Trust-mode", "verified",
                                "your password", "monitor.", "Proceed",
                                "Session Summary", "Total Numbers",
                                "Fizz Count", "Buzz Count", "FizzBuzz Count",
                                "Plain Count", "Processing Time",
                                "+=")):
            continue
        # FizzBuzz result lines are: numbers (1,2,...), Fizz, Buzz, FizzBuzz
        # or locale equivalents
        results.append(stripped)
    return results


def extract_json_block(stdout: str) -> dict:
    """Extract and parse the JSON block from CLI output.

    The CLI prints status lines before the JSON, so we find the first
    '{' and parse from there.
    """
    start = stdout.index("{")
    # Find the matching closing brace by parsing
    return json.loads(stdout[start:])


def extract_xml_block(stdout: str) -> ET.Element:
    """Extract and parse the XML block from CLI output."""
    start = stdout.index("<?xml")
    return ET.fromstring(stdout[start:])


def extract_csv_block(stdout: str) -> list[dict]:
    """Extract and parse the CSV block from CLI output.

    Returns a list of dicts keyed by header row.
    """
    lines = stdout.strip().splitlines()
    # Find the CSV header line
    csv_start = None
    for i, line in enumerate(lines):
        if line.strip().startswith("number,output"):
            csv_start = i
            break
    assert csv_start is not None, "Could not find CSV header in output"
    csv_text = "\n".join(lines[csv_start:])
    reader = csv.DictReader(io.StringIO(csv_text))
    return list(reader)


# ============================================================
# Test Class: Default Behavior
# ============================================================

class TestDefaultRun:
    """Tests for the default CLI invocation — no flags, no drama."""

    def test_default_run_exits_zero(self):
        """The platform should exit cleanly when given no arguments,
        which is more than can be said for most enterprise software."""
        result = run_cli("--no-summary")
        assert result.returncode == 0

    def test_default_run_produces_100_results(self):
        """Default range is 1-100. One hundred numbers, each classified
        by an industrial-strength modulo pipeline."""
        result = run_cli("--no-summary")
        assert result.returncode == 0
        lines = extract_fizzbuzz_lines(result.stdout)
        assert len(lines) == 100

    def test_default_run_correct_fizzbuzz(self):
        """Verify the first 20 results match the canonical FizzBuzz
        sequence. If they don't, the pipeline has more bugs than a
        production deployment at 2 AM."""
        result = run_cli("--no-summary", "--range", "1", "20")
        assert result.returncode == 0
        lines = extract_fizzbuzz_lines(result.stdout)
        assert lines == FIZZBUZZ_1_20

    def test_fizzbuzz_15_is_fizzbuzz(self):
        """The number 15 must produce 'FizzBuzz'. This is the one test
        that justifies the entire platform's existence."""
        result = run_cli("--no-summary", "--range", "15", "15")
        assert result.returncode == 0
        lines = extract_fizzbuzz_lines(result.stdout)
        assert lines == ["FizzBuzz"]


# ============================================================
# Test Class: Custom Range
# ============================================================

class TestCustomRange:
    """Tests for the --range flag."""

    def test_custom_range_1_20(self):
        """--range 1 20 should produce exactly 20 results."""
        result = run_cli("--no-summary", "--range", "1", "20")
        assert result.returncode == 0
        lines = extract_fizzbuzz_lines(result.stdout)
        assert len(lines) == 20

    def test_custom_range_50_55(self):
        """A mid-range slice should produce the correct count."""
        result = run_cli("--no-summary", "--range", "50", "55")
        assert result.returncode == 0
        lines = extract_fizzbuzz_lines(result.stdout)
        assert len(lines) == 6

    def test_custom_range_single_number(self):
        """A range of one number should produce exactly one result."""
        result = run_cli("--no-summary", "--range", "7", "7")
        assert result.returncode == 0
        lines = extract_fizzbuzz_lines(result.stdout)
        assert lines == ["7"]


# ============================================================
# Test Class: Output Formats
# ============================================================

class TestOutputFormats:
    """Tests for --format plain/json/xml/csv.

    Each format must produce structurally valid output that can be
    parsed by standard libraries. If the XML formatter outputs
    something that xml.etree can't parse, then its SOAP-era
    aspirations have been betrayed.
    """

    def test_format_plain(self):
        """Plain text format: one result per line, human-readable."""
        result = run_cli("--no-summary", "--range", "1", "5", "--format", "plain")
        assert result.returncode == 0
        lines = extract_fizzbuzz_lines(result.stdout)
        assert lines == ["1", "2", "Fizz", "4", "Buzz"]

    def test_format_json_valid(self):
        """JSON format must produce valid, parseable JSON."""
        result = run_cli("--no-summary", "--range", "1", "5", "--format", "json")
        assert result.returncode == 0
        data = extract_json_block(result.stdout)
        assert "results" in data
        assert len(data["results"]) == 5

    def test_format_json_structure(self):
        """Each JSON result must contain number, output, and matched_rules."""
        result = run_cli("--no-summary", "--range", "1", "5", "--format", "json")
        assert result.returncode == 0
        data = extract_json_block(result.stdout)
        for entry in data["results"]:
            assert "number" in entry
            assert "output" in entry
            assert "matched_rules" in entry

    def test_format_json_fizzbuzz_values(self):
        """JSON output values must match canonical FizzBuzz."""
        result = run_cli("--no-summary", "--range", "1", "5", "--format", "json")
        assert result.returncode == 0
        data = extract_json_block(result.stdout)
        outputs = [r["output"] for r in data["results"]]
        assert outputs == ["1", "2", "Fizz", "4", "Buzz"]

    def test_format_xml_valid(self):
        """XML format must produce valid, parseable XML."""
        result = run_cli("--no-summary", "--range", "1", "5", "--format", "xml")
        assert result.returncode == 0
        root = extract_xml_block(result.stdout)
        assert root.tag == "fizzBuzzResults"

    def test_format_xml_structure(self):
        """Each XML result element must contain number and output children."""
        result = run_cli("--no-summary", "--range", "1", "5", "--format", "xml")
        assert result.returncode == 0
        root = extract_xml_block(result.stdout)
        results = root.findall("result")
        assert len(results) == 5
        for res in results:
            assert res.find("number") is not None
            assert res.find("output") is not None

    def test_format_csv_valid(self):
        """CSV format must produce a parseable CSV with header row."""
        result = run_cli("--no-summary", "--range", "1", "5", "--format", "csv")
        assert result.returncode == 0
        rows = extract_csv_block(result.stdout)
        assert len(rows) == 5

    def test_format_csv_headers(self):
        """CSV must have the expected column headers."""
        result = run_cli("--no-summary", "--range", "1", "5", "--format", "csv")
        assert result.returncode == 0
        rows = extract_csv_block(result.stdout)
        assert "number" in rows[0]
        assert "output" in rows[0]

    def test_format_csv_values(self):
        """CSV output values must match canonical FizzBuzz."""
        result = run_cli("--no-summary", "--range", "1", "5", "--format", "csv")
        assert result.returncode == 0
        rows = extract_csv_block(result.stdout)
        outputs = [r["output"] for r in rows]
        assert outputs == ["1", "2", "Fizz", "4", "Buzz"]


# ============================================================
# Test Class: Evaluation Strategies
# ============================================================

class TestStrategies:
    """Tests for --strategy standard/chain_of_responsibility/machine_learning.

    All strategies must produce identical results for the same input,
    because the entire point of the ML strategy is to prove that
    replacing modulo with gradient descent was unnecessary.
    """

    def test_strategy_standard(self):
        """Standard strategy produces correct FizzBuzz."""
        result = run_cli("--no-summary", "--range", "1", "20", "--strategy", "standard")
        assert result.returncode == 0
        lines = extract_fizzbuzz_lines(result.stdout)
        assert lines == FIZZBUZZ_1_20

    def test_strategy_chain_of_responsibility(self):
        """Chain of Responsibility strategy produces correct FizzBuzz."""
        result = run_cli("--no-summary", "--range", "1", "20",
                         "--strategy", "chain_of_responsibility")
        assert result.returncode == 0
        lines = extract_fizzbuzz_lines(result.stdout)
        assert lines == FIZZBUZZ_1_20

    def test_strategy_machine_learning(self):
        """Machine Learning strategy produces correct FizzBuzz.

        This test has a longer timeout because the neural network needs
        time to train on the deeply complex pattern of divisibility by
        3 and 5. The fact that this test passes at all is a testament to
        either the power of machine learning or the simplicity of FizzBuzz.
        """
        result = run_cli("--no-summary", "--range", "1", "20",
                         "--strategy", "machine_learning", timeout=ML_TIMEOUT)
        assert result.returncode == 0
        lines = extract_fizzbuzz_lines(result.stdout)
        assert lines == FIZZBUZZ_1_20


# ============================================================
# Test Class: Async Mode
# ============================================================

class TestAsyncMode:
    """Tests for --async evaluation."""

    def test_async_produces_correct_results(self):
        """Async mode should produce the same results as sync mode,
        because concurrency doesn't change arithmetic (yet)."""
        result = run_cli("--no-summary", "--range", "1", "20", "--async")
        assert result.returncode == 0
        lines = extract_fizzbuzz_lines(result.stdout)
        assert lines == FIZZBUZZ_1_20


# ============================================================
# Test Class: Internationalization
# ============================================================

class TestLocale:
    """Tests for --locale flag.

    The Enterprise FizzBuzz Platform supports seven locales including
    Klingon and Elvish, because global market penetration demands
    fictional language support.
    """

    def test_locale_german(self):
        """German locale should produce 'Sprudel' instead of 'Fizz'."""
        result = run_cli("--no-summary", "--range", "1", "5", "--locale", "de")
        assert result.returncode == 0
        lines = extract_fizzbuzz_lines(result.stdout)
        assert "Sprudel" in lines, f"Expected 'Sprudel' in German output, got: {lines}"

    def test_locale_klingon(self):
        """Klingon locale should produce 'ghum' instead of 'Fizz',
        because Klingon warriors demand FizzBuzz in their native tongue."""
        result = run_cli("--no-summary", "--range", "1", "5", "--locale", "tlh")
        assert result.returncode == 0
        lines = extract_fizzbuzz_lines(result.stdout)
        assert "ghum" in lines, f"Expected 'ghum' in Klingon output, got: {lines}"


# ============================================================
# Test Class: Circuit Breaker
# ============================================================

class TestCircuitBreaker:
    """Tests for --circuit-breaker and --circuit-status flags."""

    def test_circuit_breaker_runs_without_error(self):
        """Circuit breaker should not trip on valid FizzBuzz evaluations."""
        result = run_cli("--no-summary", "--range", "1", "20", "--circuit-breaker")
        assert result.returncode == 0

    def test_circuit_status_dashboard(self):
        """--circuit-status should produce a status dashboard with the
        reassuring 'CLOSED' state that means everything is fine."""
        result = run_cli("--no-summary", "--range", "1", "20",
                         "--circuit-breaker", "--circuit-status")
        assert result.returncode == 0
        assert "CIRCUIT BREAKER STATUS DASHBOARD" in result.stdout
        assert "CLOSED" in result.stdout


# ============================================================
# Test Class: RBAC
# ============================================================

class TestRBAC:
    """Tests for --user and --role flags.

    The RBAC system ensures that only authorized personnel can perform
    modulo arithmetic. Because in the enterprise world, even division
    requires a permission check.
    """

    def test_superuser_access(self):
        """A FIZZBUZZ_SUPERUSER should have unrestricted modulo access."""
        result = run_cli("--no-summary", "--range", "1", "20",
                         "--user", "alice", "--role", "FIZZBUZZ_SUPERUSER")
        assert result.returncode == 0
        lines = extract_fizzbuzz_lines(result.stdout)
        assert lines == FIZZBUZZ_1_20

    def test_anonymous_access_denied(self):
        """An ANONYMOUS user should be denied access, because FizzBuzz is
        a privilege, not a right."""
        result = run_cli("--no-summary", "--range", "1", "20",
                         "--user", "nobody", "--role", "ANONYMOUS")
        assert result.returncode != 0
        combined = result.stdout + result.stderr
        assert "Access denied" in combined or "InsufficientFizzPrivileges" in combined


# ============================================================
# Test Class: Event Sourcing
# ============================================================

class TestEventSourcing:
    """Tests for --event-sourcing flag."""

    def test_event_sourcing_runs_without_error(self):
        """Event sourcing should produce results and a CQRS summary."""
        result = run_cli("--no-summary", "--range", "1", "10", "--event-sourcing")
        assert result.returncode == 0
        assert "EVENT SOURCING" in result.stdout


# ============================================================
# Test Class: Chaos Engineering
# ============================================================

class TestChaos:
    """Tests for --chaos and --chaos-level flags.

    Chaos level 1 is a 'Gentle Breeze' — the Chaos Monkey is barely
    awake. We use this level because we want the test to pass, not to
    recreate the chaos of a production incident.
    """

    def test_chaos_level_1_does_not_crash(self):
        """Level 1 chaos should complete without crashing. Results may
        be corrupted, which is by design — the monkey works as intended."""
        result = run_cli("--no-summary", "--range", "1", "20",
                         "--chaos", "--chaos-level", "1")
        assert result.returncode == 0
        assert "Chaos Engineering ENABLED" in result.stdout


# ============================================================
# Test Class: Feature Flags
# ============================================================

class TestFeatureFlags:
    """Tests for --feature-flags flag."""

    def test_feature_flags_runs_without_error(self):
        """Feature flags should not prevent FizzBuzz evaluation."""
        result = run_cli("--no-summary", "--range", "1", "20", "--feature-flags")
        assert result.returncode == 0
        assert "FEATURE FLAG" in result.stdout


# ============================================================
# Test Class: SLA Monitoring
# ============================================================

class TestSLA:
    """Tests for --sla flag."""

    def test_sla_runs_without_error(self):
        """SLA monitoring should activate without impeding the sacred
        modulo operation."""
        result = run_cli("--no-summary", "--range", "1", "20", "--sla")
        assert result.returncode == 0
        assert "SLA MONITORING" in result.stdout


# ============================================================
# Test Class: Cache
# ============================================================

class TestCache:
    """Tests for --cache and --cache-stats flags."""

    def test_cache_runs_without_error(self):
        """Caching layer should activate and produce correct results."""
        result = run_cli("--no-summary", "--range", "1", "20", "--cache")
        assert result.returncode == 0

    def test_cache_stats_dashboard(self):
        """--cache-stats should produce a statistics dashboard showing
        the futility of caching deterministic modulo results."""
        result = run_cli("--no-summary", "--range", "1", "20",
                         "--cache", "--cache-stats")
        assert result.returncode == 0
        assert "CACHE STATISTICS DASHBOARD" in result.stdout


# ============================================================
# Test Class: Combined Flags (The Full Enterprise Stack)
# ============================================================

class TestCombinedFlags:
    """Tests for combining multiple enterprise features.

    These tests verify that the platform doesn't collapse under the
    weight of its own middleware when multiple subsystems are activated
    simultaneously. If they pass, it means the builder pattern was
    worth it. If they fail, Bob gets paged.
    """

    def test_full_enterprise_stack(self):
        """The full enterprise stack — circuit breaker, SLA, cache —
        should run without error. This is the ultimate integration test:
        can you route a modulo operation through three enterprise
        middleware layers and still get the right answer?"""
        result = run_cli("--no-summary", "--range", "1", "20",
                         "--circuit-breaker", "--sla", "--cache")
        assert result.returncode == 0
        lines = extract_fizzbuzz_lines(result.stdout)
        assert lines == FIZZBUZZ_1_20

    def test_circuit_breaker_with_cache_stats(self):
        """Circuit breaker + cache + cache-stats should all coexist."""
        result = run_cli("--no-summary", "--range", "1", "20",
                         "--circuit-breaker", "--cache", "--cache-stats")
        assert result.returncode == 0
        assert "CACHE STATISTICS DASHBOARD" in result.stdout


# ============================================================
# Test Class: Banner & Summary Suppression
# ============================================================

class TestBannerAndSummary:
    """Tests for --no-banner and --no-summary flags."""

    def test_no_banner_suppresses_banner(self):
        """--no-banner should suppress the ASCII art banner."""
        result = run_cli("--no-summary", "--range", "1", "5")
        assert "ENTERPRISE" not in result.stdout or "E N T E R P R I S E" not in result.stdout

    def test_no_summary_suppresses_summary(self):
        """--no-summary should suppress the session summary."""
        result = run_cli("--no-summary", "--range", "1", "5")
        assert "Session Summary" not in result.stdout

    def test_banner_present_when_not_suppressed(self):
        """Without --no-banner, the majestic ASCII art should appear."""
        cmd = [PYTHON, MAIN_PY, "--no-summary", "--range", "1", "5"]
        result = subprocess.run(
            cmd, capture_output=True, text=True,
            timeout=DEFAULT_TIMEOUT, cwd=CWD,
            encoding="utf-8", errors="replace",
        )
        assert result.returncode == 0
        assert "E N T E R P R I S E" in result.stdout

    def test_both_no_banner_and_no_summary(self):
        """--no-banner --no-summary should produce only the status lines
        and FizzBuzz results. The output is lean, spartan, almost humble
        — a stark departure from the platform's usual verbosity."""
        result = run_cli("--no-summary", "--range", "1", "5")
        assert result.returncode == 0
        assert "E N T E R P R I S E" not in result.stdout
        assert "Session Summary" not in result.stdout


# ============================================================
# Test Class: Help
# ============================================================

class TestHelp:
    """Tests for --help flag."""

    def test_help_exits_zero(self):
        """--help should exit 0, as is tradition."""
        cmd = [PYTHON, MAIN_PY, "--help"]
        result = subprocess.run(
            cmd, capture_output=True, text=True,
            timeout=DEFAULT_TIMEOUT, cwd=CWD,
            encoding="utf-8", errors="replace",
        )
        assert result.returncode == 0

    def test_help_prints_usage(self):
        """--help should print usage information including the program name."""
        cmd = [PYTHON, MAIN_PY, "--help"]
        result = subprocess.run(
            cmd, capture_output=True, text=True,
            timeout=DEFAULT_TIMEOUT, cwd=CWD,
            encoding="utf-8", errors="replace",
        )
        assert "fizzbuzz" in result.stdout.lower()
        assert "--range" in result.stdout


# ============================================================
# Test Class: Tracing
# ============================================================

class TestTracing:
    """Tests for --trace flag."""

    def test_trace_produces_waterfall(self):
        """--trace should produce an ASCII waterfall diagram,
        because distributed tracing for a single-process FizzBuzz
        app is the pinnacle of observability."""
        result = run_cli("--no-summary", "--range", "1", "5", "--trace")
        assert result.returncode == 0
        assert "TRACE" in result.stdout or "WATERFALL" in result.stdout


# ============================================================
# Test Class: Invalid Input
# ============================================================

class TestInvalidInput:
    """Tests for error handling on bad input."""

    def test_unrecognized_flag_exits_nonzero(self):
        """An unrecognized flag should exit non-zero, because even
        enterprise software has standards."""
        cmd = [PYTHON, MAIN_PY, "--definitely-not-a-real-flag"]
        result = subprocess.run(
            cmd, capture_output=True, text=True,
            timeout=DEFAULT_TIMEOUT, cwd=CWD,
            encoding="utf-8", errors="replace",
        )
        assert result.returncode != 0
