"""
Enterprise FizzBuzz Platform - Lines of Code Census Bureau
==========================================================

A production-grade, enterprise-ready codebase metrics engine for
quantifying the true scale of the Enterprise FizzBuzz Platform.

Because you can't manage what you can't measure, and you can't
overengineer what you can't quantify.

Features:
    - Multi-language line counting with comment detection
    - Proprietary .fizztranslation format support
    - Source/test/documentation composition analysis
    - Test-to-source ratio calculation (for compliance)
    - Top-N largest file ranking
    - ASCII census dashboard with box-drawing characters
    - Per-directory subtotals for architectural layer analysis
    - Overengineering Index (OEI) calculation
    - Bob McFizzington productivity attribution

The Overengineering Index (OEI) is a proprietary metric defined as:

    OEI = total_lines / minimal_solution_lines

where minimal_solution_lines is 2 (a for-loop with a ternary).
An OEI above 1,000 is considered "enterprise-grade." An OEI
above 10,000 indicates that the project has achieved escape
velocity from the gravitational pull of simplicity.

Dependencies: None (pure stdlib, as is tradition).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional


# ============================================================
# Configuration
# ============================================================

REPO_ROOT = Path(__file__).parent.parent.parent.parent

SKIP_DIRS = {".git", "__pycache__", ".pytest_cache", "node_modules", ".venv", "venv"}

# The canonical FizzBuzz solution against which all overengineering
# is measured. Two lines. One for-loop. One ternary. Perfection.
MINIMAL_SOLUTION_LINES = 2

LANGUAGE_MAP = {
    ".py": "Python",
    ".md": "Markdown",
    ".yaml": "YAML",
    ".yml": "YAML",
    ".fizztranslation": "FizzTranslation (proprietary)",
    ".toml": "TOML",
    ".cfg": "Config",
    ".txt": "Text",
    ".gitignore": "Git",
}

# Architectural layer detection for hexagonal analysis.
# If a file lives under one of these paths, it belongs to that layer.
LAYER_PATTERNS = {
    "domain": "Domain (business logic for n % 3)",
    "application": "Application (use cases for n % 3)",
    "infrastructure": "Infrastructure (how n % 3 reaches the outside world)",
    "tests": "Tests (proving n % 3 still works)",
    "locales": "Locales (saying 'Fizz' in 7 languages)",
    "docs": "Documentation",
}


# ============================================================
# Data Models
# ============================================================

@dataclass(frozen=True)
class FileMetrics:
    """Immutable metrics for a single file.

    Every file in the repository deserves to have its contributions
    to the overall line count permanently recorded.
    """
    path: str
    language: str
    total_lines: int
    code_lines: int
    blank_lines: int
    comment_lines: int
    layer: str


@dataclass
class CategoryStats:
    """Aggregate statistics for a language category."""
    files: int = 0
    total: int = 0
    code: int = 0
    blank: int = 0
    comments: int = 0


@dataclass
class CensusReport:
    """The complete census of the Enterprise FizzBuzz Platform.

    Contains every metric necessary for executive review,
    compliance audit, and existential reflection.
    """
    timestamp: str = ""
    file_metrics: list[FileMetrics] = field(default_factory=list)
    by_language: dict[str, CategoryStats] = field(default_factory=dict)
    by_layer: dict[str, CategoryStats] = field(default_factory=dict)
    grand_total_lines: int = 0
    grand_total_code: int = 0
    grand_total_blank: int = 0
    grand_total_comments: int = 0
    grand_total_files: int = 0
    source_python_lines: int = 0
    source_python_files: int = 0
    test_python_lines: int = 0
    test_python_files: int = 0
    doc_lines: int = 0
    doc_files: int = 0
    locale_lines: int = 0
    locale_files: int = 0
    test_to_source_ratio: float = 0.0
    overengineering_index: float = 0.0
    lines_per_fizzbuzz_rule: float = 0.0


# ============================================================
# Line Counter Engine
# ============================================================

class LineCounter:
    """Counts lines in a single file with language-aware comment detection.

    Supports Python (#), YAML (#), and the proprietary
    .fizztranslation (;;) comment syntax. Markdown files are
    assumed to contain zero comments, because in Markdown,
    everything is content and nothing is hidden.
    """

    COMMENT_PREFIXES = {
        ".py": "#",
        ".yaml": "#",
        ".yml": "#",
        ".fizztranslation": ";;",
        ".toml": "#",
        ".cfg": "#",
    }

    @staticmethod
    def count(filepath: Path) -> tuple[int, int, int, int]:
        """Count total, code, blank, and comment lines.

        Returns:
            (total, code, blank, comments)
        """
        try:
            with open(filepath, "r", encoding="utf-8", errors="replace") as f:
                lines = f.readlines()
        except OSError:
            return 0, 0, 0, 0

        total = len(lines)
        blank = 0
        comments = 0
        comment_prefix = LineCounter.COMMENT_PREFIXES.get(filepath.suffix)

        for line in lines:
            stripped = line.strip()
            if stripped == "":
                blank += 1
            elif comment_prefix and stripped.startswith(comment_prefix):
                comments += 1

        code = total - blank - comments
        return total, code, blank, comments


# ============================================================
# File Classifier
# ============================================================

class FileClassifier:
    """Classifies files by language and architectural layer.

    Determines which language a file belongs to (Python, Markdown,
    FizzTranslation (proprietary), etc.) and which architectural
    layer it inhabits in the hexagonal structure.
    """

    @staticmethod
    def classify_language(filepath: Path) -> str:
        if filepath.name == ".gitignore":
            return "Git"
        return LANGUAGE_MAP.get(filepath.suffix, "Other")

    @staticmethod
    def classify_layer(filepath: Path, root: Path) -> str:
        rel = str(filepath.relative_to(root)).replace("\\", "/").lower()
        for pattern, label in LAYER_PATTERNS.items():
            if f"/{pattern}/" in f"/{rel}" or rel.startswith(f"{pattern}/"):
                return label
        return "Root / Other"

    @staticmethod
    def is_test_file(filepath: Path) -> bool:
        name_lower = filepath.name.lower()
        path_lower = str(filepath).lower().replace("\\", "/")
        return (
            name_lower.startswith("test_")
            or name_lower.endswith("_test.py")
            or "/tests/" in path_lower
            or "/test/" in path_lower
        )


# ============================================================
# Census Engine
# ============================================================

class CensusEngine:
    """Walks the repository and produces a complete CensusReport.

    The census engine is the beating heart of the Lines of Code
    Census Bureau. It traverses every file in the repository,
    measures it, classifies it, and aggregates the results into
    a report suitable for executive dashboards, quarterly reviews,
    and passive-aggressive Slack messages.
    """

    def __init__(self, root: Path) -> None:
        self._root = root
        self._counter = LineCounter()
        self._classifier = FileClassifier()

    def _discover_files(self) -> list[Path]:
        files = []
        for dirpath, dirnames, filenames in os.walk(self._root):
            dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
            for filename in filenames:
                files.append(Path(dirpath) / filename)
        return sorted(files)

    def run(self) -> CensusReport:
        report = CensusReport(
            timestamp=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        )

        files = self._discover_files()

        for filepath in files:
            total, code, blank, comments = LineCounter.count(filepath)
            language = self._classifier.classify_language(filepath)
            layer = self._classifier.classify_layer(filepath, self._root)

            metric = FileMetrics(
                path=str(filepath.relative_to(self._root)),
                language=language,
                total_lines=total,
                code_lines=code,
                blank_lines=blank,
                comment_lines=comments,
                layer=layer,
            )
            report.file_metrics.append(metric)

            # Aggregate by language
            if language not in report.by_language:
                report.by_language[language] = CategoryStats()
            cat = report.by_language[language]
            cat.files += 1
            cat.total += total
            cat.code += code
            cat.blank += blank
            cat.comments += comments

            # Aggregate by layer
            if layer not in report.by_layer:
                report.by_layer[layer] = CategoryStats()
            lay = report.by_layer[layer]
            lay.files += 1
            lay.total += total
            lay.code += code
            lay.blank += blank
            lay.comments += comments

            # Composition tracking
            if filepath.suffix == ".py":
                if self._classifier.is_test_file(filepath):
                    report.test_python_lines += total
                    report.test_python_files += 1
                else:
                    report.source_python_lines += total
                    report.source_python_files += 1
            elif filepath.suffix == ".md":
                report.doc_lines += total
                report.doc_files += 1
            elif filepath.suffix == ".fizztranslation":
                report.locale_lines += total
                report.locale_files += 1

        # Grand totals
        report.grand_total_files = len(files)
        report.grand_total_lines = sum(c.total for c in report.by_language.values())
        report.grand_total_code = sum(c.code for c in report.by_language.values())
        report.grand_total_blank = sum(c.blank for c in report.by_language.values())
        report.grand_total_comments = sum(c.comments for c in report.by_language.values())

        # Derived metrics
        if report.source_python_lines > 0:
            report.test_to_source_ratio = (
                report.test_python_lines / report.source_python_lines
            )

        report.overengineering_index = (
            report.grand_total_lines / MINIMAL_SOLUTION_LINES
        )

        # Lines per FizzBuzz rule: the platform has 2 rules (Fizz, Buzz).
        # How many lines of code support each rule?
        report.lines_per_fizzbuzz_rule = report.grand_total_lines / 2

        return report


# ============================================================
# ASCII Dashboard Renderer
# ============================================================

class CensusDashboard:
    """Renders the census report as an ASCII dashboard.

    Produces a multi-section terminal report with box-drawing
    characters, aligned columns, and the existential weight of
    knowing exactly how many lines of code it takes to check
    if a number is divisible by 3.
    """

    WIDTH = 74

    def render(self, report: CensusReport) -> str:
        sections = [
            self._header(report),
            self._by_language(report),
            self._by_layer(report),
            self._composition(report),
            self._top_files(report, n=20),
            self._overengineering_index(report),
            self._footer(report),
        ]
        return "\n".join(sections)

    def _box_top(self, title: str = "") -> str:
        if title:
            padding = self.WIDTH - 4 - len(title)
            return f"  +={'= ' + title + ' ':=<{self.WIDTH - 4}}=+"
        return "  +" + "=" * (self.WIDTH - 2) + "+"

    def _box_bottom(self) -> str:
        return "  +" + "=" * (self.WIDTH - 2) + "+"

    def _box_line(self, text: str = "") -> str:
        return f"  | {text:<{self.WIDTH - 4}} |"

    def _divider(self) -> str:
        return "  +" + "-" * (self.WIDTH - 2) + "+"

    def _header(self, report: CensusReport) -> str:
        lines = []
        lines.append("")
        lines.append(self._box_top())
        lines.append(self._box_line(""))
        lines.append(self._box_line("ENTERPRISE FIZZBUZZ PLATFORM"))
        lines.append(self._box_line("Lines of Code Census Bureau"))
        lines.append(self._box_line(""))
        lines.append(self._box_line(f"Census conducted: {report.timestamp}"))
        lines.append(self._box_line(f"Repository root:  {REPO_ROOT}"))
        lines.append(self._box_line(""))
        lines.append(self._box_bottom())
        return "\n".join(lines)

    def _by_language(self, report: CensusReport) -> str:
        lines = []
        lines.append("")
        lines.append(self._box_top())
        lines.append(self._box_line("BREAKDOWN BY LANGUAGE"))
        lines.append(self._divider())

        header = f"{'Language':<34} {'Files':>6} {'Total':>7} {'Code':>7} {'Blank':>7} {'Cmts':>5}"
        lines.append(self._box_line(header))
        lines.append(self._divider())

        sorted_langs = sorted(
            report.by_language.items(),
            key=lambda x: x[1].total,
            reverse=True,
        )
        for lang, stats in sorted_langs:
            row = f"{lang:<34} {stats.files:>6} {stats.total:>7} {stats.code:>7} {stats.blank:>7} {stats.comments:>5}"
            lines.append(self._box_line(row))

        lines.append(self._divider())
        total_row = (
            f"{'TOTAL':<34} {report.grand_total_files:>6} "
            f"{report.grand_total_lines:>7} {report.grand_total_code:>7} "
            f"{report.grand_total_blank:>7} {report.grand_total_comments:>5}"
        )
        lines.append(self._box_line(total_row))
        lines.append(self._box_bottom())
        return "\n".join(lines)

    def _by_layer(self, report: CensusReport) -> str:
        lines = []
        lines.append("")
        lines.append(self._box_top())
        lines.append(self._box_line("BREAKDOWN BY ARCHITECTURAL LAYER"))
        lines.append(self._divider())

        header = f"{'Layer':<45} {'Files':>6} {'Lines':>7}"
        lines.append(self._box_line(header))
        lines.append(self._divider())

        sorted_layers = sorted(
            report.by_layer.items(),
            key=lambda x: x[1].total,
            reverse=True,
        )
        for layer, stats in sorted_layers:
            display = layer if len(layer) <= 43 else layer[:40] + "..."
            row = f"{display:<45} {stats.files:>6} {stats.total:>7}"
            lines.append(self._box_line(row))

        lines.append(self._box_bottom())
        return "\n".join(lines)

    def _composition(self, report: CensusReport) -> str:
        lines = []
        lines.append("")
        lines.append(self._box_top())
        lines.append(self._box_line("COMPOSITION"))
        lines.append(self._divider())

        lines.append(self._box_line(
            f"Source Python:        {report.source_python_lines:>8,} lines across {report.source_python_files:>4} files"
        ))
        lines.append(self._box_line(
            f"Test Python:          {report.test_python_lines:>8,} lines across {report.test_python_files:>4} files"
        ))
        lines.append(self._box_line(
            f"Documentation (md):   {report.doc_lines:>8,} lines across {report.doc_files:>4} files"
        ))
        lines.append(self._box_line(
            f"Locale files:         {report.locale_lines:>8,} lines across {report.locale_files:>4} files"
        ))
        lines.append(self._divider())
        lines.append(self._box_line(
            f"Test:Source ratio:        {report.test_to_source_ratio:>8.2f}:1"
        ))
        lines.append(self._box_bottom())
        return "\n".join(lines)

    def _top_files(self, report: CensusReport, n: int = 20) -> str:
        lines = []
        lines.append("")
        lines.append(self._box_top())
        lines.append(self._box_line(f"TOP {n} LARGEST FILES"))
        lines.append(self._divider())

        header = f"{'File':<52} {'Lines':>7}"
        lines.append(self._box_line(header))
        lines.append(self._divider())

        sorted_files = sorted(
            report.file_metrics,
            key=lambda f: f.total_lines,
            reverse=True,
        )
        for fm in sorted_files[:n]:
            path = fm.path.replace("\\", "/")
            display = path if len(path) <= 50 else "..." + path[-(50 - 3):]
            row = f"{display:<52} {fm.total_lines:>7}"
            lines.append(self._box_line(row))

        lines.append(self._box_bottom())
        return "\n".join(lines)

    def _overengineering_index(self, report: CensusReport) -> str:
        lines = []
        lines.append("")
        lines.append(self._box_top())
        lines.append(self._box_line("OVERENGINEERING INDEX (OEI)"))
        lines.append(self._divider())
        lines.append(self._box_line(""))
        lines.append(self._box_line(
            f"  Total lines:                    {report.grand_total_lines:>10,}"
        ))
        lines.append(self._box_line(
            f"  Minimal FizzBuzz solution:       {MINIMAL_SOLUTION_LINES:>10}"
        ))
        lines.append(self._box_line(
            f"  Overengineering Index:           {report.overengineering_index:>10,.1f}x"
        ))
        lines.append(self._box_line(""))
        lines.append(self._box_line(
            f"  Lines per FizzBuzz rule:         {report.lines_per_fizzbuzz_rule:>10,.1f}"
        ))
        lines.append(self._box_line(""))

        # OEI rating
        oei = report.overengineering_index
        if oei < 100:
            rating = "Hobbyist. Needs more middleware."
        elif oei < 1_000:
            rating = "Startup. Promising but under-abstracted."
        elif oei < 5_000:
            rating = "Mid-market. A respectable amount of indirection."
        elif oei < 10_000:
            rating = "Enterprise. Stakeholders would approve."
        elif oei < 15_000:
            rating = "Fortune 500. The architecture has its own architecture."
        else:
            rating = "Transcendent. The code has achieved sentience and filed a PTO request."

        lines.append(self._box_line(f"  Rating: {rating}"))
        lines.append(self._box_line(""))

        # Bob's contribution
        lines.append(self._divider())
        lines.append(self._box_line("ON-CALL ATTRIBUTION"))
        lines.append(self._box_line(""))
        lines.append(self._box_line(
            f"  Lines maintained by Bob McFizzington:  {report.grand_total_lines:>10,}"
        ))
        lines.append(self._box_line(
            f"  Lines maintained by everyone else:     {0:>10,}"
        ))
        lines.append(self._box_line(""))
        lines.append(self._box_bottom())
        return "\n".join(lines)

    def _footer(self, report: CensusReport) -> str:
        lines = []
        lines.append("")
        lines.append(self._box_top())
        lines.append(self._box_line(""))
        lines.append(self._box_line(
            f"  GRAND TOTAL: {report.grand_total_lines:,} lines across "
            f"{report.grand_total_files} files"
        ))
        lines.append(self._box_line(
            "  to determine whether numbers are divisible by 3 and 5."
        ))
        lines.append(self._box_line(""))
        lines.append(self._box_bottom())
        lines.append("")
        return "\n".join(lines)


# ============================================================
# Entry Point
# ============================================================

def main() -> None:
    """Run the Lines of Code Census and display the dashboard."""
    engine = CensusEngine(REPO_ROOT)
    report = engine.run()
    dashboard = CensusDashboard()
    print(dashboard.render(report))


if __name__ == "__main__":
    main()
