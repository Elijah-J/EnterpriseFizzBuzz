"""
Enterprise FizzBuzz Platform - Event Sourcing / CQRS Test Suite

Comprehensive tests for the Event Sourcing and CQRS subsystem.
Because an append-only audit log of modulo arithmetic operations
deserves nothing less than exhaustive test coverage.
"""

from __future__ import annotations

import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import pytest

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from config import ConfigurationManager, _SingletonMeta
from event_sourcing import (
    Command,
    CommandBus,
    CurrentResultsProjection,
    DivisibilityCheckedEvent,
    DomainEvent,
    EvaluateNumberCommand,
    EvaluateNumberCommandHandler,
    EvaluationCompletedEvent,
    EventCountProjection,
    EventSourcingMiddleware,
    EventSourcingSummary,
    EventSourcingSystem,
    EventStore,
    EventUpcaster,
    GetCurrentResultsQuery,
    GetEventCountQuery,
    GetStatisticsQuery,
    GetTemporalStateQuery,
    LabelAssignedEvent,
    NumberReceivedEvent,
    Query,
    QueryBus,
    ReplayEventsCommand,
    RuleMatchedEvent,
    SnapshotStore,
    SnapshotTakenEvent,
    StatisticsProjection,
    TemporalQueryEngine,
)
from exceptions import (
    CommandHandlerNotFoundError,
    CommandValidationError,
    EventSequenceError,
    EventVersionConflictError,
    ProjectionError,
    QueryHandlerNotFoundError,
    SnapshotCorruptionError,
    TemporalQueryError,
)
from models import (
    EventType,
    FizzBuzzResult,
    ProcessingContext,
    RuleDefinition,
    RuleMatch,
)


# ============================================================
# Fixtures
# ============================================================


@pytest.fixture(autouse=True)
def reset_singletons():
    """Reset all singletons between tests."""
    _SingletonMeta.reset()
    yield


@pytest.fixture
def event_store():
    """Create a fresh event store."""
    return EventStore()


@pytest.fixture
def snapshot_store():
    """Create a fresh snapshot store."""
    return SnapshotStore(interval=5)


@pytest.fixture
def upcaster():
    """Create an event upcaster with default registrations."""
    return EventUpcaster()


@pytest.fixture
def command_bus():
    """Create a fresh command bus."""
    return CommandBus()


@pytest.fixture
def query_bus():
    """Create a fresh query bus."""
    return QueryBus()


@pytest.fixture
def results_projection():
    """Create a fresh results projection."""
    return CurrentResultsProjection()


@pytest.fixture
def stats_projection():
    """Create a fresh statistics projection."""
    return StatisticsProjection()


@pytest.fixture
def event_count_projection():
    """Create a fresh event count projection."""
    return EventCountProjection()


@pytest.fixture
def es_system():
    """Create a fully wired Event Sourcing system."""
    return EventSourcingSystem(snapshot_interval=5)


def _make_fizz_result(number: int) -> FizzBuzzResult:
    """Helper to create a Fizz result."""
    return FizzBuzzResult(
        number=number,
        output="Fizz",
        matched_rules=[
            RuleMatch(
                rule=RuleDefinition(name="FizzRule", divisor=3, label="Fizz", priority=1),
                number=number,
            )
        ],
        processing_time_ns=1000,
    )


def _make_buzz_result(number: int) -> FizzBuzzResult:
    """Helper to create a Buzz result."""
    return FizzBuzzResult(
        number=number,
        output="Buzz",
        matched_rules=[
            RuleMatch(
                rule=RuleDefinition(name="BuzzRule", divisor=5, label="Buzz", priority=2),
                number=number,
            )
        ],
        processing_time_ns=1000,
    )


def _make_fizzbuzz_result(number: int) -> FizzBuzzResult:
    """Helper to create a FizzBuzz result."""
    return FizzBuzzResult(
        number=number,
        output="FizzBuzz",
        matched_rules=[
            RuleMatch(
                rule=RuleDefinition(name="FizzRule", divisor=3, label="Fizz", priority=1),
                number=number,
            ),
            RuleMatch(
                rule=RuleDefinition(name="BuzzRule", divisor=5, label="Buzz", priority=2),
                number=number,
            ),
        ],
        processing_time_ns=1000,
    )


def _make_plain_result(number: int) -> FizzBuzzResult:
    """Helper to create a plain number result."""
    return FizzBuzzResult(
        number=number,
        output=str(number),
        matched_rules=[],
        processing_time_ns=1000,
    )


# ============================================================
# DomainEvent Tests
# ============================================================


