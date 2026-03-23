"""
Enterprise FizzBuzz Platform - FizzPrint TeX-Inspired Typesetting Engine

Produces publication-quality FizzBuzz reports using Knuth's box-glue-penalty
model and the Knuth-Plass optimal line breaking algorithm. The engine
computes globally optimal paragraph breaks by minimizing total demerits
across all feasible breakpoint sequences, ensuring that every "Fizz",
"Buzz", and "FizzBuzz" is rendered with the same typographic precision
that Knuth demanded for The Art of Computer Programming.

Typographic fidelity is non-negotiable in enterprise FizzBuzz reporting.
Stakeholders reviewing divisibility analysis must not be distracted by
suboptimal line breaks, poor kerning, or inconsistent glyph spacing.
"""

from __future__ import annotations

import logging
import math
import time
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Callable, Optional

from enterprise_fizzbuzz.domain.interfaces import IMiddleware
from enterprise_fizzbuzz.domain.models import FizzBuzzResult, ProcessingContext

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

INFINITY = 10_000
INFINITY_BADNESS = 10_000


# ---------------------------------------------------------------------------
# Glyph and Font Metrics
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class GlyphMetrics:
    """Precise typographic measurements for a single character glyph.

    All dimensions are expressed in PostScript points (1/72 inch), the
    standard unit of typographic measurement since the dawn of digital
    publishing. Each glyph carries width, height, depth, and italic
    correction data sufficient to produce mathematically precise layouts.
    """

    character: str
    width: float
    height: float
    depth: float
    italic_correction: float = 0.0


class FontMetrics:
    """Complete metric table for a monospaced or proportional font.

    Maintains per-character glyph metrics, kerning pair adjustments,
    and ligature substitution rules. The kerning table encodes signed
    adjustments for specific character pairs (e.g., AV, To) that
    improve visual spacing. The ligature table maps character sequences
    to their typographic ligature replacements (fi, fl, ff).
    """

    def __init__(
        self,
        name: str = "Courier",
        size: float = 10.0,
        char_width: float = 6.0,
        ascent: float = 8.0,
        descent: float = 2.0,
    ) -> None:
        self.name = name
        self.size = size
        self._default_width = char_width
        self._ascent = ascent
        self._descent = descent
        self._metrics: dict[str, GlyphMetrics] = {}
        self._kerning_pairs: dict[tuple[str, str], float] = {}
        self._ligature_table: dict[str, str] = {}

        self._build_default_metrics()
        self._build_kerning_table()
        self._build_ligature_table()

    def _build_default_metrics(self) -> None:
        """Populate glyph metrics for the printable ASCII range."""
        for code in range(32, 127):
            ch = chr(code)
            width = self._default_width
            # Proportional width adjustments for common characters
            if ch in ("i", "l", "1", "!", "|", "'", ":"):
                width = self._default_width * 0.6
            elif ch in ("m", "w", "M", "W"):
                width = self._default_width * 1.3
            elif ch in ("f", "t", "r"):
                width = self._default_width * 0.75
            self._metrics[ch] = GlyphMetrics(
                character=ch,
                width=width,
                height=self._ascent,
                depth=self._descent,
            )

    def _build_kerning_table(self) -> None:
        """Register kerning pair adjustments for improved letter spacing.

        These pairs are derived from standard typographic practice. The
        adjustment values reduce or increase inter-character spacing to
        eliminate visually distracting gaps between certain letter
        combinations.
        """
        kern = self._default_width * 0.15
        self._kerning_pairs = {
            ("A", "V"): -kern,
            ("A", "W"): -kern,
            ("A", "T"): -kern * 0.8,
            ("A", "Y"): -kern,
            ("F", "."): -kern * 0.6,
            ("F", ","): -kern * 0.6,
            ("L", "T"): -kern * 0.7,
            ("L", "V"): -kern * 0.5,
            ("L", "Y"): -kern * 0.5,
            ("P", "."): -kern * 0.8,
            ("P", ","): -kern * 0.8,
            ("T", "a"): -kern * 0.6,
            ("T", "e"): -kern * 0.6,
            ("T", "o"): -kern * 0.6,
            ("V", "a"): -kern * 0.5,
            ("V", "e"): -kern * 0.5,
            ("V", "o"): -kern * 0.5,
            ("W", "a"): -kern * 0.4,
            ("W", "e"): -kern * 0.4,
            ("Y", "a"): -kern * 0.6,
            ("Y", "e"): -kern * 0.6,
            ("Y", "o"): -kern * 0.6,
            ("r", "."): -kern * 0.4,
            ("r", ","): -kern * 0.4,
        }

    def _build_ligature_table(self) -> None:
        """Register standard typographic ligatures.

        Ligatures fi, fl, and ff have been used in Western typography
        since the era of movable type to prevent the ascender of f from
        colliding with the dot of i or the ascender of l.
        """
        self._ligature_table = {
            "fi": "\ufb01",   # ﬁ
            "fl": "\ufb02",   # ﬂ
            "ff": "\ufb00",   # ﬀ
        }

    def glyph(self, ch: str) -> GlyphMetrics:
        """Retrieve metrics for a single character."""
        if ch in self._metrics:
            return self._metrics[ch]
        return GlyphMetrics(
            character=ch,
            width=self._default_width,
            height=self._ascent,
            depth=self._descent,
        )

    def kerning(self, left: str, right: str) -> float:
        """Return the kerning adjustment between two adjacent characters."""
        return self._kerning_pairs.get((left, right), 0.0)

    def ligature(self, seq: str) -> Optional[str]:
        """Check if a character sequence forms a known ligature."""
        return self._ligature_table.get(seq)

    def string_width(self, text: str) -> float:
        """Compute the total width of a string including kerning."""
        if not text:
            return 0.0
        total = self.glyph(text[0]).width
        for i in range(1, len(text)):
            total += self.kerning(text[i - 1], text[i])
            total += self.glyph(text[i]).width
        return total


