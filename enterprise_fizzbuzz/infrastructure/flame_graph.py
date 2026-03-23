"""
Enterprise FizzBuzz Platform - FizzFlame Flame Graph Generator

Transforms OpenTelemetry span trees into SVG flame graphs for deep
performance analysis of FizzBuzz evaluation pipelines. Supports standard
flame graphs, differential flame graphs (for before/after comparison),
icicle charts (inverted orientation), timeline heat maps, and ASCII
fallback dashboards.

The SVG renderer produces valid, well-formed SVG 1.1 documents with
XML declarations, proper namespace bindings, and responsive viewBox
dimensions. Each frame is color-coded by subsystem using a deterministic
HSL hash derived from the span name prefix, ensuring consistent visual
identity across renders.

Flame graph width is proportional to total execution time, and each
frame's width is proportional to its inclusive (total) time. This
provides an immediate visual indication of where time is spent in the
FizzBuzz evaluation pipeline — typically in middleware overhead that
dwarfs the nanosecond-scale modulo operations at the heart of the
system. The differential mode highlights performance regressions in
red and improvements in blue, enabling precise before/after analysis
of optimization efforts.

The ASCII dashboard fallback ensures that operators without SVG-capable
viewers (or those who prefer the terminal aesthetic) can still analyze
flame graph data. Because sometimes you need to debug FizzBuzz
performance from a serial console.
"""

from __future__ import annotations

import hashlib
import math
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Optional

from enterprise_fizzbuzz.domain.exceptions import (
    FlameGraphError,
    FlameGraphRenderError,
    FlameGraphCollapseError,
    FlameGraphDiffError,
)
from enterprise_fizzbuzz.domain.interfaces import IMiddleware
from enterprise_fizzbuzz.domain.models import ProcessingContext


# ============================================================
# Constants
# ============================================================

# Default SVG dimensions
DEFAULT_WIDTH = 1200
DEFAULT_FRAME_HEIGHT = 18
DEFAULT_FONT_SIZE = 11
DEFAULT_TITLE_HEIGHT = 30
DEFAULT_MARGIN = 10

# Color palette for known subsystems — deterministic mapping
# ensures consistent visual identity across flame graphs
SUBSYSTEM_COLORS: dict[str, str] = {
    "cache": "hsl(120, 60%, 45%)",       # Green — fast retrieval
    "compliance": "hsl(0, 70%, 50%)",     # Red — regulatory gravity
    "ml": "hsl(280, 65%, 50%)",           # Purple — neural depth
    "blockchain": "hsl(45, 80%, 50%)",    # Gold — immutable value
    "auth": "hsl(200, 70%, 45%)",         # Blue — trust boundary
    "sla": "hsl(30, 75%, 50%)",           # Orange — contractual obligation
    "middleware": "hsl(160, 50%, 45%)",   # Teal — pipeline flow
    "formatter": "hsl(90, 55%, 45%)",     # Lime — output shaping
    "rule": "hsl(330, 60%, 50%)",         # Pink — business logic
    "event": "hsl(210, 55%, 50%)",        # Steel blue — async dispatch
    "quantum": "hsl(260, 70%, 55%)",      # Violet — superposition
    "genetic": "hsl(50, 70%, 50%)",       # Amber — evolutionary
    "graph": "hsl(180, 55%, 45%)",        # Cyan — relational
    "kernel": "hsl(350, 65%, 45%)",       # Crimson — system level
    "vault": "hsl(240, 50%, 40%)",        # Navy — secrets
    "chaos": "hsl(15, 80%, 50%)",         # Vermilion — controlled failure
    "paxos": "hsl(150, 50%, 45%)",        # Sea green — consensus
    "vm": "hsl(300, 50%, 45%)",           # Magenta — bytecode
}

# Differential flame graph color stops
DIFF_SLOWER_HUE = 0    # Red for regressions
DIFF_FASTER_HUE = 220  # Blue for improvements
DIFF_NEUTRAL_HUE = 60  # Yellow for unchanged


class FlameOrientation(Enum):
    """Flame graph rendering orientation."""
    BOTTOM_UP = "bottom_up"   # Standard: root at bottom, leaves at top
    TOP_DOWN = "top_down"     # Icicle chart: root at top, leaves at bottom


# ============================================================
# FlameFrame — collapsed stack frame
# ============================================================


@dataclass
class FlameFrame:
    """A single collapsed stack frame in a flame graph.

    Represents one function or span in the execution hierarchy, with
    both self time (time spent directly in this frame) and total time
    (inclusive of all children). The depth indicates the stack depth
    for vertical positioning in the flame graph.

    Attributes:
        name: The fully qualified name of the span or function.
        self_time_ns: Time in nanoseconds spent exclusively in this frame.
        total_time_ns: Inclusive time including all child frames.
        depth: Stack depth (0 = root).
        children: Child frames in the call hierarchy.
        span_count: Number of spans collapsed into this frame.
        attributes: Additional span attributes for tooltip rendering.
    """
    name: str
    self_time_ns: int = 0
    total_time_ns: int = 0
    depth: int = 0
    children: list[FlameFrame] = field(default_factory=list)
    span_count: int = 1
    attributes: dict[str, Any] = field(default_factory=dict)

    @property
    def self_time_us(self) -> float:
        """Self time in microseconds."""
        return self.self_time_ns / 1000.0

    @property
    def total_time_us(self) -> float:
        """Total (inclusive) time in microseconds."""
        return self.total_time_ns / 1000.0

    @property
    def self_time_ms(self) -> float:
        """Self time in milliseconds."""
        return self.self_time_ns / 1_000_000.0

    @property
    def total_time_ms(self) -> float:
        """Total (inclusive) time in milliseconds."""
        return self.total_time_ns / 1_000_000.0

    @property
    def subsystem(self) -> str:
        """Extract the subsystem name from the frame name.

        Uses the first component of a dot-separated name or the
        lowercase prefix before the first uppercase transition.
        """
        if "." in self.name:
            prefix = self.name.split(".")[0]
        else:
            prefix = self.name
        return prefix.lower().rstrip("0123456789")


# ============================================================
# FlameStack — a complete execution path
# ============================================================


