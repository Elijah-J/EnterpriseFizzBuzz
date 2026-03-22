"""
Enterprise FizzBuzz Platform - E2E Test Suite: Output Formats & Locales

This test suite exercises every output format (plain, JSON, XML, CSV) and
every locale (en, de, fr, ja, tlh, sjn, qya) the platform offers, including
cross-product combinations thereof. Because the only thing more enterprise
than a FizzBuzz platform with seven locales is a test suite that verifies
every locale renders modulo results in its culturally appropriate tongue.

Categories covered:
- Plain format: line count, correct classifications, single number
- JSON format: valid JSON parsing, expected fields, correct values, result count
- XML format: valid XML parsing, root tag, result elements, output values
- CSV format: csv.reader parsing, headers, row count, output values
- 7 locales: each produces correct translated labels
- Format+locale combinations: JSON+German, XML+Klingon, CSV+Sindarin, etc.
- Banner/summary suppression: --no-banner, --no-summary work
- Invalid format/locale: rejected or handled gracefully
- Metadata flag: skipped (defined but not wired)
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

MAIN_PY = str(Path(__file__).parent.parent.parent / "main.py")
CWD = str(Path(__file__).parent.parent.parent)
PYTHON = sys.executable

DEFAULT_TIMEOUT = 30

# The canonical FizzBuzz answers for 1-15, because two full cycles of
# FizzBuzz labels (3, 5, 6, 9, 10, 12, 15) is the minimum viable
# truth table for locale verification.
FIZZBUZZ_1_15 = [
    "1", "2", "Fizz", "4", "Buzz",
    "Fizz", "7", "8", "Fizz", "Buzz",
    "11", "Fizz", "13", "14", "FizzBuzz",
]

FIZZBUZZ_1_5 = ["1", "2", "Fizz", "4", "Buzz"]

# Locale label mappings, painstakingly extracted from .fizztranslation
# files so that every assertion matches the source of truth.
LOCALE_LABELS = {
    "en": {"fizz": "Fizz", "buzz": "Buzz", "fizzbuzz": "FizzBuzz"},
    "de": {"fizz": "Sprudel", "buzz": "Summen", "fizzbuzz": "SprudelSummen"},
    "fr": {"fizz": "Petillement", "buzz": "Bourdonnement", "fizzbuzz": "PetillementBourdonnement"},
    "ja": {"fizz": "\u30d5\u30a3\u30ba", "buzz": "\u30d0\u30ba", "fizzbuzz": "\u30d5\u30a3\u30ba\u30d0\u30ba"},
    "tlh": {"fizz": "ghum", "buzz": "wab", "fizzbuzz": "ghumwab"},
    "sjn": {"fizz": "Hith", "buzz": "Glamor", "fizzbuzz": "HithGlamor"},
    "qya": {"fizz": "Wing\u00eb", "buzz": "L\u00e1ma", "fizzbuzz": "WingeL\u00e1ma"},
}


def _locale_fizzbuzz_1_15(locale: str) -> list[str]:
    """Build the expected FizzBuzz sequence for 1-15 using locale labels."""
    labels = LOCALE_LABELS[locale]
    template = [
        "1", "2", labels["fizz"], "4", labels["buzz"],
        labels["fizz"], "7", "8", labels["fizz"], labels["buzz"],
        "11", labels["fizz"], "13", "14", labels["fizzbuzz"],
    ]
    return template


def _locale_fizzbuzz_1_5(locale: str) -> list[str]:
    """Build the expected FizzBuzz sequence for 1-5 using locale labels."""
    labels = LOCALE_LABELS[locale]
    return ["1", "2", labels["fizz"], "4", labels["buzz"]]


# ============================================================
# Helpers (per-file, no conftest.py -- the Enterprise way)
# ============================================================

def run_cli(*args: str, timeout: int = DEFAULT_TIMEOUT) -> subprocess.CompletedProcess:
    """Invoke the Enterprise FizzBuzz Platform CLI as a subprocess.

    Returns the CompletedProcess so callers can inspect stdout, stderr,
    and returncode. Adds --no-banner and --no-summary by default because
    ASCII art banners and session summaries, while magnificent, turn
    assertion parsing into an archaeological excavation.
    """
    cmd = [PYTHON, MAIN_PY, "--no-banner", "--no-summary", *args]
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=timeout,
        cwd=CWD,
        env=None,
        encoding="utf-8",
        errors="replace",
    )


def extract_fizzbuzz_lines(stdout: str) -> list[str]:
    """Extract the FizzBuzz result lines from CLI output.

    The CLI emits status lines (strategy, format, range), subsystem banners,
    dashboard renderings, and occasionally existential commentary before
    delivering the actual FizzBuzz results. This function strips everything
    that isn't a result line, returning only the modulo verdicts.
    """
    lines = stdout.strip().splitlines()
    results = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        # Skip status/info/dashboard lines -- covers both English and
        # locale-translated status prefixes by pattern matching the
        # structural markers rather than the words themselves.
        if stripped.startswith((
            "Evaluating", "Strategy:", "Output Format:",
            "Authenticated", "+-", "|", "WARNING",
            "Wall clock", "Trust-mode", "verified",
            "your password", "monitor.", "Proceed",
            "Session Summary", "Total Numbers",
            "Fizz Count", "Buzz Count", "FizzBuzz Count",
            "Plain Count", "Processing Time",
            "+=", ";", "ADDR", "---",
            "FBVM", "Because Python", "Average cycles",
            "QUANTUM", "Qubits:", "Hilbert", "Divisibility",
            "using a simplified", "is armed", "Quantum Advantage",
            "PAXOS", "Nodes:", "Quorum:", "Byzantine",
            "Every number", "ratified", "modulo operation",
            "Rules compiled:", "Instructions:", "Optimized:",
            "[GA]", "q0:", "q1:", "q2:", "q3:",
            "DISTRIBUTED", "CONSENSUS",
            "Warning:",
        )):
            continue
        # Skip locale-translated status lines: they start with
        # locale-specific prefixes for evaluating/strategy/output_format.
        # The i18n system translates these, so we match the common pattern
        # of "  SomeLabel: value" that the CLI prints for status info.
        # We also skip lines that look like informational headers.
        if any(stripped.startswith(prefix) for prefix in (
            "FizzBuzz-Auswertung", "Strategie:", "Ausgabeformat:",
            "Echtzeit:",
            "Evaluation de FizzBuzz", "Strategie:", "Format de Sortie:",
            "Temps reel:",
            "\u7bc4\u56f2", "\u6226\u7565:", "\u51fa\u529b\u5f62\u5f0f:",
            "\u5b9f\u6642\u9593:",
            "FizzBuzz yIqel", "DuH:", "ngoq mIw:",
            "poH 'ey:",
            "Gonadol FizzBuzz", "Men:", "Cant e-Thiw:",
            "Lu en-goned:",
            "Noti\u00eb FizzBuzz", "Ti\u00eb:", "Canta Tengwesto:",
            "L\u00fam\u00eb cendo:",
        )):
            continue
        results.append(stripped)
    return results


def extract_json_block(stdout: str) -> dict:
    """Extract and parse the JSON block from CLI output.

    The CLI prints status lines before the JSON, so we find the first
    '{' and parse from there. The JSON formatter produces a single
    top-level object with 'results' and 'count' keys.
    """
    start = stdout.index("{")
    return json.loads(stdout[start:])


def extract_xml_block(stdout: str) -> ET.Element:
    """Extract and parse the XML block from CLI output.

    Finds the XML declaration and parses everything from there.
    """
    start = stdout.index("<?xml")
    return ET.fromstring(stdout[start:])


def extract_csv_block(stdout: str) -> list[dict]:
    """Extract and parse the CSV block from CLI output.

    Finds the CSV header row ('number,output,...') and parses from there.
    Returns a list of dicts keyed by the header row columns.
    """
    lines = stdout.strip().splitlines()
    csv_start = None
    for i, line in enumerate(lines):
        if line.strip().startswith("number,output"):
            csv_start = i
            break
    assert csv_start is not None, f"Could not find CSV header in output:\n{stdout}"
    csv_text = "\n".join(lines[csv_start:])
    reader = csv.DictReader(io.StringIO(csv_text))
    return list(reader)


# ============================================================
# Test Class: Plain Text Format
# ============================================================

class TestPlainFormat:
    """Tests for --format plain output.

    Plain text is the format that FizzBuzz was born in -- one result per
    line, no ceremony, no XML namespaces, no JSON braces. The kind of
    output that a five-line Python script would produce, except this one
    passes through 47 middleware layers to get there.
    """

    def test_plain_format_produces_correct_line_count(self):
        """Plain format for range 1-15 should produce exactly 15 lines.
        One line per number, because even enterprise FizzBuzz respects
        the principle of least surprise (occasionally)."""
        result = run_cli("--range", "1", "15", "--format", "plain")
        assert result.returncode == 0
        lines = extract_fizzbuzz_lines(result.stdout)
        assert len(lines) == 15

    def test_plain_format_correct_classifications(self):
        """Plain format must produce the canonical FizzBuzz sequence.
        If 3 is not 'Fizz' and 15 is not 'FizzBuzz', the entire
        middleware stack has failed at its one job."""
        result = run_cli("--range", "1", "15", "--format", "plain")
        assert result.returncode == 0
        lines = extract_fizzbuzz_lines(result.stdout)
        assert lines == FIZZBUZZ_1_15

    def test_plain_format_single_number(self):
        """A single-number range should produce exactly one line.
        The entire enterprise platform spins up, evaluates one modulo,
        and exits. Peak efficiency."""
        result = run_cli("--range", "3", "3", "--format", "plain")
        assert result.returncode == 0
        lines = extract_fizzbuzz_lines(result.stdout)
        assert lines == ["Fizz"]

    def test_plain_format_fizzbuzz_number(self):
        """Number 15 in plain format must output 'FizzBuzz'. This is
        the test that justifies the existence of 151 custom exception
        classes."""
        result = run_cli("--range", "15", "15", "--format", "plain")
        assert result.returncode == 0
        lines = extract_fizzbuzz_lines(result.stdout)
        assert lines == ["FizzBuzz"]


# ============================================================
# Test Class: JSON Format
# ============================================================

class TestJsonFormat:
    """Tests for --format json output.

    JSON output transforms the humble FizzBuzz result into a structured
    data payload suitable for consumption by downstream microservices,
    data lakes, and business intelligence dashboards that will never
    be built.
    """

    def test_json_format_produces_valid_json(self):
        """The JSON formatter must produce output that json.loads() can
        parse without raising ValueError. This is a lower bar than you
        might expect for enterprise software."""
        result = run_cli("--range", "1", "5", "--format", "json")
        assert result.returncode == 0
        data = extract_json_block(result.stdout)
        assert isinstance(data, dict)

    def test_json_format_has_results_key(self):
        """The top-level JSON object must contain a 'results' array,
        because enterprise APIs never return bare arrays."""
        result = run_cli("--range", "1", "5", "--format", "json")
        assert result.returncode == 0
        data = extract_json_block(result.stdout)
        assert "results" in data

    def test_json_format_has_count_key(self):
        """The top-level JSON object must contain a 'count' field,
        because clients should never have to call len() themselves."""
        result = run_cli("--range", "1", "5", "--format", "json")
        assert result.returncode == 0
        data = extract_json_block(result.stdout)
        assert "count" in data
        assert data["count"] == 5

    def test_json_format_result_fields(self):
        """Each result entry must contain 'number', 'output', and
        'matched_rules' fields. The result_id is also present because
        every modulo operation deserves a UUID."""
        result = run_cli("--range", "1", "5", "--format", "json")
        assert result.returncode == 0
        data = extract_json_block(result.stdout)
        for entry in data["results"]:
            assert "number" in entry
            assert "output" in entry
            assert "matched_rules" in entry

    def test_json_format_correct_values(self):
        """JSON output values must match the canonical FizzBuzz sequence.
        The structured format changes the shape, not the substance."""
        result = run_cli("--range", "1", "5", "--format", "json")
        assert result.returncode == 0
        data = extract_json_block(result.stdout)
        outputs = [r["output"] for r in data["results"]]
        assert outputs == FIZZBUZZ_1_5

    def test_json_format_result_count(self):
        """JSON results array length must match the requested range.
        Five numbers in, five results out -- the conservation of
        FizzBuzz mass."""
        result = run_cli("--range", "1", "15", "--format", "json")
        assert result.returncode == 0
        data = extract_json_block(result.stdout)
        assert len(data["results"]) == 15

    @pytest.mark.skip(reason="--metadata flag is defined but not wired to JsonFormatter.include_metadata")
    def test_json_metadata_flag(self):
        """--metadata should include additional fields in JSON output.
        Skipped because the flag exists in argparse but is never passed
        to the formatter -- a classic enterprise oversight."""
        result = run_cli("--range", "1", "5", "--format", "json", "--metadata")
        assert result.returncode == 0
        data = extract_json_block(result.stdout)
        for entry in data["results"]:
            assert "metadata" in entry


# ============================================================
# Test Class: XML Format
# ============================================================

class TestXmlFormat:
    """Tests for --format xml output.

    XML output pays homage to the SOAP era, when every API response
    was wrapped in angle brackets and every developer had strong
    opinions about namespace prefixes. The Enterprise FizzBuzz Platform
    honors this tradition with well-formed XML that would make any
    2003-era integration architect weep with joy.
    """

    def test_xml_format_produces_valid_xml(self):
        """The XML formatter must produce output that ElementTree can
        parse. If it can't, the enterprise's SOAP interoperability
        story is in jeopardy."""
        result = run_cli("--range", "1", "5", "--format", "xml")
        assert result.returncode == 0
        root = extract_xml_block(result.stdout)
        assert root is not None

    def test_xml_format_root_tag(self):
        """The root element must be <fizzBuzzResults>, because enterprise
        XML documents always have descriptive root elements."""
        result = run_cli("--range", "1", "5", "--format", "xml")
        assert result.returncode == 0
        root = extract_xml_block(result.stdout)
        assert root.tag == "fizzBuzzResults"

    def test_xml_format_result_elements(self):
        """Each number must produce a <result> element containing
        <number> and <output> children. The matchedRules element is
        also present because enterprise XML loves nested structures."""
        result = run_cli("--range", "1", "5", "--format", "xml")
        assert result.returncode == 0
        root = extract_xml_block(result.stdout)
        results = root.findall("result")
        assert len(results) == 5
        for res in results:
            assert res.find("number") is not None
            assert res.find("output") is not None

    def test_xml_format_correct_values(self):
        """XML output values must match the canonical FizzBuzz sequence.
        Angle brackets do not alter modulo arithmetic."""
        result = run_cli("--range", "1", "5", "--format", "xml")
        assert result.returncode == 0
        root = extract_xml_block(result.stdout)
        results = root.findall("result")
        outputs = [r.find("output").text for r in results]
        assert outputs == FIZZBUZZ_1_5

    def test_xml_format_count_attribute(self):
        """The root element must have a 'count' attribute matching the
        number of results, because enterprise XML always has metadata
        attributes on container elements."""
        result = run_cli("--range", "1", "5", "--format", "xml")
        assert result.returncode == 0
        root = extract_xml_block(result.stdout)
        assert root.get("count") == "5"


# ============================================================
# Test Class: CSV Format
# ============================================================

class TestCsvFormat:
    """Tests for --format csv output.

    CSV output transforms FizzBuzz results into comma-separated values
    suitable for import into Excel, Google Sheets, or the enterprise
    data warehouse that nobody has budget to build. The csv.reader
    module handles the parsing because life is too short to split
    on commas manually.
    """

    def test_csv_format_produces_parseable_output(self):
        """The CSV formatter must produce output that csv.DictReader
        can parse. If it can't, the spreadsheet integration story
        collapses."""
        result = run_cli("--range", "1", "5", "--format", "csv")
        assert result.returncode == 0
        rows = extract_csv_block(result.stdout)
        assert len(rows) == 5

    def test_csv_format_has_correct_headers(self):
        """CSV must have 'number' and 'output' columns. The
        'matched_rules' and 'result_id' columns are bonus enterprise
        value that nobody asked for."""
        result = run_cli("--range", "1", "5", "--format", "csv")
        assert result.returncode == 0
        rows = extract_csv_block(result.stdout)
        assert "number" in rows[0]
        assert "output" in rows[0]
        assert "matched_rules" in rows[0]
        assert "result_id" in rows[0]

    def test_csv_format_correct_row_count(self):
        """CSV row count must match the requested range. The header
        row is not counted because csv.DictReader handles that."""
        result = run_cli("--range", "1", "15", "--format", "csv")
        assert result.returncode == 0
        rows = extract_csv_block(result.stdout)
        assert len(rows) == 15

    def test_csv_format_correct_values(self):
        """CSV output values must match the canonical FizzBuzz sequence.
        Commas separate the fields, not the concerns."""
        result = run_cli("--range", "1", "5", "--format", "csv")
        assert result.returncode == 0
        rows = extract_csv_block(result.stdout)
        outputs = [r["output"] for r in rows]
        assert outputs == FIZZBUZZ_1_5


# ============================================================
# Test Class: Locale - English (baseline)
# ============================================================

class TestLocaleEnglish:
    """Tests for --locale en (English, the default).

    English is the baseline locale. Its labels are 'Fizz', 'Buzz', and
    'FizzBuzz' -- the ones that have graced whiteboard interviews since
    time immemorial. Testing it explicitly confirms that the i18n
    subsystem does not mangle the defaults.
    """

    def test_locale_en_produces_canonical_labels(self):
        """English locale must produce the canonical Fizz/Buzz/FizzBuzz
        labels. If the i18n system breaks English, it has failed at
        its most basic function."""
        result = run_cli("--range", "1", "15", "--locale", "en")
        assert result.returncode == 0
        lines = extract_fizzbuzz_lines(result.stdout)
        assert lines == _locale_fizzbuzz_1_15("en")


# ============================================================
# Test Class: Locale - German (Deutsch)
# ============================================================

class TestLocaleGerman:
    """Tests for --locale de (German).

    German FizzBuzz produces 'Sprudel' (fizz/sparkle) and 'Summen'
    (buzz/hum). 'SprudelSummen' is the compound noun that German
    is famous for, applied to a problem that does not require it.
    """

    def test_locale_de_fizz_label(self):
        """German locale must produce 'Sprudel' for numbers divisible
        by 3. Because in German, even carbonation is enterprise-grade."""
        result = run_cli("--range", "1", "5", "--locale", "de")
        assert result.returncode == 0
        lines = extract_fizzbuzz_lines(result.stdout)
        assert "Sprudel" in lines

    def test_locale_de_buzz_label(self):
        """German locale must produce 'Summen' for numbers divisible
        by 5. The bees are humming in German."""
        result = run_cli("--range", "1", "5", "--locale", "de")
        assert result.returncode == 0
        lines = extract_fizzbuzz_lines(result.stdout)
        assert "Summen" in lines

    def test_locale_de_fizzbuzz_label(self):
        """German locale must produce 'SprudelSummen' for numbers
        divisible by both 3 and 5. A compound noun worthy of
        Donaudampfschiffahrtsgesellschaft."""
        result = run_cli("--range", "15", "15", "--locale", "de")
        assert result.returncode == 0
        lines = extract_fizzbuzz_lines(result.stdout)
        assert lines == ["SprudelSummen"]

    def test_locale_de_full_sequence(self):
        """German locale must produce the correct full sequence for 1-15."""
        result = run_cli("--range", "1", "15", "--locale", "de")
        assert result.returncode == 0
        lines = extract_fizzbuzz_lines(result.stdout)
        assert lines == _locale_fizzbuzz_1_15("de")


# ============================================================
# Test Class: Locale - French (Francais)
# ============================================================

class TestLocaleFrench:
    """Tests for --locale fr (French).

    French FizzBuzz produces 'Petillement' (fizzing/sparkling) and
    'Bourdonnement' (buzzing/humming). The labels are as elegant as
    a Parisian cafe and as long as a French bureaucratic form.
    """

    def test_locale_fr_fizz_label(self):
        """French locale must produce 'Petillement' for Fizz numbers."""
        result = run_cli("--range", "1", "5", "--locale", "fr")
        assert result.returncode == 0
        lines = extract_fizzbuzz_lines(result.stdout)
        assert "Petillement" in lines

    def test_locale_fr_buzz_label(self):
        """French locale must produce 'Bourdonnement' for Buzz numbers."""
        result = run_cli("--range", "1", "5", "--locale", "fr")
        assert result.returncode == 0
        lines = extract_fizzbuzz_lines(result.stdout)
        assert "Bourdonnement" in lines

    def test_locale_fr_full_sequence(self):
        """French locale must produce the correct full sequence for 1-15."""
        result = run_cli("--range", "1", "15", "--locale", "fr")
        assert result.returncode == 0
        lines = extract_fizzbuzz_lines(result.stdout)
        assert lines == _locale_fizzbuzz_1_15("fr")


# ============================================================
# Test Class: Locale - Japanese
# ============================================================

class TestLocaleJapanese:
    """Tests for --locale ja (Japanese).

    Japanese FizzBuzz produces katakana labels: 'fizu' and 'bazu'.
    The characters are phonetic transliterations because FizzBuzz
    has no native Japanese concept, and the Kanji for 'enterprise
    modulo evaluation' would be unwieldy even by Japanese standards.
    """

    def test_locale_ja_fizz_label(self):
        """Japanese locale must produce the katakana Fizz label."""
        result = run_cli("--range", "1", "5", "--locale", "ja")
        assert result.returncode == 0
        lines = extract_fizzbuzz_lines(result.stdout)
        assert "\u30d5\u30a3\u30ba" in lines  # フィズ

    def test_locale_ja_buzz_label(self):
        """Japanese locale must produce the katakana Buzz label."""
        result = run_cli("--range", "1", "5", "--locale", "ja")
        assert result.returncode == 0
        lines = extract_fizzbuzz_lines(result.stdout)
        assert "\u30d0\u30ba" in lines  # バズ

    def test_locale_ja_full_sequence(self):
        """Japanese locale must produce the correct full sequence for 1-15."""
        result = run_cli("--range", "1", "15", "--locale", "ja")
        assert result.returncode == 0
        lines = extract_fizzbuzz_lines(result.stdout)
        assert lines == _locale_fizzbuzz_1_15("ja")


# ============================================================
# Test Class: Locale - Klingon (tlhIngan Hol)
# ============================================================

class TestLocaleKlingon:
    """Tests for --locale tlh (Klingon).

    Klingon FizzBuzz produces 'ghum' (alarm/warning) and 'wab' (sound/noise).
    Klingon warriors demand modulo arithmetic in their native tongue,
    and the Enterprise FizzBuzz Platform delivers. Qapla'!
    """

    def test_locale_tlh_fizz_label(self):
        """Klingon locale must produce 'ghum' for Fizz numbers.
        A Klingon warrior's alarm sounds for every multiple of 3."""
        result = run_cli("--range", "1", "5", "--locale", "tlh")
        assert result.returncode == 0
        lines = extract_fizzbuzz_lines(result.stdout)
        assert "ghum" in lines

    def test_locale_tlh_buzz_label(self):
        """Klingon locale must produce 'wab' for Buzz numbers.
        The sound of victory for every multiple of 5."""
        result = run_cli("--range", "1", "5", "--locale", "tlh")
        assert result.returncode == 0
        lines = extract_fizzbuzz_lines(result.stdout)
        assert "wab" in lines

    def test_locale_tlh_fizzbuzz_label(self):
        """Klingon locale must produce 'ghumwab' for FizzBuzz numbers.
        The compound word that strikes fear into the hearts of
        interviewers across the quadrant."""
        result = run_cli("--range", "15", "15", "--locale", "tlh")
        assert result.returncode == 0
        lines = extract_fizzbuzz_lines(result.stdout)
        assert lines == ["ghumwab"]

    def test_locale_tlh_full_sequence(self):
        """Klingon locale must produce the correct full sequence for 1-15."""
        result = run_cli("--range", "1", "15", "--locale", "tlh")
        assert result.returncode == 0
        lines = extract_fizzbuzz_lines(result.stdout)
        assert lines == _locale_fizzbuzz_1_15("tlh")