class TestDomainEvent:
    def test_domain_event_is_frozen(self):
        event = DomainEvent()
        with pytest.raises(AttributeError):
            event.version = 99

    def test_domain_event_has_unique_id(self):
        e1 = DomainEvent()
        e2 = DomainEvent()
        assert e1.event_id != e2.event_id

    def test_domain_event_has_timestamp(self):
        event = DomainEvent()
        assert event.timestamp is not None
        assert event.timestamp.tzinfo is not None

    def test_domain_event_default_version(self):
        event = DomainEvent()
        assert event.version == 1

    def test_number_received_event(self):
        event = NumberReceivedEvent(number=42, session_id="test-session")
        assert event.number == 42
        assert event.session_id == "test-session"

    def test_divisibility_checked_event(self):
        event = DivisibilityCheckedEvent(
            number=15, divisor=3, is_divisible=True, rule_name="FizzRule"
        )
        assert event.number == 15
        assert event.divisor == 3
        assert event.is_divisible is True

    def test_rule_matched_event(self):
        event = RuleMatchedEvent(number=15, rule_name="FizzRule", label="Fizz")
        assert event.label == "Fizz"

    def test_label_assigned_event(self):
        event = LabelAssignedEvent(number=15, label="FizzBuzz", matched_rule_count=2)
        assert event.matched_rule_count == 2

    def test_evaluation_completed_event(self):
        event = EvaluationCompletedEvent(
            number=15, output="FizzBuzz", processing_time_ns=5000
        )
        assert event.output == "FizzBuzz"
        assert event.processing_time_ns == 5000

    def test_snapshot_taken_event(self):
        event = SnapshotTakenEvent(snapshot_version=42)
        assert event.snapshot_version == 42

    def test_all_domain_events_are_frozen(self):
        """Verify immutability of all concrete event types."""
        events = [
            NumberReceivedEvent(number=1),
            DivisibilityCheckedEvent(number=1, divisor=3),
            RuleMatchedEvent(number=3, rule_name="Fizz", label="Fizz"),
            LabelAssignedEvent(number=3, label="Fizz"),
            EvaluationCompletedEvent(number=3, output="Fizz"),
            SnapshotTakenEvent(snapshot_version=1),
        ]
        for event in events:
            with pytest.raises(AttributeError):
                event.sequence_number = 999


# ============================================================
# EventStore Tests
# ============================================================


class TestEventStore:
    def test_empty_store(self, event_store):
        assert event_store.get_event_count() == 0
        assert event_store.get_latest_sequence() == 0
        assert event_store.get_events() == []

    def test_append_assigns_sequence_number(self, event_store):
        event = NumberReceivedEvent(number=1)
        stored = event_store.append(event)
        assert stored.sequence_number == 1

    def test_sequence_numbers_increment(self, event_store):
        e1 = event_store.append(NumberReceivedEvent(number=1))
        e2 = event_store.append(NumberReceivedEvent(number=2))
        e3 = event_store.append(NumberReceivedEvent(number=3))
        assert e1.sequence_number == 1
        assert e2.sequence_number == 2
        assert e3.sequence_number == 3

    def test_get_events_returns_all(self, event_store):
        for i in range(5):
            event_store.append(NumberReceivedEvent(number=i))
        events = event_store.get_events()
        assert len(events) == 5

    def test_get_events_by_aggregate_id(self, event_store):
        event_store.append(NumberReceivedEvent(number=1, aggregate_id="session-1"))
        event_store.append(NumberReceivedEvent(number=2, aggregate_id="session-2"))
        event_store.append(NumberReceivedEvent(number=3, aggregate_id="session-1"))

        session1_events = event_store.get_events(aggregate_id="session-1")
        assert len(session1_events) == 2

    def test_get_events_after_sequence(self, event_store):
        for i in range(5):
            event_store.append(NumberReceivedEvent(number=i))

        events = event_store.get_events(after_sequence=3)
        assert len(events) == 2
        assert events[0].sequence_number == 4
        assert events[1].sequence_number == 5

    def test_get_events_by_type(self, event_store):
        event_store.append(NumberReceivedEvent(number=1))
        event_store.append(EvaluationCompletedEvent(number=1, output="1"))
        event_store.append(NumberReceivedEvent(number=2))

        received = event_store.get_events_by_type(NumberReceivedEvent)
        assert len(received) == 2

        completed = event_store.get_events_by_type(EvaluationCompletedEvent)
        assert len(completed) == 1

    def test_get_event_count(self, event_store):
        for i in range(3):
            event_store.append(NumberReceivedEvent(number=i))
        assert event_store.get_event_count() == 3

    def test_get_latest_sequence(self, event_store):
        event_store.append(NumberReceivedEvent(number=1))
        event_store.append(NumberReceivedEvent(number=2))
        assert event_store.get_latest_sequence() == 2

    def test_subscribe_notifies_on_append(self, event_store):
        received = []
        event_store.subscribe(lambda e: received.append(e))

        event_store.append(NumberReceivedEvent(number=42))
        assert len(received) == 1
        assert isinstance(received[0], NumberReceivedEvent)

    def test_clear(self, event_store):
        event_store.append(NumberReceivedEvent(number=1))
        event_store.clear()
        assert event_store.get_event_count() == 0
        assert event_store.get_latest_sequence() == 0

    def test_subscriber_error_does_not_break_append(self, event_store):
        """Subscriber errors should be logged but not propagated."""
        def bad_subscriber(e):
            raise RuntimeError("subscriber boom")

        event_store.subscribe(bad_subscriber)
        # Should not raise
        stored = event_store.append(NumberReceivedEvent(number=1))
        assert stored.sequence_number == 1


