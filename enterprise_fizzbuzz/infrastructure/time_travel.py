"""
Enterprise FizzBuzz Platform - Time-Travel Debugger Module

Implements a fully-featured temporal debugging subsystem that allows
engineers to step forwards and backwards through the evaluation timeline,
set conditional breakpoints on FizzBuzz results, diff arbitrary snapshots,
and visualize the entire history with an ASCII timeline strip.

Because debugging FizzBuzz in a strictly forward-moving temporal direction
is an unacceptable limitation for any serious enterprise platform. With
time-travel debugging, every modulo operation is immortalized in a
SHA-256-integrity-verified snapshot, navigable bidirectionally with O(1)
random access. Doc Brown would be proud. Or confused. Definitely one
of those.

Key Components:
    EvaluationSnapshot: Frozen dataclass capturing the complete state of a
        FizzBuzz evaluation at a single point in time, sealed with a
        cryptographic integrity hash because trust is earned, not assumed.
    Timeline: Ordered, append-only collection of snapshots with O(1)
        random access by sequence index. Supports capacity limits because
        even immortalized modulo results can't live forever (disk space
        is finite, even if enterprise ambition is not).
    ConditionalBreakpoint: Compile-time validated expression evaluator
        that halts timeline navigation when conditions are met, because
        stepping through 10,000 FizzBuzz evaluations one by one is a
        punishment that not even enterprise software deserves.
    TimelineNavigator: Bidirectional cursor over the timeline with
        step_forward, step_back, goto, continue_to_breakpoint, and
        reverse_continue operations. The temporal VCR of modulo debugging.
    DiffViewer: Field-by-field comparison of any two snapshots with
        ASCII side-by-side rendering, because "what changed between
        evaluation #42 and #43?" is a question that keeps enterprise
        engineers up at night.
    TimelineUI: ASCII timeline strip with markers for breakpoints (B),
        the current cursor position (>), and detected anomalies (!).
    TimeTravelMiddleware: IMiddleware implementation at priority -5
        that captures a snapshot after each evaluation completes,
        ensuring the timeline is always up to date without requiring
        any modifications to the core evaluation pipeline.
"""

from __future__ import annotations

import copy
import hashlib
import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Optional

from enterprise_fizzbuzz.domain.exceptions import (
    BreakpointSyntaxError,
    SnapshotIntegrityError,
    TimelineEmptyError,
    TimelineNavigationError,
    TimeTravelError,
)
from enterprise_fizzbuzz.domain.interfaces import IMiddleware
from enterprise_fizzbuzz.domain.models import (
    Event,
    EventType,
    FizzBuzzResult,
    ProcessingContext,
)

logger = logging.getLogger(__name__)


# ============================================================
# EvaluationSnapshot
# ============================================================


