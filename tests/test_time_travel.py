"""
Enterprise FizzBuzz Platform - Time-Travel Debugger Test Suite

Comprehensive tests for the temporal debugging subsystem, because
even time travel requires test coverage. Every snapshot, every
breakpoint, every navigation operation, and every ASCII dashboard
is validated with the rigor that enterprise-grade temporal mechanics
demands.

If these tests fail, either the code is broken or the timeline has
been tampered with. In either case, the implications are staggering.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from enterprise_fizzbuzz.infrastructure.time_travel import (
    AnomalyDetector,
    ConditionalBreakpoint,
    DiffViewer,
    EvaluationSnapshot,
    Timeline,
    TimelineNavigator,
    TimelineUI,
    TimeTravelMiddleware,
    _truncate,
    create_time_travel_subsystem,
    render_time_travel_summary,
)
from enterprise_fizzbuzz.domain.exceptions import (
    BreakpointSyntaxError,
    SnapshotIntegrityError,
    TimelineEmptyError,
    TimelineNavigationError,
    TimeTravelError,
)
from enterprise_fizzbuzz.domain.models import (
    EventType,
    FizzBuzzResult,
    ProcessingContext,
    RuleDefinition,
    RuleMatch,
)
from enterprise_fizzbuzz.infrastructure.config import _SingletonMeta


# ============================================================
# Fixtures
# ============================================================


@pytest.fixture(autouse=True)
def reset_singletons():
    """Reset singletons between tests to prevent cross-contamination."""
    _SingletonMeta.reset()
    yield


@pytest.fixture
def event_bus():
    """Create a mock event bus for testing."""
    bus = MagicMock()
    return bus


def _make_snapshot(
    sequence: int = 0,
    number: int = 1,
    result: str = "1",
    matched_rules: tuple[str, ...] = (),
    latency_ms: float = 0.1,
    metadata: dict | None = None,
    session_id: str = "test-session",
) -> EvaluationSnapshot:
    """Helper to create test snapshots with sensible defaults."""
    return EvaluationSnapshot.create(
        sequence=sequence,
        number=number,
        result=result,
        matched_rules=matched_rules,
        latency_ms=latency_ms,
        metadata=metadata or {},
        session_id=session_id,
    )


def _make_fizzbuzz_timeline(count: int = 15) -> Timeline:
    """Create a timeline pre-populated with a FizzBuzz sequence."""
    timeline = Timeline(max_snapshots=10000)
    for i in range(1, count + 1):
        if i % 15 == 0:
            result = "FizzBuzz"
            rules = ("FizzRule", "BuzzRule")
        elif i % 3 == 0:
            result = "Fizz"
            rules = ("FizzRule",)
        elif i % 5 == 0:
            result = "Buzz"
            rules = ("BuzzRule",)
        else:
            result = str(i)
            rules = ()
        snap = _make_snapshot(
            sequence=i - 1,
            number=i,
            result=result,
            matched_rules=rules,
            latency_ms=0.01 * i,
        )
        timeline.append(snap)
    return timeline


# ============================================================
# EvaluationSnapshot Tests
# ============================================================


class TestEvaluationSnapshot:
    """Tests for the immutable, SHA-256-verified evaluation snapshot."""

    def test_create_snapshot_has_integrity_hash(self):
        """Snapshots should be born with a cryptographic seal."""
        snap = _make_snapshot(number=42, result="Fizz")
        assert snap.integrity_hash
        assert len(snap.integrity_hash) == 64  # SHA-256 hex digest

    def test_snapshot_integrity_passes_for_pristine_snapshot(self):
        """A freshly minted snapshot should pass integrity verification."""
        snap = _make_snapshot(number=15, result="FizzBuzz")
        assert snap.verify_integrity() is True

    def test_snapshot_to_dict(self):
        """Snapshot serialization should include all essential fields."""
        snap = _make_snapshot(
            sequence=7,
            number=15,
            result="FizzBuzz",
            matched_rules=("FizzRule", "BuzzRule"),
        )
        d = snap.to_dict()
        assert d["sequence"] == 7
        assert d["number"] == 15
        assert d["result"] == "FizzBuzz"
        assert d["matched_rules"] == ["FizzRule", "BuzzRule"]
        assert "integrity_hash" in d

    def test_snapshot_is_frozen(self):
        """Snapshots are frozen dataclasses — immutability is non-negotiable."""
        snap = _make_snapshot(number=3, result="Fizz")
        with pytest.raises(AttributeError):
            snap.number = 42  # type: ignore

    def test_different_inputs_produce_different_hashes(self):
        """Two different evaluations must produce different integrity hashes."""
        snap_a = _make_snapshot(number=3, result="Fizz")
        snap_b = _make_snapshot(number=5, result="Buzz")
        assert snap_a.integrity_hash != snap_b.integrity_hash

    def test_same_inputs_produce_same_hash(self):
        """Identical inputs must produce identical integrity hashes."""
        hash_a = EvaluationSnapshot.compute_hash(
            sequence=0, number=3, result="Fizz",
            matched_rules=("FizzRule",), latency_ms=0.1,
            metadata={}, session_id="s",
        )
        hash_b = EvaluationSnapshot.compute_hash(
            sequence=0, number=3, result="Fizz",
            matched_rules=("FizzRule",), latency_ms=0.1,
            metadata={}, session_id="s",
        )
        assert hash_a == hash_b

    def test_snapshot_metadata_is_deep_copied(self):
        """Snapshot metadata should be a deep copy, not a reference."""
        original = {"key": "value"}
        snap = _make_snapshot(metadata=original)
        original["key"] = "mutated"
        assert snap.metadata["key"] == "value"

    def test_snapshot_timestamp_is_populated(self):
        """Snapshots should have a non-empty ISO timestamp."""
        snap = _make_snapshot()
        assert snap.timestamp
        assert "T" in snap.timestamp  # ISO format


# ============================================================
# Timeline Tests
# ============================================================


class TestTimeline:
    """Tests for the ordered, append-only snapshot collection."""

    def test_empty_timeline(self):
        """A new timeline should be empty and lonely."""
        tl = Timeline()
        assert tl.is_empty
        assert tl.length == 0

    def test_append_and_retrieve(self):
        """Appended snapshots should be retrievable by sequence."""
        tl = Timeline()
        snap = _make_snapshot(sequence=0, number=1, result="1")
        tl.append(snap)
        assert tl.length == 1
        assert tl.get(0).number == 1

    def test_get_by_index(self):
        """Snapshots should be retrievable by position index."""
        tl = _make_fizzbuzz_timeline(5)
        snap = tl.get_by_index(2)
        assert snap.number == 3
        assert snap.result == "Fizz"

    def test_first_and_last_sequence(self):
        """First/last sequence should track the timeline bounds."""
        tl = _make_fizzbuzz_timeline(10)
        assert tl.first_sequence == 0
        assert tl.last_sequence == 9

    def test_empty_timeline_raises_on_get(self):
        """Accessing an empty timeline should raise TimelineEmptyError."""
        tl = Timeline()
        with pytest.raises(TimelineEmptyError):
            tl.get(0)

    def test_out_of_bounds_raises_navigation_error(self):
        """Accessing a non-existent sequence should raise TimelineNavigationError."""
        tl = _make_fizzbuzz_timeline(5)
        with pytest.raises(TimelineNavigationError):
            tl.get(999)

    def test_max_capacity_eviction(self):
        """When capacity is reached, oldest snapshots should be evicted."""
        tl = Timeline(max_snapshots=5)
        for i in range(10):
            tl.append(_make_snapshot(sequence=i, number=i + 1, result=str(i + 1)))
        assert tl.length == 5
        assert tl.first_sequence == 5
        assert tl.last_sequence == 9

    def test_all_snapshots_returns_copy(self):
        """all_snapshots() should return a list, not a reference."""
        tl = _make_fizzbuzz_timeline(3)
        snaps = tl.all_snapshots()
        assert len(snaps) == 3
        snaps.clear()
        assert tl.length == 3  # original unaffected

    def test_slice(self):
        """Slicing should return snapshots in the given range."""
        tl = _make_fizzbuzz_timeline(10)
        sliced = tl.slice(2, 5)
        assert len(sliced) == 4
        assert sliced[0].sequence == 2
        assert sliced[-1].sequence == 5

    def test_anomaly_marking(self):
        """Anomalies should be trackable by sequence number."""
        tl = _make_fizzbuzz_timeline(5)
        tl.mark_anomaly(2)
        tl.mark_anomaly(4)
        assert 2 in tl.anomalies
        assert 4 in tl.anomalies
        assert len(tl.anomalies) == 2

    def test_next_sequence_increments(self):
        """next_sequence should track the next expected sequence number."""
        tl = Timeline()
        assert tl.next_sequence == 0
        tl.append(_make_snapshot(sequence=0))
        assert tl.next_sequence == 1
        tl.append(_make_snapshot(sequence=1))
        assert tl.next_sequence == 2

    def test_empty_timeline_properties_raise(self):
        """first_sequence and last_sequence should raise on empty timeline."""
        tl = Timeline()
        with pytest.raises(TimelineEmptyError):
            _ = tl.first_sequence
        with pytest.raises(TimelineEmptyError):
            _ = tl.last_sequence

    def test_get_by_index_out_of_bounds(self):
        """get_by_index should raise on invalid index."""
        tl = _make_fizzbuzz_timeline(3)
        with pytest.raises(TimelineNavigationError):
            tl.get_by_index(99)
        with pytest.raises(TimelineNavigationError):
            tl.get_by_index(-1)


# ============================================================
# ConditionalBreakpoint Tests
# ============================================================


class TestConditionalBreakpoint:
    """Tests for compiled expression-based breakpoints."""

    def test_simple_result_match(self):
        """Breakpoint should fire when result matches."""
        bp = ConditionalBreakpoint("result == 'FizzBuzz'")
        snap_hit = _make_snapshot(number=15, result="FizzBuzz")
        snap_miss = _make_snapshot(number=1, result="1")
        assert bp.evaluate(snap_hit) is True
        assert bp.evaluate(snap_miss) is False

    def test_number_condition(self):
        """Breakpoint should support numeric conditions."""
        bp = ConditionalBreakpoint("number > 10")
        assert bp.evaluate(_make_snapshot(number=11)) is True
        assert bp.evaluate(_make_snapshot(number=5)) is False

    def test_latency_condition(self):
        """Breakpoint should support latency threshold conditions."""
        bp = ConditionalBreakpoint("latency > 1.0")
        assert bp.evaluate(_make_snapshot(latency_ms=5.0)) is True
        assert bp.evaluate(_make_snapshot(latency_ms=0.1)) is False

    def test_compound_condition(self):
        """Breakpoint should support compound boolean expressions."""
        bp = ConditionalBreakpoint("number % 3 == 0 and result == 'Fizz'")
        assert bp.evaluate(_make_snapshot(number=3, result="Fizz")) is True
        assert bp.evaluate(_make_snapshot(number=6, result="Fizz")) is True
        assert bp.evaluate(_make_snapshot(number=5, result="Buzz")) is False

    def test_invalid_syntax_raises(self):
        """Invalid expression syntax should raise BreakpointSyntaxError."""
        with pytest.raises(BreakpointSyntaxError):
            ConditionalBreakpoint("result ==== 'Fizz'")

    def test_runtime_error_returns_false(self):
        """Runtime errors in evaluation should return False, not crash."""
        bp = ConditionalBreakpoint("undefined_var == 42")
        assert bp.evaluate(_make_snapshot()) is False

    def test_expression_property(self):
        """The expression property should return the original string."""
        bp = ConditionalBreakpoint("number == 42")
        assert bp.expression == "number == 42"

    def test_repr(self):
        """repr should include the expression."""
        bp = ConditionalBreakpoint("result == 'Fizz'")
        assert "result == 'Fizz'" in repr(bp)

    def test_builtins_restricted(self):
        """Breakpoints should not have access to builtins like __import__."""
        bp = ConditionalBreakpoint("__import__('os')")
        # Should not crash, just return False
        assert bp.evaluate(_make_snapshot()) is False


# ============================================================
# TimelineNavigator Tests
# ============================================================


class TestTimelineNavigator:
    """Tests for bidirectional timeline cursor navigation."""

    def test_step_forward_from_start(self):
        """First step_forward should land on the first snapshot."""
        tl = _make_fizzbuzz_timeline(5)
        nav = TimelineNavigator(tl)
        snap = nav.step_forward()
        assert snap is not None
        assert snap.sequence == 0
        assert snap.number == 1

    def test_step_forward_sequential(self):
        """Sequential step_forward should advance through the timeline."""
        tl = _make_fizzbuzz_timeline(5)
        nav = TimelineNavigator(tl)
        for i in range(5):
            snap = nav.step_forward()
            assert snap is not None
            assert snap.sequence == i
        # One more should return None (at end)
        assert nav.step_forward() is None

    def test_step_back_from_end(self):
        """First step_back should land on the last snapshot."""
        tl = _make_fizzbuzz_timeline(5)
        nav = TimelineNavigator(tl)
        snap = nav.step_back()
        assert snap is not None
        assert snap.sequence == 4

    def test_step_back_to_start(self):
        """Stepping back past the start should return None."""
        tl = _make_fizzbuzz_timeline(3)
        nav = TimelineNavigator(tl)
        nav.goto(0)
        assert nav.step_back() is None

    def test_goto(self):
        """goto should jump directly to a specific sequence."""
        tl = _make_fizzbuzz_timeline(10)
        nav = TimelineNavigator(tl)
        snap = nav.goto(5)
        assert snap.sequence == 5
        assert snap.number == 6

    def test_goto_invalid_raises(self):
        """goto to invalid sequence should raise TimelineNavigationError."""
        tl = _make_fizzbuzz_timeline(5)
        nav = TimelineNavigator(tl)
        with pytest.raises(TimelineNavigationError):
            nav.goto(999)

    def test_current_when_unpositioned_raises(self):
        """current() should raise when cursor is not positioned."""
        tl = _make_fizzbuzz_timeline(5)
        nav = TimelineNavigator(tl)
        with pytest.raises(TimelineNavigationError):
            nav.current()

    def test_current_after_step(self):
        """current() should return the snapshot at the cursor."""
        tl = _make_fizzbuzz_timeline(5)
        nav = TimelineNavigator(tl)
        nav.step_forward()
        snap = nav.current()
        assert snap.sequence == 0

    def test_continue_to_breakpoint(self):
        """continue_to_breakpoint should stop at the first matching snapshot."""
        tl = _make_fizzbuzz_timeline(15)
        nav = TimelineNavigator(tl)
        bp = ConditionalBreakpoint("result == 'FizzBuzz'")
        snap = nav.continue_to_breakpoint([bp])
        assert snap is not None
        assert snap.number == 15
        assert snap.result == "FizzBuzz"

    def test_continue_to_breakpoint_no_match(self):
        """continue_to_breakpoint should return None if no match."""
        tl = _make_fizzbuzz_timeline(15)
        nav = TimelineNavigator(tl)
        bp = ConditionalBreakpoint("result == 'Wuzz'")
        assert nav.continue_to_breakpoint([bp]) is None

    def test_reverse_continue(self):
        """reverse_continue should find the last matching snapshot backwards."""
        tl = _make_fizzbuzz_timeline(15)
        nav = TimelineNavigator(tl)
        bp = ConditionalBreakpoint("result == 'Fizz'")
        snap = nav.reverse_continue([bp])
        assert snap is not None
        assert snap.result == "Fizz"
        # Should be the last Fizz before seq 14 (FizzBuzz)
        assert snap.number == 12

    def test_at_start_and_at_end(self):
        """at_start and at_end should reflect cursor position."""
        tl = _make_fizzbuzz_timeline(5)
        nav = TimelineNavigator(tl)
        nav.goto(0)
        assert nav.at_start is True
        assert nav.at_end is False
        nav.goto(4)
        assert nav.at_start is False
        assert nav.at_end is True

    def test_reset(self):
        """reset should return cursor to unpositioned state."""
        tl = _make_fizzbuzz_timeline(5)
        nav = TimelineNavigator(tl)
        nav.goto(3)
        nav.reset()
        assert nav.cursor == -1

    def test_empty_timeline_step_raises(self):
        """Navigation on empty timeline should raise TimelineEmptyError."""
        tl = Timeline()
        nav = TimelineNavigator(tl)
        with pytest.raises(TimelineEmptyError):
            nav.step_forward()
        with pytest.raises(TimelineEmptyError):
            nav.step_back()

    def test_continue_with_no_breakpoints(self):
        """continue_to_breakpoint with empty list should return None."""
        tl = _make_fizzbuzz_timeline(5)
        nav = TimelineNavigator(tl)
        assert nav.continue_to_breakpoint([]) is None

    def test_reverse_continue_with_no_breakpoints(self):
        """reverse_continue with empty list should return None."""
        tl = _make_fizzbuzz_timeline(5)
        nav = TimelineNavigator(tl)
        assert nav.reverse_continue([]) is None


# ============================================================
# DiffViewer Tests
# ============================================================


class TestDiffViewer:
    """Tests for snapshot field-by-field comparison."""

    def test_identical_snapshots_no_changes(self):
        """Diffing identical snapshots should show no changes."""
        snap = _make_snapshot(number=3, result="Fizz")
        diffs = DiffViewer.diff(snap, snap)
        assert all(not d.changed for d in diffs)

    def test_different_results_detected(self):
        """Diffing snapshots with different results should flag the change."""
        snap_a = _make_snapshot(sequence=0, number=3, result="Fizz")
        snap_b = _make_snapshot(sequence=1, number=5, result="Buzz")
        diffs = DiffViewer.diff(snap_a, snap_b)
        changed_fields = {d.field_name for d in diffs if d.changed}
        assert "number" in changed_fields
        assert "result" in changed_fields
        assert "sequence" in changed_fields

    def test_has_changes(self):
        """has_changes should return True when fields differ."""
        snap_a = _make_snapshot(number=1, result="1")
        snap_b = _make_snapshot(number=2, result="2")
        assert DiffViewer.has_changes(snap_a, snap_b) is True

    def test_no_changes(self):
        """has_changes should return False for identical snapshots."""
        snap = _make_snapshot(number=3, result="Fizz")
        assert DiffViewer.has_changes(snap, snap) is False

    def test_render_ascii_contains_header(self):
        """ASCII diff should contain the TIME-TRAVEL DIFF header."""
        snap_a = _make_snapshot(sequence=0, number=3, result="Fizz")
        snap_b = _make_snapshot(sequence=1, number=5, result="Buzz")
        output = DiffViewer.render_ascii(snap_a, snap_b, width=60)
        assert "TIME-TRAVEL DIFF" in output
        assert "Seq #0" in output
        assert "Seq #1" in output

    def test_diff_field_indicators(self):
        """Changed fields should have [~] indicator, unchanged [=]."""
        snap_a = _make_snapshot(sequence=0, number=3, result="Fizz", session_id="s")
        snap_b = _make_snapshot(sequence=0, number=3, result="Buzz", session_id="s")
        diffs = DiffViewer.diff(snap_a, snap_b)
        result_diff = next(d for d in diffs if d.field_name == "result")
        assert result_diff.changed is True
        assert result_diff.indicator == "[~]"
        number_diff = next(d for d in diffs if d.field_name == "number")
        assert number_diff.changed is False
        assert number_diff.indicator == "[=]"


# ============================================================
# TimelineUI Tests
# ============================================================


class TestTimelineUI:
    """Tests for the ASCII timeline strip renderer."""

    def test_empty_timeline_strip(self):
        """Empty timeline should render a placeholder strip."""
        tl = Timeline()
        strip = TimelineUI.render_strip(tl, width=40)
        assert "empty timeline" in strip

    def test_strip_contains_cursor_marker(self):
        """The timeline strip should show '>' at the cursor position."""
        tl = _make_fizzbuzz_timeline(10)
        strip = TimelineUI.render_strip(tl, cursor=5, width=40)
        assert ">" in strip

    def test_strip_contains_anomaly_marker(self):
        """The timeline strip should show '!' for anomalies."""
        tl = _make_fizzbuzz_timeline(10)
        tl.mark_anomaly(5)
        strip = TimelineUI.render_strip(tl, width=40)
        assert "!" in strip

    def test_strip_contains_breakpoint_marker(self):
        """The timeline strip should show 'B' for breakpoints."""
        tl = _make_fizzbuzz_timeline(10)
        strip = TimelineUI.render_strip(tl, breakpoint_sequences={3}, width=40)
        assert "B" in strip

    def test_dashboard_contains_title(self):
        """The full dashboard should contain the title header."""
        tl = _make_fizzbuzz_timeline(5)
        nav = TimelineNavigator(tl)
        nav.step_forward()
        output = TimelineUI.render_dashboard(tl, nav, width=60)
        assert "TIME-TRAVEL DEBUGGER DASHBOARD" in output

    def test_dashboard_shows_snapshot_count(self):
        """Dashboard should display the number of snapshots."""
        tl = _make_fizzbuzz_timeline(10)
        nav = TimelineNavigator(tl)
        output = TimelineUI.render_dashboard(tl, nav, width=60)
        assert "10" in output


# ============================================================
# AnomalyDetector Tests
# ============================================================


class TestAnomalyDetector:
    """Tests for temporal anomaly detection."""

    def test_no_anomaly_for_consistent_results(self):
        """Consistent results should not trigger anomalies."""
        detector = AnomalyDetector()
        snap = _make_snapshot(number=3, result="Fizz")
        assert detector.check(snap) is None

    def test_anomaly_for_inconsistent_result(self):
        """Different results for the same number should trigger an anomaly."""
        detector = AnomalyDetector()
        snap1 = _make_snapshot(number=3, result="Fizz")
        snap2 = _make_snapshot(number=3, result="Buzz")
        detector.check(snap1)
        anomaly = detector.check(snap2)
        assert anomaly is not None
        assert "anomaly" in anomaly.lower()

    def test_reset_clears_memory(self):
        """reset() should clear the detector's memory."""
        detector = AnomalyDetector()
        detector.check(_make_snapshot(number=3, result="Fizz"))
        detector.reset()
        # After reset, same number with different result should not trigger
        anomaly = detector.check(_make_snapshot(number=3, result="Buzz"))
        assert anomaly is None