# ============================================================
# SnapshotStore Tests
# ============================================================


class TestSnapshotStore:
    def test_empty_store(self, snapshot_store):
        assert snapshot_store.get_latest_snapshot("test") is None
        assert snapshot_store.get_snapshot_count() == 0

    def test_save_and_retrieve_snapshot(self, snapshot_store):
        state = {"total_evaluations": 5, "fizz_count": 2}
        snapshot_store.save_snapshot("test-agg", state, version=10)

        snapshot = snapshot_store.get_latest_snapshot("test-agg")
        assert snapshot is not None
        assert snapshot["state"]["total_evaluations"] == 5
        assert snapshot["version"] == 10

    def test_latest_snapshot_is_most_recent(self, snapshot_store):
        snapshot_store.save_snapshot("agg", {"count": 1}, version=1)
        snapshot_store.save_snapshot("agg", {"count": 2}, version=2)
        snapshot_store.save_snapshot("agg", {"count": 3}, version=3)

        latest = snapshot_store.get_latest_snapshot("agg")
        assert latest["state"]["count"] == 3
        assert latest["version"] == 3

    def test_snapshot_count(self, snapshot_store):
        snapshot_store.save_snapshot("agg1", {}, version=1)
        snapshot_store.save_snapshot("agg1", {}, version=2)
        snapshot_store.save_snapshot("agg2", {}, version=1)

        assert snapshot_store.get_snapshot_count() == 3
        assert snapshot_store.get_snapshot_count("agg1") == 2
        assert snapshot_store.get_snapshot_count("agg2") == 1

    def test_should_snapshot(self, snapshot_store):
        # interval is 5
        assert snapshot_store.should_snapshot(0) is False
        assert snapshot_store.should_snapshot(4) is False
        assert snapshot_store.should_snapshot(5) is True
        assert snapshot_store.should_snapshot(10) is True

    def test_snapshot_is_deep_copy(self, snapshot_store):
        state = {"items": [1, 2, 3]}
        snapshot_store.save_snapshot("agg", state, version=1)

        # Modify original
        state["items"].append(4)

        # Snapshot should be unaffected
        snapshot = snapshot_store.get_latest_snapshot("agg")
        assert len(snapshot["state"]["items"]) == 3

    def test_clear(self, snapshot_store):
        snapshot_store.save_snapshot("agg", {}, version=1)
        snapshot_store.clear()
        assert snapshot_store.get_snapshot_count() == 0


# ============================================================
# EventUpcaster Tests
# ============================================================


class TestEventUpcaster:
    def test_default_upcaster_registered(self, upcaster):
        registered = upcaster.get_registered_upcasters()
        assert "NumberReceivedEvent" in registered
        assert (1, 2) in registered["NumberReceivedEvent"]

    def test_upcast_v1_to_v2(self, upcaster):
        data = {"number": 42, "session_id": "test"}
        result = upcaster.upcast("NumberReceivedEvent", data, from_version=1, to_version=2)
        assert "priority" in result
        assert result["priority"] == "normal"
        assert result["number"] == 42

    def test_upcast_same_version_returns_unchanged(self, upcaster):
        data = {"number": 42}
        result = upcaster.upcast("NumberReceivedEvent", data, from_version=2, to_version=2)
        assert result == data

    def test_upcast_unknown_type_returns_unchanged(self, upcaster):
        data = {"foo": "bar"}
        result = upcaster.upcast("UnknownEvent", data, from_version=1, to_version=5)
        assert result == data

    def test_register_custom_upcaster(self, upcaster):
        upcaster.register(
            "CustomEvent",
            from_version=1,
            to_version=2,
            transform=lambda d: {**d, "new_field": "added"},
        )
        data = {"existing": "value"}
        result = upcaster.upcast("CustomEvent", data, from_version=1, to_version=2)
        assert result["new_field"] == "added"
        assert result["existing"] == "value"

    def test_chained_upcasting(self, upcaster):
        """Test multi-step upcasting v1 -> v2 -> v3."""
        upcaster.register(
            "ChainEvent",
            from_version=1,
            to_version=2,
            transform=lambda d: {**d, "v2_field": True},
        )
        upcaster.register(
            "ChainEvent",
            from_version=2,
            to_version=3,
            transform=lambda d: {**d, "v3_field": True},
        )

        data = {"original": True}
        result = upcaster.upcast("ChainEvent", data, from_version=1, to_version=3)
        assert result["original"] is True
        assert result["v2_field"] is True
        assert result["v3_field"] is True


# ============================================================
# CommandBus Tests
# ============================================================


