"""
Enterprise FizzBuzz Platform - FizzFlame Flame Graph Generator Tests

Comprehensive test suite for the flame graph subsystem, covering
stack collapsing, SVG rendering, differential analysis, icicle charts,
timeline heat maps, ASCII dashboards, and middleware integration.

Each test validates that the FizzFlame subsystem produces correct,
well-formed output for the critical task of profiling FizzBuzz
evaluations — operations whose total execution time is measured
in microseconds, visualized with the same tooling used to profile
multi-second database queries in production systems.
"""

from __future__ import annotations

import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import Any, Optional
from unittest.mock import MagicMock

import pytest

from enterprise_fizzbuzz.domain.models import ProcessingContext
from enterprise_fizzbuzz.domain.exceptions import (
    FlameGraphCollapseError,
    FlameGraphDiffError,
    FlameGraphError,
    FlameGraphRenderError,
)
from enterprise_fizzbuzz.infrastructure.flame_graph import (
    DEFAULT_FRAME_HEIGHT,
    DEFAULT_WIDTH,
    DIFF_FASTER_HUE,
    DIFF_SLOWER_HUE,
    SUBSYSTEM_COLORS,
    DifferentialFlameGraph,
    FlameFrame,
    FlameGraphDashboard,
    FlameGraphMiddleware,
    FlameOrientation,
    FlameStack,
    HeatMapBucket,
    IcicleChart,
    SVGRenderer,
    StackCollapser,
    TimelineHeatMap,
    _diff_color,
    _escape_xml,
    _subsystem_color,
)


# ============================================================
# Fixtures — synthetic span data
# ============================================================


@dataclass
class MockSpan:
    """Minimal span mock matching the OTel Span interface."""
    name: str
    span_id: str
    trace_id: str = "a" * 32
    parent_span_id: Optional[str] = None
    start_time_ns: int = 0
    end_time_ns: int = 0
    attributes: dict[str, Any] = field(default_factory=dict)
    status_code: Any = None
    _ended: bool = True

    @property
    def is_ended(self) -> bool:
        return self._ended


def make_span_tree() -> list[MockSpan]:
    """Create a simple span tree:

    root (0-1000ns)
      ├── child_a (100-600ns)
      │     └── grandchild (200-400ns)
      └── child_b (600-900ns)
    """
    return [
        MockSpan(
            name="RuleEngine.evaluate",
            span_id="root0001",
            parent_span_id=None,
            start_time_ns=1000,
            end_time_ns=2000,
        ),
        MockSpan(
            name="CacheMiddleware.process",
            span_id="child001",
            parent_span_id="root0001",
            start_time_ns=1100,
            end_time_ns=1600,
        ),
        MockSpan(
            name="CacheStore.lookup",
            span_id="grand001",
            parent_span_id="child001",
            start_time_ns=1200,
            end_time_ns=1400,
        ),
        MockSpan(
            name="ComplianceMiddleware.process",
            span_id="child002",
            parent_span_id="root0001",
            start_time_ns=1600,
            end_time_ns=1900,
        ),
    ]


def make_deep_span_tree(depth: int = 10) -> list[MockSpan]:
    """Create a linear chain of spans for testing deep trees."""
    spans = []
    for i in range(depth):
        spans.append(MockSpan(
            name=f"Layer{i}.process",
            span_id=f"deep{i:04d}",
            parent_span_id=f"deep{i - 1:04d}" if i > 0 else None,
            start_time_ns=1000 + i * 100,
            end_time_ns=1000 + (depth - i) * 100 + i * 100,
        ))
    return spans


def make_wide_span_tree(width: int = 5) -> list[MockSpan]:
    """Create a flat tree with many children under one root."""
    spans = [
        MockSpan(
            name="Root.evaluate",
            span_id="wideroot",
            parent_span_id=None,
            start_time_ns=0,
            end_time_ns=width * 100,
        )
    ]
    for i in range(width):
        spans.append(MockSpan(
            name=f"Middleware{i}.process",
            span_id=f"wide{i:04d}",
            parent_span_id="wideroot",
            start_time_ns=i * 100,
            end_time_ns=(i + 1) * 100,
        ))
    return spans


# ============================================================
# FlameFrame Tests
# ============================================================