# ============================================================
# TimeTravelMiddleware Tests
# ============================================================


class TestTimeTravelMiddleware:
    """Tests for the middleware that captures snapshots into the timeline."""

    def test_middleware_captures_snapshot(self):
        """Middleware should capture a snapshot after processing."""
        timeline = Timeline()
        mw = TimeTravelMiddleware(timeline)

        ctx = ProcessingContext(number=3, session_id="test")
        result_obj = FizzBuzzResult(number=3, output="Fizz")
        ctx.results.append(result_obj)

        def next_handler(c: ProcessingContext) -> ProcessingContext:
            return c

        mw.process(ctx, next_handler)
        assert timeline.length == 1
        snap = timeline.get(0)
        assert snap.number == 3
        assert snap.result == "Fizz"

    def test_middleware_priority_is_negative_five(self):
        """TimeTravelMiddleware should have priority -5."""
        mw = TimeTravelMiddleware(Timeline())
        assert mw.get_priority() == -5
        assert mw.get_name() == "TimeTravelMiddleware"

    def test_middleware_passes_result_through(self):
        """Middleware should not modify the pipeline result."""
        timeline = Timeline()
        mw = TimeTravelMiddleware(timeline)

        ctx = ProcessingContext(number=5, session_id="test")
        result_obj = FizzBuzzResult(number=5, output="Buzz")
        ctx.results.append(result_obj)

        def next_handler(c: ProcessingContext) -> ProcessingContext:
            return c

        result = mw.process(ctx, next_handler)
        assert result.results[-1].output == "Buzz"

    def test_middleware_emits_event(self, event_bus):
        """Middleware should publish TIME_TRAVEL_SNAPSHOT_CAPTURED events."""
        timeline = Timeline()
        mw = TimeTravelMiddleware(timeline, event_bus=event_bus)

        ctx = ProcessingContext(number=3, session_id="test")
        ctx.results.append(FizzBuzzResult(number=3, output="Fizz"))

        mw.process(ctx, lambda c: c)

        event_bus.publish.assert_called()
        event = event_bus.publish.call_args[0][0]
        assert event.event_type == EventType.TIME_TRAVEL_SNAPSHOT_CAPTURED

    def test_middleware_detects_anomalies(self, event_bus):
        """Middleware should detect and mark anomalies in the timeline."""
        timeline = Timeline()
        mw = TimeTravelMiddleware(
            timeline, event_bus=event_bus, enable_anomaly_detection=True
        )

        # First evaluation of number 3 => Fizz
        ctx1 = ProcessingContext(number=3, session_id="test")
        ctx1.results.append(FizzBuzzResult(number=3, output="Fizz"))
        mw.process(ctx1, lambda c: c)

        # Second evaluation of number 3 => Buzz (anomaly!)
        ctx2 = ProcessingContext(number=3, session_id="test")
        ctx2.results.append(FizzBuzzResult(number=3, output="Buzz"))
        mw.process(ctx2, lambda c: c)

        assert len(timeline.anomalies) == 1

    def test_middleware_handles_empty_results(self):
        """Middleware should handle contexts with no results gracefully."""
        timeline = Timeline()
        mw = TimeTravelMiddleware(timeline)

        ctx = ProcessingContext(number=1, session_id="test")
        # No results appended

        mw.process(ctx, lambda c: c)
        assert timeline.length == 1
        snap = timeline.get(0)
        assert snap.result == ""

    def test_middleware_timeline_property(self):
        """The timeline property should expose the underlying timeline."""
        timeline = Timeline()
        mw = TimeTravelMiddleware(timeline)
        assert mw.timeline is timeline