# ---------------------------------------------------------------------------
# Box-Glue-Penalty Model
# ---------------------------------------------------------------------------

class NodeType(Enum):
    """Classification of nodes in the Knuth box-glue-penalty model."""
    BOX = auto()
    GLUE = auto()
    PENALTY = auto()


@dataclass
class Box:
    """A fixed-width element representing a typeset character or word.

    In Knuth's model, a box is an indivisible unit of content with a
    fixed natural width. Line breaks cannot occur inside a box.
    """

    width: float
    content: str = ""

    @property
    def node_type(self) -> NodeType:
        return NodeType.BOX


@dataclass
class Glue:
    """A stretchable/shrinkable space between boxes.

    Glue has a natural width, a stretch component (how much it can
    grow), and a shrink component (how much it can contract). The
    typesetting engine adjusts glue widths to achieve justified
    lines with minimal visual distortion.
    """

    width: float
    stretch: float
    shrink: float

    @property
    def node_type(self) -> NodeType:
        return NodeType.GLUE


@dataclass
class Penalty:
    """A potential breakpoint with an associated cost.

    Penalty nodes indicate places where the line may be broken. A
    penalty of -INFINITY forces a break, a penalty of +INFINITY
    forbids it, and intermediate values influence the optimizer's
    choice. A flagged penalty indicates a hyphenation point.
    """

    penalty: float
    width: float = 0.0
    flagged: bool = False

    @property
    def node_type(self) -> NodeType:
        return NodeType.PENALTY


# Type alias for nodes in the paragraph stream
Node = Box | Glue | Penalty


# ---------------------------------------------------------------------------
# Hyphenation Engine
# ---------------------------------------------------------------------------

class HyphenationEngine:
    """Pattern-based hyphenation engine inspired by Liang's algorithm.

    Franklin Liang's 1983 dissertation introduced the pattern-based
    approach used in TeX, which achieves 89% accuracy for English
    hyphenation. This implementation uses a simplified vowel-consonant
    boundary heuristic that covers the majority of English words
    encountered in FizzBuzz output — which, to be fair, is a limited
    vocabulary consisting primarily of "Fizz", "Buzz", and "FizzBuzz".
    """

    VOWELS = set("aeiouAEIOU")
    MIN_PREFIX = 2  # Minimum characters before first hyphen
    MIN_SUFFIX = 3  # Minimum characters after last hyphen
    MIN_WORD_LENGTH = 5  # Words shorter than this are never hyphenated

    def hyphenate(self, word: str) -> list[str]:
        """Split a word into syllables at valid hyphenation points.

        Returns a list of syllable fragments. For example:
            "FizzBuzz" -> ["Fizz", "Buzz"]
            "evaluation" -> ["eval", "ua", "tion"]
        """
        if len(word) < self.MIN_WORD_LENGTH:
            return [word]

        points = self._find_hyphenation_points(word)
        if not points:
            return [word]

        syllables = []
        prev = 0
        for pt in points:
            syllables.append(word[prev:pt])
            prev = pt
        syllables.append(word[prev:])
        return syllables

    def _find_hyphenation_points(self, word: str) -> list[int]:
        """Identify valid hyphenation points using vowel-consonant transitions.

        A hyphenation point is placed at a vowel-to-consonant boundary
        (VC pattern) when the resulting fragments satisfy minimum length
        constraints. This simplified rule covers the dominant syllabification
        pattern in English.
        """
        points = []
        lower = word.lower()
        for i in range(self.MIN_PREFIX, len(word) - self.MIN_SUFFIX + 1):
            if lower[i - 1] in self.VOWELS and lower[i] not in self.VOWELS:
                # Verify consonant is followed by a vowel (VCV pattern)
                if i + 1 < len(lower) and lower[i + 1] in self.VOWELS:
                    points.append(i)
        return points


# ---------------------------------------------------------------------------
# Knuth-Plass Line Breaking Algorithm
# ---------------------------------------------------------------------------