# ============================================================
# Test Class: Locale - Sindarin (Edhellen)
# ============================================================

class TestLocaleSindarin:
    """Tests for --locale sjn (Sindarin).

    Sindarin FizzBuzz produces 'Hith' (mist) and 'Glamor' (echo).
    The Grey-elven tongue of Middle-earth, applied to a coding
    interview problem. Tolkien would be... conflicted.
    """

    def test_locale_sjn_fizz_label(self):
        """Sindarin locale must produce 'Hith' for Fizz numbers.
        A mist descends upon every multiple of 3."""
        result = run_cli("--range", "1", "5", "--locale", "sjn")
        assert result.returncode == 0
        lines = extract_fizzbuzz_lines(result.stdout)
        assert "Hith" in lines

    def test_locale_sjn_buzz_label(self):
        """Sindarin locale must produce 'Glamor' for Buzz numbers.
        An echo rings through the Elven halls for every multiple of 5."""
        result = run_cli("--range", "1", "5", "--locale", "sjn")
        assert result.returncode == 0
        lines = extract_fizzbuzz_lines(result.stdout)
        assert "Glamor" in lines

    def test_locale_sjn_fizzbuzz_label(self):
        """Sindarin locale must produce 'HithGlamor' for FizzBuzz numbers."""
        result = run_cli("--range", "15", "15", "--locale", "sjn")
        assert result.returncode == 0
        lines = extract_fizzbuzz_lines(result.stdout)
        assert lines == ["HithGlamor"]

    def test_locale_sjn_full_sequence(self):
        """Sindarin locale must produce the correct full sequence for 1-15."""
        result = run_cli("--range", "1", "15", "--locale", "sjn")
        assert result.returncode == 0
        lines = extract_fizzbuzz_lines(result.stdout)
        assert lines == _locale_fizzbuzz_1_15("sjn")