class TestFlameFrame:
    """Tests for the FlameFrame dataclass."""

    def test_creation(self):
        frame = FlameFrame(name="test", self_time_ns=500, total_time_ns=1000, depth=0)
        assert frame.name == "test"
        assert frame.self_time_ns == 500
        assert frame.total_time_ns == 1000
        assert frame.depth == 0

    def test_self_time_us(self):
        frame = FlameFrame(name="test", self_time_ns=1500)
        assert frame.self_time_us == 1.5

    def test_total_time_us(self):
        frame = FlameFrame(name="test", total_time_ns=2500)
        assert frame.total_time_us == 2.5

    def test_self_time_ms(self):
        frame = FlameFrame(name="test", self_time_ns=1_500_000)
        assert frame.self_time_ms == 1.5

    def test_total_time_ms(self):
        frame = FlameFrame(name="test", total_time_ns=2_500_000)
        assert frame.total_time_ms == 2.5

    def test_subsystem_dotted_name(self):
        frame = FlameFrame(name="CacheMiddleware.process")
        assert frame.subsystem == "cachemiddleware"

    def test_subsystem_simple_name(self):
        frame = FlameFrame(name="evaluate")
        assert frame.subsystem == "evaluate"

    def test_children_default_empty(self):
        frame = FlameFrame(name="test")
        assert frame.children == []

    def test_attributes_default_empty(self):
        frame = FlameFrame(name="test")
        assert frame.attributes == {}

    def test_span_count_default(self):
        frame = FlameFrame(name="test")
        assert frame.span_count == 1


# ============================================================
# FlameStack Tests
# ============================================================


class TestFlameStack:
    """Tests for the FlameStack dataclass."""

    def test_creation(self):
        stack = FlameStack()
        assert stack.frames == []
        assert stack.total_time_ns == 0
        assert stack.trace_id == ""

    def test_collapsed_format(self):
        stack = FlameStack(
            frames=[
                FlameFrame(name="root"),
                FlameFrame(name="child"),
                FlameFrame(name="leaf"),
            ],
            total_time_ns=500,
        )
        assert stack.collapsed == "root;child;leaf 500"

    def test_depth(self):
        stack = FlameStack(
            frames=[FlameFrame(name=f"frame{i}") for i in range(5)]
        )
        assert stack.depth == 5

    def test_append(self):
        stack = FlameStack()
        stack.append(FlameFrame(name="test"))
        assert len(stack.frames) == 1
        assert stack.frames[0].name == "test"

    def test_empty_collapsed(self):
        stack = FlameStack(total_time_ns=100)
        assert stack.collapsed == " 100"


# ============================================================
# StackCollapser Tests
# ============================================================


class TestStackCollapser:
    """Tests for the StackCollapser span tree collapsing."""

    def test_collapse_simple_tree(self):
        spans = make_span_tree()
        collapser = StackCollapser()
        roots = collapser.collapse_spans(spans)

        assert len(roots) == 1
        root = roots[0]
        assert root.name == "RuleEngine.evaluate"
        assert root.total_time_ns == 1000
        assert len(root.children) == 2

    def test_collapse_empty_spans(self):
        collapser = StackCollapser()
        roots = collapser.collapse_spans([])
        assert roots == []

    def test_self_time_computation(self):
        spans = make_span_tree()
        collapser = StackCollapser()
        roots = collapser.collapse_spans(spans)

        root = roots[0]
        # Root total = 1000, children = 500 + 300 = 800, self = 200
        assert root.self_time_ns == 200

    def test_child_self_time(self):
        spans = make_span_tree()
        collapser = StackCollapser()
        roots = collapser.collapse_spans(spans)

        cache_child = roots[0].children[0]
        assert cache_child.name == "CacheMiddleware.process"
        # Total = 500, grandchild = 200, self = 300
        assert cache_child.self_time_ns == 300

    def test_leaf_self_equals_total(self):
        spans = make_span_tree()
        collapser = StackCollapser()
        roots = collapser.collapse_spans(spans)

        grandchild = roots[0].children[0].children[0]
        assert grandchild.name == "CacheStore.lookup"
        assert grandchild.self_time_ns == grandchild.total_time_ns

    def test_depth_assignment(self):
        spans = make_span_tree()
        collapser = StackCollapser()
        roots = collapser.collapse_spans(spans)

        assert roots[0].depth == 0
        assert roots[0].children[0].depth == 1
        assert roots[0].children[0].children[0].depth == 2

    def test_deep_tree(self):
        spans = make_deep_span_tree(15)
        collapser = StackCollapser()
        roots = collapser.collapse_spans(spans)

        assert len(roots) == 1
        frame = roots[0]
        depth = 0
        while frame.children:
            depth += 1
            frame = frame.children[0]
        assert depth == 14

    def test_wide_tree(self):
        spans = make_wide_span_tree(8)
        collapser = StackCollapser()
        roots = collapser.collapse_spans(spans)

        assert len(roots) == 1
        assert len(roots[0].children) == 8

    def test_multiple_roots(self):
        spans = [
            MockSpan(name="root_a", span_id="r1", start_time_ns=0, end_time_ns=100),
            MockSpan(name="root_b", span_id="r2", start_time_ns=100, end_time_ns=200),
        ]
        collapser = StackCollapser()
        roots = collapser.collapse_spans(spans)
        assert len(roots) == 2

    def test_orphaned_parent_becomes_root(self):
        spans = [
            MockSpan(
                name="child",
                span_id="c1",
                parent_span_id="missing",
                start_time_ns=0,
                end_time_ns=100,
            ),
        ]
        collapser = StackCollapser()
        roots = collapser.collapse_spans(spans)
        assert len(roots) == 1
        assert roots[0].name == "child"

    def test_extract_stacks(self):
        spans = make_span_tree()
        collapser = StackCollapser()
        roots = collapser.collapse_spans(spans)
        stacks = collapser.extract_stacks(roots)

        # Two leaf paths: root→cache→lookup, root→compliance
        assert len(stacks) == 2

    def test_extract_stacks_collapsed_format(self):
        spans = make_span_tree()
        collapser = StackCollapser()
        roots = collapser.collapse_spans(spans)
        stacks = collapser.extract_stacks(roots)

        collapsed = [s.collapsed for s in stacks]
        assert any("CacheStore.lookup" in c for c in collapsed)
        assert any("ComplianceMiddleware.process" in c for c in collapsed)

    def test_zero_duration_span(self):
        spans = [
            MockSpan(name="instant", span_id="z1", start_time_ns=100, end_time_ns=100),
        ]
        collapser = StackCollapser()
        roots = collapser.collapse_spans(spans)
        assert roots[0].total_time_ns == 0
        assert roots[0].self_time_ns == 0