class TestCommandBus:
    def test_dispatch_to_registered_handler(self, command_bus):
        results = []
        command_bus.register(EvaluateNumberCommand, lambda cmd: results.append(cmd.number))

        command_bus.dispatch(EvaluateNumberCommand(number=42, session_id="test"))
        assert results == [42]

    def test_dispatch_unregistered_raises(self, command_bus):
        with pytest.raises(CommandHandlerNotFoundError):
            command_bus.dispatch(EvaluateNumberCommand(number=1, session_id="test"))

    def test_register_and_dispatch_multiple_types(self, command_bus):
        eval_results = []
        replay_results = []

        command_bus.register(EvaluateNumberCommand, lambda cmd: eval_results.append(cmd.number))
        command_bus.register(ReplayEventsCommand, lambda cmd: replay_results.append("replayed"))

        command_bus.dispatch(EvaluateNumberCommand(number=7, session_id="test"))
        command_bus.dispatch(ReplayEventsCommand())

        assert eval_results == [7]
        assert replay_results == ["replayed"]

    def test_handler_return_value(self, command_bus):
        command_bus.register(EvaluateNumberCommand, lambda cmd: cmd.number * 2)
        result = command_bus.dispatch(EvaluateNumberCommand(number=21, session_id="test"))
        assert result == 42


# ============================================================
# QueryBus Tests
# ============================================================


class TestQueryBus:
    def test_dispatch_to_registered_handler(self, query_bus):
        query_bus.register(GetEventCountQuery, lambda q: 42)
        result = query_bus.dispatch(GetEventCountQuery())
        assert result == 42

    def test_dispatch_unregistered_raises(self, query_bus):
        with pytest.raises(QueryHandlerNotFoundError):
            query_bus.dispatch(GetEventCountQuery())

    def test_multiple_query_types(self, query_bus):
        query_bus.register(GetEventCountQuery, lambda q: 100)
        query_bus.register(GetStatisticsQuery, lambda q: {"fizz": 5})
        query_bus.register(GetCurrentResultsQuery, lambda q: {1: "1", 3: "Fizz"})

        assert query_bus.dispatch(GetEventCountQuery()) == 100
        assert query_bus.dispatch(GetStatisticsQuery()) == {"fizz": 5}
        assert query_bus.dispatch(GetCurrentResultsQuery()) == {1: "1", 3: "Fizz"}


# ============================================================
# Projection Tests
# ============================================================


class TestCurrentResultsProjection:
    def test_empty_projection(self, results_projection):
        assert results_projection.get_results() == {}
        assert results_projection.get_count() == 0

    def test_apply_evaluation_completed(self, results_projection):
        event = EvaluationCompletedEvent(number=3, output="Fizz")
        results_projection.apply(event)
        assert results_projection.get_result(3) == "Fizz"
        assert results_projection.get_count() == 1

    def test_apply_multiple_events(self, results_projection):
        results_projection.apply(EvaluationCompletedEvent(number=1, output="1"))
        results_projection.apply(EvaluationCompletedEvent(number=3, output="Fizz"))
        results_projection.apply(EvaluationCompletedEvent(number=5, output="Buzz"))

        results = results_projection.get_results()
        assert results == {1: "1", 3: "Fizz", 5: "Buzz"}

    def test_ignores_non_evaluation_events(self, results_projection):
        results_projection.apply(NumberReceivedEvent(number=1))
        assert results_projection.get_count() == 0

    def test_clear(self, results_projection):
        results_projection.apply(EvaluationCompletedEvent(number=3, output="Fizz"))
        results_projection.clear()
        assert results_projection.get_count() == 0

    def test_get_results_returns_copy(self, results_projection):
        results_projection.apply(EvaluationCompletedEvent(number=3, output="Fizz"))
        results = results_projection.get_results()
        results.clear()
        assert results_projection.get_count() == 1  # original unaffected


class TestStatisticsProjection:
    def test_empty_projection(self, stats_projection):
        stats = stats_projection.get_statistics()
        assert stats["total_evaluations"] == 0
        assert stats["fizz_count"] == 0

    def test_counts_fizz(self, stats_projection):
        stats_projection.apply(EvaluationCompletedEvent(number=3, output="Fizz"))
        stats_projection.apply(EvaluationCompletedEvent(number=6, output="Fizz"))
        stats = stats_projection.get_statistics()
        assert stats["fizz_count"] == 2
        assert stats["total_evaluations"] == 2

    def test_counts_buzz(self, stats_projection):
        stats_projection.apply(EvaluationCompletedEvent(number=5, output="Buzz"))
        stats = stats_projection.get_statistics()
        assert stats["buzz_count"] == 1

    def test_counts_fizzbuzz(self, stats_projection):
        stats_projection.apply(EvaluationCompletedEvent(number=15, output="FizzBuzz"))
        stats = stats_projection.get_statistics()
        assert stats["fizzbuzz_count"] == 1

    def test_counts_plain(self, stats_projection):
        stats_projection.apply(EvaluationCompletedEvent(number=7, output="7"))
        stats = stats_projection.get_statistics()
        assert stats["plain_count"] == 1

    def test_tracks_processing_time(self, stats_projection):
        stats_projection.apply(
            EvaluationCompletedEvent(number=3, output="Fizz", processing_time_ns=5000)
        )
        stats_projection.apply(
            EvaluationCompletedEvent(number=5, output="Buzz", processing_time_ns=3000)
        )
        stats = stats_projection.get_statistics()
        assert stats["total_processing_ns"] == 8000
        assert stats["avg_processing_ns"] == 4000.0

    def test_clear(self, stats_projection):
        stats_projection.apply(EvaluationCompletedEvent(number=3, output="Fizz"))
        stats_projection.clear()
        stats = stats_projection.get_statistics()
        assert stats["total_evaluations"] == 0