# ============================================================
# Factory Function Tests
# ============================================================


class TestFactoryFunction:
    """Tests for the create_time_travel_subsystem factory."""

    def test_creates_all_components(self):
        """Factory should return (Timeline, Middleware, Navigator) tuple."""
        tl, mw, nav = create_time_travel_subsystem()
        assert isinstance(tl, Timeline)
        assert isinstance(mw, TimeTravelMiddleware)
        assert isinstance(nav, TimelineNavigator)

    def test_respects_max_snapshots(self):
        """Factory should pass max_snapshots to the Timeline."""
        tl, _, _ = create_time_travel_subsystem(max_snapshots=50)
        # Add more than 50 snapshots
        for i in range(60):
            tl.append(_make_snapshot(sequence=i))
        assert tl.length == 50


# ============================================================
# Summary Renderer Tests
# ============================================================


class TestRenderSummary:
    """Tests for the post-execution summary renderer."""

    def test_summary_with_data(self):
        """Summary should contain key statistics."""
        tl = _make_fizzbuzz_timeline(15)
        nav = TimelineNavigator(tl)
        output = render_time_travel_summary(tl, nav, width=60)
        assert "15" in output  # snapshot count
        assert "SESSION SUMMARY" in output

    def test_summary_empty_timeline(self):
        """Summary should handle empty timelines gracefully."""
        tl = Timeline()
        nav = TimelineNavigator(tl)
        output = render_time_travel_summary(tl, nav, width=60)
        assert "No snapshots captured" in output

    def test_summary_with_breakpoints(self):
        """Summary should display breakpoint information."""
        tl = _make_fizzbuzz_timeline(5)
        nav = TimelineNavigator(tl)
        bps = [ConditionalBreakpoint("result == 'Fizz'")]
        output = render_time_travel_summary(tl, nav, breakpoints=bps, width=60)
        assert "Breakpoint" in output