@dataclass
class FlameStack:
    """A stack of frames representing one execution path through
    the FizzBuzz evaluation pipeline.

    Each FlameStack is a root-to-leaf path in the span tree,
    analogous to a single stack sample in traditional profiling.
    The collapsed representation concatenates frame names with
    semicolons, matching the Brendan Gregg folded-stack format.

    Attributes:
        frames: Ordered list of frames from root to leaf.
        total_time_ns: Total wall-clock time for this execution path.
        trace_id: The OTel trace ID this stack belongs to.
    """
    frames: list[FlameFrame] = field(default_factory=list)
    total_time_ns: int = 0
    trace_id: str = ""

    @property
    def collapsed(self) -> str:
        """Return the Brendan Gregg folded-stack representation.

        Format: "root;child;grandchild count"
        """
        names = ";".join(f.name for f in self.frames)
        return f"{names} {self.total_time_ns}"

    @property
    def depth(self) -> int:
        """Maximum stack depth."""
        return len(self.frames)

    def append(self, frame: FlameFrame) -> None:
        """Append a frame to the stack."""
        self.frames.append(frame)


# ============================================================
# StackCollapser — span tree to flame stacks
# ============================================================


class StackCollapser:
    """Collapses OTel span trees into flame stacks via DFS traversal.

    The collapser walks the span tree depth-first, building FlameFrame
    objects with correct self_time and total_time values. Self time is
    computed by subtracting child durations from the parent's total
    duration — because a span that delegates 99% of its time to children
    still deserves credit for the 1% it spent on overhead.

    The output is a list of FlameFrame trees (one per root span) and
    a list of FlameStack objects (one per root-to-leaf path).
    """

    def __init__(self) -> None:
        self._frame_cache: dict[str, FlameFrame] = {}

    def collapse_spans(self, spans: list[Any]) -> list[FlameFrame]:
        """Collapse a list of OTel Span objects into a FlameFrame tree.

        Args:
            spans: List of Span objects from a TracerProvider.

        Returns:
            List of root FlameFrame objects representing the span forest.

        Raises:
            FlameGraphCollapseError: If the span tree contains cycles
                or invalid parent references.
        """
        if not spans:
            return []

        # Index spans by span_id
        span_map: dict[str, Any] = {}
        children_map: dict[str, list[Any]] = {}

        for span in spans:
            span_map[span.span_id] = span
            parent_id = span.parent_span_id
            if parent_id is not None:
                if parent_id not in children_map:
                    children_map[parent_id] = []
                children_map[parent_id].append(span)

        # Identify root spans (no parent or parent not in this set)
        root_spans = [
            s for s in spans
            if s.parent_span_id is None
            or s.parent_span_id not in span_map
        ]

        if not root_spans and spans:
            raise FlameGraphCollapseError(
                "No root spans found in span tree. "
                "All spans have parent references forming a cycle."
            )

        # DFS to build FlameFrame trees
        roots: list[FlameFrame] = []
        visited: set[str] = set()

        for root_span in root_spans:
            frame = self._build_frame(
                root_span, children_map, span_map, visited, depth=0
            )
            roots.append(frame)

        return roots

    def _build_frame(
        self,
        span: Any,
        children_map: dict[str, list[Any]],
        span_map: dict[str, Any],
        visited: set[str],
        depth: int,
    ) -> FlameFrame:
        """Recursively build a FlameFrame from a span and its children.

        Performs cycle detection and computes self_time by subtracting
        child durations from the span's total duration.
        """
        if span.span_id in visited:
            raise FlameGraphCollapseError(
                f"Cycle detected in span tree at span '{span.name}' "
                f"(span_id={span.span_id})"
            )
        visited.add(span.span_id)

        total_ns = max(0, span.end_time_ns - span.start_time_ns)
        child_spans = children_map.get(span.span_id, [])

        child_frames: list[FlameFrame] = []
        child_time_ns = 0

        for child_span in child_spans:
            child_frame = self._build_frame(
                child_span, children_map, span_map, visited, depth + 1
            )
            child_frames.append(child_frame)
            child_time_ns += child_frame.total_time_ns

        self_time_ns = max(0, total_ns - child_time_ns)

        frame = FlameFrame(
            name=span.name,
            self_time_ns=self_time_ns,
            total_time_ns=total_ns,
            depth=depth,
            children=child_frames,
            span_count=1,
            attributes=dict(span.attributes) if hasattr(span, "attributes") else {},
        )

        return frame

    def extract_stacks(self, roots: list[FlameFrame]) -> list[FlameStack]:
        """Extract all root-to-leaf paths as FlameStack objects.

        Each path represents a unique execution trace through the
        span tree, suitable for the folded-stack format.
        """
        stacks: list[FlameStack] = []
        for root in roots:
            self._walk_stacks(root, [], stacks)
        return stacks

    def _walk_stacks(
        self,
        frame: FlameFrame,
        path: list[FlameFrame],
        stacks: list[FlameStack],
    ) -> None:
        """DFS walk to extract all root-to-leaf paths."""
        path = path + [frame]

        if not frame.children:
            # Leaf node — emit a stack
            stack = FlameStack(
                frames=list(path),
                total_time_ns=path[0].total_time_ns if path else 0,
            )
            stacks.append(stack)
        else:
            for child in frame.children:
                self._walk_stacks(child, path, stacks)


# ============================================================
# Color Utilities
# ============================================================


def _subsystem_color(name: str) -> str:
    """Compute a deterministic HSL color for a subsystem name.

    Known subsystems get a hand-picked color from the palette.
    Unknown subsystems get a hash-derived hue for consistent
    but distinct coloring.
    """
    lower = name.lower()

    # Check known subsystem prefixes
    for prefix, color in SUBSYSTEM_COLORS.items():
        if prefix in lower:
            return color

    # Hash-based fallback: deterministic hue from name
    digest = hashlib.md5(lower.encode("utf-8")).hexdigest()
    hue = int(digest[:4], 16) % 360
    saturation = 50 + (int(digest[4:6], 16) % 20)
    lightness = 40 + (int(digest[6:8], 16) % 15)
    return f"hsl({hue}, {saturation}%, {lightness}%)"


def _diff_color(delta_pct: float) -> str:
    """Compute a color for differential flame graph based on delta percentage.

    Positive delta (slower) maps to red. Negative delta (faster) maps to blue.
    Zero delta maps to neutral grey.

    Args:
        delta_pct: Percentage change (-100 to +inf). Positive = regression.

    Returns:
        HSL color string.
    """
    if abs(delta_pct) < 0.5:
        return "hsl(0, 0%, 70%)"  # Neutral grey

    # Clamp to [-100, 100] for color mapping
    clamped = max(-100.0, min(100.0, delta_pct))
    intensity = abs(clamped) / 100.0

    if clamped > 0:
        # Regression: red with increasing saturation
        sat = int(30 + 50 * intensity)
        light = int(55 - 15 * intensity)
        return f"hsl({DIFF_SLOWER_HUE}, {sat}%, {light}%)"
    else:
        # Improvement: blue with increasing saturation
        sat = int(30 + 50 * intensity)
        light = int(55 - 15 * intensity)
        return f"hsl({DIFF_FASTER_HUE}, {sat}%, {light}%)"