class TestEventCountProjection:
    def test_empty_projection(self, event_count_projection):
        assert event_count_projection.get_total() == 0
        assert event_count_projection.get_counts() == {}

    def test_counts_by_type(self, event_count_projection):
        event_count_projection.apply(NumberReceivedEvent(number=1))
        event_count_projection.apply(NumberReceivedEvent(number=2))
        event_count_projection.apply(EvaluationCompletedEvent(number=1, output="1"))

        counts = event_count_projection.get_counts()
        assert counts["NumberReceivedEvent"] == 2
        assert counts["EvaluationCompletedEvent"] == 1
        assert event_count_projection.get_total() == 3

    def test_clear(self, event_count_projection):
        event_count_projection.apply(NumberReceivedEvent(number=1))
        event_count_projection.clear()
        assert event_count_projection.get_total() == 0


# ============================================================
# TemporalQueryEngine Tests
# ============================================================


class TestTemporalQueryEngine:
    def test_query_empty_store(self, event_store):
        engine = TemporalQueryEngine(event_store)
        state = engine.query_at_sequence(0)
        assert state["total_evaluations"] == 0
        assert state["events_processed"] == 0

    def test_query_at_sequence(self, event_store):
        engine = TemporalQueryEngine(event_store)

        # Add some events
        event_store.append(EvaluationCompletedEvent(number=1, output="1"))
        event_store.append(EvaluationCompletedEvent(number=2, output="2"))
        event_store.append(EvaluationCompletedEvent(number=3, output="Fizz"))
        event_store.append(EvaluationCompletedEvent(number=4, output="4"))

        # Query at sequence 2 (should see only first 2 events)
        state = engine.query_at_sequence(2)
        assert state["total_evaluations"] == 2
        assert state["plain_count"] == 2
        assert state["fizz_count"] == 0

        # Query at sequence 3 (should see first 3 events)
        state = engine.query_at_sequence(3)
        assert state["total_evaluations"] == 3
        assert state["plain_count"] == 2
        assert state["fizz_count"] == 1

    def test_query_at_timestamp(self, event_store):
        engine = TemporalQueryEngine(event_store)

        before = datetime.now(timezone.utc)
        event_store.append(EvaluationCompletedEvent(number=3, output="Fizz"))
        # All events so far should be visible
        after = datetime.now(timezone.utc)

        state = engine.query_at_timestamp(after)
        assert state["total_evaluations"] == 1
        assert state["fizz_count"] == 1

    def test_get_event_timeline(self, event_store):
        engine = TemporalQueryEngine(event_store)
        event_store.append(NumberReceivedEvent(number=1))
        event_store.append(EvaluationCompletedEvent(number=1, output="1"))

        timeline = engine.get_event_timeline()
        assert len(timeline) == 2
        assert timeline[0]["type"] == "NumberReceivedEvent"
        assert timeline[1]["type"] == "EvaluationCompletedEvent"
        assert timeline[0]["sequence"] == 1
        assert timeline[1]["sequence"] == 2

    def test_results_accumulate_in_state(self, event_store):
        engine = TemporalQueryEngine(event_store)

        event_store.append(EvaluationCompletedEvent(number=3, output="Fizz"))
        event_store.append(EvaluationCompletedEvent(number=5, output="Buzz"))
        event_store.append(EvaluationCompletedEvent(number=15, output="FizzBuzz"))
        event_store.append(EvaluationCompletedEvent(number=7, output="7"))

        state = engine.query_at_sequence(100)  # large seq to get all
        assert state["results"] == {3: "Fizz", 5: "Buzz", 15: "FizzBuzz", 7: "7"}
        assert state["fizz_count"] == 1
        assert state["buzz_count"] == 1
        assert state["fizzbuzz_count"] == 1
        assert state["plain_count"] == 1


# ============================================================
# EvaluateNumberCommandHandler Tests
# ============================================================


