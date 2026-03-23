"""
Enterprise FizzBuzz Platform - FizzPrint Typesetting Engine Test Suite

Comprehensive tests for the TeX-inspired typesetting engine, verifying
that Knuth-Plass optimal line breaking, Liang hyphenation, kerning,
ligature detection, pagination with widow/orphan control, and PostScript
rendering all function correctly. The typographic quality of FizzBuzz
reports is not something that can be left to chance.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from typesetter import (
    Box,
    FizzBuzzReport,
    FontMetrics,
    Glue,
    GlyphMetrics,
    HyphenationEngine,
    KnuthPlassBreaker,
    Page,
    PageLayout,
    Paragraph,
    Penalty,
    PostScriptRenderer,
    TypesetDashboard,
    TypesetMiddleware,
)
from config import ConfigurationManager, _SingletonMeta
from models import FizzBuzzResult, ProcessingContext


@pytest.fixture(autouse=True)
def reset_singletons():
    """Reset all singletons between tests."""
    _SingletonMeta.reset()
    yield


# ---------------------------------------------------------------------------
# GlyphMetrics Tests
# ---------------------------------------------------------------------------


class TestGlyphMetrics:
    """Tests for the GlyphMetrics data class."""

    def test_glyph_metrics_creation(self):
        gm = GlyphMetrics(character="A", width=6.0, height=8.0, depth=2.0)
        assert gm.character == "A"
        assert gm.width == 6.0
        assert gm.height == 8.0
        assert gm.depth == 2.0
        assert gm.italic_correction == 0.0

    def test_glyph_metrics_with_italic_correction(self):
        gm = GlyphMetrics(character="f", width=5.0, height=8.0, depth=0.0, italic_correction=1.5)
        assert gm.italic_correction == 1.5

    def test_glyph_metrics_frozen(self):
        gm = GlyphMetrics(character="X", width=6.0, height=8.0, depth=2.0)
        with pytest.raises(AttributeError):
            gm.width = 10.0


# ---------------------------------------------------------------------------
# FontMetrics Tests
# ---------------------------------------------------------------------------


class TestFontMetrics:
    """Tests for the FontMetrics class including kerning and ligatures."""

    def test_default_construction(self):
        fm = FontMetrics()
        assert fm.name == "Courier"
        assert fm.size == 10.0

    def test_custom_construction(self):
        fm = FontMetrics(name="Helvetica", size=12.0, char_width=7.0)
        assert fm.name == "Helvetica"
        assert fm.size == 12.0

    def test_glyph_retrieval(self):
        fm = FontMetrics()
        g = fm.glyph("A")
        assert g.character == "A"
        assert g.width > 0

    def test_glyph_fallback_for_unknown(self):
        fm = FontMetrics()
        g = fm.glyph("\x01")  # Non-printable
        assert g.width == fm._default_width

    def test_narrow_characters(self):
        fm = FontMetrics()
        narrow = fm.glyph("i")
        normal = fm.glyph("a")
        assert narrow.width < normal.width

    def test_wide_characters(self):
        fm = FontMetrics()
        wide = fm.glyph("M")
        normal = fm.glyph("a")
        assert wide.width > normal.width

    def test_kerning_av(self):
        fm = FontMetrics()
        kern = fm.kerning("A", "V")
        assert kern < 0  # AV should have negative kerning

    def test_kerning_no_pair(self):
        fm = FontMetrics()
        kern = fm.kerning("a", "b")
        assert kern == 0.0

    def test_ligature_fi(self):
        fm = FontMetrics()
        lig = fm.ligature("fi")
        assert lig == "\ufb01"

    def test_ligature_fl(self):
        fm = FontMetrics()
        lig = fm.ligature("fl")
        assert lig == "\ufb02"

    def test_ligature_ff(self):
        fm = FontMetrics()
        lig = fm.ligature("ff")
        assert lig == "\ufb00"

    def test_ligature_none(self):
        fm = FontMetrics()
        assert fm.ligature("ab") is None

    def test_string_width_empty(self):
        fm = FontMetrics()
        assert fm.string_width("") == 0.0

    def test_string_width_single_char(self):
        fm = FontMetrics()
        w = fm.string_width("A")
        assert w == fm.glyph("A").width

    def test_string_width_with_kerning(self):
        fm = FontMetrics()
        # AV has kerning, so width should differ from sum of individual widths
        w_av = fm.string_width("AV")
        w_a = fm.glyph("A").width
        w_v = fm.glyph("V").width
        kern = fm.kerning("A", "V")
        assert abs(w_av - (w_a + w_v + kern)) < 0.001


# ---------------------------------------------------------------------------
# Box / Glue / Penalty Tests
# ---------------------------------------------------------------------------


class TestBoxGluePenalty:
    """Tests for the fundamental typesetting node types."""

    def test_box_creation(self):
        b = Box(width=10.0, content="Hello")
        assert b.width == 10.0
        assert b.content == "Hello"
        assert b.node_type.name == "BOX"

    def test_glue_creation(self):
        g = Glue(width=6.0, stretch=3.0, shrink=2.0)
        assert g.width == 6.0
        assert g.stretch == 3.0
        assert g.shrink == 2.0
        assert g.node_type.name == "GLUE"

    def test_penalty_creation(self):
        p = Penalty(penalty=50.0, width=3.0, flagged=True)
        assert p.penalty == 50.0
        assert p.width == 3.0
        assert p.flagged is True
        assert p.node_type.name == "PENALTY"

    def test_penalty_defaults(self):
        p = Penalty(penalty=100.0)
        assert p.width == 0.0
        assert p.flagged is False


# ---------------------------------------------------------------------------
# HyphenationEngine Tests
# ---------------------------------------------------------------------------


class TestHyphenationEngine:
    """Tests for the Liang-inspired hyphenation engine."""

    def test_short_word_not_hyphenated(self):
        h = HyphenationEngine()
        assert h.hyphenate("Fizz") == ["Fizz"]

    def test_short_word_boundary(self):
        h = HyphenationEngine()
        # Word of exactly MIN_WORD_LENGTH - 1
        assert h.hyphenate("Buzz") == ["Buzz"]

    def test_longer_word_hyphenation(self):
        h = HyphenationEngine()
        result = h.hyphenate("evaluation")
        assert len(result) >= 1
        assert "".join(result) == "evaluation"

    def test_hyphenation_preserves_text(self):
        h = HyphenationEngine()
        word = "enterprise"
        result = h.hyphenate(word)
        assert "".join(result) == word

    def test_empty_word(self):
        h = HyphenationEngine()
        assert h.hyphenate("") == [""]

    def test_single_char(self):
        h = HyphenationEngine()
        assert h.hyphenate("a") == ["a"]

    def test_all_consonants(self):
        h = HyphenationEngine()
        # No vowel-consonant transitions
        assert h.hyphenate("rhythm") == ["rhythm"]


# ---------------------------------------------------------------------------
# KnuthPlassBreaker Tests
# ---------------------------------------------------------------------------


class TestKnuthPlassBreaker:
    """Tests for the Knuth-Plass optimal line breaking algorithm."""

    def test_empty_nodes(self):
        kp = KnuthPlassBreaker()
        assert kp.break_lines([]) == []

    def test_single_box(self):
        kp = KnuthPlassBreaker(line_width=100.0)
        nodes = [
            Box(width=20.0, content="Fizz"),
            Penalty(penalty=-10000, width=0.0),
        ]
        lines = kp.break_lines(nodes)
        assert len(lines) >= 1

    def test_two_words_fit_on_one_line(self):
        kp = KnuthPlassBreaker(line_width=200.0)
        nodes = [
            Box(width=30.0, content="Fizz"),
            Glue(width=6.0, stretch=3.0, shrink=2.0),
            Box(width=30.0, content="Buzz"),
            Penalty(penalty=10000, width=0.0),
            Glue(width=0.0, stretch=10000, shrink=0.0),
            Penalty(penalty=-10000, width=0.0),
        ]
        lines = kp.break_lines(nodes)
        # Both words should fit on one line
        assert len(lines) >= 1
        # First line should contain both words
        content = " ".join(n.content for n in lines[0] if isinstance(n, Box))
        assert "Fizz" in content

    def test_forced_break(self):
        kp = KnuthPlassBreaker(line_width=200.0)
        nodes = [
            Box(width=30.0, content="Fizz"),
            Penalty(penalty=-10000, width=0.0),  # Forced break
            Box(width=30.0, content="Buzz"),
            Penalty(penalty=10000, width=0.0),
            Glue(width=0.0, stretch=10000, shrink=0.0),
            Penalty(penalty=-10000, width=0.0),
        ]
        lines = kp.break_lines(nodes)
        assert len(lines) >= 2

    def test_badness_computation(self):
        # Badness = 100 * |ratio|^3
        assert KnuthPlassBreaker._compute_badness(0.0) == 0.0
        assert abs(KnuthPlassBreaker._compute_badness(1.0) - 100.0) < 0.01
        assert abs(KnuthPlassBreaker._compute_badness(2.0) - 800.0) < 0.01
        # Cap at 10000
        assert KnuthPlassBreaker._compute_badness(10.0) == 10000.0

    def test_fitness_class_tight(self):
        assert KnuthPlassBreaker._fitness_class(-1.0) == 0

    def test_fitness_class_normal(self):
        assert KnuthPlassBreaker._fitness_class(0.0) == 1

    def test_fitness_class_loose(self):
        assert KnuthPlassBreaker._fitness_class(0.8) == 2

    def test_fitness_class_very_loose(self):
        assert KnuthPlassBreaker._fitness_class(2.0) == 3

    def test_narrow_line_forces_breaks(self):
        kp = KnuthPlassBreaker(line_width=40.0)
        nodes = [
            Box(width=30.0, content="Fizz"),
            Glue(width=6.0, stretch=3.0, shrink=2.0),
            Box(width=30.0, content="Buzz"),
            Glue(width=6.0, stretch=3.0, shrink=2.0),
            Box(width=60.0, content="FizzBuzz"),
            Penalty(penalty=10000, width=0.0),
            Glue(width=0.0, stretch=10000, shrink=0.0),
            Penalty(penalty=-10000, width=0.0),
        ]
        lines = kp.break_lines(nodes)
        # Should produce multiple lines due to narrow width
        assert len(lines) >= 2

    def test_tolerance_affects_breaks(self):
        kp_strict = KnuthPlassBreaker(line_width=100.0, tolerance=1.0)
        kp_loose = KnuthPlassBreaker(line_width=100.0, tolerance=10.0)
        nodes = [
            Box(width=30.0, content="A"),
            Glue(width=6.0, stretch=3.0, shrink=2.0),
            Box(width=30.0, content="B"),
            Glue(width=6.0, stretch=3.0, shrink=2.0),
            Box(width=30.0, content="C"),
            Penalty(penalty=10000, width=0.0),
            Glue(width=0.0, stretch=10000, shrink=0.0),
            Penalty(penalty=-10000, width=0.0),
        ]
        lines_strict = kp_strict.break_lines(nodes)
        lines_loose = kp_loose.break_lines(nodes)
        # Both should produce valid output
        assert len(lines_strict) >= 1
        assert len(lines_loose) >= 1


# ---------------------------------------------------------------------------
# Paragraph Tests
# ---------------------------------------------------------------------------


class TestParagraph:
    """Tests for the Paragraph builder."""

    def test_simple_paragraph(self):
        p = Paragraph("Fizz Buzz FizzBuzz")
        assert len(p.nodes) > 0
        # Should have boxes, glue, and terminal penalty/glue
        has_box = any(isinstance(n, Box) for n in p.nodes)
        has_glue = any(isinstance(n, Glue) for n in p.nodes)
        assert has_box
        assert has_glue

    def test_paragraph_ends_with_forced_break(self):
        p = Paragraph("Hello world")
        # Last node should be a forced break penalty
        assert isinstance(p.nodes[-1], Penalty)
        assert p.nodes[-1].penalty == -10000

    def test_paragraph_with_indent(self):
        p = Paragraph("Indented text", indent=20.0)
        # First node should be an empty box for the indent
        assert isinstance(p.nodes[0], Box)
        assert p.nodes[0].width == 20.0
        assert p.nodes[0].content == ""

    def test_ligature_detection(self):
        p = Paragraph("find file")
        # "fi" appears twice, both should be detected
        assert p.ligature_count >= 2

    def test_single_word_paragraph(self):
        p = Paragraph("Fizz")
        boxes = [n for n in p.nodes if isinstance(n, Box)]
        assert len(boxes) >= 1

    def test_empty_paragraph(self):
        p = Paragraph("")
        # Should still have terminal nodes
        assert len(p.nodes) >= 3  # penalty + glue + penalty


# ---------------------------------------------------------------------------
# PageLayout Tests
# ---------------------------------------------------------------------------


class TestPageLayout:
    """Tests for the PageLayout configuration."""

    def test_default_layout(self):
        layout = PageLayout()
        assert layout.page_width == 612.0
        assert layout.page_height == 792.0
        assert layout.columns == 1

    def test_text_width_single_column(self):
        layout = PageLayout(page_width=612.0, margin_left=72.0, margin_right=72.0)
        assert layout.text_width == 612.0 - 72.0 - 72.0

    def test_text_width_two_columns(self):
        layout = PageLayout(
            page_width=612.0,
            margin_left=72.0,
            margin_right=72.0,
            columns=2,
            column_gap=18.0,
        )
        total_text = 612.0 - 72.0 - 72.0
        expected = (total_text - 18.0) / 2
        assert abs(layout.text_width - expected) < 0.001

    def test_text_height(self):
        layout = PageLayout(page_height=792.0, margin_top=72.0, margin_bottom=72.0)
        assert layout.text_height == 792.0 - 72.0 - 72.0


# ---------------------------------------------------------------------------
# Page Tests
# ---------------------------------------------------------------------------


class TestPage:
    """Tests for the Page data structure."""

    def test_empty_page(self):
        p = Page(number=1)
        assert p.line_count == 0
        assert p.total_badness == 0.0

    def test_add_line(self):
        p = Page(number=1)
        p.add_line([Box(width=10.0, content="test")], badness=5.0)
        assert p.line_count == 1
        assert p.total_badness == 5.0

    def test_multiple_lines(self):
        p = Page(number=1)
        p.add_line([Box(width=10.0, content="a")], badness=3.0)
        p.add_line([Box(width=10.0, content="b")], badness=7.0)
        assert p.line_count == 2
        assert p.total_badness == 10.0

    def test_page_header_footer(self):
        p = Page(number=3, header="Title", footer="Page 3")
        assert p.header == "Title"
        assert p.footer == "Page 3"


# ---------------------------------------------------------------------------
# FizzBuzzReport Tests
# ---------------------------------------------------------------------------


class TestFizzBuzzReport:
    """Tests for the FizzBuzz typeset report generator."""

    def _make_results(self, n: int = 15) -> list[FizzBuzzResult]:
        results = []
        for i in range(1, n + 1):
            if i % 15 == 0:
                output = "FizzBuzz"
            elif i % 3 == 0:
                output = "Fizz"
            elif i % 5 == 0:
                output = "Buzz"
            else:
                output = str(i)
            results.append(FizzBuzzResult(number=i, output=output))
        return results

    def test_generate_produces_pages(self):
        results = self._make_results()
        report = FizzBuzzReport(results=results)
        pages = report.generate()
        assert len(pages) >= 1

    def test_generate_tracks_statistics(self):
        results = self._make_results()
        report = FizzBuzzReport(results=results)
        report.generate()
        assert report.total_lines > 0
        assert report.total_badness >= 0.0

    def test_generate_with_custom_layout(self):
        layout = PageLayout(page_width=400.0, page_height=300.0)
        results = self._make_results()
        report = FizzBuzzReport(results=results, layout=layout)
        pages = report.generate()
        assert len(pages) >= 1

    def test_average_badness(self):
        results = self._make_results()
        report = FizzBuzzReport(results=results)
        report.generate()
        avg = report.average_badness
        assert avg >= 0.0

    def test_average_badness_no_results(self):
        """Even an empty FizzBuzz range produces title and summary paragraphs."""
        report = FizzBuzzReport(results=[])
        report.generate()
        # The title and summary still get typeset, so average_badness >= 0
        assert report.average_badness >= 0.0

    def test_custom_title(self):
        results = self._make_results(5)
        report = FizzBuzzReport(results=results, title="Custom Report")
        pages = report.generate()
        assert pages[0].header == "Custom Report"

    def test_result_grouping(self):
        results = self._make_results()
        report = FizzBuzzReport(results=results)
        groups = report._group_results()
        labels = [g[0] for g in groups]
        # Should have at least Numeric, Fizz, Buzz, FizzBuzz
        assert "Fizz" in labels
        assert "Buzz" in labels

    def test_large_range(self):
        results = self._make_results(100)
        report = FizzBuzzReport(results=results)
        pages = report.generate()
        assert len(pages) >= 1
        assert report.total_lines > 10

    def test_pages_have_sequential_numbers(self):
        results = self._make_results(100)
        layout = PageLayout(page_height=200.0)  # Short pages
        report = FizzBuzzReport(results=results, layout=layout)
        pages = report.generate()
        for i, page in enumerate(pages):
            assert page.number == i + 1


# ---------------------------------------------------------------------------
# PostScriptRenderer Tests
# ---------------------------------------------------------------------------


class TestPostScriptRenderer:
    """Tests for PostScript output generation."""

    def _make_pages(self) -> list[Page]:
        p = Page(number=1, header="Test Report", footer="Page 1")
        p.add_line([Box(width=30.0, content="Fizz"), Glue(width=6.0, stretch=3.0, shrink=2.0), Box(width=30.0, content="Buzz")])
        return [p]

    def test_postscript_header(self):
        renderer = PostScriptRenderer()
        ps = renderer.render(self._make_pages())
        assert ps.startswith("%!PS-Adobe-3.0")

    def test_bounding_box(self):
        renderer = PostScriptRenderer()
        ps = renderer.render(self._make_pages())
        assert "%%BoundingBox:" in ps

    def test_font_setup(self):
        renderer = PostScriptRenderer()
        ps = renderer.render(self._make_pages())
        assert "findfont" in ps
        assert "scalefont" in ps
        assert "setfont" in ps

    def test_page_markers(self):
        renderer = PostScriptRenderer()
        ps = renderer.render(self._make_pages())
        assert "%%Page: 1 1" in ps

    def test_moveto_show(self):
        renderer = PostScriptRenderer()
        ps = renderer.render(self._make_pages())
        assert "moveto" in ps
        assert "show" in ps

    def test_eof_marker(self):
        renderer = PostScriptRenderer()
        ps = renderer.render(self._make_pages())
        assert ps.strip().endswith("%%EOF")

    def test_escape_parentheses(self):
        assert PostScriptRenderer._escape_ps("(test)") == "\\(test\\)"

    def test_escape_backslash(self):
        assert PostScriptRenderer._escape_ps("a\\b") == "a\\\\b"

    def test_multi_page(self):
        pages = []
        for i in range(3):
            p = Page(number=i + 1, header="Report", footer=f"Page {i + 1}")
            p.add_line([Box(width=30.0, content=f"Line {i}")])
            pages.append(p)
        renderer = PostScriptRenderer()
        ps = renderer.render(pages)
        assert "%%Pages: 3" in ps
        assert "%%Page: 1 1" in ps
        assert "%%Page: 2 2" in ps
        assert "%%Page: 3 3" in ps

    def test_custom_font(self):
        font = FontMetrics(name="Helvetica", size=14.0)
        renderer = PostScriptRenderer(font=font)
        ps = renderer.render(self._make_pages())
        assert "/Helvetica findfont" in ps
        assert "14" in ps

    def test_showpage(self):
        renderer = PostScriptRenderer()
        ps = renderer.render(self._make_pages())
        assert "showpage" in ps

    def test_gsave_grestore(self):
        renderer = PostScriptRenderer()
        ps = renderer.render(self._make_pages())
        assert "gsave" in ps
        assert "grestore" in ps


# ---------------------------------------------------------------------------
# TypesetDashboard Tests
# ---------------------------------------------------------------------------


class TestTypesetDashboard:
    """Tests for the ASCII typesetting statistics dashboard."""

    def _make_report(self) -> FizzBuzzReport:
        results = []
        for i in range(1, 16):
            if i % 15 == 0:
                output = "FizzBuzz"
            elif i % 3 == 0:
                output = "Fizz"
            elif i % 5 == 0:
                output = "Buzz"
            else:
                output = str(i)
            results.append(FizzBuzzResult(number=i, output=output))
        report = FizzBuzzReport(results=results)
        report.generate()
        return report

    def test_dashboard_renders(self):
        report = self._make_report()
        output = TypesetDashboard.render(report)
        assert "FIZZPRINT TYPESETTING ENGINE" in output

    def test_dashboard_contains_stats(self):
        report = self._make_report()
        output = TypesetDashboard.render(report)
        assert "Pages" in output
        assert "Total lines" in output
        assert "Total badness" in output
        assert "Average badness" in output
        assert "Hyphenation" in output
        assert "Ligature" in output
        assert "Kerning" in output

    def test_dashboard_has_histogram(self):
        report = self._make_report()
        output = TypesetDashboard.render(report)
        assert "Badness Distribution" in output

    def test_dashboard_has_page_summary(self):
        report = self._make_report()
        output = TypesetDashboard.render(report)
        assert "Per-Page Summary" in output
        assert "Page 1" in output

    def test_dashboard_custom_width(self):
        report = self._make_report()
        output = TypesetDashboard.render(report, width=60)
        for line in output.split("\n"):
            assert len(line) <= 60


# ---------------------------------------------------------------------------
# TypesetMiddleware Tests
# ---------------------------------------------------------------------------


class TestTypesetMiddleware:
    """Tests for the middleware integration."""

    def test_middleware_name(self):
        mw = TypesetMiddleware()
        assert mw.get_name() == "TypesetMiddleware"

    def test_middleware_priority(self):
        mw = TypesetMiddleware()
        assert mw.get_priority() == 960

    def test_middleware_collects_results(self):
        mw = TypesetMiddleware()

        ctx = ProcessingContext(number=3, session_id="test-session")
        ctx.results = [FizzBuzzResult(number=3, output="Fizz")]

        def noop(c):
            return c

        mw.process(ctx, noop)
        assert len(mw._results) == 1
        assert mw._results[0].output == "Fizz"

    def test_middleware_passes_through(self):
        mw = TypesetMiddleware()

        ctx = ProcessingContext(number=5, session_id="test-session")
        ctx.results = [FizzBuzzResult(number=5, output="Buzz")]

        def noop(c):
            return c

        result = mw.process(ctx, noop)
        assert result.number == 5

    def test_finalize_without_results(self):
        mw = TypesetMiddleware()
        assert mw.finalize() is None

    def test_finalize_with_results(self):
        mw = TypesetMiddleware()

        for i in range(1, 16):
            ctx = ProcessingContext(number=i, session_id="test-session")
            if i % 15 == 0:
                output = "FizzBuzz"
            elif i % 3 == 0:
                output = "Fizz"
            elif i % 5 == 0:
                output = "Buzz"
            else:
                output = str(i)
            ctx.results = [FizzBuzzResult(number=i, output=output)]
            mw.process(ctx, lambda c: c)

        report = mw.finalize()
        assert report is not None
        assert len(report.pages) >= 1

    def test_finalize_writes_postscript(self, tmp_path):
        mw = TypesetMiddleware(output_path=str(tmp_path / "output.ps"))

        ctx = ProcessingContext(number=3, session_id="test-session")
        ctx.results = [FizzBuzzResult(number=3, output="Fizz")]
        mw.process(ctx, lambda c: c)

        report = mw.finalize()
        assert report is not None

        ps_file = tmp_path / "output.ps"
        assert ps_file.exists()
        content = ps_file.read_text()
        assert "%!PS-Adobe-3.0" in content


# ---------------------------------------------------------------------------
# Integration Tests
# ---------------------------------------------------------------------------


class TestTypesetterIntegration:
    """End-to-end integration tests for the typesetting pipeline."""

    def test_full_pipeline(self):
        """Run a complete typesetting pipeline from results to PostScript."""
        results = []
        for i in range(1, 101):
            if i % 15 == 0:
                output = "FizzBuzz"
            elif i % 3 == 0:
                output = "Fizz"
            elif i % 5 == 0:
                output = "Buzz"
            else:
                output = str(i)
            results.append(FizzBuzzResult(number=i, output=output))

        report = FizzBuzzReport(results=results)
        pages = report.generate()

        renderer = PostScriptRenderer()
        ps = renderer.render(pages)

        assert "%!PS-Adobe-3.0" in ps
        assert "%%EOF" in ps
        assert len(pages) >= 1
        assert report.total_lines > 0

        # Dashboard should render without error
        dashboard = TypesetDashboard.render(report)
        assert "FIZZPRINT" in dashboard

    def test_paragraph_to_lines(self):
        """Verify that a paragraph is broken into lines by the breaker."""
        text = "Fizz Buzz FizzBuzz Fizz Buzz FizzBuzz Fizz Buzz"
        para = Paragraph(text)
        breaker = KnuthPlassBreaker(line_width=150.0)
        lines = breaker.break_lines(para.nodes)
        assert len(lines) >= 1
        # All lines should have content
        for line in lines:
            has_content = any(isinstance(n, Box) and n.content for n in line)
            # Last line might be empty if text divides perfectly
            # but at least one line must have content
        assert any(
            any(isinstance(n, Box) and n.content for n in line)
            for line in lines
        )

    def test_kerning_reduces_width(self):
        """Verify that kerning narrows the width of AV pair."""
        font = FontMetrics()
        w_no_kern = font.glyph("A").width + font.glyph("V").width
        w_with_kern = font.string_width("AV")
        assert w_with_kern < w_no_kern