@dataclass
class _Breakpoint:
    """Internal bookkeeping for a feasible breakpoint in the paragraph.

    Tracks the index in the node list, the line number, total width/stretch/shrink
    up to this point, accumulated demerits, and a pointer to the previous
    best breakpoint for reconstructing the optimal solution.
    """

    index: int
    line: int
    total_width: float
    total_stretch: float
    total_shrink: float
    demerits: float
    previous: Optional[_Breakpoint] = None
    fitness_class: int = 1


class KnuthPlassBreaker:
    """Optimal line breaking using Knuth and Plass's dynamic programming algorithm.

    Minimizes total demerits across all lines in a paragraph, where
    demerits = sum of (badness + penalty)^3 over all chosen breakpoints.
    Badness measures how far each line's glue must stretch or shrink
    from its natural width to fill the target line width.

    This is the same algorithm used in TeX, applied here with equal
    seriousness to the challenge of formatting FizzBuzz output.
    """

    def __init__(
        self,
        line_width: float = 400.0,
        tolerance: float = 5.0,
        hyphen_penalty: float = 50.0,
        consecutive_flag_demerits: float = 3000.0,
    ) -> None:
        self.line_width = line_width
        self.tolerance = tolerance
        self.hyphen_penalty = hyphen_penalty
        self.consecutive_flag_demerits = consecutive_flag_demerits

    def break_lines(self, nodes: list[Node]) -> list[list[Node]]:
        """Compute optimal line breaks for a list of box/glue/penalty nodes.

        Returns a list of lines, where each line is a sublist of nodes.
        """
        if not nodes:
            return []

        # Compute prefix sums for width, stretch, and shrink
        n = len(nodes)
        sum_width = [0.0] * (n + 1)
        sum_stretch = [0.0] * (n + 1)
        sum_shrink = [0.0] * (n + 1)

        for i, node in enumerate(nodes):
            sum_width[i + 1] = sum_width[i]
            sum_stretch[i + 1] = sum_stretch[i]
            sum_shrink[i + 1] = sum_shrink[i]

            if isinstance(node, Box):
                sum_width[i + 1] += node.width
            elif isinstance(node, Glue):
                sum_width[i + 1] += node.width
                sum_stretch[i + 1] += node.stretch
                sum_shrink[i + 1] += node.shrink

        # Initialize active breakpoint list with the start of paragraph
        active: list[_Breakpoint] = [
            _Breakpoint(
                index=0,
                line=0,
                total_width=0.0,
                total_stretch=0.0,
                total_shrink=0.0,
                demerits=0.0,
            )
        ]

        # Best breakpoint found at the end of the paragraph
        best_at: dict[int, _Breakpoint] = {}

        for i, node in enumerate(nodes):
            if not self._is_legal_breakpoint(node, nodes, i):
                continue

            # Compute the width of content after breaking at i
            # (glue immediately after a break is discarded)
            after_w = sum_width[i + 1] if i + 1 <= n else sum_width[i]
            after_str = sum_stretch[i + 1] if i + 1 <= n else sum_stretch[i]
            after_shr = sum_shrink[i + 1] if i + 1 <= n else sum_shrink[i]
            # Skip glue nodes after the break for prefix sum alignment
            j = i + 1
            while j < n and isinstance(nodes[j], Glue):
                j += 1
            if j <= n:
                after_w = sum_width[j]
                after_str = sum_stretch[j]
                after_shr = sum_shrink[j]

            # Penalty width contributes to the line that ends here
            penalty_width = node.width if isinstance(node, Penalty) else 0.0

            new_active: list[_Breakpoint] = []
            is_forced = isinstance(node, Penalty) and node.penalty <= -INFINITY
            deactivated: list[tuple[_Breakpoint, float]] = []

            for bp in active:
                # Compute the width of the line from bp to i
                line_w = sum_width[i] - bp.total_width + penalty_width
                line_str = sum_stretch[i] - bp.total_stretch
                line_shr = sum_shrink[i] - bp.total_shrink

                adjustment_ratio = self._compute_adjustment_ratio(
                    line_w, line_str, line_shr
                )

                # Deactivate breakpoints that can never produce a feasible line
                if adjustment_ratio < -1.0 and not is_forced:
                    # This breakpoint is too far back; lines are overfull
                    # Track it for emergency break if needed
                    deactivated.append((bp, adjustment_ratio))
                    continue

                # Accept the break if it's within tolerance or forced
                if is_forced or (adjustment_ratio >= -1.0 and adjustment_ratio <= self.tolerance):
                    # Feasible break
                    badness = self._compute_badness(adjustment_ratio)
                    penalty_value = node.penalty if isinstance(node, Penalty) else 0.0
                    demerits = self._compute_demerits(
                        badness, penalty_value, node, bp
                    )
                    fitness = self._fitness_class(adjustment_ratio)

                    candidate = _Breakpoint(
                        index=i,
                        line=bp.line + 1,
                        total_width=after_w,
                        total_stretch=after_str,
                        total_shrink=after_shr,
                        demerits=bp.demerits + demerits,
                        previous=bp,
                        fitness_class=fitness,
                    )

                    if i not in best_at or candidate.demerits < best_at[i].demerits:
                        best_at[i] = candidate

                # Keep bp active if lines from it can still be underfull
                if not is_forced:
                    new_active.append(bp)

            # Emergency break: if breakpoints were deactivated without ever
            # producing a feasible break at this position, force a break
            # using the least-bad deactivated breakpoint. This mirrors TeX's
            # emergency pass behavior for overfull lines.
            if deactivated and i not in best_at:
                # Pick the deactivated bp with ratio closest to -1 (least overfull)
                best_emergency_bp, best_ratio = min(
                    deactivated, key=lambda x: abs(x[1])
                )
                badness = INFINITY_BADNESS
                penalty_value = node.penalty if isinstance(node, Penalty) else 0.0
                demerits = (1.0 + badness) ** 3
                candidate = _Breakpoint(
                    index=i,
                    line=best_emergency_bp.line + 1,
                    total_width=after_w,
                    total_stretch=after_str,
                    total_shrink=after_shr,
                    demerits=best_emergency_bp.demerits + demerits,
                    previous=best_emergency_bp,
                    fitness_class=0,
                )
                best_at[i] = candidate

            # Add the best candidate at position i as a new active node
            if i in best_at:
                new_active.append(best_at[i])

            active = new_active if new_active else active

        # Find the best terminal breakpoint (the one at the end of the paragraph)
        # Prefer breakpoints at the last node
        best_overall: Optional[_Breakpoint] = None
        for bp in active:
            if best_overall is None or bp.demerits < best_overall.demerits:
                best_overall = bp

        if best_overall is None or best_overall.index == 0:
            # Fallback: return all nodes as a single line
            return [nodes]

        # Reconstruct break positions
        breaks: list[int] = []
        bp = best_overall
        while bp is not None and bp.index > 0:
            breaks.append(bp.index)
            bp = bp.previous
        breaks.reverse()

        # Split nodes into lines
        lines: list[list[Node]] = []
        prev = 0
        for b in breaks:
            line_nodes = nodes[prev:b]
            # Strip trailing glue and penalty
            while line_nodes and isinstance(line_nodes[-1], (Glue, Penalty)):
                line_nodes = line_nodes[:-1]
            if line_nodes:
                lines.append(line_nodes)
            # Skip the break node and any following glue
            prev = b + 1
            while prev < n and isinstance(nodes[prev], Glue):
                prev += 1

        # Remaining nodes form the last line
        if prev < n:
            last_line = nodes[prev:]
            while last_line and isinstance(last_line[-1], (Glue, Penalty)):
                last_line = last_line[:-1]
            if last_line:
                lines.append(last_line)

        return lines if lines else [nodes]

    def _is_legal_breakpoint(self, node: Node, nodes: list[Node], index: int) -> bool:
        """Determine if a break is legal at this node."""
        if isinstance(node, Penalty):
            return node.penalty < INFINITY
        if isinstance(node, Glue):
            # Can break at glue only if preceded by a box
            return index > 0 and isinstance(nodes[index - 1], Box)
        return False

    def _compute_adjustment_ratio(
        self, line_width: float, stretch: float, shrink: float
    ) -> float:
        """Compute how much glue must stretch or shrink to fill the line."""
        diff = self.line_width - line_width
        if abs(diff) < 0.001:
            return 0.0
        if diff > 0:
            return diff / stretch if stretch > 0 else INFINITY
        return diff / shrink if shrink > 0 else -INFINITY

    @staticmethod
    def _compute_badness(adjustment_ratio: float) -> float:
        """Compute badness = 100 * |adjustment_ratio|^3, capped at 10000."""
        raw = 100.0 * abs(adjustment_ratio) ** 3
        return min(raw, INFINITY_BADNESS)

    def _compute_demerits(
        self, badness: float, penalty: float, node: Node, prev_bp: _Breakpoint
    ) -> float:
        """Compute demerits for a potential breakpoint.

        Demerits = (1 + badness + penalty)^3 for positive penalties,
        or (1 + badness)^3 - penalty^3 for negative penalties.
        Additional demerits apply for consecutive flagged breaks
        (i.e., consecutive hyphenations).
        """
        if isinstance(node, Penalty) and penalty >= 0:
            d = (1.0 + badness + penalty) ** 3
        elif isinstance(node, Penalty) and penalty > -INFINITY:
            d = (1.0 + badness) ** 3 - penalty ** 3
        else:
            d = (1.0 + badness) ** 3

        # Penalize consecutive hyphenations
        if isinstance(node, Penalty) and node.flagged and prev_bp.fitness_class > 0:
            d += self.consecutive_flag_demerits

        return d

    @staticmethod
    def _fitness_class(adjustment_ratio: float) -> int:
        """Classify line tightness: 0=tight, 1=normal, 2=loose, 3=very loose."""
        if adjustment_ratio < -0.5:
            return 0
        if adjustment_ratio <= 0.5:
            return 1
        if adjustment_ratio <= 1.0:
            return 2
        return 3