class TestEvaluateNumberCommandHandler:
    def test_handle_emits_events(self, event_store, snapshot_store):
        handler = EvaluateNumberCommandHandler(
            event_store=event_store,
            snapshot_store=snapshot_store,
            evaluate_fn=lambda n: _make_fizz_result(n),
        )
        command = EvaluateNumberCommand(number=3, session_id="test")
        result = handler.handle(command)

        assert result.output == "Fizz"
        assert event_store.get_event_count() >= 4  # received, div_check, match, label, completed

        # Verify event types
        events = event_store.get_events()
        event_types = [type(e).__name__ for e in events]
        assert "NumberReceivedEvent" in event_types
        assert "DivisibilityCheckedEvent" in event_types
        assert "RuleMatchedEvent" in event_types
        assert "LabelAssignedEvent" in event_types
        assert "EvaluationCompletedEvent" in event_types

    def test_handle_plain_number(self, event_store, snapshot_store):
        handler = EvaluateNumberCommandHandler(
            event_store=event_store,
            snapshot_store=snapshot_store,
            evaluate_fn=lambda n: _make_plain_result(n),
        )
        command = EvaluateNumberCommand(number=7, session_id="test")
        result = handler.handle(command)

        assert result.output == "7"
        # Should have a "not divisible" check
        div_events = event_store.get_events_by_type(DivisibilityCheckedEvent)
        assert len(div_events) == 1
        assert div_events[0].is_divisible is False

    def test_handle_without_evaluate_fn(self, event_store, snapshot_store):
        handler = EvaluateNumberCommandHandler(
            event_store=event_store,
            snapshot_store=snapshot_store,
        )
        command = EvaluateNumberCommand(number=42, session_id="test")
        result = handler.handle(command)
        # Fallback produces str(number)
        assert result.output == "42"

    def test_snapshot_triggered(self):
        """Test that snapshots are taken at the configured interval."""
        event_store = EventStore()
        # Each plain number evaluation emits 4 events (received, div_check,
        # label, completed). Setting interval=4 ensures a snapshot triggers
        # after exactly one evaluation.
        snapshot_store = SnapshotStore(interval=4)

        handler = EvaluateNumberCommandHandler(
            event_store=event_store,
            snapshot_store=snapshot_store,
            evaluate_fn=lambda n: _make_plain_result(n),
        )

        handler.handle(EvaluateNumberCommand(number=1, session_id="test"))

        # After 4 events, should_snapshot(4) returns True, so a snapshot
        # should have been saved (plus a SnapshotTakenEvent appended).
        assert snapshot_store.get_snapshot_count() >= 1


# ============================================================
# EventSourcingMiddleware Tests
# ============================================================


class TestEventSourcingMiddleware:
    def test_middleware_emits_events(self):
        event_store = EventStore()
        command_bus = CommandBus()
        middleware = EventSourcingMiddleware(
            command_bus=command_bus,
            event_store=event_store,
        )

        context = ProcessingContext(number=3, session_id="test")

        def handler(ctx):
            result = _make_fizz_result(ctx.number)
            ctx.results.append(result)
            return ctx

        result_ctx = middleware.process(context, handler)
        assert result_ctx.metadata.get("event_sourcing") is True
        assert event_store.get_event_count() > 0

    def test_middleware_tags_context(self):
        event_store = EventStore()
        command_bus = CommandBus()
        middleware = EventSourcingMiddleware(
            command_bus=command_bus,
            event_store=event_store,
        )

        context = ProcessingContext(number=7, session_id="test")

        def handler(ctx):
            result = _make_plain_result(ctx.number)
            ctx.results.append(result)
            return ctx

        result_ctx = middleware.process(context, handler)
        assert result_ctx.metadata["event_sourcing"] is True
        assert result_ctx.metadata["event_count"] > 0

    def test_get_name(self):
        middleware = EventSourcingMiddleware(
            command_bus=CommandBus(),
            event_store=EventStore(),
        )
        assert middleware.get_name() == "EventSourcingMiddleware"

    def test_get_priority(self):
        middleware = EventSourcingMiddleware(
            command_bus=CommandBus(),
            event_store=EventStore(),
        )
        assert middleware.get_priority() == 5

    def test_middleware_handles_empty_results(self):
        """If next_handler produces no results, middleware should not crash."""
        event_store = EventStore()
        middleware = EventSourcingMiddleware(
            command_bus=CommandBus(),
            event_store=event_store,
        )

        context = ProcessingContext(number=1, session_id="test")
        result_ctx = middleware.process(context, lambda ctx: ctx)
        assert event_store.get_event_count() == 0


# ============================================================
# EventSourcingSystem Tests
# ============================================================


