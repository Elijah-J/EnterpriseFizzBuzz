"""
Enterprise FizzBuzz Platform - Lines of Code Census Bureau Test Suite

Comprehensive tests for the codebase metrics engine that quantifies the
true scale of the Enterprise FizzBuzz Platform. Because an untested
metrics tool in a repo with 800+ tests would be an embarrassment to
Bob McFizzington, and Bob has suffered enough.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from enterprise_fizzbuzz.infrastructure.utils.loc import (
    CategoryStats,
    CensusDashboard,
    CensusEngine,
    CensusReport,
    FileClassifier,
    FileMetrics,
    LineCounter,
    MINIMAL_SOLUTION_LINES,
)


# ============================================================
# Fixtures
# ============================================================


@pytest.fixture
def simple_py_file(tmp_path: Path) -> Path:
    """A Python file with known line composition: 3 code, 1 blank, 2 comments."""
    content = "# a comment\nimport os\n\n# another comment\nx = 1\ny = 2\n"
    f = tmp_path / "simple.py"
    f.write_text(content, encoding="utf-8")
    return f


@pytest.fixture
def simple_yaml_file(tmp_path: Path) -> Path:
    """A YAML file with 2 code lines, 1 comment, 1 blank."""
    content = "# yaml comment\nkey: value\n\nanother_key: 42\n"
    f = tmp_path / "config.yaml"
    f.write_text(content, encoding="utf-8")
    return f


@pytest.fixture
def fizztranslation_file(tmp_path: Path) -> Path:
    """A proprietary .fizztranslation file. The ;; comment prefix is a trade secret."""
    content = ";; This is a proprietary comment\nFizz=Sprudel\n\nBuzz=Brause\n"
    f = tmp_path / "de.fizztranslation"
    f.write_text(content, encoding="utf-8")
    return f


@pytest.fixture
def empty_file(tmp_path: Path) -> Path:
    """A file with zero lines. Existentially void, yet still counted."""
    f = tmp_path / "empty.py"
    f.write_text("", encoding="utf-8")
    return f


@pytest.fixture
def populated_tmp_repo(tmp_path: Path) -> Path:
    """A miniature Enterprise FizzBuzz repo with known files for census testing."""
    # Source Python file
    src_dir = tmp_path / "enterprise_fizzbuzz" / "domain"
    src_dir.mkdir(parents=True)
    (src_dir / "fizz.py").write_text("# domain logic\nclass Fizz:\n    pass\n", encoding="utf-8")

    # Test Python file
    test_dir = tmp_path / "tests"
    test_dir.mkdir()
    (test_dir / "test_fizz.py").write_text("# test\ndef test_fizz():\n    assert True\n", encoding="utf-8")

    # Markdown doc
    (tmp_path / "README.md").write_text("# README\n\nHello world.\n", encoding="utf-8")

    # YAML config
    (tmp_path / "config.yaml").write_text("key: value\n# a comment\n", encoding="utf-8")

    # Locale file
    locale_dir = tmp_path / "locales"
    locale_dir.mkdir()
    (locale_dir / "en.fizztranslation").write_text(";; English\nFizz=Fizz\nBuzz=Buzz\n", encoding="utf-8")

    return tmp_path


# ============================================================
# LineCounter Tests
# ============================================================


class TestLineCounter:
    """Tests for the engine that counts lines with the gravity they deserve."""

    def test_count_python_file(self, simple_py_file: Path):
        """A Python file with known content must produce exact line counts.
        Getting this wrong would invalidate the entire census."""
        total, code, blank, comments = LineCounter.count(simple_py_file)
        assert total == 6
        assert code == 3
        assert blank == 1
        assert comments == 2

    def test_count_yaml_file(self, simple_yaml_file: Path):
        """YAML files use # for comments, just like Python. The census
        bureau recognises this shared heritage."""
        total, code, blank, comments = LineCounter.count(simple_yaml_file)
        assert total == 4
        assert code == 2
        assert blank == 1
        assert comments == 1

    def test_count_fizztranslation_file(self, fizztranslation_file: Path):
        """The proprietary .fizztranslation format uses ;; for comments.
        This is a trade secret. Please do not share with competitors."""
        total, code, blank, comments = LineCounter.count(fizztranslation_file)
        assert total == 4
        assert code == 2
        assert blank == 1
        assert comments == 1

    def test_count_empty_file(self, empty_file: Path):
        """A file with zero lines contributes zero to every metric.
        It exists solely to increase the file count."""
        total, code, blank, comments = LineCounter.count(empty_file)
        assert total == 0
        assert code == 0
        assert blank == 0
        assert comments == 0

    def test_count_nonexistent_file(self, tmp_path: Path):
        """Attempting to count lines in a nonexistent file returns zeros,
        because the census bureau is graceful under pressure."""
        total, code, blank, comments = LineCounter.count(tmp_path / "ghost.py")
        assert total == 0
        assert code == 0
        assert blank == 0
        assert comments == 0

    def test_count_markdown_has_no_comments(self, tmp_path: Path):
        """Markdown files have no comment syntax. Every line is content,
        because in Markdown, nothing is hidden."""
        f = tmp_path / "doc.md"
        f.write_text("# Heading\n\nParagraph.\n", encoding="utf-8")
        total, code, blank, comments = LineCounter.count(f)
        assert total == 3
        assert comments == 0
        assert code == 2
        assert blank == 1

    def test_count_file_with_only_blanks(self, tmp_path: Path):
        """A file of nothing but blank lines. All blank, no code, no comments.
        A monument to whitespace."""
        f = tmp_path / "blanks.py"
        f.write_text("\n\n\n\n", encoding="utf-8")
        total, code, blank, comments = LineCounter.count(f)
        assert total == 4
        assert blank == 4
        assert code == 0
        assert comments == 0

    def test_count_file_with_only_comments(self, tmp_path: Path):
        """A Python file that is nothing but comments. All commentary,
        no action. Like a standup that goes long."""
        f = tmp_path / "commentary.py"
        f.write_text("# one\n# two\n# three\n", encoding="utf-8")
        total, code, blank, comments = LineCounter.count(f)
        assert total == 3
        assert comments == 3
        assert code == 0
        assert blank == 0


# ============================================================
# FileClassifier Tests
# ============================================================


class TestFileClassifier:
    """Tests for the engine that sorts files into their proper social strata."""

    @pytest.mark.parametrize(
        "filename, expected_language",
        [
            ("main.py", "Python"),
            ("config.yaml", "YAML"),
            ("config.yml", "YAML"),
            ("translations.fizztranslation", "FizzTranslation (proprietary)"),
            ("README.md", "Markdown"),
            ("pyproject.toml", "TOML"),
            ("setup.cfg", "Config"),
            ("requirements.txt", "Text"),
            ("unknown.xyz", "Other"),
        ],
    )
    def test_classify_language_by_extension(self, tmp_path: Path, filename: str, expected_language: str):
        """Every file extension maps to the correct language classification.
        Misclassification would compromise the census bureau's credibility."""
        filepath = tmp_path / filename
        assert FileClassifier.classify_language(filepath) == expected_language

    def test_classify_language_gitignore(self, tmp_path: Path):
        """The .gitignore file is classified by name, not extension,
        because it is special and knows it."""
        filepath = tmp_path / ".gitignore"
        assert FileClassifier.classify_language(filepath) == "Git"

    @pytest.mark.parametrize(
        "rel_path, expected_layer_substring",
        [
            ("domain/models.py", "Domain"),
            ("application/services.py", "Application"),
            ("infrastructure/db.py", "Infrastructure"),
            ("tests/test_fizz.py", "Tests"),
            ("locales/en.fizztranslation", "Locales"),
        ],
    )
    def test_classify_layer_for_known_directories(self, tmp_path: Path, rel_path: str, expected_layer_substring: str):
        """Files under architectural directories must be assigned to
        the correct layer. Hexagonal integrity depends on it."""
        filepath = tmp_path / rel_path
        layer = FileClassifier.classify_layer(filepath, tmp_path)
        assert expected_layer_substring in layer

    def test_classify_layer_root_file(self, tmp_path: Path):
        """A file at the repository root belongs to no layer.
        It is a free agent, unbound by hexagonal convention."""
        filepath = tmp_path / "main.py"
        layer = FileClassifier.classify_layer(filepath, tmp_path)
        assert layer == "Root / Other"

    def test_is_test_file_by_prefix(self, tmp_path: Path):
        """Files starting with test_ are test files. This is the law."""
        filepath = tmp_path / "test_fizzbuzz.py"
        assert FileClassifier.is_test_file(filepath) is True

    def test_is_test_file_by_suffix(self, tmp_path: Path):
        """Files ending with _test.py are also test files.
        The census bureau respects both naming conventions."""
        filepath = tmp_path / "fizzbuzz_test.py"
        assert FileClassifier.is_test_file(filepath) is True

    def test_is_test_file_by_directory(self, tmp_path: Path):
        """Any file under a tests/ directory is a test file,
        regardless of its name."""
        filepath = tmp_path / "tests" / "conftest.py"
        assert FileClassifier.is_test_file(filepath) is True

    def test_is_not_test_file(self, tmp_path: Path):
        """A regular source file is not a test file.
        It has production responsibilities."""
        filepath = tmp_path / "enterprise_fizzbuzz" / "domain" / "models.py"
        assert FileClassifier.is_test_file(filepath) is False