# ============================================================
# Color Utility Tests
# ============================================================


class TestColorUtilities:
    """Tests for color mapping functions."""

    def test_known_subsystem_cache(self):
        color = _subsystem_color("CacheMiddleware.process")
        assert "120" in color  # Green hue

    def test_known_subsystem_compliance(self):
        color = _subsystem_color("ComplianceMiddleware.process")
        assert "hsl(0" in color  # Red hue

    def test_known_subsystem_ml(self):
        color = _subsystem_color("MLEngine.predict")
        assert "280" in color  # Purple hue

    def test_unknown_subsystem_deterministic(self):
        color_a = _subsystem_color("FooBarBaz")
        color_b = _subsystem_color("FooBarBaz")
        assert color_a == color_b

    def test_different_names_different_colors(self):
        color_a = _subsystem_color("AlphaService")
        color_b = _subsystem_color("BetaService")
        # Not guaranteed different, but likely
        # At minimum both should be valid HSL
        assert color_a.startswith("hsl(")
        assert color_b.startswith("hsl(")

    def test_diff_color_positive(self):
        color = _diff_color(50.0)
        assert "hsl(0" in color  # Red for slower

    def test_diff_color_negative(self):
        color = _diff_color(-50.0)
        assert f"hsl({DIFF_FASTER_HUE}" in color  # Blue for faster

    def test_diff_color_neutral(self):
        color = _diff_color(0.0)
        assert "70%" in color  # Grey

    def test_diff_color_extreme_positive(self):
        color = _diff_color(200.0)  # Clamped to 100
        assert "hsl(0" in color

    def test_diff_color_extreme_negative(self):
        color = _diff_color(-200.0)  # Clamped to -100
        assert f"hsl({DIFF_FASTER_HUE}" in color


# ============================================================
# SVG Renderer Tests
# ============================================================