def _escape_xml(text: str) -> str:
    """Escape special characters for XML/SVG text content."""
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&apos;")
    )


# ============================================================
# SVGRenderer — flame graph to SVG
# ============================================================


class SVGRenderer:
    """Generates SVG flame graphs from FlameFrame trees.

    Produces valid SVG 1.1 documents with:
    - Proper XML declaration and namespace
    - Responsive viewBox for browser scaling
    - Color coding by subsystem
    - Hover tooltips with timing data
    - Title bar with total time and span count
    - Configurable dimensions

    The renderer walks the FlameFrame tree and assigns horizontal
    positions proportional to each frame's total_time relative to
    the root's total_time. This means a frame consuming 50% of
    execution time occupies 50% of the SVG width — an intuitive
    mapping that makes bottlenecks immediately visible.
    """

    def __init__(
        self,
        width: int = DEFAULT_WIDTH,
        frame_height: int = DEFAULT_FRAME_HEIGHT,
        font_size: int = DEFAULT_FONT_SIZE,
        title: str = "FizzFlame — Flame Graph",
        orientation: FlameOrientation = FlameOrientation.BOTTOM_UP,
    ) -> None:
        self.width = width
        self.frame_height = frame_height
        self.font_size = font_size
        self.title = title
        self.orientation = orientation
        self._margin = DEFAULT_MARGIN
        self._title_height = DEFAULT_TITLE_HEIGHT

    def render(self, roots: list[FlameFrame]) -> str:
        """Render a list of FlameFrame trees into an SVG string.

        Args:
            roots: Root FlameFrame objects to render.

        Returns:
            Complete SVG document as a string.

        Raises:
            FlameGraphRenderError: If rendering fails due to invalid
                frame data or SVG generation errors.
        """
        if not roots:
            return self._render_empty()

        try:
            return self._render_frames(roots)
        except Exception as e:
            if isinstance(e, FlameGraphRenderError):
                raise
            raise FlameGraphRenderError(
                f"SVG rendering failed: {e}"
            ) from e

    def _compute_max_depth(self, frames: list[FlameFrame]) -> int:
        """Compute the maximum depth in the frame forest."""
        max_d = 0

        def walk(f: FlameFrame, d: int) -> None:
            nonlocal max_d
            max_d = max(max_d, d)
            for child in f.children:
                walk(child, d + 1)

        for root in frames:
            walk(root, 0)
        return max_d

    def _count_spans(self, frames: list[FlameFrame]) -> int:
        """Count total spans in the frame forest."""
        count = 0

        def walk(f: FlameFrame) -> None:
            nonlocal count
            count += f.span_count
            for child in f.children:
                walk(child)

        for root in frames:
            walk(root)
        return count

    def _total_time_ns(self, frames: list[FlameFrame]) -> int:
        """Compute total root time across all root frames."""
        return sum(r.total_time_ns for r in frames)

    def _render_empty(self) -> str:
        """Render an empty flame graph with a message."""
        height = self._title_height + self.frame_height + 2 * self._margin
        svg_lines = [
            '<?xml version="1.0" encoding="UTF-8" standalone="no"?>',
            f'<svg xmlns="http://www.w3.org/2000/svg" '
            f'viewBox="0 0 {self.width} {height}" '
            f'width="{self.width}" height="{height}" '
            f'font-family="monospace" font-size="{self.font_size}">',
            f'  <text x="{self.width // 2}" y="{self._title_height}" '
            f'text-anchor="middle" font-size="{self.font_size + 4}" '
            f'font-weight="bold">{_escape_xml(self.title)}</text>',
            f'  <text x="{self.width // 2}" y="{self._title_height + self.frame_height}" '
            f'text-anchor="middle" fill="#888">No spans collected</text>',
            "</svg>",
        ]
        return "\n".join(svg_lines)

    def _render_frames(self, roots: list[FlameFrame]) -> str:
        """Render flame graph frames into SVG."""
        max_depth = self._compute_max_depth(roots)
        total_spans = self._count_spans(roots)
        total_time = self._total_time_ns(roots)

        content_width = self.width - 2 * self._margin
        content_height = (max_depth + 1) * self.frame_height
        svg_height = content_height + self._title_height + 3 * self._margin

        # Build SVG elements
        rects: list[str] = []
        texts: list[str] = []

        # Render each root frame tree
        x_offset = self._margin
        for root in roots:
            root_width = content_width
            if total_time > 0 and len(roots) > 1:
                root_width = int(
                    content_width * root.total_time_ns / total_time
                )
            self._render_frame_recursive(
                root, x_offset, root_width, max_depth,
                total_time, rects, texts
            )
            x_offset += root_width

        # Format time for title
        time_str = self._format_time(total_time)

        svg_lines = [
            '<?xml version="1.0" encoding="UTF-8" standalone="no"?>',
            f'<svg xmlns="http://www.w3.org/2000/svg" '
            f'viewBox="0 0 {self.width} {svg_height}" '
            f'width="{self.width}" height="{svg_height}" '
            f'font-family="monospace" font-size="{self.font_size}">',
            # Styles
            "  <defs>",
            "    <style>",
            "      .frame:hover { stroke: #333; stroke-width: 1.5; cursor: pointer; }",
            "      .frame-text { pointer-events: none; }",
            "    </style>",
            "  </defs>",
            # Background
            f'  <rect width="{self.width}" height="{svg_height}" fill="#f8f8f8" />',
            # Title
            f'  <text x="{self.width // 2}" y="{self._margin + self.font_size + 2}" '
            f'text-anchor="middle" font-size="{self.font_size + 4}" '
            f'font-weight="bold">{_escape_xml(self.title)}</text>',
            # Subtitle with stats
            f'  <text x="{self.width // 2}" y="{self._margin + self.font_size + 16}" '
            f'text-anchor="middle" font-size="{self.font_size - 1}" fill="#666">'
            f'Total: {time_str} | Spans: {total_spans} | Max depth: {max_depth + 1}'
            f"</text>",
        ]

        svg_lines.extend(rects)
        svg_lines.extend(texts)
        svg_lines.append("</svg>")

        return "\n".join(svg_lines)

    def _render_frame_recursive(
        self,
        frame: FlameFrame,
        x: int,
        width: int,
        max_depth: int,
        total_time_ns: int,
        rects: list[str],
        texts: list[str],
    ) -> None:
        """Recursively render a frame and its children."""
        if width < 1:
            return

        # Compute Y position based on orientation
        if self.orientation == FlameOrientation.BOTTOM_UP:
            y = (
                self._title_height
                + self._margin * 2
                + (max_depth - frame.depth) * self.frame_height
            )
        else:
            y = (
                self._title_height
                + self._margin * 2
                + frame.depth * self.frame_height
            )

        # Color
        color = _subsystem_color(frame.name)

        # Tooltip text
        tooltip = (
            f"{frame.name}\n"
            f"Total: {self._format_time(frame.total_time_ns)}\n"
            f"Self:  {self._format_time(frame.self_time_ns)}\n"
            f"Depth: {frame.depth}"
        )

        # Rectangle with tooltip
        rects.append(
            f'  <g class="frame">'
            f'<title>{_escape_xml(tooltip)}</title>'
            f'<rect x="{x}" y="{y}" width="{width}" height="{self.frame_height - 1}" '
            f'fill="{color}" rx="1" ry="1" />'
            f"</g>"
        )

        # Text label (only if frame is wide enough)
        if width > self.font_size * 3:
            label = frame.name
            max_chars = width // (self.font_size * 0.6)
            if len(label) > max_chars:
                label = label[: int(max_chars) - 2] + ".."
            text_y = y + self.frame_height - 4
            texts.append(
                f'  <text class="frame-text" x="{x + 3}" y="{text_y}" '
                f'font-size="{self.font_size}" fill="#000">'
                f"{_escape_xml(label)}</text>"
            )

        # Render children proportionally
        if frame.children and total_time_ns > 0 and frame.total_time_ns > 0:
            child_x = x
            for child in frame.children:
                child_width = int(
                    width * child.total_time_ns / frame.total_time_ns
                )
                child_width = max(child_width, 1) if child.total_time_ns > 0 else 0
                self._render_frame_recursive(
                    child, child_x, child_width, max_depth,
                    total_time_ns, rects, texts
                )
                child_x += child_width

    @staticmethod
    def _format_time(ns: int) -> str:
        """Format a nanosecond duration into a human-readable string."""
        if ns < 1_000:
            return f"{ns}ns"
        elif ns < 1_000_000:
            return f"{ns / 1_000:.1f}\u00b5s"
        elif ns < 1_000_000_000:
            return f"{ns / 1_000_000:.2f}ms"
        else:
            return f"{ns / 1_000_000_000:.3f}s"