# ============================================================
# CensusEngine Tests
# ============================================================


class TestCensusEngine:
    """Tests for the beating heart of the Lines of Code Census Bureau."""

    def test_run_on_populated_directory(self, populated_tmp_repo: Path):
        """Running the census on a known directory must produce correct
        grand totals. Every line must be accounted for."""
        engine = CensusEngine(populated_tmp_repo)
        report = engine.run()

        assert report.grand_total_files == 5
        # fizz.py=3, test_fizz.py=3, README.md=3, config.yaml=2, en.fizztranslation=3
        assert report.grand_total_lines == 14

    def test_run_tracks_per_language_breakdown(self, populated_tmp_repo: Path):
        """The by-language breakdown must contain entries for each language
        present in the repository."""
        engine = CensusEngine(populated_tmp_repo)
        report = engine.run()

        assert "Python" in report.by_language
        assert "YAML" in report.by_language
        assert "Markdown" in report.by_language
        assert "FizzTranslation (proprietary)" in report.by_language

    def test_run_tracks_per_layer_breakdown(self, populated_tmp_repo: Path):
        """The by-layer breakdown must reflect the hexagonal architecture."""
        engine = CensusEngine(populated_tmp_repo)
        report = engine.run()

        layer_names = list(report.by_layer.keys())
        has_domain = any("Domain" in l for l in layer_names)
        has_tests = any("Tests" in l for l in layer_names)
        assert has_domain, "Domain layer should be present"
        assert has_tests, "Tests layer should be present"

    def test_run_composition_tracking(self, populated_tmp_repo: Path):
        """The census must correctly separate source Python from test Python.
        Conflating them would undermine the test-to-source ratio."""
        engine = CensusEngine(populated_tmp_repo)
        report = engine.run()

        assert report.source_python_files == 1
        assert report.source_python_lines == 3
        assert report.test_python_files == 1
        assert report.test_python_lines == 3

    def test_run_doc_and_locale_tracking(self, populated_tmp_repo: Path):
        """Documentation and locale files must be tracked separately,
        because they serve fundamentally different purposes."""
        engine = CensusEngine(populated_tmp_repo)
        report = engine.run()

        assert report.doc_files == 1
        assert report.doc_lines == 3
        assert report.locale_files == 1
        assert report.locale_lines == 3

    def test_run_test_to_source_ratio(self, populated_tmp_repo: Path):
        """A 1:1 test-to-source ratio is the minimum for enterprise compliance."""
        engine = CensusEngine(populated_tmp_repo)
        report = engine.run()

        assert report.test_to_source_ratio == pytest.approx(1.0)

    def test_run_on_empty_directory(self, tmp_path: Path):
        """An empty directory produces a report with all zeros.
        The census bureau does not fabricate data."""
        engine = CensusEngine(tmp_path)
        report = engine.run()

        assert report.grand_total_files == 0
        assert report.grand_total_lines == 0
        assert report.grand_total_code == 0
        assert report.grand_total_blank == 0
        assert report.grand_total_comments == 0

    def test_run_skips_pycache(self, tmp_path: Path):
        """__pycache__ directories are excluded from the census.
        Bytecode does not deserve representation."""
        pycache = tmp_path / "__pycache__"
        pycache.mkdir()
        (pycache / "cached.pyc").write_text("fake bytecode\n", encoding="utf-8")
        (tmp_path / "real.py").write_text("x = 1\n", encoding="utf-8")

        engine = CensusEngine(tmp_path)
        report = engine.run()

        assert report.grand_total_files == 1

    def test_run_timestamp_present(self, populated_tmp_repo: Path):
        """The census report must bear a timestamp, because auditors
        need to know when the count was taken."""
        engine = CensusEngine(populated_tmp_repo)
        report = engine.run()

        assert report.timestamp != ""
        assert "T" in report.timestamp  # ISO 8601 format