class TestSVGRenderer:
    """Tests for SVG flame graph rendering."""

    def test_render_empty(self):
        renderer = SVGRenderer()
        svg = renderer.render([])
        assert '<?xml version="1.0"' in svg
        assert "<svg" in svg
        assert "</svg>" in svg
        assert "No spans collected" in svg

    def test_render_single_frame(self):
        frame = FlameFrame(
            name="root", self_time_ns=1000, total_time_ns=1000, depth=0
        )
        renderer = SVGRenderer()
        svg = renderer.render([frame])
        assert '<?xml version="1.0"' in svg
        assert "root" in svg
        assert "</svg>" in svg

    def test_render_valid_svg(self):
        spans = make_span_tree()
        collapser = StackCollapser()
        roots = collapser.collapse_spans(spans)

        renderer = SVGRenderer()
        svg = renderer.render(roots)

        # Parse as XML to validate structure
        # Strip XML declaration for ET compatibility
        svg_body = svg.split("?>", 1)[-1].strip()
        root_el = ET.fromstring(svg_body)
        assert root_el.tag.endswith("svg")

    def test_render_contains_all_spans(self):
        spans = make_span_tree()
        collapser = StackCollapser()
        roots = collapser.collapse_spans(spans)

        renderer = SVGRenderer()
        svg = renderer.render(roots)

        assert "RuleEngine.evaluate" in svg
        assert "CacheMiddleware.process" in svg
        assert "CacheStore.lookup" in svg
        assert "ComplianceMiddleware.process" in svg

    def test_render_has_viewbox(self):
        frame = FlameFrame(name="test", total_time_ns=100, depth=0)
        renderer = SVGRenderer(width=800)
        svg = renderer.render([frame])
        assert 'viewBox="0 0 800' in svg

    def test_render_custom_title(self):
        frame = FlameFrame(name="test", total_time_ns=100, depth=0)
        renderer = SVGRenderer(title="Custom Title")
        svg = renderer.render([frame])
        assert "Custom Title" in svg

    def test_render_title_bar_stats(self):
        spans = make_span_tree()
        collapser = StackCollapser()
        roots = collapser.collapse_spans(spans)

        renderer = SVGRenderer()
        svg = renderer.render(roots)

        assert "Spans:" in svg
        assert "Max depth:" in svg

    def test_render_tooltips(self):
        spans = make_span_tree()
        collapser = StackCollapser()
        roots = collapser.collapse_spans(spans)

        renderer = SVGRenderer()
        svg = renderer.render(roots)

        assert "<title>" in svg
        assert "Total:" in svg
        assert "Self:" in svg

    def test_render_color_coding(self):
        spans = make_span_tree()
        collapser = StackCollapser()
        roots = collapser.collapse_spans(spans)

        renderer = SVGRenderer()
        svg = renderer.render(roots)

        # Should contain fill attributes with hsl colors
        assert "hsl(" in svg

    def test_render_responsive_width(self):
        frame = FlameFrame(name="test", total_time_ns=100, depth=0)
        renderer = SVGRenderer(width=1600)
        svg = renderer.render([frame])
        assert 'width="1600"' in svg

    def test_render_configurable_frame_height(self):
        frame = FlameFrame(name="test", total_time_ns=100, depth=0)
        renderer = SVGRenderer(frame_height=24)
        svg = renderer.render([frame])
        assert 'height="23"' in svg  # frame_height - 1

    def test_render_deep_tree(self):
        spans = make_deep_span_tree(20)
        collapser = StackCollapser()
        roots = collapser.collapse_spans(spans)

        renderer = SVGRenderer()
        svg = renderer.render(roots)
        assert "</svg>" in svg

    def test_render_wide_tree(self):
        spans = make_wide_span_tree(10)
        collapser = StackCollapser()
        roots = collapser.collapse_spans(spans)

        renderer = SVGRenderer()
        svg = renderer.render(roots)
        for i in range(10):
            assert f"Middleware{i}.process" in svg

    def test_format_time_nanoseconds(self):
        assert SVGRenderer._format_time(500) == "500ns"

    def test_format_time_microseconds(self):
        result = SVGRenderer._format_time(1500)
        assert "\u00b5s" in result

    def test_format_time_milliseconds(self):
        result = SVGRenderer._format_time(1_500_000)
        assert "ms" in result

    def test_format_time_seconds(self):
        result = SVGRenderer._format_time(1_500_000_000)
        assert "s" in result

    def test_render_multiple_roots(self):
        roots = [
            FlameFrame(name="root_a", total_time_ns=500, self_time_ns=500, depth=0),
            FlameFrame(name="root_b", total_time_ns=300, self_time_ns=300, depth=0),
        ]
        renderer = SVGRenderer()
        svg = renderer.render(roots)
        assert "root_a" in svg
        assert "root_b" in svg


# ============================================================
# Icicle Chart Tests
# ============================================================