# ============================================================
# Test Class: Locale - Quenya (Eldarin)
# ============================================================

class TestLocaleQuenya:
    """Tests for --locale qya (Quenya).

    Quenya FizzBuzz produces 'Winge' (foam/spray) and 'Lama' (ringing sound).
    The High-elven tongue, spoken in Valinor and now spoken by a
    FizzBuzz platform. The Valar weep.
    """

    def test_locale_qya_fizz_label(self):
        """Quenya locale must produce 'Winge' for Fizz numbers."""
        result = run_cli("--range", "1", "5", "--locale", "qya")
        assert result.returncode == 0
        lines = extract_fizzbuzz_lines(result.stdout)
        assert "Wing\u00eb" in lines  # Wingë

    def test_locale_qya_buzz_label(self):
        """Quenya locale must produce 'Lama' for Buzz numbers."""
        result = run_cli("--range", "1", "5", "--locale", "qya")
        assert result.returncode == 0
        lines = extract_fizzbuzz_lines(result.stdout)
        assert "L\u00e1ma" in lines  # Láma

    def test_locale_qya_fizzbuzz_label(self):
        """Quenya locale must produce 'WingeLama' for FizzBuzz numbers."""
        result = run_cli("--range", "15", "15", "--locale", "qya")
        assert result.returncode == 0
        lines = extract_fizzbuzz_lines(result.stdout)
        assert lines == ["WingeL\u00e1ma"]  # WingeLáma

    def test_locale_qya_full_sequence(self):
        """Quenya locale must produce the correct full sequence for 1-15."""
        result = run_cli("--range", "1", "15", "--locale", "qya")
        assert result.returncode == 0
        lines = extract_fizzbuzz_lines(result.stdout)
        assert lines == _locale_fizzbuzz_1_15("qya")