# ---------------------------------------------------------------------------
# Paragraph
# ---------------------------------------------------------------------------

class Paragraph:
    """A typesettable paragraph built from text, using the box-glue-penalty model.

    Converts a text string into a sequence of Box, Glue, and Penalty nodes
    suitable for processing by the KnuthPlassBreaker. Handles ligature
    detection, kerning application, and hyphenation insertion.
    """

    def __init__(
        self,
        text: str,
        font: Optional[FontMetrics] = None,
        hyphenator: Optional[HyphenationEngine] = None,
        indent: float = 0.0,
    ) -> None:
        self.text = text
        self.font = font or FontMetrics()
        self.hyphenator = hyphenator or HyphenationEngine()
        self.indent = indent
        self.nodes: list[Node] = []
        self.ligature_count = 0
        self.kerning_adjustments = 0
        self.hyphenation_count = 0
        self._build()

    def _build(self) -> None:
        """Convert the text into a node list."""
        self.nodes = []
        if self.indent > 0:
            self.nodes.append(Box(width=self.indent, content=""))

        words = self.text.split()
        space_width = self.font.glyph(" ").width
        space_stretch = space_width * 0.5
        space_shrink = space_width * 0.33

        for wi, word in enumerate(words):
            # Apply ligature detection
            display_word, lig_count = self._apply_ligatures(word)
            self.ligature_count += lig_count

            # Generate boxes for the word, with optional hyphenation
            syllables = self.hyphenator.hyphenate(word)
            if len(syllables) > 1:
                self.hyphenation_count += len(syllables) - 1
                for si, syl in enumerate(syllables):
                    w = self._word_width(syl)
                    self.nodes.append(Box(width=w, content=syl))
                    if si < len(syllables) - 1:
                        # Insert flagged penalty and hyphen box at syllable boundary
                        hyphen_width = self.font.glyph("-").width
                        self.nodes.append(
                            Penalty(
                                penalty=self.hyphenator.__class__.__name__
                                and 50.0,
                                width=hyphen_width,
                                flagged=True,
                            )
                        )
            else:
                w = self._word_width(word)
                self.nodes.append(Box(width=w, content=word))

            # Add inter-word glue (except after last word)
            if wi < len(words) - 1:
                self.nodes.append(Glue(
                    width=space_width,
                    stretch=space_stretch,
                    shrink=space_shrink,
                ))

        # Append finishing penalty and glue to close the paragraph
        self.nodes.append(Penalty(penalty=INFINITY, width=0.0))
        self.nodes.append(Glue(width=0.0, stretch=INFINITY, shrink=0.0))
        self.nodes.append(Penalty(penalty=-INFINITY, width=0.0))

    def _apply_ligatures(self, word: str) -> tuple[str, int]:
        """Detect and count ligatures in a word."""
        count = 0
        result = word
        for seq, lig in self.font._ligature_table.items():
            while seq in result:
                count += 1
                result = result.replace(seq, lig, 1)
        return result, count

    def _word_width(self, word: str) -> float:
        """Compute the typographic width of a word including kerning."""
        total = 0.0
        for i, ch in enumerate(word):
            total += self.font.glyph(ch).width
            if i > 0:
                kern = self.font.kerning(word[i - 1], ch)
                if kern != 0.0:
                    self.kerning_adjustments += 1
                    total += kern
        return max(total, 0.0)