class TestIcicleChart:
    """Tests for the inverted flame graph (icicle chart)."""

    def test_render_empty(self):
        chart = IcicleChart()
        svg = chart.render([])
        assert "No spans collected" in svg

    def test_render_produces_valid_svg(self):
        spans = make_span_tree()
        collapser = StackCollapser()
        roots = collapser.collapse_spans(spans)

        chart = IcicleChart()
        svg = chart.render(roots)
        assert '<?xml version="1.0"' in svg
        assert "</svg>" in svg

    def test_render_top_down_orientation(self):
        chart = IcicleChart(title="Icicle Test")
        frame = FlameFrame(name="root", total_time_ns=100, depth=0)
        svg = chart.render([frame])
        assert "Icicle Test" in svg

    def test_render_contains_frame_names(self):
        spans = make_span_tree()
        collapser = StackCollapser()
        roots = collapser.collapse_spans(spans)

        chart = IcicleChart()
        svg = chart.render(roots)
        assert "RuleEngine.evaluate" in svg


# ============================================================
# DifferentialFlameGraph Tests
# ============================================================


class TestDifferentialFlameGraph:
    """Tests for differential flame graph generation."""

    def test_diff_empty_inputs(self):
        diff = DifferentialFlameGraph()
        svg = diff.diff([], [])
        assert "</svg>" in svg

    def test_diff_same_data(self):
        frame_a = FlameFrame(
            name="root", total_time_ns=1000, self_time_ns=1000, depth=0
        )
        frame_b = FlameFrame(
            name="root", total_time_ns=1000, self_time_ns=1000, depth=0
        )
        diff = DifferentialFlameGraph()
        svg = diff.diff([frame_a], [frame_b])
        assert "</svg>" in svg

    def test_diff_regression_detected(self):
        before = [FlameFrame(name="slow", total_time_ns=100, self_time_ns=100, depth=0)]
        after = [FlameFrame(name="slow", total_time_ns=200, self_time_ns=200, depth=0)]

        diff = DifferentialFlameGraph()
        svg = diff.diff(before, after)
        assert "Regressions:" in svg

    def test_diff_improvement_detected(self):
        before = [FlameFrame(name="fast", total_time_ns=200, self_time_ns=200, depth=0)]
        after = [FlameFrame(name="fast", total_time_ns=100, self_time_ns=100, depth=0)]

        diff = DifferentialFlameGraph()
        svg = diff.diff(before, after)
        assert "Improvements:" in svg

    def test_diff_new_frame(self):
        before: list[FlameFrame] = []
        after = [FlameFrame(name="new_code", total_time_ns=500, self_time_ns=500, depth=0)]

        diff = DifferentialFlameGraph()
        svg = diff.diff(before, after)
        assert "</svg>" in svg

    def test_diff_removed_frame(self):
        before = [FlameFrame(name="old_code", total_time_ns=500, self_time_ns=500, depth=0)]
        after: list[FlameFrame] = []

        diff = DifferentialFlameGraph()
        svg = diff.diff(before, after)
        assert "</svg>" in svg

    def test_diff_produces_valid_svg(self):
        spans_a = make_span_tree()
        spans_b = make_span_tree()
        # Make "after" spans slightly slower
        for s in spans_b:
            s.end_time_ns += 50

        collapser = StackCollapser()
        before = collapser.collapse_spans(spans_a)
        after = collapser.collapse_spans(spans_b)

        diff = DifferentialFlameGraph()
        svg = diff.diff(before, after)
        assert '<?xml version="1.0"' in svg

    def test_diff_legend_present(self):
        before = [FlameFrame(name="test", total_time_ns=100, self_time_ns=100, depth=0)]
        after = [FlameFrame(name="test", total_time_ns=150, self_time_ns=150, depth=0)]

        diff = DifferentialFlameGraph()
        svg = diff.diff(before, after)
        assert "Slower" in svg
        assert "Faster" in svg
        assert "No change" in svg


# ============================================================
# TimelineHeatMap Tests
# ============================================================