class TestEventSourcingSystem:
    def test_system_initialization(self, es_system):
        assert es_system.event_store is not None
        assert es_system.snapshot_store is not None
        assert es_system.command_bus is not None
        assert es_system.query_bus is not None
        assert es_system.temporal_engine is not None
        assert es_system.results_projection is not None
        assert es_system.stats_projection is not None
        assert es_system.event_count_projection is not None

    def test_create_middleware(self, es_system):
        middleware = es_system.create_middleware()
        assert isinstance(middleware, EventSourcingMiddleware)
        assert middleware.get_name() == "EventSourcingMiddleware"

    def test_query_bus_dispatches(self, es_system):
        # Event count query should work
        count = es_system.query_bus.dispatch(GetEventCountQuery())
        assert count == 0

    def test_projections_wired_to_store(self, es_system):
        """Test that projections automatically receive events."""
        es_system.event_store.append(
            EvaluationCompletedEvent(number=3, output="Fizz")
        )

        # Projections should have received the event
        stats = es_system.stats_projection.get_statistics()
        assert stats["fizz_count"] == 1

        results = es_system.results_projection.get_results()
        assert results[3] == "Fizz"

        counts = es_system.event_count_projection.get_counts()
        assert "EvaluationCompletedEvent" in counts

    def test_render_summary(self, es_system):
        es_system.event_store.append(
            EvaluationCompletedEvent(number=3, output="Fizz", processing_time_ns=1000)
        )
        summary = es_system.render_summary()
        assert "EVENT SOURCING / CQRS SUMMARY" in summary
        assert "Total Events" in summary

    def test_replay_events(self, es_system):
        # Add some events
        es_system.event_store.append(
            EvaluationCompletedEvent(number=3, output="Fizz")
        )
        es_system.event_store.append(
            EvaluationCompletedEvent(number=5, output="Buzz")
        )

        # Clear projections and replay
        result = es_system.replay_events()
        assert result["replayed_events"] == 2
        assert result["statistics"]["fizz_count"] == 1
        assert result["statistics"]["buzz_count"] == 1

    def test_temporal_query_via_query_bus(self, es_system):
        es_system.event_store.append(
            EvaluationCompletedEvent(number=3, output="Fizz")
        )
        es_system.event_store.append(
            EvaluationCompletedEvent(number=5, output="Buzz")
        )

        # Query at sequence 1 (only first event)
        state = es_system.query_bus.dispatch(
            GetTemporalStateQuery(as_of_sequence=1)
        )
        assert state["total_evaluations"] == 1
        assert state["fizz_count"] == 1

    def test_temporal_query_default(self, es_system):
        """Query with no as_of should return current state."""
        es_system.event_store.append(
            EvaluationCompletedEvent(number=3, output="Fizz")
        )
        state = es_system.query_bus.dispatch(GetTemporalStateQuery())
        assert state["total_evaluations"] == 1


# ============================================================
# Exception Tests
# ============================================================


class TestEventSourcingExceptions:
    def test_event_store_error(self):
        from exceptions import EventStoreError

        err = EventStoreError("test error")
        assert "EFP-ES00" in str(err)

    def test_event_sequence_error(self):
        err = EventSequenceError(5, 3)
        assert "EFP-ES01" in str(err)
        assert "expected sequence 5" in str(err)

    def test_snapshot_corruption_error(self):
        err = SnapshotCorruptionError("agg-1", 10)
        assert "EFP-ES03" in str(err)
        assert "agg-1" in str(err)

    def test_command_validation_error(self):
        err = CommandValidationError("EvaluateNumber", "number out of range")
        assert "EFP-ES04" in str(err)

    def test_command_handler_not_found_error(self):
        err = CommandHandlerNotFoundError("UnknownCommand")
        assert "EFP-ES05" in str(err)
        assert "UnknownCommand" in str(err)

    def test_query_handler_not_found_error(self):
        err = QueryHandlerNotFoundError("UnknownQuery")
        assert "EFP-ES06" in str(err)

    def test_projection_error(self):
        err = ProjectionError("StatsProjection", 0.0, 0.0, "division by zero")
        assert "EFP-CRT01" in str(err)

    def test_temporal_query_error(self):
        err = TemporalQueryError("2026-01-01T00:00:00Z", "no events before this time")
        assert "EFP-ES08" in str(err)

    def test_event_version_conflict_error(self):
        err = EventVersionConflictError("NumberReceivedEvent", 99, "1-5")
        assert "EFP-ES09" in str(err)


# ============================================================
# EventType Tests
# ============================================================


class TestEventSourcingEventTypes:
    def test_new_event_types_exist(self):
        assert EventType.ES_NUMBER_RECEIVED is not None
        assert EventType.ES_DIVISIBILITY_CHECKED is not None
        assert EventType.ES_RULE_MATCHED is not None
        assert EventType.ES_LABEL_ASSIGNED is not None
        assert EventType.ES_EVALUATION_COMPLETED is not None
        assert EventType.ES_SNAPSHOT_TAKEN is not None
        assert EventType.ES_COMMAND_DISPATCHED is not None
        assert EventType.ES_COMMAND_HANDLED is not None
        assert EventType.ES_QUERY_DISPATCHED is not None
        assert EventType.ES_PROJECTION_UPDATED is not None
        assert EventType.ES_EVENT_REPLAYED is not None
        assert EventType.ES_TEMPORAL_QUERY_EXECUTED is not None


# ============================================================
# Config Tests
# ============================================================


class TestEventSourcingConfig:
    def test_config_defaults(self):
        config = ConfigurationManager()
        config.load()
        assert config.event_sourcing_enabled is False
        assert config.event_sourcing_snapshot_interval == 10
        assert config.event_sourcing_max_events_before_compaction == 1000
        assert config.event_sourcing_enable_temporal_queries is True
        assert config.event_sourcing_enable_projections is True
        assert config.event_sourcing_event_version == 1


# ============================================================
# Integration Tests
# ============================================================