# ---------------------------------------------------------------------------
# Page Layout
# ---------------------------------------------------------------------------

@dataclass
class PageLayout:
    """Configurable page geometry for the typesetting engine.

    Defines margins, column count, and widow/orphan control parameters.
    All dimensions are in PostScript points (1/72 inch). The default
    values correspond to US Letter paper (612 x 792 pt) with 1-inch
    margins.
    """

    page_width: float = 612.0   # US Letter width in points
    page_height: float = 792.0  # US Letter height in points
    margin_top: float = 72.0
    margin_bottom: float = 72.0
    margin_left: float = 72.0
    margin_right: float = 72.0
    columns: int = 1
    column_gap: float = 18.0
    widow_threshold: int = 2   # Minimum lines at top of page
    orphan_threshold: int = 2  # Minimum lines at bottom of page

    @property
    def text_width(self) -> float:
        """Usable text width per column."""
        total = self.page_width - self.margin_left - self.margin_right
        if self.columns > 1:
            return (total - self.column_gap * (self.columns - 1)) / self.columns
        return total

    @property
    def text_height(self) -> float:
        """Usable text height on the page."""
        return self.page_height - self.margin_top - self.margin_bottom


# ---------------------------------------------------------------------------
# Page
# ---------------------------------------------------------------------------

@dataclass
class Page:
    """A single page of typeset content with headers and footers.

    Collects formatted paragraph lines and tracks page metadata
    including page number, line count, and badness statistics.
    """

    number: int = 1
    lines: list[list[Node]] = field(default_factory=list)
    header: str = ""
    footer: str = ""
    total_badness: float = 0.0

    @property
    def line_count(self) -> int:
        return len(self.lines)

    def add_line(self, line: list[Node], badness: float = 0.0) -> None:
        """Append a formatted line to this page."""
        self.lines.append(line)
        self.total_badness += badness