class TestTimelineHeatMap:
    """Tests for the timeline heat map."""

    def test_compute_empty_buckets(self):
        hm = TimelineHeatMap()
        buckets = hm.compute_buckets([])
        assert buckets == []

    def test_compute_buckets_count(self):
        hm = TimelineHeatMap(bucket_count=10)
        spans = make_span_tree()
        buckets = hm.compute_buckets(spans)
        assert len(buckets) == 10

    def test_bucket_span_count(self):
        hm = TimelineHeatMap(bucket_count=5)
        spans = make_span_tree()
        buckets = hm.compute_buckets(spans)

        # At least one bucket should have spans
        total_activity = sum(b.span_count for b in buckets)
        assert total_activity > 0

    def test_bucket_subsystems_populated(self):
        hm = TimelineHeatMap(bucket_count=5)
        spans = make_span_tree()
        buckets = hm.compute_buckets(spans)

        all_subs = set()
        for b in buckets:
            all_subs.update(b.subsystems)
        assert len(all_subs) > 0

    def test_render_svg_empty(self):
        hm = TimelineHeatMap()
        svg = hm.render_svg([])
        assert "</svg>" in svg
        assert "No span data" in svg

    def test_render_svg_valid(self):
        hm = TimelineHeatMap(bucket_count=10)
        spans = make_span_tree()
        buckets = hm.compute_buckets(spans)
        svg = hm.render_svg(buckets)

        assert '<?xml version="1.0"' in svg
        assert "</svg>" in svg

    def test_render_svg_has_tooltip(self):
        hm = TimelineHeatMap(bucket_count=5)
        spans = make_span_tree()
        buckets = hm.compute_buckets(spans)
        svg = hm.render_svg(buckets)
        assert "<title>" in svg
        assert "Active spans:" in svg

    def test_render_svg_has_axis_labels(self):
        hm = TimelineHeatMap(bucket_count=5)
        spans = make_span_tree()
        buckets = hm.compute_buckets(spans)
        svg = hm.render_svg(buckets)
        assert "t=0" in svg
        assert "t=end" in svg

    def test_heat_map_custom_dimensions(self):
        hm = TimelineHeatMap(width=800, height=200)
        spans = make_span_tree()
        buckets = hm.compute_buckets(spans)
        svg = hm.render_svg(buckets)
        assert 'width="800"' in svg
        assert 'height="200"' in svg


# ============================================================
# FlameGraphDashboard Tests (ASCII)
# ============================================================


class TestFlameGraphDashboard:
    """Tests for the ASCII flame graph dashboard."""

    def test_render_empty(self):
        dash = FlameGraphDashboard()
        output = dash.render([])
        assert "FizzFlame" in output
        assert "No flame graph data collected" in output

    def test_render_summary(self):
        spans = make_span_tree()
        collapser = StackCollapser()
        roots = collapser.collapse_spans(spans)

        dash = FlameGraphDashboard()
        output = dash.render(roots)
        assert "Total time:" in output
        assert "Span count:" in output
        assert "Max depth:" in output

    def test_render_top_frames_by_self_time(self):
        spans = make_span_tree()
        collapser = StackCollapser()
        roots = collapser.collapse_spans(spans)

        dash = FlameGraphDashboard()
        output = dash.render(roots)
        assert "Top Frames by Self Time" in output

    def test_render_top_frames_by_total_time(self):
        spans = make_span_tree()
        collapser = StackCollapser()
        roots = collapser.collapse_spans(spans)

        dash = FlameGraphDashboard()
        output = dash.render(roots)
        assert "Top Frames by Total Time" in output

    def test_render_subsystem_distribution(self):
        spans = make_span_tree()
        collapser = StackCollapser()
        roots = collapser.collapse_spans(spans)

        dash = FlameGraphDashboard()
        output = dash.render(roots)
        assert "Subsystem Time Distribution" in output

    def test_render_ascii_flame(self):
        spans = make_span_tree()
        collapser = StackCollapser()
        roots = collapser.collapse_spans(spans)

        dash = FlameGraphDashboard()
        output = dash.render(roots)
        assert "Flame Graph (ASCII)" in output

    def test_render_custom_width(self):
        dash = FlameGraphDashboard(width=100)
        spans = make_span_tree()
        collapser = StackCollapser()
        roots = collapser.collapse_spans(spans)
        output = dash.render(roots)
        assert "FizzFlame" in output

    def test_render_border_present(self):
        dash = FlameGraphDashboard(width=72)
        output = dash.render([])
        assert "+" + "-" * 70 + "+" in output


# ============================================================
# FlameGraphMiddleware Tests
# ============================================================