# ============================================================
# Overengineering Index Tests
# ============================================================


class TestOverengineeringIndex:
    """Tests for the metric that quantifies how far we've strayed from simplicity."""

    def test_oei_calculation(self, populated_tmp_repo: Path):
        """The OEI is total lines divided by MINIMAL_SOLUTION_LINES.
        For our test repo with 14 lines, OEI should be 7.0."""
        engine = CensusEngine(populated_tmp_repo)
        report = engine.run()

        expected_oei = report.grand_total_lines / MINIMAL_SOLUTION_LINES
        assert report.overengineering_index == pytest.approx(expected_oei)

    def test_oei_rating_hobbyist(self, tmp_path: Path):
        """An OEI below 100 earns the 'Hobbyist' rating.
        Needs more middleware."""
        # 10 lines -> OEI = 5.0
        (tmp_path / "tiny.py").write_text("x = 1\n" * 10, encoding="utf-8")
        engine = CensusEngine(tmp_path)
        report = engine.run()

        assert report.overengineering_index < 100
        dashboard = CensusDashboard()
        output = dashboard.render(report)
        assert "Hobbyist" in output

    def test_oei_rating_startup(self, tmp_path: Path):
        """An OEI between 100 and 1,000 earns the 'Startup' rating.
        Promising but under-abstracted."""
        # 500 lines -> OEI = 250.0
        (tmp_path / "medium.py").write_text("x = 1\n" * 500, encoding="utf-8")
        engine = CensusEngine(tmp_path)
        report = engine.run()

        assert 100 <= report.overengineering_index < 1_000
        dashboard = CensusDashboard()
        output = dashboard.render(report)
        assert "Startup" in output

    def test_oei_rating_enterprise(self, tmp_path: Path):
        """An OEI between 5,000 and 10,000 earns the 'Enterprise' rating.
        Stakeholders would approve."""
        # 12,000 lines -> OEI = 6,000
        (tmp_path / "enterprise.py").write_text("x = 1\n" * 12_000, encoding="utf-8")
        engine = CensusEngine(tmp_path)
        report = engine.run()

        assert 5_000 <= report.overengineering_index < 10_000
        dashboard = CensusDashboard()
        output = dashboard.render(report)
        assert "Enterprise" in output

    def test_lines_per_fizzbuzz_rule(self, populated_tmp_repo: Path):
        """Lines per FizzBuzz rule is total lines divided by 2.
        Each of the two rules (Fizz, Buzz) shares the burden equally."""
        engine = CensusEngine(populated_tmp_repo)
        report = engine.run()

        assert report.lines_per_fizzbuzz_rule == pytest.approx(report.grand_total_lines / 2)