# ---------------------------------------------------------------------------
# FizzBuzz Report
# ---------------------------------------------------------------------------

class FizzBuzzReport:
    """Generates a typeset report of FizzBuzz evaluation results.

    Composes paragraphs from evaluation results, runs them through the
    Knuth-Plass line breaker, paginates the output with widow/orphan
    control, and produces a sequence of Pages ready for rendering.
    """

    def __init__(
        self,
        results: list[FizzBuzzResult],
        layout: Optional[PageLayout] = None,
        font: Optional[FontMetrics] = None,
        title: str = "Enterprise FizzBuzz Evaluation Report",
    ) -> None:
        self.results = results
        self.layout = layout or PageLayout()
        self.font = font or FontMetrics()
        self.title = title
        self.pages: list[Page] = []
        self.total_demerits = 0.0
        self.total_badness = 0.0
        self.total_lines = 0
        self.hyphenation_count = 0
        self.ligature_count = 0
        self.kerning_adjustments = 0
        self._line_badnesses: list[float] = []

    def generate(self) -> list[Page]:
        """Typeset the evaluation results and return a list of pages."""
        breaker = KnuthPlassBreaker(line_width=self.layout.text_width)
        hyphenator = HyphenationEngine()
        line_height = self.font.size * 1.2  # Standard 120% leading
        max_lines_per_page = int(self.layout.text_height / line_height)

        # Build paragraphs from results
        all_lines: list[list[Node]] = []

        # Title paragraph
        title_para = Paragraph(
            self.title, font=self.font, hyphenator=hyphenator
        )
        title_lines = breaker.break_lines(title_para.nodes)
        all_lines.extend(title_lines)
        # Add blank line after title
        all_lines.append([Box(width=0, content="")])

        # Summary paragraph
        fizz_count = sum(1 for r in self.results if r.output == "Fizz")
        buzz_count = sum(1 for r in self.results if r.output == "Buzz")
        fizzbuzz_count = sum(1 for r in self.results if r.output == "FizzBuzz")
        number_count = len(self.results) - fizz_count - buzz_count - fizzbuzz_count

        summary_text = (
            f"Analysis of {len(self.results)} integers yielded "
            f"{fizzbuzz_count} FizzBuzz results, {fizz_count} Fizz results, "
            f"{buzz_count} Buzz results, and {number_count} numeric passthrough results."
        )
        summary_para = Paragraph(
            summary_text,
            font=self.font,
            hyphenator=hyphenator,
            indent=self.font.glyph(" ").width * 4,
        )
        summary_lines = breaker.break_lines(summary_para.nodes)
        all_lines.extend(summary_lines)
        all_lines.append([Box(width=0, content="")])

        # Result paragraphs — group consecutive same-type results
        groups = self._group_results()
        for group_label, group_results in groups:
            group_text = (
                f"{group_label}: "
                + ", ".join(
                    f"{r.number}" for r in group_results
                )
                + "."
            )
            para = Paragraph(
                group_text,
                font=self.font,
                hyphenator=hyphenator,
                indent=self.font.glyph(" ").width * 2,
            )
            self.hyphenation_count += para.hyphenation_count
            self.ligature_count += para.ligature_count
            self.kerning_adjustments += para.kerning_adjustments

            lines = breaker.break_lines(para.nodes)
            all_lines.extend(lines)

        # Compute per-line badness
        for line in all_lines:
            line_width = sum(
                n.width for n in line if isinstance(n, (Box, Glue))
            )
            diff = self.layout.text_width - line_width
            if abs(diff) < 0.001:
                badness = 0.0
            else:
                ratio = diff / (self.layout.text_width * 0.3) if diff > 0 else diff / (self.layout.text_width * 0.1)
                badness = min(100.0 * abs(ratio) ** 3, INFINITY_BADNESS)
            self._line_badnesses.append(badness)
            self.total_badness += badness

        self.total_lines = len(all_lines)

        # Paginate with widow/orphan control
        self.pages = self._paginate(all_lines, max_lines_per_page)

        return self.pages

    def _group_results(self) -> list[tuple[str, list[FizzBuzzResult]]]:
        """Group results by their output classification."""
        groups: dict[str, list[FizzBuzzResult]] = {}
        order: list[str] = []
        for r in self.results:
            key = r.output if r.output in ("Fizz", "Buzz", "FizzBuzz") else "Numeric"
            if key not in groups:
                groups[key] = []
                order.append(key)
            groups[key].append(r)
        return [(k, groups[k]) for k in order]

    def _paginate(
        self, all_lines: list[list[Node]], max_per_page: int
    ) -> list[Page]:
        """Distribute lines across pages with widow/orphan control."""
        pages: list[Page] = []
        page_num = 1
        idx = 0
        total = len(all_lines)

        while idx < total:
            page = Page(
                number=page_num,
                header=self.title,
                footer=f"Page {page_num}",
            )

            lines_on_page = min(max_per_page, total - idx)

            # Orphan control: if we would leave fewer than threshold lines
            # of the next paragraph on this page, pull one back
            if total - idx - lines_on_page > 0:
                remaining_after = total - idx - lines_on_page
                if remaining_after < self.layout.orphan_threshold and lines_on_page > self.layout.orphan_threshold:
                    lines_on_page -= 1

            # Widow control: if the next page would start with fewer than
            # threshold lines, reduce this page to push more lines forward
            if total - idx - lines_on_page > 0:
                next_page_lines = total - idx - lines_on_page
                if next_page_lines < self.layout.widow_threshold and lines_on_page > self.layout.widow_threshold:
                    lines_on_page -= 1

            for i in range(lines_on_page):
                line_idx = idx + i
                badness = self._line_badnesses[line_idx] if line_idx < len(self._line_badnesses) else 0.0
                page.add_line(all_lines[line_idx], badness)

            pages.append(page)
            idx += lines_on_page
            page_num += 1

        return pages

    @property
    def average_badness(self) -> float:
        """Mean badness across all lines."""
        if self.total_lines == 0:
            return 0.0
        return self.total_badness / self.total_lines