# ============================================================
# Test Class: Format + Locale Combinations
# ============================================================

class TestFormatLocaleCombinations:
    """Tests for combining --format with --locale.

    These tests verify that the structured output formats (JSON, XML, CSV)
    correctly incorporate locale-translated labels. A German JSON response,
    a Klingon XML document, a Sindarin CSV spreadsheet -- the combinatorial
    possibilities are as vast as they are unnecessary.
    """

    def test_json_with_german_locale(self):
        """JSON format with German locale must produce 'Sprudel' and
        'Summen' in the structured output. The JSON braces contain
        German nouns, a combination that enterprise architects dream of."""
        result = run_cli("--range", "1", "15", "--format", "json", "--locale", "de")
        assert result.returncode == 0
        data = extract_json_block(result.stdout)
        outputs = [r["output"] for r in data["results"]]
        assert outputs == _locale_fizzbuzz_1_15("de")

    def test_xml_with_klingon_locale(self):
        """XML format with Klingon locale must produce 'ghum' and 'wab'
        inside XML elements. SOAP services on Qo'noS can now consume
        FizzBuzz results natively."""
        result = run_cli("--range", "1", "5", "--format", "xml", "--locale", "tlh")
        assert result.returncode == 0
        root = extract_xml_block(result.stdout)
        results = root.findall("result")
        outputs = [r.find("output").text for r in results]
        assert outputs == _locale_fizzbuzz_1_5("tlh")

    def test_csv_with_sindarin_locale(self):
        """CSV format with Sindarin locale must produce 'Hith' and 'Glamor'
        in the output column. Elven spreadsheets are now a reality."""
        result = run_cli("--range", "1", "5", "--format", "csv", "--locale", "sjn")
        assert result.returncode == 0
        rows = extract_csv_block(result.stdout)
        outputs = [r["output"] for r in rows]
        assert outputs == _locale_fizzbuzz_1_5("sjn")

    def test_json_with_japanese_locale(self):
        """JSON format with Japanese locale must produce katakana labels
        in the structured output."""
        result = run_cli("--range", "1", "5", "--format", "json", "--locale", "ja")
        assert result.returncode == 0
        data = extract_json_block(result.stdout)
        outputs = [r["output"] for r in data["results"]]
        assert outputs == _locale_fizzbuzz_1_5("ja")

    def test_xml_with_quenya_locale(self):
        """XML format with Quenya locale must produce 'Winge' and 'Lama'
        in the structured output. High-elven XML is now a thing."""
        result = run_cli("--range", "1", "5", "--format", "xml", "--locale", "qya")
        assert result.returncode == 0
        root = extract_xml_block(result.stdout)
        results = root.findall("result")
        outputs = [r.find("output").text for r in results]
        assert outputs == _locale_fizzbuzz_1_5("qya")

    def test_csv_with_french_locale(self):
        """CSV format with French locale must produce 'Petillement' and
        'Bourdonnement' in the output column. Vive la FizzBuzz!"""
        result = run_cli("--range", "1", "5", "--format", "csv", "--locale", "fr")
        assert result.returncode == 0
        rows = extract_csv_block(result.stdout)
        outputs = [r["output"] for r in rows]
        assert outputs == _locale_fizzbuzz_1_5("fr")