class TestEventSourcingIntegration:
    def test_full_evaluation_flow(self):
        """Test the complete ES flow: command -> events -> projections."""
        system = EventSourcingSystem(snapshot_interval=100)

        # Simulate evaluating numbers 1-15 through the middleware
        middleware = system.create_middleware()

        for n in range(1, 16):
            context = ProcessingContext(number=n, session_id="integration-test")

            if n % 15 == 0:
                result = _make_fizzbuzz_result(n)
            elif n % 3 == 0:
                result = _make_fizz_result(n)
            elif n % 5 == 0:
                result = _make_buzz_result(n)
            else:
                result = _make_plain_result(n)

            def make_handler(r):
                def handler(ctx):
                    ctx.results.append(r)
                    return ctx
                return handler

            middleware.process(context, make_handler(result))

        # Verify event store has events
        assert system.event_store.get_event_count() > 0

        # Verify projections
        stats = system.stats_projection.get_statistics()
        assert stats["total_evaluations"] == 15
        assert stats["fizz_count"] == 4  # 3, 6, 9, 12
        assert stats["buzz_count"] == 2  # 5, 10
        assert stats["fizzbuzz_count"] == 1  # 15
        assert stats["plain_count"] == 8  # 1, 2, 4, 7, 8, 11, 13, 14

        results = system.results_projection.get_results()
        assert results[3] == "Fizz"
        assert results[5] == "Buzz"
        assert results[15] == "FizzBuzz"
        assert results[7] == "7"

    def test_temporal_query_mid_evaluation(self):
        """Test temporal queries at different points during evaluation."""
        system = EventSourcingSystem(snapshot_interval=100)
        middleware = system.create_middleware()

        # Evaluate 1, 2, 3
        for n in [1, 2, 3]:
            context = ProcessingContext(number=n, session_id="temporal-test")
            if n % 3 == 0:
                result = _make_fizz_result(n)
            else:
                result = _make_plain_result(n)

            def make_handler(r):
                def handler(ctx):
                    ctx.results.append(r)
                    return ctx
                return handler

            middleware.process(context, make_handler(result))

        # Get the sequence number after first evaluation
        # Each number generates multiple events, so we need to find the right seq
        events = system.event_store.get_events()
        # Find the first EvaluationCompletedEvent
        first_completed_seq = None
        for e in events:
            if isinstance(e, EvaluationCompletedEvent) and e.number == 1:
                first_completed_seq = e.sequence_number
                break

        assert first_completed_seq is not None

        # Query at that sequence should show 1 evaluation
        state = system.temporal_engine.query_at_sequence(first_completed_seq)
        assert state["total_evaluations"] == 1
        assert state["plain_count"] == 1

    def test_event_store_subscriber_integration(self):
        """Test that event store subscribers receive events in real-time."""
        system = EventSourcingSystem(snapshot_interval=100)
        received_events = []
        system.event_store.subscribe(lambda e: received_events.append(type(e).__name__))

        middleware = system.create_middleware()
        context = ProcessingContext(number=3, session_id="sub-test")

        def handler(ctx):
            ctx.results.append(_make_fizz_result(ctx.number))
            return ctx

        middleware.process(context, handler)

        # Should have received events (projections + our custom subscriber)
        assert len(received_events) > 0
        assert "NumberReceivedEvent" in received_events
        assert "EvaluationCompletedEvent" in received_events

    def test_summary_rendering(self):
        """Test that the ASCII summary renders without errors."""
        system = EventSourcingSystem(snapshot_interval=100)

        # Populate with some data
        for n in [3, 5, 15, 7]:
            system.event_store.append(
                EvaluationCompletedEvent(
                    number=n,
                    output="Fizz" if n == 3 else "Buzz" if n == 5 else "FizzBuzz" if n == 15 else "7",
                    processing_time_ns=1000,
                )
            )

        summary = system.render_summary()
        assert "EVENT SOURCING / CQRS SUMMARY" in summary
        assert "Total Events" in summary
        assert "Evaluations" in summary
        assert "EvaluationCompletedEvent" in summary

    def test_middleware_in_pipeline(self):
        """Test ES middleware works in a MiddlewarePipeline."""
        from middleware import MiddlewarePipeline

        system = EventSourcingSystem(snapshot_interval=100)
        es_middleware = system.create_middleware()

        pipeline = MiddlewarePipeline()
        pipeline.add(es_middleware)

        context = ProcessingContext(number=3, session_id="pipeline-test")

        def final_handler(ctx):
            ctx.results.append(_make_fizz_result(ctx.number))
            return ctx

        result = pipeline.execute(context, final_handler)
        assert result.metadata.get("event_sourcing") is True
        assert system.event_store.get_event_count() > 0

    def test_replay_rebuilds_projections(self):
        """Test that replaying events correctly rebuilds projections."""
        system = EventSourcingSystem(snapshot_interval=100)

        # Add events
        system.event_store.append(
            EvaluationCompletedEvent(number=3, output="Fizz")
        )
        system.event_store.append(
            EvaluationCompletedEvent(number=5, output="Buzz")
        )

        # Verify projections have data
        assert system.stats_projection.get_statistics()["total_evaluations"] == 2

        # Replay (clears and rebuilds)
        replay_result = system.replay_events()
        assert replay_result["replayed_events"] == 2
        assert system.stats_projection.get_statistics()["total_evaluations"] == 2