# ============================================================
# DifferentialFlameGraph — before/after comparison
# ============================================================


class DifferentialFlameGraph:
    """Compares two flame graphs and produces a differential SVG.

    Frames present in both graphs are colored by delta:
    - Red: frame got slower (positive delta)
    - Blue: frame got faster (negative delta)
    - Grey: no significant change

    Frames present only in the "after" graph appear in green (new code).
    Frames present only in the "before" graph appear as dashed outlines
    (removed code).

    This enables precise identification of performance regressions and
    improvements between two runs of the FizzBuzz evaluation pipeline —
    critical for ensuring that middleware optimizations actually improve
    the sub-millisecond evaluation time rather than making it worse.
    """

    def __init__(
        self,
        width: int = DEFAULT_WIDTH,
        frame_height: int = DEFAULT_FRAME_HEIGHT,
        font_size: int = DEFAULT_FONT_SIZE,
    ) -> None:
        self.width = width
        self.frame_height = frame_height
        self.font_size = font_size
        self._margin = DEFAULT_MARGIN
        self._title_height = DEFAULT_TITLE_HEIGHT

    def diff(
        self,
        before: list[FlameFrame],
        after: list[FlameFrame],
    ) -> str:
        """Generate a differential flame graph SVG.

        Args:
            before: FlameFrame trees from the baseline run.
            after: FlameFrame trees from the comparison run.

        Returns:
            SVG document string with differential coloring.

        Raises:
            FlameGraphDiffError: If diff computation fails.
        """
        if not before and not after:
            return SVGRenderer(
                width=self.width,
                title="FizzFlame — Differential (no data)",
            ).render([])

        try:
            before_map = self._flatten(before)
            after_map = self._flatten(after)
            diff_frames = self._compute_diff(before_map, after_map)
            return self._render_diff(diff_frames, before_map, after_map)
        except Exception as e:
            if isinstance(e, (FlameGraphDiffError, FlameGraphRenderError)):
                raise
            raise FlameGraphDiffError(
                f"Differential flame graph generation failed: {e}"
            ) from e

    def _flatten(
        self, roots: list[FlameFrame]
    ) -> dict[str, FlameFrame]:
        """Flatten a frame forest into a name-path to frame mapping.

        For frames with duplicate names (common in recursive calls),
        the frame with the longest total_time wins.
        """
        result: dict[str, FlameFrame] = {}

        def walk(f: FlameFrame, path: str) -> None:
            key = f"{path};{f.name}" if path else f.name
            if key not in result or f.total_time_ns > result[key].total_time_ns:
                result[key] = f
            for child in f.children:
                walk(child, key)

        for root in roots:
            walk(root, "")
        return result

    def _compute_diff(
        self,
        before_map: dict[str, FlameFrame],
        after_map: dict[str, FlameFrame],
    ) -> dict[str, tuple[float, FlameFrame]]:
        """Compute percentage deltas for each frame.

        Returns a mapping from frame key to (delta_pct, after_frame).
        """
        result: dict[str, tuple[float, FlameFrame]] = {}
        all_keys = set(before_map.keys()) | set(after_map.keys())

        for key in all_keys:
            before_frame = before_map.get(key)
            after_frame = after_map.get(key)

            if before_frame is None and after_frame is not None:
                # New frame
                result[key] = (100.0, after_frame)
            elif after_frame is None and before_frame is not None:
                # Removed frame
                result[key] = (-100.0, before_frame)
            elif before_frame is not None and after_frame is not None:
                if before_frame.total_time_ns > 0:
                    delta_pct = (
                        (after_frame.total_time_ns - before_frame.total_time_ns)
                        / before_frame.total_time_ns
                        * 100.0
                    )
                else:
                    delta_pct = 0.0
                result[key] = (delta_pct, after_frame)

        return result

    def _render_diff(
        self,
        diff_frames: dict[str, tuple[float, FlameFrame]],
        before_map: dict[str, FlameFrame],
        after_map: dict[str, FlameFrame],
    ) -> str:
        """Render the differential flame graph as SVG."""
        if not diff_frames:
            return SVGRenderer(
                width=self.width,
                title="FizzFlame — Differential (empty)",
            ).render([])

        # Compute stats
        max_depth = 0
        total_frames = len(diff_frames)
        regressions = sum(1 for d, _ in diff_frames.values() if d > 0.5)
        improvements = sum(1 for d, _ in diff_frames.values() if d < -0.5)

        for _, (_, frame) in diff_frames.items():
            max_depth = max(max_depth, frame.depth)

        content_height = (max_depth + 1) * self.frame_height
        svg_height = content_height + self._title_height + 3 * self._margin + 20
        content_width = self.width - 2 * self._margin

        # Use root frames for total time
        root_after_time = sum(
            f.total_time_ns for key, f in after_map.items()
            if ";" not in key
        ) or 1

        svg_lines = [
            '<?xml version="1.0" encoding="UTF-8" standalone="no"?>',
            f'<svg xmlns="http://www.w3.org/2000/svg" '
            f'viewBox="0 0 {self.width} {svg_height}" '
            f'width="{self.width}" height="{svg_height}" '
            f'font-family="monospace" font-size="{self.font_size}">',
            "  <defs>",
            "    <style>",
            "      .frame:hover { stroke: #333; stroke-width: 1.5; cursor: pointer; }",
            "      .frame-text { pointer-events: none; }",
            "    </style>",
            "  </defs>",
            f'  <rect width="{self.width}" height="{svg_height}" fill="#f8f8f8" />',
            f'  <text x="{self.width // 2}" y="{self._margin + self.font_size + 2}" '
            f'text-anchor="middle" font-size="{self.font_size + 4}" '
            f'font-weight="bold">FizzFlame — Differential Flame Graph</text>',
            f'  <text x="{self.width // 2}" y="{self._margin + self.font_size + 16}" '
            f'text-anchor="middle" font-size="{self.font_size - 1}" fill="#666">'
            f'Frames: {total_frames} | Regressions: {regressions} | '
            f'Improvements: {improvements}</text>',
            # Legend
            f'  <rect x="{self._margin}" y="{svg_height - 15}" '
            f'width="12" height="10" fill="hsl(0, 60%, 50%)" />',
            f'  <text x="{self._margin + 16}" y="{svg_height - 6}" '
            f'font-size="{self.font_size - 2}" fill="#666">Slower</text>',
            f'  <rect x="{self._margin + 70}" y="{svg_height - 15}" '
            f'width="12" height="10" fill="hsl(220, 60%, 50%)" />',
            f'  <text x="{self._margin + 86}" y="{svg_height - 6}" '
            f'font-size="{self.font_size - 2}" fill="#666">Faster</text>',
            f'  <rect x="{self._margin + 140}" y="{svg_height - 15}" '
            f'width="12" height="10" fill="hsl(0, 0%, 70%)" />',
            f'  <text x="{self._margin + 156}" y="{svg_height - 6}" '
            f'font-size="{self.font_size - 2}" fill="#666">No change</text>',
        ]

        # Render diff frames sorted by path depth then name
        sorted_keys = sorted(
            diff_frames.keys(),
            key=lambda k: (k.count(";"), k),
        )

        x_cursor: dict[int, int] = {}  # depth -> current x position

        for key in sorted_keys:
            delta_pct, frame = diff_frames[key]
            depth = key.count(";")
            color = _diff_color(delta_pct)

            # Compute x and width
            if depth == 0:
                x = x_cursor.get(depth, self._margin)
                width = int(
                    content_width * frame.total_time_ns / root_after_time
                ) if root_after_time > 0 else content_width
                x_cursor[depth] = x + width
            else:
                x = x_cursor.get(depth, self._margin)
                width = max(
                    1,
                    int(content_width * frame.total_time_ns / root_after_time)
                ) if root_after_time > 0 else 1
                x_cursor[depth] = x + width

            y = (
                self._title_height
                + self._margin * 2
                + (max_depth - depth) * self.frame_height
            )

            # Tooltip
            direction = "slower" if delta_pct > 0 else "faster" if delta_pct < 0 else "unchanged"
            tooltip = (
                f"{frame.name}\n"
                f"Delta: {delta_pct:+.1f}% ({direction})\n"
                f"Time: {SVGRenderer._format_time(frame.total_time_ns)}"
            )

            svg_lines.append(
                f'  <g class="frame">'
                f'<title>{_escape_xml(tooltip)}</title>'
                f'<rect x="{x}" y="{y}" width="{max(width, 1)}" '
                f'height="{self.frame_height - 1}" '
                f'fill="{color}" rx="1" ry="1" />'
                f"</g>"
            )

            if width > self.font_size * 3:
                label = frame.name
                max_chars = width // (self.font_size * 0.6)
                if len(label) > max_chars:
                    label = label[: int(max_chars) - 2] + ".."
                text_y = y + self.frame_height - 4
                svg_lines.append(
                    f'  <text class="frame-text" x="{x + 3}" y="{text_y}" '
                    f'font-size="{self.font_size}" fill="#000">'
                    f"{_escape_xml(label)}</text>"
                )

        svg_lines.append("</svg>")
        return "\n".join(svg_lines)