class TestFlameGraphMiddleware:
    """Tests for the flame graph middleware."""

    def test_get_name(self):
        mw = FlameGraphMiddleware()
        assert mw.get_name() == "FlameGraphMiddleware"

    def test_process_passthrough(self):
        mw = FlameGraphMiddleware()
        ctx = MagicMock(spec=ProcessingContext)

        def next_handler(c):
            return c

        result = mw.process(ctx, next_handler)
        assert result == ctx

    def test_eval_count_incremented(self):
        mw = FlameGraphMiddleware()
        ctx = MagicMock(spec=ProcessingContext)

        mw.process(ctx, lambda c: c)
        mw.process(ctx, lambda c: c)
        mw.process(ctx, lambda c: c)

        assert mw.eval_count == 3

    def test_eval_times_recorded(self):
        mw = FlameGraphMiddleware()
        ctx = MagicMock(spec=ProcessingContext)

        mw.process(ctx, lambda c: c)

        assert len(mw.eval_times) == 1
        start, end = mw.eval_times[0]
        assert start > 0
        assert end >= start

    def test_add_spans(self):
        mw = FlameGraphMiddleware()
        spans = make_span_tree()
        mw.add_spans(spans)

        assert len(mw.collected_spans) == 4

    def test_collected_spans_defensive_copy(self):
        mw = FlameGraphMiddleware()
        spans = make_span_tree()
        mw.add_spans(spans)

        collected = mw.collected_spans
        collected.clear()
        assert len(mw.collected_spans) == 4  # Original unchanged

    def test_generate_flame_graph(self):
        mw = FlameGraphMiddleware()
        mw.add_spans(make_span_tree())

        svg = mw.generate_flame_graph()
        assert '<?xml version="1.0"' in svg
        assert "</svg>" in svg

    def test_generate_flame_graph_to_file(self, tmp_path):
        mw = FlameGraphMiddleware()
        mw.add_spans(make_span_tree())

        output = str(tmp_path / "test.svg")
        svg = mw.generate_flame_graph(output_path=output)

        with open(output, "r", encoding="utf-8") as f:
            content = f.read()
        assert content == svg

    def test_generate_icicle_chart(self):
        mw = FlameGraphMiddleware()
        mw.add_spans(make_span_tree())

        svg = mw.generate_icicle_chart()
        assert "</svg>" in svg

    def test_generate_heat_map(self):
        mw = FlameGraphMiddleware()
        mw.add_spans(make_span_tree())

        svg = mw.generate_heat_map()
        assert "</svg>" in svg

    def test_generate_dashboard(self):
        mw = FlameGraphMiddleware()
        mw.add_spans(make_span_tree())

        output = mw.generate_dashboard()
        assert "FizzFlame" in output
        assert "Total time:" in output


# ============================================================
# XML Escape Tests
# ============================================================


class TestEscapeXml:
    """Tests for XML escape utility."""

    def test_ampersand(self):
        assert _escape_xml("a & b") == "a &amp; b"

    def test_less_than(self):
        assert _escape_xml("a < b") == "a &lt; b"

    def test_greater_than(self):
        assert _escape_xml("a > b") == "a &gt; b"

    def test_double_quote(self):
        assert _escape_xml('a "b" c') == "a &quot;b&quot; c"

    def test_single_quote(self):
        assert _escape_xml("a 'b' c") == "a &apos;b&apos; c"

    def test_no_escape_needed(self):
        assert _escape_xml("hello world") == "hello world"

    def test_all_special_chars(self):
        result = _escape_xml('<tag attr="val" & \'quoted\'>')
        assert "&lt;" in result
        assert "&gt;" in result
        assert "&amp;" in result
        assert "&quot;" in result
        assert "&apos;" in result


# ============================================================
# Edge Cases and Error Handling
# ============================================================