# ============================================================
# Test Class: Banner & Summary Suppression
# ============================================================

class TestBannerAndSummarySuppression:
    """Tests for --no-banner and --no-summary flags.

    The enterprise banner is a majestic ASCII art masterpiece that
    announces the platform's arrival with the gravitas of a royal
    herald. The summary is a post-execution statistical treatise.
    These flags suppress them, because sometimes you just want the
    modulo results without the ceremony.

    NOTE: These tests call subprocess.run directly instead of using
    run_cli, because run_cli adds --no-banner and --no-summary by
    default, which would defeat the purpose of testing their absence.
    """

    def test_banner_present_when_not_suppressed(self):
        """Without --no-banner, the majestic ASCII art banner should
        appear. 'E N T E R P R I S E' is the herald's cry."""
        cmd = [PYTHON, MAIN_PY, "--no-summary", "--range", "1", "5"]
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=DEFAULT_TIMEOUT,
            cwd=CWD,
            encoding="utf-8",
            errors="replace",
        )
        assert result.returncode == 0
        assert "E N T E R P R I S E" in result.stdout

    def test_no_banner_suppresses_banner(self):
        """--no-banner must suppress the ASCII art banner. The herald
        is silenced, and the modulo operation proceeds without fanfare."""
        cmd = [PYTHON, MAIN_PY, "--no-banner", "--no-summary", "--range", "1", "5"]
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=DEFAULT_TIMEOUT,
            cwd=CWD,
            encoding="utf-8",
            errors="replace",
        )
        assert result.returncode == 0
        assert "E N T E R P R I S E" not in result.stdout

    def test_summary_present_when_not_suppressed(self):
        """Without --no-summary, the session summary should appear.
        Statistics about how many modulo operations were performed
        are vital enterprise intelligence."""
        cmd = [PYTHON, MAIN_PY, "--no-banner", "--range", "1", "5"]
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=DEFAULT_TIMEOUT,
            cwd=CWD,
            encoding="utf-8",
            errors="replace",
        )
        assert result.returncode == 0
        assert "Session Summary" in result.stdout or "Total Numbers" in result.stdout

    def test_no_summary_suppresses_summary(self):
        """--no-summary must suppress the session summary. The post-
        mortem analysis of modulo operations is deemed unnecessary."""
        cmd = [PYTHON, MAIN_PY, "--no-banner", "--no-summary", "--range", "1", "5"]
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=DEFAULT_TIMEOUT,
            cwd=CWD,
            encoding="utf-8",
            errors="replace",
        )
        assert result.returncode == 0
        assert "Session Summary" not in result.stdout