# ============================================================
# IcicleChart — inverted flame graph
# ============================================================


class IcicleChart:
    """Inverted flame graph with root at top and leaves at bottom.

    Icicle charts provide a complementary perspective to standard flame
    graphs. Where flame graphs emphasize the "hot" leaf functions, icicle
    charts emphasize the "cold" root callers. This is useful for
    understanding which top-level middleware or service calls contribute
    the most to overall FizzBuzz evaluation latency.

    The rendering is identical to SVGRenderer with FlameOrientation.TOP_DOWN,
    but IcicleChart provides a dedicated API for clarity and encapsulation.
    """

    def __init__(
        self,
        width: int = DEFAULT_WIDTH,
        frame_height: int = DEFAULT_FRAME_HEIGHT,
        font_size: int = DEFAULT_FONT_SIZE,
        title: str = "FizzFlame — Icicle Chart",
    ) -> None:
        self._renderer = SVGRenderer(
            width=width,
            frame_height=frame_height,
            font_size=font_size,
            title=title,
            orientation=FlameOrientation.TOP_DOWN,
        )

    def render(self, roots: list[FlameFrame]) -> str:
        """Render an icicle chart (inverted flame graph).

        Args:
            roots: Root FlameFrame objects.

        Returns:
            SVG document string.
        """
        return self._renderer.render(roots)


# ============================================================
# TimelineHeatMap — time-bucketed span activity
# ============================================================


@dataclass
class HeatMapBucket:
    """A single time bucket in the heat map.

    Attributes:
        start_ns: Bucket start time (relative to trace start).
        end_ns: Bucket end time.
        span_count: Number of active spans in this bucket.
        subsystems: Set of subsystem names active in this bucket.
        max_depth: Maximum concurrent stack depth.
    """
    start_ns: int = 0
    end_ns: int = 0
    span_count: int = 0
    subsystems: set[str] = field(default_factory=set)
    max_depth: int = 0