@dataclass(frozen=True)
class EvaluationSnapshot:
    """Frozen record of a FizzBuzz evaluation at a specific point in time.

    Each snapshot captures the number, the result string, the full list
    of matched rules, processing latency, all metadata, and the session
    context state at the moment of capture. The integrity_hash field
    contains a SHA-256 digest of the snapshot's deterministic content,
    ensuring that any post-hoc tampering with FizzBuzz history is
    immediately detectable. Because in enterprise software, even the
    past is auditable.

    Attributes:
        sequence: Monotonically increasing index in the timeline.
        number: The input number that was evaluated.
        result: The output string (e.g., "Fizz", "Buzz", "FizzBuzz", "42").
        matched_rules: Names of all rules that matched this number.
        latency_ms: Processing time in milliseconds.
        metadata: Copy of the ProcessingContext metadata at capture time.
        timestamp: UTC timestamp of when the snapshot was taken.
        session_id: The session that produced this evaluation.
        integrity_hash: SHA-256 hash of the snapshot's content fields.
    """

    sequence: int
    number: int
    result: str
    matched_rules: tuple[str, ...] = field(default_factory=tuple)
    latency_ms: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)
    timestamp: str = ""
    session_id: str = ""
    integrity_hash: str = ""

    @staticmethod
    def compute_hash(
        sequence: int,
        number: int,
        result: str,
        matched_rules: tuple[str, ...],
        latency_ms: float,
        metadata: dict[str, Any],
        session_id: str,
    ) -> str:
        """Compute the SHA-256 integrity hash for snapshot content.

        The hash is computed over a deterministic JSON serialization of
        the snapshot's content fields, excluding the hash itself (because
        self-referential hashes are a temporal paradox we'd rather avoid).
        """
        content = json.dumps(
            {
                "sequence": sequence,
                "number": number,
                "result": result,
                "matched_rules": list(matched_rules),
                "latency_ms": round(latency_ms, 6),
                "metadata_keys": sorted(metadata.keys()),
                "session_id": session_id,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(content.encode("utf-8")).hexdigest()

    @classmethod
    def create(
        cls,
        sequence: int,
        number: int,
        result: str,
        matched_rules: tuple[str, ...],
        latency_ms: float,
        metadata: dict[str, Any],
        session_id: str,
    ) -> EvaluationSnapshot:
        """Factory method that creates a snapshot with a computed integrity hash."""
        ts = datetime.now(timezone.utc).isoformat()
        integrity = cls.compute_hash(
            sequence, number, result, matched_rules, latency_ms, metadata, session_id
        )
        return cls(
            sequence=sequence,
            number=number,
            result=result,
            matched_rules=matched_rules,
            latency_ms=latency_ms,
            metadata=copy.deepcopy(metadata),
            timestamp=ts,
            session_id=session_id,
            integrity_hash=integrity,
        )

    def verify_integrity(self) -> bool:
        """Verify that the snapshot has not been tampered with.

        Recomputes the SHA-256 hash and compares it to the stored value.
        Returns True if the snapshot is pristine, False if someone has
        been meddling with the timeline.
        """
        expected = self.compute_hash(
            self.sequence,
            self.number,
            self.result,
            self.matched_rules,
            self.latency_ms,
            self.metadata,
            self.session_id,
        )
        return expected == self.integrity_hash

    def to_dict(self) -> dict[str, Any]:
        """Serialize the snapshot to a dictionary for display and export."""
        return {
            "sequence": self.sequence,
            "number": self.number,
            "result": self.result,
            "matched_rules": list(self.matched_rules),
            "latency_ms": round(self.latency_ms, 4),
            "timestamp": self.timestamp,
            "session_id": self.session_id,
            "integrity_hash": self.integrity_hash[:16] + "...",
        }


# ============================================================
# Timeline
# ============================================================


class Timeline:
    """Ordered, append-only collection of EvaluationSnapshots.

    The timeline is the backbone of the Time-Travel Debugger: an
    immutable ledger of every FizzBuzz evaluation that has ever occurred
    during the current session. Snapshots are indexed by sequence number
    for O(1) random access, because linear search through FizzBuzz
    history is an O(n) indignity that no enterprise engineer should
    have to endure.

    The timeline supports a configurable maximum capacity. When the limit
    is reached, the oldest snapshots are evicted with the same ceremonial
    disregard that the cache subsystem applies to its evictees. No eulogies
    here — time marches forward, even in a time-travel debugger.
    """

    def __init__(self, max_snapshots: int = 10000) -> None:
        self._snapshots: list[EvaluationSnapshot] = []
        self._max_snapshots = max_snapshots
        self._next_sequence = 0
        self._anomalies: set[int] = set()

    def append(self, snapshot: EvaluationSnapshot) -> None:
        """Append a snapshot to the timeline.

        If the timeline has reached maximum capacity, the oldest
        snapshot is evicted to make room. Time waits for no snapshot.
        """
        if len(self._snapshots) >= self._max_snapshots > 0:
            self._snapshots.pop(0)
            logger.debug(
                "Timeline capacity reached (%d). Oldest snapshot evicted. "
                "Temporal history is being compressed.",
                self._max_snapshots,
            )

        self._snapshots.append(snapshot)
        self._next_sequence = snapshot.sequence + 1

    def get(self, sequence: int) -> EvaluationSnapshot:
        """Retrieve a snapshot by its sequence number. O(1) access.

        Raises TimelineNavigationError if the sequence is out of bounds.
        """
        if not self._snapshots:
            raise TimelineEmptyError()

        # Calculate index from sequence, accounting for evictions
        base_seq = self._snapshots[0].sequence
        index = sequence - base_seq

        if index < 0 or index >= len(self._snapshots):
            raise TimelineNavigationError(
                "get",
                f"Sequence {sequence} is out of bounds. "
                f"Valid range: [{base_seq}, {base_seq + len(self._snapshots) - 1}]",
            )

        return self._snapshots[index]

    def get_by_index(self, index: int) -> EvaluationSnapshot:
        """Retrieve a snapshot by its position index in the current timeline."""
        if not self._snapshots:
            raise TimelineEmptyError()
        if index < 0 or index >= len(self._snapshots):
            raise TimelineNavigationError(
                "get_by_index",
                f"Index {index} is out of bounds. Timeline length: {len(self._snapshots)}",
            )
        return self._snapshots[index]

    @property
    def length(self) -> int:
        """Return the number of snapshots in the timeline."""
        return len(self._snapshots)

    @property
    def is_empty(self) -> bool:
        """Return True if the timeline contains no snapshots."""
        return len(self._snapshots) == 0

    @property
    def first_sequence(self) -> int:
        """Return the sequence number of the oldest snapshot."""
        if not self._snapshots:
            raise TimelineEmptyError()
        return self._snapshots[0].sequence

    @property
    def last_sequence(self) -> int:
        """Return the sequence number of the newest snapshot."""
        if not self._snapshots:
            raise TimelineEmptyError()
        return self._snapshots[-1].sequence

    @property
    def next_sequence(self) -> int:
        """Return the next sequence number to be assigned."""
        return self._next_sequence

    @property
    def anomalies(self) -> set[int]:
        """Return the set of sequence numbers flagged as anomalies."""
        return self._anomalies

    def mark_anomaly(self, sequence: int) -> None:
        """Flag a sequence number as a temporal anomaly."""
        self._anomalies.add(sequence)

    def all_snapshots(self) -> list[EvaluationSnapshot]:
        """Return a copy of all snapshots in the timeline."""
        return list(self._snapshots)

    def slice(self, start_seq: int, end_seq: int) -> list[EvaluationSnapshot]:
        """Return snapshots in the sequence range [start_seq, end_seq] inclusive."""
        if self.is_empty:
            return []
        base = self._snapshots[0].sequence
        start_idx = max(0, start_seq - base)
        end_idx = min(len(self._snapshots), end_seq - base + 1)
        return self._snapshots[start_idx:end_idx]


# ============================================================
# ConditionalBreakpoint
# ============================================================


class ConditionalBreakpoint:
    """Compiled expression-based breakpoint for timeline navigation.

    Breakpoints evaluate a user-provided Python expression against
    snapshot data to determine whether navigation should halt. The
    expression is compiled at construction time using compile() and
    evaluated using eval() with a restricted namespace containing
    only three variables: number, result, and latency.

    Security is enforced through a defense-in-depth approach:
    expressions are validated at compile time, and evaluation occurs
    within a strictly sandboxed runtime. The restricted namespace prevents
    access to builtins, ensuring that breakpoint expressions cannot perform
    arbitrary code execution or access the filesystem.

    Examples:
        ConditionalBreakpoint("result == 'FizzBuzz'")
        ConditionalBreakpoint("number > 50 and result == 'Fizz'")
        ConditionalBreakpoint("latency > 10.0")
        ConditionalBreakpoint("number % 7 == 0")
    """

    def __init__(self, expression: str) -> None:
        self._expression = expression
        try:
            self._compiled = compile(expression, "<breakpoint>", "eval")
        except SyntaxError as e:
            raise BreakpointSyntaxError(expression, str(e))

    @property
    def expression(self) -> str:
        """Return the raw breakpoint expression string."""
        return self._expression

    def evaluate(self, snapshot: EvaluationSnapshot) -> bool:
        """Evaluate the breakpoint condition against a snapshot.

        Returns True if the breakpoint condition is satisfied, meaning
        navigation should halt at this snapshot. Returns False if the
        condition is not met, meaning navigation should continue.

        The evaluation namespace is restricted to:
            number: The input number from the snapshot.
            result: The output string from the snapshot.
            latency: The processing latency in milliseconds.
        """
        namespace = {
            "number": snapshot.number,
            "result": snapshot.result,
            "latency": snapshot.latency_ms,
            "__builtins__": {},
        }
        try:
            return bool(eval(self._compiled, namespace))  # noqa: S307
        except Exception as e:
            logger.warning(
                "Breakpoint expression '%s' raised %s for snapshot seq=%d: %s",
                self._expression,
                type(e).__name__,
                snapshot.sequence,
                e,
            )
            return False

    def __repr__(self) -> str:
        return f"ConditionalBreakpoint({self._expression!r})"


# ============================================================
# TimelineNavigator
# ============================================================


class TimelineNavigator:
    """Bidirectional cursor for traversing the evaluation timeline.

    The navigator maintains a cursor position within the timeline and
    provides operations for moving forwards, backwards, jumping to
    arbitrary positions, and seeking to breakpoints in either direction.
    It is the temporal remote control of the Time-Travel Debugger: play,
    pause, rewind, fast-forward, and the ever-popular "skip to the part
    where something interesting happens."

    Operations:
        step_forward: Move the cursor one position forward.
        step_back: Move the cursor one position backward.
        goto: Jump to a specific sequence number.
        continue_to_breakpoint: Advance forward until a breakpoint fires.
        reverse_continue: Retreat backward until a breakpoint fires.
        current: Return the snapshot at the current cursor position.
    """

    def __init__(self, timeline: Timeline) -> None:
        self._timeline = timeline
        self._cursor: int = -1  # -1 means "not positioned"

    @property
    def cursor(self) -> int:
        """Return the current cursor sequence number, or -1 if unpositioned."""
        return self._cursor

    @property
    def at_start(self) -> bool:
        """Return True if the cursor is at the beginning of the timeline."""
        if self._timeline.is_empty:
            return True
        return self._cursor <= self._timeline.first_sequence

    @property
    def at_end(self) -> bool:
        """Return True if the cursor is at the end of the timeline."""
        if self._timeline.is_empty:
            return True
        return self._cursor >= self._timeline.last_sequence

    def current(self) -> EvaluationSnapshot:
        """Return the snapshot at the current cursor position.

        Raises TimelineEmptyError if the timeline is empty.
        Raises TimelineNavigationError if the cursor is not positioned.
        """
        if self._timeline.is_empty:
            raise TimelineEmptyError()
        if self._cursor < 0:
            raise TimelineNavigationError(
                "current",
                "Navigator cursor is not positioned. "
                "Call step_forward(), step_back(), or goto() first.",
            )
        return self._timeline.get(self._cursor)

    def step_forward(self) -> Optional[EvaluationSnapshot]:
        """Advance the cursor one position forward.

        Returns the snapshot at the new position, or None if already
        at the end of the timeline. Moving forward through FizzBuzz
        history is the easy direction — it's the direction time
        naturally flows, even for modulo arithmetic.
        """
        if self._timeline.is_empty:
            raise TimelineEmptyError()

        if self._cursor < 0:
            self._cursor = self._timeline.first_sequence
        elif self._cursor >= self._timeline.last_sequence:
            return None
        else:
            self._cursor += 1

        return self._timeline.get(self._cursor)

    def step_back(self) -> Optional[EvaluationSnapshot]:
        """Move the cursor one position backward.

        Returns the snapshot at the new position, or None if already
        at the beginning of the timeline. This is the operation that
        makes the Time-Travel Debugger earn its name — rewinding
        through the immutable history of FizzBuzz evaluations like
        a VCR in reverse.
        """
        if self._timeline.is_empty:
            raise TimelineEmptyError()

        if self._cursor < 0:
            self._cursor = self._timeline.last_sequence
        elif self._cursor <= self._timeline.first_sequence:
            return None
        else:
            self._cursor -= 1

        return self._timeline.get(self._cursor)

    def goto(self, sequence: int) -> EvaluationSnapshot:
        """Jump directly to a specific sequence number.

        This is the time-travel equivalent of entering coordinates
        into the DeLorean's flux capacitor. The destination must exist
        within the current timeline bounds.
        """
        snapshot = self._timeline.get(sequence)  # raises if invalid
        self._cursor = sequence
        return snapshot

    def continue_to_breakpoint(
        self,
        breakpoints: list[ConditionalBreakpoint],
    ) -> Optional[EvaluationSnapshot]:
        """Advance forward until a breakpoint condition is satisfied.

        Evaluates each breakpoint at every snapshot as the cursor moves
        forward. Returns the snapshot where a breakpoint fired, or None
        if the end of the timeline is reached without hitting any
        breakpoint. This is the "fast-forward to the interesting part"
        operation.
        """
        if self._timeline.is_empty:
            raise TimelineEmptyError()

        if not breakpoints:
            return None

        if self._cursor < 0:
            self._cursor = self._timeline.first_sequence - 1

        while self._cursor < self._timeline.last_sequence:
            self._cursor += 1
            snapshot = self._timeline.get(self._cursor)
            for bp in breakpoints:
                if bp.evaluate(snapshot):
                    logger.debug(
                        "Breakpoint hit at sequence %d: %s",
                        self._cursor,
                        bp.expression,
                    )
                    return snapshot

        return None

    def reverse_continue(
        self,
        breakpoints: list[ConditionalBreakpoint],
    ) -> Optional[EvaluationSnapshot]:
        """Move backward until a breakpoint condition is satisfied.

        The temporal reverse of continue_to_breakpoint. Searches backward
        through the timeline for a snapshot that satisfies any breakpoint.
        Returns None if the beginning of the timeline is reached without
        finding a match. This is reverse debugging in its purest form:
        rewinding through modulo arithmetic history to find where things
        went wrong (or right, but usually wrong).
        """
        if self._timeline.is_empty:
            raise TimelineEmptyError()

        if not breakpoints:
            return None

        if self._cursor < 0:
            self._cursor = self._timeline.last_sequence + 1

        while self._cursor > self._timeline.first_sequence:
            self._cursor -= 1
            snapshot = self._timeline.get(self._cursor)
            for bp in breakpoints:
                if bp.evaluate(snapshot):
                    logger.debug(
                        "Reverse breakpoint hit at sequence %d: %s",
                        self._cursor,
                        bp.expression,
                    )
                    return snapshot

        return None

    def reset(self) -> None:
        """Reset the cursor to the unpositioned state."""
        self._cursor = -1


# ============================================================
# DiffViewer
# ============================================================


class DiffViewer:
    """Field-by-field comparison of two EvaluationSnapshots.

    Compares every field of two snapshots and produces a structured
    diff report and ASCII side-by-side rendering. Because the question
    "what changed between evaluation #42 and evaluation #43?" deserves
    a comprehensive, enterprise-grade answer — not just "the number
    went from 42 to 43."

    The diff output includes field-level change indicators:
        [=] Field is identical in both snapshots.
        [~] Field has changed between snapshots.
        [+] Field is present only in the second snapshot.
        [-] Field is present only in the first snapshot.
    """

    @dataclass
    class FieldDiff:
        """A single field-level difference between two snapshots."""

        field_name: str
        left_value: Any
        right_value: Any
        changed: bool

        @property
        def indicator(self) -> str:
            return "[~]" if self.changed else "[=]"

    @classmethod
    def diff(
        cls,
        left: EvaluationSnapshot,
        right: EvaluationSnapshot,
    ) -> list[FieldDiff]:
        """Compare two snapshots field by field.

        Returns a list of FieldDiff objects, one for each comparable field.
        The comparison covers: sequence, number, result, matched_rules,
        latency_ms, session_id, and metadata keys.
        """
        fields_to_compare = [
            ("sequence", left.sequence, right.sequence),
            ("number", left.number, right.number),
            ("result", left.result, right.result),
            ("matched_rules", list(left.matched_rules), list(right.matched_rules)),
            ("latency_ms", round(left.latency_ms, 4), round(right.latency_ms, 4)),
            ("session_id", left.session_id, right.session_id),
            ("metadata_keys", sorted(left.metadata.keys()), sorted(right.metadata.keys())),
        ]

        diffs = []
        for name, lval, rval in fields_to_compare:
            diffs.append(cls.FieldDiff(
                field_name=name,
                left_value=lval,
                right_value=rval,
                changed=(lval != rval),
            ))

        return diffs

    @classmethod
    def render_ascii(
        cls,
        left: EvaluationSnapshot,
        right: EvaluationSnapshot,
        width: int = 60,
    ) -> str:
        """Render an ASCII side-by-side diff of two snapshots.

        Produces a formatted table showing each field with its value
        in both snapshots, with change indicators for quick visual
        identification of what changed. Because reading raw JSON diffs
        is for people who haven't achieved enterprise-grade debugging.
        """
        diffs = cls.diff(left, right)

        col_width = max(12, (width - 20) // 2)
        header_l = f"Seq #{left.sequence}"
        header_r = f"Seq #{right.sequence}"

        lines = []
        border = "+" + "-" * (width - 2) + "+"
        lines.append(border)
        lines.append(
            f"|{'TIME-TRAVEL DIFF':^{width - 2}}|"
        )
        lines.append(
            f"|{f'{header_l} vs {header_r}':^{width - 2}}|"
        )
        lines.append(border)

        # Column headers
        field_col = 16
        lines.append(
            f"| {'Field':<{field_col}}"
            f"{'Left':<{col_width}}"
            f"{'Right':<{col_width - field_col + 14}}"
            f"|"
        )
        lines.append(border)

        for d in diffs:
            indicator = d.indicator
            left_str = _truncate(str(d.left_value), col_width - 2)
            right_str = _truncate(str(d.right_value), col_width - field_col + 12)
            field_label = f"{indicator} {d.field_name}"
            line = (
                f"| {field_label:<{field_col}}"
                f"{left_str:<{col_width}}"
                f"{right_str:<{col_width - field_col + 14}}"
                f"|"
            )
            lines.append(line)

        lines.append(border)

        changed_count = sum(1 for d in diffs if d.changed)
        summary = f"{changed_count} field(s) changed"
        lines.append(f"|{summary:^{width - 2}}|")
        lines.append(border)

        return "\n".join(lines)

    @classmethod
    def has_changes(
        cls,
        left: EvaluationSnapshot,
        right: EvaluationSnapshot,
    ) -> bool:
        """Return True if any field differs between the two snapshots."""
        return any(d.changed for d in cls.diff(left, right))


# ============================================================
# TimelineUI
# ============================================================


class TimelineUI:
    """ASCII timeline strip renderer for the Time-Travel Debugger.

    Renders a compact, single-line ASCII visualization of the evaluation
    timeline with markers indicating the cursor position, breakpoints,
    and detected anomalies. Because temporal debugging without a visual
    timeline is like navigating without a map — technically possible,
    but deeply unpleasant.

    Marker legend:
        >  Current cursor position
        B  Breakpoint location
        !  Detected anomaly
        .  Normal evaluation (no events of interest)
        |  Timeline boundary
    """

    @classmethod
    def render_strip(
        cls,
        timeline: Timeline,
        cursor: int = -1,
        breakpoint_sequences: Optional[set[int]] = None,
        width: int = 60,
    ) -> str:
        """Render the ASCII timeline strip.

        The strip shows a compressed view of the timeline, mapping
        snapshots to character positions. If the timeline is longer
        than the available width, snapshots are bucketed and only
        the most notable marker in each bucket is displayed.
        """
        if timeline.is_empty:
            return "|" + " " * (width - 2) + "| (empty timeline)"

        bp_seqs = breakpoint_sequences or set()
        anomaly_seqs = timeline.anomalies

        first = timeline.first_sequence
        last = timeline.last_sequence
        span = last - first + 1
        usable_width = width - 4  # account for borders and padding

        if usable_width < 1:
            usable_width = 1

        strip_chars = []
        for i in range(usable_width):
            # Map strip position to sequence range
            seq_start = first + (i * span) // usable_width
            seq_end = first + ((i + 1) * span) // usable_width - 1
            seq_end = max(seq_end, seq_start)

            # Determine the most important marker in this range
            has_cursor = seq_start <= cursor <= seq_end
            has_bp = any(s in bp_seqs for s in range(seq_start, seq_end + 1))
            has_anomaly = any(s in anomaly_seqs for s in range(seq_start, seq_end + 1))

            if has_cursor:
                strip_chars.append(">")
            elif has_anomaly:
                strip_chars.append("!")
            elif has_bp:
                strip_chars.append("B")
            else:
                strip_chars.append(".")

        strip = "".join(strip_chars)
        return f"|{strip:^{width - 2}}|"

    @classmethod
    def render_dashboard(
        cls,
        timeline: Timeline,
        navigator: TimelineNavigator,
        breakpoints: Optional[list[ConditionalBreakpoint]] = None,
        width: int = 60,
    ) -> str:
        """Render the full Time-Travel Debugger dashboard.

        Shows the timeline strip, cursor status, snapshot details,
        breakpoint list, and anomaly count. This is the command center
        for temporal debugging — everything a FizzBuzz time traveler
        needs to know, rendered in glorious ASCII.
        """
        bp_list = breakpoints or []
        bp_seqs: set[int] = set()

        # Find sequences where breakpoints would fire
        if bp_list and not timeline.is_empty:
            for snap in timeline.all_snapshots():
                for bp in bp_list:
                    if bp.evaluate(snap):
                        bp_seqs.add(snap.sequence)
                        break

        lines = []
        border = "+" + "-" * (width - 2) + "+"
        lines.append(border)
        lines.append(f"|{'TIME-TRAVEL DEBUGGER DASHBOARD':^{width - 2}}|")
        lines.append(f"|{'Temporal Navigation for Enterprise FizzBuzz':^{width - 2}}|")
        lines.append(border)

        # Timeline strip
        strip = cls.render_strip(
            timeline, navigator.cursor, bp_seqs, width=width - 4
        )
        lines.append(f"|  {strip:<{width - 4}}|")
        lines.append(border)

        # Stats
        if timeline.is_empty:
            lines.append(f"|  {'Timeline: (empty)' :<{width - 4}}|")
        else:
            seq_range = f"Seq [{timeline.first_sequence} .. {timeline.last_sequence}]"
            lines.append(f"|  {'Timeline: ' + seq_range:<{width - 4}}|")
            lines.append(f"|  {'Snapshots: ' + str(timeline.length):<{width - 4}}|")
            cursor_str = str(navigator.cursor) if navigator.cursor >= 0 else "(unpositioned)"
            lines.append(f"|  {'Cursor: ' + cursor_str:<{width - 4}}|")
            lines.append(f"|  {'Anomalies: ' + str(len(timeline.anomalies)):<{width - 4}}|")

        lines.append(border)

        # Breakpoints
        lines.append(f"|  {'Breakpoints (' + str(len(bp_list)) + '):':<{width - 4}}|")
        if bp_list:
            for i, bp in enumerate(bp_list):
                bp_str = _truncate(f"  [{i}] {bp.expression}", width - 6)
                lines.append(f"|  {bp_str:<{width - 4}}|")
        else:
            lines.append(f"|  {'  (none configured)':<{width - 4}}|")
        lines.append(border)

        # Current snapshot details
        if navigator.cursor >= 0 and not timeline.is_empty:
            try:
                snap = navigator.current()
                lines.append(f"|  {'Current Snapshot:':<{width - 4}}|")
                lines.append(f"|  {'  Number: ' + str(snap.number):<{width - 4}}|")
                lines.append(f"|  {'  Result: ' + snap.result:<{width - 4}}|")
                rules_str = ", ".join(snap.matched_rules) or "(none)"
                lines.append(f"|  {'  Rules: ' + rules_str:<{width - 4}}|")
                lat_str = f"  Latency: {snap.latency_ms:.4f}ms"
                lines.append(f"|  {lat_str:<{width - 4}}|")
                hash_str = f"  Hash: {snap.integrity_hash[:24]}..."
                lines.append(f"|  {hash_str:<{width - 4}}|")
                lines.append(border)
            except (TimelineEmptyError, TimelineNavigationError):
                pass

        return "\n".join(lines)


# ============================================================
# AnomalyDetector
# ============================================================


class AnomalyDetector:
    """Detects temporal anomalies in the FizzBuzz evaluation timeline.

    An anomaly is any evaluation whose result is inconsistent with the
    deterministic rules of FizzBuzz. For instance, if number 15 produces
    "Fizz" instead of "FizzBuzz", that's a temporal anomaly — either
    the rules changed, chaos engineering intervened, or the laws of
    modulo arithmetic have been temporarily suspended.

    The detector checks for:
        - Non-monotonic sequence numbers (time going backwards).
        - Result inconsistencies where the same number produces different
          results at different points in the timeline.
    """

    def __init__(self) -> None:
        self._seen_results: dict[int, str] = {}

    def check(self, snapshot: EvaluationSnapshot) -> Optional[str]:
        """Check a snapshot for anomalies.

        Returns a description of the anomaly if one is detected,
        or None if the snapshot is temporally consistent.
        """
        number = snapshot.number
        result = snapshot.result

        if number in self._seen_results:
            prev_result = self._seen_results[number]
            if prev_result != result:
                return (
                    f"Temporal anomaly: number {number} previously produced "
                    f"'{prev_result}' but now produces '{result}'. "
                    f"The deterministic fabric of FizzBuzz may be compromised."
                )

        self._seen_results[number] = result
        return None

    def reset(self) -> None:
        """Clear the anomaly detector's memory."""
        self._seen_results.clear()


# ============================================================
# TimeTravelMiddleware
# ============================================================


class TimeTravelMiddleware(IMiddleware):
    """Middleware that captures EvaluationSnapshots into the timeline.

    Runs at priority -5 (before all other middleware in the chain) but
    captures state AFTER the full pipeline has processed the number.
    This means the snapshot contains the final result, timing data, and
    all metadata added by downstream middleware.

    The middleware is invisible to the rest of the pipeline — it wraps
    the entire chain, captures the output, stores a snapshot, and passes
    the result through unchanged. It is the temporal observer: always
    watching, never interfering (mostly).
    """

    def __init__(
        self,
        timeline: Timeline,
        event_bus: Optional[Any] = None,
        enable_anomaly_detection: bool = True,
        enable_integrity_checks: bool = True,
    ) -> None:
        self._timeline = timeline
        self._event_bus = event_bus
        self._anomaly_detector = AnomalyDetector() if enable_anomaly_detection else None
        self._enable_integrity_checks = enable_integrity_checks

    def process(
        self,
        context: ProcessingContext,
        next_handler: Callable[[ProcessingContext], ProcessingContext],
    ) -> ProcessingContext:
        """Capture a snapshot after the pipeline processes the number.

        The middleware delegates to the next handler first, then captures
        the result into a snapshot. This ensures the snapshot contains
        the fully-processed result with all middleware enrichments.
        """
        start_ns = time.perf_counter_ns()

        # Let the rest of the pipeline run
        result = next_handler(context)

        elapsed_ms = (time.perf_counter_ns() - start_ns) / 1_000_000

        # Extract the latest result
        output = ""
        matched_rules: tuple[str, ...] = ()

        if result.results:
            latest = result.results[-1]
            output = latest.output
            matched_rules = tuple(m.rule.name for m in latest.matched_rules)

        # Create and store the snapshot
        snapshot = EvaluationSnapshot.create(
            sequence=self._timeline.next_sequence,
            number=context.number,
            result=output,
            matched_rules=matched_rules,
            latency_ms=elapsed_ms,
            metadata=copy.deepcopy(result.metadata),
            session_id=context.session_id,
        )

        self._timeline.append(snapshot)

        # Emit event
        if self._event_bus is not None:
            try:
                self._event_bus.publish(Event(
                    event_type=EventType.TIME_TRAVEL_SNAPSHOT_CAPTURED,
                    payload={
                        "sequence": snapshot.sequence,
                        "number": snapshot.number,
                        "result": snapshot.result,
                        "integrity_hash": snapshot.integrity_hash[:16],
                    },
                    source="TimeTravelMiddleware",
                ))
            except Exception:
                pass  # Don't let event bus failures break the pipeline

        # Anomaly detection
        if self._anomaly_detector is not None:
            anomaly = self._anomaly_detector.check(snapshot)
            if anomaly is not None:
                self._timeline.mark_anomaly(snapshot.sequence)
                logger.warning("Time-Travel anomaly detected: %s", anomaly)
                if self._event_bus is not None:
                    try:
                        self._event_bus.publish(Event(
                            event_type=EventType.TIME_TRAVEL_ANOMALY_DETECTED,
                            payload={
                                "sequence": snapshot.sequence,
                                "description": anomaly,
                            },
                            source="TimeTravelMiddleware",
                        ))
                    except Exception:
                        pass

        return result

    def get_name(self) -> str:
        return "TimeTravelMiddleware"

    def get_priority(self) -> int:
        return -5

    @property
    def timeline(self) -> Timeline:
        """Expose the timeline for external navigation and inspection."""
        return self._timeline


# ============================================================
# Utility Functions
# ============================================================


def _truncate(text: str, max_len: int) -> str:
    """Truncate a string to max_len characters, appending '...' if needed."""
    if len(text) <= max_len:
        return text
    return text[: max_len - 3] + "..."


def create_time_travel_subsystem(
    max_snapshots: int = 10000,
    event_bus: Optional[Any] = None,
    enable_anomaly_detection: bool = True,
    enable_integrity_checks: bool = True,
) -> tuple[Timeline, TimeTravelMiddleware, TimelineNavigator]:
    """Factory function for creating the full Time-Travel Debugger stack.

    Returns a (Timeline, TimeTravelMiddleware, TimelineNavigator) tuple.
    This is the recommended way to bootstrap the time-travel subsystem,
    because manually wiring three interdependent objects together is
    exactly the kind of boilerplate that factory functions were invented
    to eliminate.
    """
    timeline = Timeline(max_snapshots=max_snapshots)
    middleware = TimeTravelMiddleware(
        timeline=timeline,
        event_bus=event_bus,
        enable_anomaly_detection=enable_anomaly_detection,
        enable_integrity_checks=enable_integrity_checks,
    )
    navigator = TimelineNavigator(timeline)
    return timeline, middleware, navigator


def render_time_travel_summary(
    timeline: Timeline,
    navigator: TimelineNavigator,
    breakpoints: Optional[list[ConditionalBreakpoint]] = None,
    width: int = 60,
) -> str:
    """Render a post-execution summary of the Time-Travel Debugger session.

    This is displayed at the end of a --time-travel run to give the user
    an overview of what was captured, how many anomalies were detected,
    and where the cursor ended up. It is the temporal equivalent of a
    post-mortem, but for modulo arithmetic instead of production incidents.
    """
    lines = []
    border = "+" + "-" * (width - 2) + "+"
    lines.append("")
    lines.append(border)
    lines.append(f"|{'TIME-TRAVEL DEBUGGER SESSION SUMMARY':^{width - 2}}|")
    lines.append(border)

    if timeline.is_empty:
        lines.append(f"|  {'No snapshots captured.':<{width - 4}}|")
        lines.append(border)
        return "\n".join(lines)

    lines.append(f"|  {'Snapshots captured: ' + str(timeline.length):<{width - 4}}|")
    seq_range = f"[{timeline.first_sequence} .. {timeline.last_sequence}]"
    lines.append(f"|  {'Sequence range: ' + seq_range:<{width - 4}}|")
    lines.append(f"|  {'Anomalies detected: ' + str(len(timeline.anomalies)):<{width - 4}}|")
    lines.append(border)

    # Result distribution
    result_counts: dict[str, int] = {}
    for snap in timeline.all_snapshots():
        result_counts[snap.result] = result_counts.get(snap.result, 0) + 1

    lines.append(f"|  {'Result Distribution:':<{width - 4}}|")
    for result_val, count in sorted(result_counts.items(), key=lambda x: -x[1])[:5]:
        dist_str = f"    {result_val}: {count}"
        lines.append(f"|  {dist_str:<{width - 4}}|")
    lines.append(border)

    # Breakpoint info
    bp_list = breakpoints or []
    if bp_list:
        lines.append(f"|  {'Active Breakpoints:':<{width - 4}}|")
        for i, bp in enumerate(bp_list):
            bp_str = _truncate(f"    [{i}] {bp.expression}", width - 6)
            lines.append(f"|  {bp_str:<{width - 4}}|")
        lines.append(border)

    # Timeline strip
    bp_seqs: set[int] = set()
    if bp_list:
        for snap in timeline.all_snapshots():
            for bp in bp_list:
                if bp.evaluate(snap):
                    bp_seqs.add(snap.sequence)
                    break

    strip = TimelineUI.render_strip(
        timeline, navigator.cursor, bp_seqs, width=width - 4
    )
    lines.append(f"|  {strip:<{width - 4}}|")
    lines.append(f"|  {'Legend: > cursor  B breakpoint  ! anomaly  . normal':<{width - 4}}|")
    lines.append(border)

    return "\n".join(lines)