# ============================================================
# Exception Tests
# ============================================================


class TestExceptions:
    """Tests for the Time-Travel Debugger exception hierarchy."""

    def test_time_travel_error_base(self):
        """TimeTravelError should be the base for all TT exceptions."""
        err = TimeTravelError("test", error_code="EFP-TT00")
        assert "EFP-TT00" in str(err)

    def test_timeline_empty_error(self):
        """TimelineEmptyError should have error code EFP-TT01."""
        err = TimelineEmptyError()
        assert err.error_code == "EFP-TT01"

    def test_snapshot_integrity_error(self):
        """SnapshotIntegrityError should include hash details."""
        err = SnapshotIntegrityError(42, "aaa", "bbb")
        assert "42" in str(err)
        assert err.error_code == "EFP-TT02"

    def test_breakpoint_syntax_error(self):
        """BreakpointSyntaxError should include the expression."""
        err = BreakpointSyntaxError("bad ==== expr", "invalid syntax")
        assert "bad ==== expr" in str(err)
        assert err.error_code == "EFP-TT03"

    def test_timeline_navigation_error(self):
        """TimelineNavigationError should include the operation."""
        err = TimelineNavigationError("goto", "out of bounds")
        assert "goto" in str(err)
        assert err.error_code == "EFP-TT04"


# ============================================================
# EventType Tests
# ============================================================


class TestEventTypes:
    """Tests for Time-Travel Debugger event type entries."""

    def test_event_types_exist(self):
        """All TIME_TRAVEL_* event types should be defined."""
        assert EventType.TIME_TRAVEL_SNAPSHOT_CAPTURED
        assert EventType.TIME_TRAVEL_NAVIGATION
        assert EventType.TIME_TRAVEL_BREAKPOINT_HIT
        assert EventType.TIME_TRAVEL_ANOMALY_DETECTED
        assert EventType.TIME_TRAVEL_DASHBOARD_RENDERED


# ============================================================
# Utility Tests
# ============================================================


class TestUtilities:
    """Tests for utility functions."""

    def test_truncate_short_string(self):
        """Short strings should not be truncated."""
        assert _truncate("hello", 10) == "hello"

    def test_truncate_long_string(self):
        """Long strings should be truncated with ellipsis."""
        result = _truncate("a very long string indeed", 10)
        assert len(result) == 10
        assert result.endswith("...")

    def test_truncate_exact_length(self):
        """Strings at exact max length should not be truncated."""
        assert _truncate("12345", 5) == "12345"