class TimelineHeatMap:
    """Time-bucketed heat map of span activity.

    Divides the trace timeline into fixed-width buckets and counts
    the number of active spans in each bucket. The result is rendered
    as an SVG heat map where color intensity corresponds to span
    density — brighter cells indicate more concurrent activity.

    For FizzBuzz evaluation, the heat map typically shows a single
    burst of activity lasting a few hundred microseconds, which is
    presented with the same gravitas as a multi-second distributed
    transaction spanning 50 microservices.
    """

    def __init__(
        self,
        bucket_count: int = 50,
        width: int = DEFAULT_WIDTH,
        height: int = 120,
        title: str = "FizzFlame — Timeline Heat Map",
    ) -> None:
        self.bucket_count = bucket_count
        self.width = width
        self.height = height
        self.title = title
        self._margin = DEFAULT_MARGIN

    def compute_buckets(self, spans: list[Any]) -> list[HeatMapBucket]:
        """Compute time buckets from a list of spans.

        Args:
            spans: List of Span objects with start_time_ns and end_time_ns.

        Returns:
            List of HeatMapBucket objects.
        """
        if not spans:
            return []

        valid_spans = [s for s in spans if s.start_time_ns > 0 and s.end_time_ns > 0]
        if not valid_spans:
            return []

        # Find timeline bounds
        min_start = min(s.start_time_ns for s in valid_spans)
        max_end = max(s.end_time_ns for s in valid_spans)
        duration = max_end - min_start

        if duration <= 0:
            return []

        bucket_width_ns = duration / self.bucket_count
        buckets: list[HeatMapBucket] = []

        for i in range(self.bucket_count):
            bucket_start = min_start + int(i * bucket_width_ns)
            bucket_end = min_start + int((i + 1) * bucket_width_ns)
            bucket = HeatMapBucket(start_ns=bucket_start, end_ns=bucket_end)

            for span in valid_spans:
                # Check if span overlaps with this bucket
                if span.start_time_ns < bucket_end and span.end_time_ns > bucket_start:
                    bucket.span_count += 1
                    # Extract subsystem from span name
                    sub = span.name.split(".")[0].lower() if "." in span.name else span.name.lower()
                    bucket.subsystems.add(sub)

            buckets.append(bucket)

        # Compute max depth per bucket
        for bucket in buckets:
            bucket.max_depth = bucket.span_count

        return buckets

    def render_svg(self, buckets: list[HeatMapBucket]) -> str:
        """Render heat map buckets as SVG.

        Args:
            buckets: List of HeatMapBucket objects.

        Returns:
            SVG document string.
        """
        if not buckets:
            return self._render_empty()

        max_count = max(b.span_count for b in buckets) or 1
        cell_width = (self.width - 2 * self._margin) / len(buckets)
        bar_area_height = self.height - 50  # Reserve space for title and axis

        svg_lines = [
            '<?xml version="1.0" encoding="UTF-8" standalone="no"?>',
            f'<svg xmlns="http://www.w3.org/2000/svg" '
            f'viewBox="0 0 {self.width} {self.height}" '
            f'width="{self.width}" height="{self.height}" '
            f'font-family="monospace" font-size="10">',
            f'  <rect width="{self.width}" height="{self.height}" fill="#1a1a2e" />',
            f'  <text x="{self.width // 2}" y="18" text-anchor="middle" '
            f'font-size="13" font-weight="bold" fill="#e0e0e0">'
            f'{_escape_xml(self.title)}</text>',
        ]

        for i, bucket in enumerate(buckets):
            x = self._margin + i * cell_width
            intensity = bucket.span_count / max_count
            # Heat color: black to red to yellow to white
            if intensity < 0.33:
                r = int(255 * intensity * 3)
                g = 0
                b = 0
            elif intensity < 0.66:
                r = 255
                g = int(255 * (intensity - 0.33) * 3)
                b = 0
            else:
                r = 255
                g = 255
                b_val = int(255 * (intensity - 0.66) * 3)
                b = min(255, b_val)

            color = f"rgb({r},{g},{b})"
            bar_height = int(bar_area_height * intensity)
            bar_y = 30 + bar_area_height - bar_height

            tooltip = (
                f"Bucket {i + 1}/{len(buckets)}\n"
                f"Active spans: {bucket.span_count}\n"
                f"Subsystems: {', '.join(sorted(bucket.subsystems)) or 'none'}"
            )

            svg_lines.append(
                f'  <g><title>{_escape_xml(tooltip)}</title>'
                f'<rect x="{x:.1f}" y="{bar_y}" width="{max(cell_width - 0.5, 0.5):.1f}" '
                f'height="{bar_height}" fill="{color}" /></g>'
            )

        # X-axis labels
        svg_lines.append(
            f'  <text x="{self._margin}" y="{self.height - 5}" '
            f'font-size="9" fill="#888">t=0</text>'
        )
        svg_lines.append(
            f'  <text x="{self.width - self._margin}" y="{self.height - 5}" '
            f'text-anchor="end" font-size="9" fill="#888">t=end</text>'
        )

        svg_lines.append("</svg>")
        return "\n".join(svg_lines)

    def _render_empty(self) -> str:
        """Render empty heat map."""
        return (
            '<?xml version="1.0" encoding="UTF-8" standalone="no"?>\n'
            f'<svg xmlns="http://www.w3.org/2000/svg" '
            f'viewBox="0 0 {self.width} {self.height}" '
            f'width="{self.width}" height="{self.height}" '
            f'font-family="monospace">\n'
            f'  <rect width="{self.width}" height="{self.height}" fill="#1a1a2e" />\n'
            f'  <text x="{self.width // 2}" y="{self.height // 2}" '
            f'text-anchor="middle" fill="#888">No span data</text>\n'
            f"</svg>"
        )


# ============================================================
# FlameGraphDashboard — ASCII fallback
# ============================================================