# ---------------------------------------------------------------------------
# PostScript Renderer
# ---------------------------------------------------------------------------

class PostScriptRenderer:
    """Renders typeset pages to simplified PostScript output.

    Generates DSC-compliant PostScript with proper BoundingBox declarations,
    font setup via findfont/scalefont/setfont, and text placement via
    moveto/show. The output is directly interpretable by any PostScript
    Level 2 compatible RIP or viewer such as Ghostscript.
    """

    def __init__(
        self,
        layout: Optional[PageLayout] = None,
        font: Optional[FontMetrics] = None,
    ) -> None:
        self.layout = layout or PageLayout()
        self.font = font or FontMetrics()

    def render(self, pages: list[Page]) -> str:
        """Generate PostScript source for all pages."""
        lines: list[str] = []
        lines.append("%!PS-Adobe-3.0")
        lines.append(
            f"%%BoundingBox: 0 0 "
            f"{int(self.layout.page_width)} {int(self.layout.page_height)}"
        )
        lines.append(f"%%Pages: {len(pages)}")
        lines.append(f"%%Title: Enterprise FizzBuzz Evaluation Report")
        lines.append("%%EndComments")
        lines.append("")
        lines.append(
            f"/{self.font.name} findfont {self.font.size} scalefont setfont"
        )
        lines.append("")

        for page in pages:
            lines.append(f"%%Page: {page.number} {page.number}")
            lines.append("gsave")

            # Header
            if page.header:
                hx = self.layout.margin_left
                hy = self.layout.page_height - self.layout.margin_top + 20
                lines.append(f"{hx:.1f} {hy:.1f} moveto")
                lines.append(f"({self._escape_ps(page.header)}) show")

            # Body lines
            line_height = self.font.size * 1.2
            y_start = self.layout.page_height - self.layout.margin_top
            x_start = self.layout.margin_left

            for li, line in enumerate(page.lines):
                y = y_start - li * line_height
                text = self._line_to_text(line)
                if text.strip():
                    lines.append(f"{x_start:.1f} {y:.1f} moveto")
                    lines.append(f"({self._escape_ps(text)}) show")

            # Footer
            if page.footer:
                fx = self.layout.margin_left
                fy = self.layout.margin_bottom - 15
                lines.append(f"{fx:.1f} {fy:.1f} moveto")
                lines.append(f"({self._escape_ps(page.footer)}) show")

            lines.append("grestore")
            lines.append("showpage")
            lines.append("")

        lines.append("%%EOF")
        return "\n".join(lines)

    @staticmethod
    def _escape_ps(text: str) -> str:
        """Escape special PostScript characters in string literals."""
        text = text.replace("\\", "\\\\")
        text = text.replace("(", "\\(")
        text = text.replace(")", "\\)")
        return text

    @staticmethod
    def _line_to_text(line: list[Node]) -> str:
        """Extract the text content from a line of nodes."""
        parts = []
        for node in line:
            if isinstance(node, Box):
                parts.append(node.content)
            elif isinstance(node, Glue):
                parts.append(" ")
        return "".join(parts)


# ---------------------------------------------------------------------------
# TypesetDashboard
# ---------------------------------------------------------------------------