class TestEdgeCases:
    """Tests for edge cases and error handling."""

    def test_negative_timing_clamped_to_zero(self):
        spans = [
            MockSpan(
                name="backwards",
                span_id="neg1",
                start_time_ns=200,
                end_time_ns=100,  # end before start
            ),
        ]
        collapser = StackCollapser()
        roots = collapser.collapse_spans(spans)
        assert roots[0].total_time_ns == 0

    def test_very_large_span_tree(self):
        """Ensure the collapser handles 100+ spans without error."""
        spans = [
            MockSpan(
                name="root", span_id="bigroot",
                start_time_ns=0, end_time_ns=100_000,
            )
        ]
        for i in range(100):
            spans.append(MockSpan(
                name=f"child_{i}", span_id=f"big{i:04d}",
                parent_span_id="bigroot",
                start_time_ns=i * 1000,
                end_time_ns=(i + 1) * 1000,
            ))

        collapser = StackCollapser()
        roots = collapser.collapse_spans(spans)
        assert len(roots) == 1
        assert len(roots[0].children) == 100

    def test_render_very_narrow_frames(self):
        """Frames too narrow for text should render without error."""
        root = FlameFrame(
            name="root", total_time_ns=1_000_000, self_time_ns=0, depth=0,
            children=[
                FlameFrame(
                    name=f"tiny_{i}", total_time_ns=1, self_time_ns=1, depth=1,
                )
                for i in range(100)
            ],
        )
        renderer = SVGRenderer(width=200)
        svg = renderer.render([root])
        assert "</svg>" in svg

    def test_heat_map_all_zero_duration_spans(self):
        spans = [
            MockSpan(name=f"z{i}", span_id=f"z{i}", start_time_ns=100, end_time_ns=100)
            for i in range(5)
        ]
        hm = TimelineHeatMap(bucket_count=5)
        buckets = hm.compute_buckets(spans)
        # No valid timeline — should return empty
        assert len(buckets) == 0

    def test_flame_frame_with_attributes(self):
        frame = FlameFrame(
            name="test",
            attributes={"fizzotel.sampled": True, "custom": "value"},
        )
        assert frame.attributes["custom"] == "value"

    def test_svg_xml_declaration(self):
        renderer = SVGRenderer()
        svg = renderer.render([FlameFrame(name="x", total_time_ns=1, depth=0)])
        assert svg.startswith('<?xml version="1.0" encoding="UTF-8"')

    def test_svg_namespace(self):
        renderer = SVGRenderer()
        svg = renderer.render([FlameFrame(name="x", total_time_ns=1, depth=0)])
        assert 'xmlns="http://www.w3.org/2000/svg"' in svg

    def test_heat_map_bucket_dataclass(self):
        bucket = HeatMapBucket(
            start_ns=0, end_ns=100, span_count=5,
            subsystems={"cache", "auth"}, max_depth=3,
        )
        assert bucket.span_count == 5
        assert "cache" in bucket.subsystems

    def test_flame_orientation_enum(self):
        assert FlameOrientation.BOTTOM_UP.value == "bottom_up"
        assert FlameOrientation.TOP_DOWN.value == "top_down"


# ============================================================
# Integration Tests
# ============================================================


class TestIntegration:
    """End-to-end integration tests."""

    def test_full_pipeline_span_to_svg(self):
        """Complete pipeline: spans → collapse → render → valid SVG."""
        spans = make_span_tree()
        collapser = StackCollapser()
        roots = collapser.collapse_spans(spans)
        stacks = collapser.extract_stacks(roots)

        renderer = SVGRenderer(
            width=1000,
            frame_height=20,
            title="Integration Test Flame Graph",
        )
        svg = renderer.render(roots)

        # Validate SVG structure
        assert '<?xml version="1.0"' in svg
        assert 'viewBox="0 0 1000' in svg
        assert "Integration Test Flame Graph" in svg
        assert "</svg>" in svg

    def test_full_pipeline_icicle(self):
        """Complete pipeline: spans → collapse → icicle chart."""
        spans = make_span_tree()
        collapser = StackCollapser()
        roots = collapser.collapse_spans(spans)

        chart = IcicleChart(title="Icicle Integration")
        svg = chart.render(roots)
        assert "Icicle Integration" in svg

    def test_full_pipeline_heat_map(self):
        """Complete pipeline: spans → heat map → SVG."""
        spans = make_span_tree()
        hm = TimelineHeatMap(bucket_count=20, width=800)
        buckets = hm.compute_buckets(spans)
        svg = hm.render_svg(buckets)
        assert "</svg>" in svg

    def test_full_pipeline_dashboard(self):
        """Complete pipeline: spans → collapse → ASCII dashboard."""
        spans = make_span_tree()
        collapser = StackCollapser()
        roots = collapser.collapse_spans(spans)

        dash = FlameGraphDashboard(width=80)
        output = dash.render(roots, spans=spans)
        assert "FizzFlame" in output
        assert "RuleEngine.evaluate" in output

    def test_middleware_full_pipeline(self):
        """Middleware collects spans and generates all output formats."""
        mw = FlameGraphMiddleware()
        ctx = MagicMock(spec=ProcessingContext)

        # Simulate evaluations
        for _ in range(5):
            mw.process(ctx, lambda c: c)

        # Add spans
        mw.add_spans(make_span_tree())

        # All formats should succeed
        svg = mw.generate_flame_graph()
        assert "</svg>" in svg

        icicle = mw.generate_icicle_chart()
        assert "</svg>" in icicle

        heat = mw.generate_heat_map()
        assert "</svg>" in heat

        dash = mw.generate_dashboard()
        assert "FizzFlame" in dash