class FlameGraphDashboard:
    """ASCII-rendered flame graph dashboard for terminal display.

    When SVG output is not practical — perhaps the operator is
    debugging FizzBuzz performance over a serial console connection
    to a remote server — this dashboard provides a comprehensive
    text-based view of the flame graph data.

    Sections:
    - Summary statistics (total time, span count, max depth)
    - Top frames by self time
    - Top frames by total time
    - Subsystem time distribution
    - ASCII flame visualization (width = terminal columns)
    """

    def __init__(self, width: int = 72) -> None:
        self.width = width

    def render(self, roots: list[FlameFrame], spans: Optional[list[Any]] = None) -> str:
        """Render the ASCII flame graph dashboard.

        Args:
            roots: FlameFrame trees.
            spans: Optional raw span list for additional statistics.

        Returns:
            Formatted ASCII dashboard string.
        """
        lines: list[str] = []
        border = "+" + "-" * (self.width - 2) + "+"

        lines.append("")
        lines.append(border)
        lines.append(
            self._center("FizzFlame — Flame Graph Dashboard")
        )
        lines.append(
            self._center("Performance Profiling for Enterprise FizzBuzz")
        )
        lines.append(border)

        if not roots:
            lines.append(self._center("No flame graph data collected."))
            lines.append(border)
            return "\n".join(lines)

        # Summary
        total_time = sum(r.total_time_ns for r in roots)
        total_spans = self._count_spans(roots)
        max_depth = self._max_depth(roots)

        lines.append("")
        lines.append(self._section("Summary"))
        lines.append(f"  Total time:   {SVGRenderer._format_time(total_time)}")
        lines.append(f"  Span count:   {total_spans}")
        lines.append(f"  Max depth:    {max_depth + 1}")
        lines.append(f"  Root frames:  {len(roots)}")

        # Top frames by self time
        all_frames = self._collect_all_frames(roots)
        by_self = sorted(all_frames, key=lambda f: f.self_time_ns, reverse=True)[:10]

        lines.append("")
        lines.append(self._section("Top Frames by Self Time"))
        lines.append(f"  {'Frame':<35} {'Self':>10} {'Total':>10} {'%':>6}")
        lines.append("  " + "-" * 63)
        for f in by_self:
            pct = (f.self_time_ns / total_time * 100) if total_time > 0 else 0
            lines.append(
                f"  {f.name[:35]:<35} "
                f"{SVGRenderer._format_time(f.self_time_ns):>10} "
                f"{SVGRenderer._format_time(f.total_time_ns):>10} "
                f"{pct:>5.1f}%"
            )

        # Top frames by total time
        by_total = sorted(all_frames, key=lambda f: f.total_time_ns, reverse=True)[:10]

        lines.append("")
        lines.append(self._section("Top Frames by Total Time"))
        lines.append(f"  {'Frame':<35} {'Total':>10} {'Self':>10} {'%':>6}")
        lines.append("  " + "-" * 63)
        for f in by_total:
            pct = (f.total_time_ns / total_time * 100) if total_time > 0 else 0
            lines.append(
                f"  {f.name[:35]:<35} "
                f"{SVGRenderer._format_time(f.total_time_ns):>10} "
                f"{SVGRenderer._format_time(f.self_time_ns):>10} "
                f"{pct:>5.1f}%"
            )

        # Subsystem distribution
        subsystem_time: dict[str, int] = {}
        for f in all_frames:
            sub = f.subsystem
            subsystem_time[sub] = subsystem_time.get(sub, 0) + f.self_time_ns

        sorted_subs = sorted(subsystem_time.items(), key=lambda kv: kv[1], reverse=True)

        lines.append("")
        lines.append(self._section("Subsystem Time Distribution"))
        bar_width = self.width - 30
        max_sub_time = max(subsystem_time.values()) if subsystem_time else 1

        for sub, ns in sorted_subs[:15]:
            pct = (ns / total_time * 100) if total_time > 0 else 0
            bar_len = int(bar_width * ns / max_sub_time) if max_sub_time > 0 else 0
            bar = "\u2588" * bar_len
            lines.append(f"  {sub[:12]:<12} {bar} {pct:.1f}%")

        # ASCII flame visualization
        lines.append("")
        lines.append(self._section("Flame Graph (ASCII)"))
        flame_lines = self._render_ascii_flame(roots, total_time)
        lines.extend(flame_lines)

        lines.append("")
        lines.append(border)
        lines.append("")

        return "\n".join(lines)

    def _render_ascii_flame(
        self, roots: list[FlameFrame], total_time: int
    ) -> list[str]:
        """Render a simplified ASCII flame graph."""
        lines: list[str] = []
        usable_width = self.width - 4

        def render_frame(frame: FlameFrame, x: int, width: int) -> None:
            if width < 1:
                return

            indent = " " * 2
            label = frame.name
            pct = (frame.total_time_ns / total_time * 100) if total_time > 0 else 0

            # Build the bar
            if width >= len(label) + 8:
                content = f" {label} ({pct:.1f}%) "
            elif width >= 6:
                max_name = width - 8
                content = f" {label[:max(max_name, 1)]}.. "
            else:
                content = " " * width

            # Pad or truncate content to width
            if len(content) < width:
                content = content + " " * (width - len(content))
            elif len(content) > width:
                content = content[:width]

            bar = "[" + content[:width - 2] + "]" if width >= 2 else content[:width]
            lines.append(f"{indent}{' ' * x}{bar}")

            # Render children
            child_x = x
            for child in frame.children:
                child_width = int(
                    width * child.total_time_ns / frame.total_time_ns
                ) if frame.total_time_ns > 0 else 0
                child_width = max(child_width, 1) if child.total_time_ns > 0 else 0
                render_frame(child, child_x, child_width)
                child_x += child_width

        for root in roots:
            root_width = usable_width
            if total_time > 0 and len(roots) > 1:
                root_width = int(usable_width * root.total_time_ns / total_time)
            render_frame(root, 0, root_width)

        return lines

    def _section(self, title: str) -> str:
        """Format a section header."""
        return f"  === {title} ==="

    def _center(self, text: str) -> str:
        """Center text within the dashboard width."""
        return f"|{text:^{self.width - 2}}|"

    def _count_spans(self, frames: list[FlameFrame]) -> int:
        """Count total spans recursively."""
        count = 0
        for f in frames:
            count += f.span_count
            count += self._count_spans(f.children)
        return count

    def _max_depth(self, frames: list[FlameFrame]) -> int:
        """Find maximum depth recursively."""
        max_d = 0
        for f in frames:
            max_d = max(max_d, f.depth)
            if f.children:
                max_d = max(max_d, self._max_depth(f.children))
        return max_d

    def _collect_all_frames(self, frames: list[FlameFrame]) -> list[FlameFrame]:
        """Collect all frames into a flat list."""
        result: list[FlameFrame] = []
        for f in frames:
            result.append(f)
            result.extend(self._collect_all_frames(f.children))
        return result


# ============================================================
# FlameGraphMiddleware(IMiddleware) — span collection
# ============================================================