class TypesetDashboard:
    """ASCII dashboard displaying typesetting metrics and quality scores.

    Presents a comprehensive overview of the typesetting run including
    page count, line count, badness distribution, hyphenation statistics,
    ligature counts, and kerning adjustments. The dashboard uses the
    same box-drawing character conventions as other EFP dashboards.
    """

    @staticmethod
    def render(report: FizzBuzzReport, width: int = 72) -> str:
        """Render the typesetting statistics dashboard."""
        lines: list[str] = []
        hr = "+" + "-" * (width - 2) + "+"

        def row(label: str, value: str) -> str:
            inner = width - 4
            left = f"  {label}"
            right = f"{value}  "
            pad = inner - len(left) - len(right)
            if pad < 1:
                pad = 1
            return "|" + left + " " * pad + right + "|"

        lines.append(hr)
        title = " FIZZPRINT TYPESETTING ENGINE "
        pad_total = width - 2 - len(title)
        pad_left = pad_total // 2
        pad_right = pad_total - pad_left
        lines.append("|" + " " * pad_left + title + " " * pad_right + "|")
        lines.append(hr)
        lines.append(row("Pages", str(len(report.pages))))
        lines.append(row("Total lines", str(report.total_lines)))
        lines.append(row("Total badness", f"{report.total_badness:.1f}"))
        lines.append(row("Average badness", f"{report.average_badness:.1f}"))
        lines.append(row("Hyphenation points", str(report.hyphenation_count)))
        lines.append(row("Ligatures detected", str(report.ligature_count)))
        lines.append(row("Kerning adjustments", str(report.kerning_adjustments)))
        lines.append(hr)

        # Badness histogram
        lines.append("|" + " " * (width - 2) + "|")
        hist_title = "  Badness Distribution"
        lines.append("|" + hist_title + " " * (width - 2 - len(hist_title)) + "|")

        buckets = [0] * 5
        bucket_labels = ["0-10", "10-100", "100-500", "500-1k", "1k+"]
        for b in report._line_badnesses:
            if b <= 10:
                buckets[0] += 1
            elif b <= 100:
                buckets[1] += 1
            elif b <= 500:
                buckets[2] += 1
            elif b <= 1000:
                buckets[3] += 1
            else:
                buckets[4] += 1

        max_count = max(buckets) if buckets else 1
        bar_max = width - 22  # space for label and padding

        for label, count in zip(bucket_labels, buckets):
            bar_len = int((count / max(max_count, 1)) * bar_max) if max_count > 0 else 0
            bar = "#" * bar_len
            entry = f"  {label:>6s} |{bar:<{bar_max}s} {count}"
            # Pad or truncate to fit
            inner = width - 2
            if len(entry) < inner:
                entry += " " * (inner - len(entry))
            elif len(entry) > inner:
                entry = entry[:inner]
            lines.append("|" + entry + "|")

        lines.append(hr)

        # Page summary
        lines.append("|" + " " * (width - 2) + "|")
        page_title = "  Per-Page Summary"
        lines.append("|" + page_title + " " * (width - 2 - len(page_title)) + "|")

        for page in report.pages[:10]:  # Show first 10 pages
            pg_info = f"  Page {page.number}: {page.line_count} lines, badness {page.total_badness:.0f}"
            inner = width - 2
            if len(pg_info) < inner:
                pg_info += " " * (inner - len(pg_info))
            lines.append("|" + pg_info[:inner] + "|")

        if len(report.pages) > 10:
            more = f"  ... and {len(report.pages) - 10} more pages"
            inner = width - 2
            more += " " * (inner - len(more))
            lines.append("|" + more[:inner] + "|")

        lines.append(hr)
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# TypesetMiddleware
# ---------------------------------------------------------------------------

class TypesetMiddleware(IMiddleware):
    """Middleware that typesets FizzBuzz evaluation results in real time.

    Collects results as they pass through the pipeline and, upon
    completion, generates a publication-quality typeset report using
    the Knuth-Plass optimal line breaking algorithm. The report
    can be output as PostScript or rendered as an ASCII dashboard.
    """

    def __init__(
        self,
        output_path: Optional[str] = None,
        enable_dashboard: bool = False,
        layout: Optional[PageLayout] = None,
        font: Optional[FontMetrics] = None,
    ) -> None:
        self.output_path = output_path
        self.enable_dashboard = enable_dashboard
        self.layout = layout or PageLayout()
        self.font = font or FontMetrics()
        self._results: list[FizzBuzzResult] = []
        self.report: Optional[FizzBuzzReport] = None

    def process(
        self,
        context: ProcessingContext,
        next_handler: Callable[[ProcessingContext], ProcessingContext],
    ) -> ProcessingContext:
        """Collect evaluation results for post-pipeline typesetting."""
        result = next_handler(context)

        if result.results:
            self._results.append(result.results[-1])

        return result

    def finalize(self) -> Optional[FizzBuzzReport]:
        """Generate the typeset report from collected results.

        Called after the full evaluation pipeline completes. Produces the
        FizzBuzzReport and optionally writes PostScript output to disk.
        Returns the report for dashboard rendering.
        """
        if not self._results:
            return None

        self.report = FizzBuzzReport(
            results=self._results,
            layout=self.layout,
            font=self.font,
        )
        self.report.generate()

        if self.output_path:
            renderer = PostScriptRenderer(layout=self.layout, font=self.font)
            ps_content = renderer.render(self.report.pages)
            with open(self.output_path, "w", encoding="utf-8") as f:
                f.write(ps_content)
            logger.info(
                "FizzPrint PostScript output written to %s (%d pages)",
                self.output_path,
                len(self.report.pages),
            )

        return self.report

    def get_name(self) -> str:
        return "TypesetMiddleware"

    def get_priority(self) -> int:
        return 960