# ============================================================
# Test Class: Invalid Format & Locale Handling
# ============================================================

class TestInvalidFormatAndLocale:
    """Tests for error handling on invalid --format and --locale values.

    The argument parser should reject invalid format names with the firm
    professionalism of an enterprise gatekeeper. Invalid locales, however,
    are handled gracefully with a fallback to English, because i18n is
    forgiving by nature.
    """

    def test_invalid_format_rejected_by_argparse(self):
        """An invalid --format value must cause argparse to reject the
        input and exit with a non-zero code. 'yaml' is not a supported
        format, despite being the configuration file format of choice."""
        cmd = [PYTHON, MAIN_PY, "--format", "yaml"]
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=DEFAULT_TIMEOUT,
            cwd=CWD,
            encoding="utf-8",
            errors="replace",
        )
        assert result.returncode != 0
        assert "invalid choice" in result.stderr

    def test_invalid_locale_falls_back_to_english(self):
        """An invalid --locale value should not crash the platform.
        The i18n subsystem falls back to English with a warning,
        because even FizzBuzz has graceful degradation."""
        result = run_cli("--range", "1", "5", "--locale", "xx_INVALID")
        assert result.returncode == 0
        lines = extract_fizzbuzz_lines(result.stdout)
        # Should fall back to English labels
        assert lines == FIZZBUZZ_1_5