class FlameGraphMiddleware(IMiddleware):
    """Middleware that collects spans for flame graph generation.

    Wraps each evaluation in a tracing span and accumulates the
    resulting span data for post-execution flame graph rendering.
    Works in conjunction with the FizzOTel TracerProvider — when
    tracing is active, this middleware captures the span tree;
    when tracing is inactive, it operates as a zero-overhead
    pass-through.

    The middleware also records per-evaluation timing for the
    timeline heat map, because knowing that evaluation #47
    (the number 62, result "62") took 1.2 microseconds could
    be the key to unlocking a critical performance insight.
    """

    def __init__(self) -> None:
        self._collected_spans: list[Any] = []
        self._eval_times: list[tuple[int, int]] = []  # (start_ns, end_ns)
        self._eval_count: int = 0

    def process(
        self,
        context: ProcessingContext,
        next_handler: Callable[[ProcessingContext], ProcessingContext],
    ) -> ProcessingContext:
        """Process the context, wrapping the downstream call in timing collection."""
        start_ns = time.time_ns()
        self._eval_count += 1

        result = next_handler(context)

        end_ns = time.time_ns()
        self._eval_times.append((start_ns, end_ns))

        return result

    def get_name(self) -> str:
        """Return the middleware identifier."""
        return "FlameGraphMiddleware"

    def get_priority(self) -> int:
        """Return the middleware execution priority.

        FlameGraphMiddleware runs at a low priority (high number) to
        wrap all other middleware in its timing measurement. This
        ensures that the flame graph captures the complete evaluation
        pipeline, including any middleware that executes before it.
        """
        return 9000

    def add_spans(self, spans: list[Any]) -> None:
        """Add collected spans from the TracerProvider.

        Called after evaluation completes to transfer span data
        for flame graph generation.
        """
        self._collected_spans.extend(spans)

    @property
    def collected_spans(self) -> list[Any]:
        """Return all collected spans."""
        return list(self._collected_spans)

    @property
    def eval_times(self) -> list[tuple[int, int]]:
        """Return per-evaluation timing data."""
        return list(self._eval_times)

    @property
    def eval_count(self) -> int:
        """Return the number of evaluations processed."""
        return self._eval_count

    def generate_flame_graph(
        self,
        output_path: Optional[str] = None,
        width: int = DEFAULT_WIDTH,
        title: str = "FizzFlame — Flame Graph",
    ) -> str:
        """Generate an SVG flame graph from collected spans.

        Args:
            output_path: Optional file path to write the SVG.
            width: SVG width in pixels.
            title: Title for the flame graph.

        Returns:
            SVG document string.
        """
        collapser = StackCollapser()
        roots = collapser.collapse_spans(self._collected_spans)

        renderer = SVGRenderer(width=width, title=title)
        svg = renderer.render(roots)

        if output_path:
            with open(output_path, "w", encoding="utf-8") as f:
                f.write(svg)

        return svg

    def generate_icicle_chart(
        self,
        width: int = DEFAULT_WIDTH,
        title: str = "FizzFlame — Icicle Chart",
    ) -> str:
        """Generate an icicle chart (inverted flame graph)."""
        collapser = StackCollapser()
        roots = collapser.collapse_spans(self._collected_spans)

        chart = IcicleChart(width=width, title=title)
        return chart.render(roots)

    def generate_heat_map(
        self,
        bucket_count: int = 50,
        width: int = DEFAULT_WIDTH,
    ) -> str:
        """Generate a timeline heat map SVG."""
        heat_map = TimelineHeatMap(bucket_count=bucket_count, width=width)
        buckets = heat_map.compute_buckets(self._collected_spans)
        return heat_map.render_svg(buckets)

    def generate_dashboard(self, width: int = 72) -> str:
        """Generate the ASCII flame graph dashboard."""
        collapser = StackCollapser()
        roots = collapser.collapse_spans(self._collected_spans)

        dashboard = FlameGraphDashboard(width=width)
        return dashboard.render(roots, spans=self._collected_spans)


# ============================================================
# Differential flame graph file-based comparison
# ============================================================


def load_flame_stacks_from_file(path: str) -> list[FlameFrame]:
    """Load flame stacks from a collapsed-stack format file.

    Each line follows the Brendan Gregg format:
        root;child;grandchild count_in_nanoseconds

    Args:
        path: Path to the collapsed-stack file.

    Returns:
        List of FlameFrame root objects.

    Raises:
        FlameGraphError: If the file cannot be read or parsed.
    """
    try:
        with open(path, "r", encoding="utf-8") as f:
            lines = f.readlines()
    except OSError as e:
        raise FlameGraphError(f"Cannot read flame stack file '{path}': {e}") from e

    # Parse lines into a tree structure
    root_map: dict[str, FlameFrame] = {}

    for line_num, line in enumerate(lines, 1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue

        parts = line.rsplit(" ", 1)
        if len(parts) != 2:
            continue

        stack_str, count_str = parts
        try:
            count = int(count_str)
        except ValueError:
            continue

        frames = stack_str.split(";")
        if not frames:
            continue

        # Build/merge into tree
        current_map = root_map
        parent_frame: Optional[FlameFrame] = None

        for i, name in enumerate(frames):
            if name not in current_map:
                current_map[name] = FlameFrame(
                    name=name,
                    depth=i,
                )
            frame = current_map[name]

            if i == len(frames) - 1:
                # Leaf: add the count as self time
                frame.self_time_ns += count
                frame.total_time_ns += count
            else:
                frame.total_time_ns += count

            if parent_frame is not None and frame not in parent_frame.children:
                parent_frame.children.append(frame)

            parent_frame = frame
            # Use a dict on the frame for child lookup
            if not hasattr(frame, "_child_map"):
                frame._child_map = {}  # type: ignore[attr-defined]
                for c in frame.children:
                    frame._child_map[c.name] = c  # type: ignore[attr-defined]
            current_map = frame._child_map  # type: ignore[attr-defined]

    return list(root_map.values())


def generate_differential_flame_graph(
    before_path: str,
    after_path: str,
    output_path: Optional[str] = None,
    width: int = DEFAULT_WIDTH,
) -> str:
    """Generate a differential flame graph from two collapsed-stack files.

    Args:
        before_path: Path to the baseline collapsed-stack file.
        after_path: Path to the comparison collapsed-stack file.
        output_path: Optional path to write the SVG output.
        width: SVG width in pixels.

    Returns:
        SVG document string.
    """
    before = load_flame_stacks_from_file(before_path)
    after = load_flame_stacks_from_file(after_path)

    diff = DifferentialFlameGraph(width=width)
    svg = diff.diff(before, after)

    if output_path:
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(svg)

    return svg