# ============================================================
# CensusDashboard Tests
# ============================================================


class TestCensusDashboard:
    """Tests for the ASCII dashboard that communicates the census results
    to executives who will never read them."""

    @pytest.fixture
    def rendered_dashboard(self, populated_tmp_repo: Path) -> str:
        """A pre-rendered dashboard for a known repository."""
        engine = CensusEngine(populated_tmp_repo)
        report = engine.run()
        dashboard = CensusDashboard()
        return dashboard.render(report)

    def test_dashboard_contains_language_breakdown(self, rendered_dashboard: str):
        """The dashboard must contain a language breakdown section,
        because executives love pie charts and this is the ASCII equivalent."""
        assert "BREAKDOWN BY LANGUAGE" in rendered_dashboard

    def test_dashboard_contains_layer_breakdown(self, rendered_dashboard: str):
        """The architectural layer breakdown proves we have a hexagonal
        architecture, not just a pile of files."""
        assert "BREAKDOWN BY ARCHITECTURAL LAYER" in rendered_dashboard

    def test_dashboard_contains_overengineering_index(self, rendered_dashboard: str):
        """The OEI section is the crown jewel of the dashboard."""
        assert "OVERENGINEERING INDEX" in rendered_dashboard

    def test_dashboard_contains_oncall_attribution(self, rendered_dashboard: str):
        """Bob McFizzington must be credited for 100% of lines maintained.
        Everyone else maintains exactly 0."""
        assert "ON-CALL ATTRIBUTION" in rendered_dashboard

    def test_dashboard_credits_bob_with_everything(self, rendered_dashboard: str):
        """Bob McFizzington is credited with all lines. Everyone else
        is credited with zero. This is enterprise accountability."""
        assert "Bob McFizzington" in rendered_dashboard
        assert "everyone else" in rendered_dashboard.lower()

    def test_dashboard_contains_composition(self, rendered_dashboard: str):
        """The composition section separates source from test from docs."""
        assert "COMPOSITION" in rendered_dashboard

    def test_dashboard_contains_top_files(self, rendered_dashboard: str):
        """The top files section ranks the largest files. In the real repo,
        this is a leaderboard of overengineering."""
        assert "TOP" in rendered_dashboard
        assert "LARGEST FILES" in rendered_dashboard

    def test_dashboard_contains_grand_total(self, rendered_dashboard: str):
        """The footer must contain the grand total, because the whole
        point is knowing the number."""
        assert "GRAND TOTAL" in rendered_dashboard

    def test_dashboard_mentions_divisibility(self, rendered_dashboard: str):
        """The footer reminds us that all of this exists to determine
        whether numbers are divisible by 3 and 5."""
        assert "divisible by 3 and 5" in rendered_dashboard


# ============================================================
# Data Model Tests
# ============================================================


class TestDataModels:
    """Tests for the census data models, because even metrics need structure."""

    def test_file_metrics_is_frozen(self):
        """FileMetrics is a frozen dataclass. Once a file's lines are counted,
        the record is immutable. Like a blockchain, but useful."""
        fm = FileMetrics(
            path="main.py",
            language="Python",
            total_lines=100,
            code_lines=80,
            blank_lines=10,
            comment_lines=10,
            layer="Root / Other",
        )
        with pytest.raises(AttributeError):
            fm.total_lines = 200  # type: ignore[misc]

    def test_category_stats_defaults_to_zero(self):
        """A fresh CategoryStats has all zeros. No lines, no files,
        no meaning."""
        stats = CategoryStats()
        assert stats.files == 0
        assert stats.total == 0
        assert stats.code == 0
        assert stats.blank == 0
        assert stats.comments == 0

    def test_census_report_defaults(self):
        """A fresh CensusReport is a blank canvas of unrealized metrics."""
        report = CensusReport()
        assert report.grand_total_lines == 0
        assert report.grand_total_files == 0
        assert report.overengineering_index == 0.0
        assert report.file_metrics == []
        assert report.by_language == {}
