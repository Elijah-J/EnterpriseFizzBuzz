"""
Enterprise FizzBuzz Platform - Observer / Event Bus Test Suite

Comprehensive tests for the publish-subscribe backbone that ensures every
FizzBuzz event reaches every stakeholder who subscribed to be notified about
modulo arithmetic outcomes. Because in enterprise software, an unobserved
event is indistinguishable from an event that never happened, and the
compliance department will not accept quantum uncertainty as an excuse.
"""

from __future__ import annotations

import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from enterprise_fizzbuzz.domain.interfaces import IObserver
from enterprise_fizzbuzz.domain.models import Event, EventType
from enterprise_fizzbuzz.infrastructure.observers import (
    ConsoleObserver,
    EventBus,
    StatisticsObserver,
)


# ============================================================
# Test Helpers
# ============================================================


class RecordingObserver(IObserver):
    """An observer that faithfully records every event it witnesses.

    The enterprise equivalent of a court stenographer, except it
    works for free and never requests a bathroom break.
    """

    def __init__(self, name: str = "RecordingObserver") -> None:
        self._name = name
        self._events: list[Event] = []

    def on_event(self, event: Event) -> None:
        self._events.append(event)

    def get_name(self) -> str:
        return self._name

    @property
    def events(self) -> list[Event]:
        return list(self._events)

    @property
    def event_count(self) -> int:
        return len(self._events)


class ExplodingObserver(IObserver):
    """An observer that raises an exception on every event.

    Simulates the production experience of a third-party integration
    that looked great in the demo but catches fire the moment real
    data flows through it.
    """

    def __init__(self, name: str = "ExplodingObserver") -> None:
        self._name = name

    def on_event(self, event: Event) -> None:
        raise RuntimeError(f"{self._name} detonated on {event.event_type.name}")

    def get_name(self) -> str:
        return self._name


def _make_event(
    event_type: EventType = EventType.NUMBER_PROCESSED,
    payload: dict[str, Any] | None = None,
    source: str = "TestHarness",
) -> Event:
    """Factory for constructing events without drowning in boilerplate."""
    return Event(
        event_type=event_type,
        payload=payload or {},
        source=source,
    )


# ============================================================
# Fixtures
# ============================================================


@pytest.fixture
def bus() -> EventBus:
    """A fresh event bus, unsullied by previous FizzBuzz events."""
    return EventBus()


@pytest.fixture
def recorder() -> RecordingObserver:
    """A recording observer ready to document the proceedings."""
    return RecordingObserver()


@pytest.fixture
def stats_observer() -> StatisticsObserver:
    """A statistics observer, eager to count things that do not matter."""
    return StatisticsObserver()


@pytest.fixture
def console_observer() -> ConsoleObserver:
    """A console observer in non-verbose mode."""
    return ConsoleObserver(verbose=False)


@pytest.fixture
def subscribed_bus(bus: EventBus, recorder: RecordingObserver) -> EventBus:
    """An event bus with a recording observer already subscribed."""
    bus.subscribe(recorder)
    return bus


# ============================================================
# Subscribe / Unsubscribe Tests
# ============================================================


class TestSubscribeUnsubscribe:
    """Tests for observer lifecycle management on the event bus."""

    def test_subscribed_observer_receives_event(self, bus: EventBus, recorder: RecordingObserver):
        """An observer that subscribes should receive published events.
        This is, admittedly, the minimum viable expectation."""
        bus.subscribe(recorder)
        bus.publish(_make_event())
        assert recorder.event_count == 1

    def test_unsubscribed_observer_receives_nothing(self, bus: EventBus, recorder: RecordingObserver):
        """After unsubscribing, an observer should be dead to the bus.
        No events, no notifications, no closure."""
        bus.subscribe(recorder)
        bus.publish(_make_event())
        bus.unsubscribe(recorder)
        bus.publish(_make_event())
        assert recorder.event_count == 1

    def test_subscribe_same_observer_twice_is_idempotent(self, bus: EventBus, recorder: RecordingObserver):
        """Subscribing the same observer twice should not cause duplicate
        deliveries. The bus deduplicates, because double-counting FizzBuzz
        events would be a compliance nightmare."""
        bus.subscribe(recorder)
        bus.subscribe(recorder)
        bus.publish(_make_event())
        assert recorder.event_count == 1

    def test_unsubscribe_nonexistent_observer_is_safe(self, bus: EventBus, recorder: RecordingObserver):
        """Unsubscribing an observer that was never subscribed should not
        raise an exception. Graceful no-ops are the hallmark of mature systems."""
        bus.unsubscribe(recorder)  # should not raise

    def test_subscribe_after_unsubscribe_works(self, bus: EventBus, recorder: RecordingObserver):
        """An observer should be able to re-subscribe after unsubscribing,
        like an employee who quits and then returns three months later."""
        bus.subscribe(recorder)
        bus.unsubscribe(recorder)
        bus.subscribe(recorder)
        bus.publish(_make_event())
        assert recorder.event_count == 1

    def test_no_observers_publish_does_not_raise(self, bus: EventBus):
        """Publishing to an empty bus should not raise. A tree that falls
        in an empty forest still falls; it just has no compliance witnesses."""
        bus.publish(_make_event())  # should not raise


# ============================================================
# Multiple Observers Tests
# ============================================================


class TestMultipleObservers:
    """Tests verifying that all subscribed observers receive the same events."""

    def test_two_observers_both_receive_event(self, bus: EventBus):
        """Two observers subscribed to the same bus should both receive
        every published event. Democracy in action."""
        obs_a = RecordingObserver("ObserverA")
        obs_b = RecordingObserver("ObserverB")
        bus.subscribe(obs_a)
        bus.subscribe(obs_b)
        bus.publish(_make_event())
        assert obs_a.event_count == 1
        assert obs_b.event_count == 1

    def test_five_observers_all_receive_all_events(self, bus: EventBus):
        """Scaling to five observers should work identically. The event bus
        makes no distinction between two stakeholders and five."""
        observers = [RecordingObserver(f"Observer{i}") for i in range(5)]
        for obs in observers:
            bus.subscribe(obs)
        for _ in range(10):
            bus.publish(_make_event())
        for obs in observers:
            assert obs.event_count == 10

    def test_unsubscribing_one_does_not_affect_others(self, bus: EventBus):
        """When one observer unsubscribes, the remaining observers should
        continue receiving events undisturbed."""
        obs_a = RecordingObserver("ObserverA")
        obs_b = RecordingObserver("ObserverB")
        bus.subscribe(obs_a)
        bus.subscribe(obs_b)
        bus.publish(_make_event())
        bus.unsubscribe(obs_a)
        bus.publish(_make_event())
        assert obs_a.event_count == 1
        assert obs_b.event_count == 2

    def test_observers_receive_identical_event_objects(self, bus: EventBus):
        """All observers should receive the exact same Event instance,
        because creating copies would be wasteful and the Event is frozen anyway."""
        obs_a = RecordingObserver("ObserverA")
        obs_b = RecordingObserver("ObserverB")
        bus.subscribe(obs_a)
        bus.subscribe(obs_b)
        event = _make_event()
        bus.publish(event)
        assert obs_a.events[0] is obs_b.events[0]
        assert obs_a.events[0] is event


# ============================================================
# Event Types Tests
# ============================================================


class TestEventTypes:
    """Tests verifying that different event types flow correctly through the bus."""

    def test_fizz_event_delivered(self, subscribed_bus: EventBus, recorder: RecordingObserver):
        """A FIZZ_DETECTED event should arrive with its type intact."""
        subscribed_bus.publish(_make_event(EventType.FIZZ_DETECTED))
        assert recorder.events[0].event_type == EventType.FIZZ_DETECTED

    def test_buzz_event_delivered(self, subscribed_bus: EventBus, recorder: RecordingObserver):
        """A BUZZ_DETECTED event should arrive with its type intact."""
        subscribed_bus.publish(_make_event(EventType.BUZZ_DETECTED))
        assert recorder.events[0].event_type == EventType.BUZZ_DETECTED

    def test_fizzbuzz_event_delivered(self, subscribed_bus: EventBus, recorder: RecordingObserver):
        """A FIZZBUZZ_DETECTED event, the rarest and most prestigious
        of all FizzBuzz events, should be delivered faithfully."""
        subscribed_bus.publish(_make_event(EventType.FIZZBUZZ_DETECTED))
        assert recorder.events[0].event_type == EventType.FIZZBUZZ_DETECTED

    def test_error_event_carries_payload(self, subscribed_bus: EventBus, recorder: RecordingObserver):
        """An ERROR_OCCURRED event should preserve its payload, because
        losing error details is how postmortems become mysteries."""
        payload = {"error": "Modulo operator returned NaN", "severity": "critical"}
        subscribed_bus.publish(_make_event(EventType.ERROR_OCCURRED, payload=payload))
        assert recorder.events[0].payload == payload

    def test_mixed_event_types_delivered_in_sequence(self, subscribed_bus: EventBus, recorder: RecordingObserver):
        """A sequence of different event types should arrive in order,
        each with its correct type preserved."""
        types = [
            EventType.SESSION_STARTED,
            EventType.NUMBER_PROCESSED,
            EventType.FIZZ_DETECTED,
            EventType.SESSION_ENDED,
        ]
        for t in types:
            subscribed_bus.publish(_make_event(t))
        received_types = [e.event_type for e in recorder.events]
        assert received_types == types


# ============================================================
# Event History Tests
# ============================================================


class TestEventHistory:
    """Tests for the event bus's built-in audit trail."""

    def test_event_history_records_all_published_events(self, bus: EventBus):
        """The event history should contain every event ever published,
        because enterprise software never forgets."""
        for _ in range(5):
            bus.publish(_make_event())
        assert len(bus.get_event_history()) == 5

    def test_event_history_returns_copy(self, bus: EventBus):
        """get_event_history should return a copy, not the internal list.
        Allowing callers to mutate the history would violate the immutable
        audit trail guarantee that the compliance team insisted on."""
        bus.publish(_make_event())
        history = bus.get_event_history()
        history.clear()
        assert len(bus.get_event_history()) == 1

    def test_clear_history_empties_the_record(self, bus: EventBus):
        """clear_history should wipe the slate clean, which is technically
        a compliance violation but sometimes you just need a fresh start."""
        bus.publish(_make_event())
        bus.clear_history()
        assert len(bus.get_event_history()) == 0

    def test_event_history_preserves_order(self, bus: EventBus):
        """Events in the history should appear in the order they were published."""
        events = [_make_event(EventType.SESSION_STARTED, source=f"Source{i}") for i in range(5)]
        for e in events:
            bus.publish(e)
        history = bus.get_event_history()
        for i, h in enumerate(history):
            assert h.source == f"Source{i}"


# ============================================================
# Observer Statistics Tests
# ============================================================


class TestStatisticsObserver:
    """Tests for the StatisticsObserver's heroic counting abilities."""

    def test_fizz_count_increments_on_fizz_event(self, bus: EventBus, stats_observer: StatisticsObserver):
        """The StatisticsObserver should count FIZZ_DETECTED events."""
        bus.subscribe(stats_observer)
        bus.publish(_make_event(EventType.FIZZ_DETECTED))
        bus.publish(_make_event(EventType.FIZZ_DETECTED))
        assert stats_observer.get_summary_data()["fizz_count"] == 2

    def test_buzz_count_increments_on_buzz_event(self, bus: EventBus, stats_observer: StatisticsObserver):
        """The StatisticsObserver should count BUZZ_DETECTED events."""
        bus.subscribe(stats_observer)
        bus.publish(_make_event(EventType.BUZZ_DETECTED))
        assert stats_observer.get_summary_data()["buzz_count"] == 1

    def test_fizzbuzz_count_increments_on_fizzbuzz_event(self, bus: EventBus, stats_observer: StatisticsObserver):
        """The rarest classification gets its own counter, naturally."""
        bus.subscribe(stats_observer)
        bus.publish(_make_event(EventType.FIZZBUZZ_DETECTED))
        assert stats_observer.get_summary_data()["fizzbuzz_count"] == 1

    def test_plain_count_increments_on_plain_number_event(self, bus: EventBus, stats_observer: StatisticsObserver):
        """Plain numbers: the unsung heroes of FizzBuzz, counted but never celebrated."""
        bus.subscribe(stats_observer)
        bus.publish(_make_event(EventType.PLAIN_NUMBER_DETECTED))
        bus.publish(_make_event(EventType.PLAIN_NUMBER_DETECTED))
        bus.publish(_make_event(EventType.PLAIN_NUMBER_DETECTED))
        assert stats_observer.get_summary_data()["plain_count"] == 3

    def test_total_count_increments_on_number_processed(self, bus: EventBus, stats_observer: StatisticsObserver):
        """NUMBER_PROCESSED is the master counter — every number that enters
        the pipeline, regardless of classification, is counted here."""
        bus.subscribe(stats_observer)
        for _ in range(7):
            bus.publish(_make_event(EventType.NUMBER_PROCESSED))
        assert stats_observer.get_summary_data()["total_count"] == 7

    def test_error_recorded_with_message(self, bus: EventBus, stats_observer: StatisticsObserver):
        """ERROR_OCCURRED events should have their messages captured verbatim."""
        bus.subscribe(stats_observer)
        bus.publish(_make_event(EventType.ERROR_OCCURRED, payload={"error": "Division by zero (ironic)"}))
        summary = stats_observer.get_summary_data()
        assert len(summary["errors"]) == 1
        assert summary["errors"][0] == "Division by zero (ironic)"

    def test_error_with_missing_error_key_records_unknown(self, bus: EventBus, stats_observer: StatisticsObserver):
        """An ERROR_OCCURRED event without an 'error' key in the payload
        should record 'Unknown', because even errors deserve a name."""
        bus.subscribe(stats_observer)
        bus.publish(_make_event(EventType.ERROR_OCCURRED, payload={}))
        assert stats_observer.get_summary_data()["errors"] == ["Unknown"]

    def test_reset_clears_all_statistics(self, bus: EventBus, stats_observer: StatisticsObserver):
        """reset() should zero all counters and clear the error list."""
        bus.subscribe(stats_observer)
        bus.publish(_make_event(EventType.FIZZ_DETECTED))
        bus.publish(_make_event(EventType.BUZZ_DETECTED))
        bus.publish(_make_event(EventType.ERROR_OCCURRED, payload={"error": "oops"}))
        stats_observer.reset()
        summary = stats_observer.get_summary_data()
        assert summary["fizz_count"] == 0
        assert summary["buzz_count"] == 0
        assert summary["fizzbuzz_count"] == 0
        assert summary["plain_count"] == 0
        assert summary["total_count"] == 0
        assert summary["errors"] == []

    def test_get_name_returns_correct_identifier(self, stats_observer: StatisticsObserver):
        """The StatisticsObserver should identify itself by name, for audit trail purposes."""
        assert stats_observer.get_name() == "StatisticsObserver"

    def test_unrelated_event_types_do_not_affect_counts(self, bus: EventBus, stats_observer: StatisticsObserver):
        """Events like SESSION_STARTED should be politely ignored by the
        statistics counters. Not every event deserves a metric."""
        bus.subscribe(stats_observer)
        bus.publish(_make_event(EventType.SESSION_STARTED))
        bus.publish(_make_event(EventType.SESSION_ENDED))
        bus.publish(_make_event(EventType.MIDDLEWARE_ENTERED))
        summary = stats_observer.get_summary_data()
        assert summary["fizz_count"] == 0
        assert summary["total_count"] == 0


# ============================================================
# ConsoleObserver Tests
# ============================================================


class TestConsoleObserver:
    """Tests for the ConsoleObserver, the platform's real-time commentary system."""

    def test_get_name_returns_correct_identifier(self, console_observer: ConsoleObserver):
        """The ConsoleObserver should know its own name."""
        assert console_observer.get_name() == "ConsoleObserver"

    def test_verbose_mode_prints_all_events(self, capsys: pytest.CaptureFixture):
        """In verbose mode, the ConsoleObserver prints every event, including
        the mundane ones that nobody asked to see."""
        obs = ConsoleObserver(verbose=True)
        obs.on_event(_make_event(EventType.SESSION_STARTED))
        captured = capsys.readouterr()
        assert "SESSION_STARTED" in captured.out

    def test_non_verbose_mode_prints_fizz(self, capsys: pytest.CaptureFixture):
        """In non-verbose mode, FIZZ_DETECTED events are important enough
        to make the cut."""
        obs = ConsoleObserver(verbose=False)
        obs.on_event(_make_event(EventType.FIZZ_DETECTED))
        captured = capsys.readouterr()
        assert "FIZZ_DETECTED" in captured.out

    def test_non_verbose_mode_suppresses_mundane_events(self, capsys: pytest.CaptureFixture):
        """In non-verbose mode, SESSION_STARTED events are deemed too boring
        for console output."""
        obs = ConsoleObserver(verbose=False)
        obs.on_event(_make_event(EventType.SESSION_STARTED))
        captured = capsys.readouterr()
        assert captured.out == ""


# ============================================================
# Error Isolation Tests
# ============================================================


class TestErrorIsolation:
    """Tests proving that one observer's tantrum does not ruin the party for others."""

    def test_exploding_observer_does_not_prevent_delivery_to_others(self, bus: EventBus):
        """If one observer raises an exception, the remaining observers
        should still receive the event. Error isolation is the difference
        between a minor incident and a platform-wide outage."""
        exploder = ExplodingObserver()
        recorder = RecordingObserver()
        bus.subscribe(exploder)
        bus.subscribe(recorder)
        bus.publish(_make_event())
        assert recorder.event_count == 1

    def test_exploding_observer_between_two_recorders(self, bus: EventBus):
        """An exploding observer sandwiched between two healthy observers
        should not prevent either from receiving the event."""
        recorder_before = RecordingObserver("Before")
        exploder = ExplodingObserver()
        recorder_after = RecordingObserver("After")
        bus.subscribe(recorder_before)
        bus.subscribe(exploder)
        bus.subscribe(recorder_after)
        bus.publish(_make_event())
        assert recorder_before.event_count == 1
        assert recorder_after.event_count == 1

    def test_multiple_exploding_observers_do_not_break_bus(self, bus: EventBus):
        """Even if every observer except one explodes, the surviving observer
        should still receive the event. Resilience through stubbornness."""
        recorder = RecordingObserver()
        bus.subscribe(ExplodingObserver("Bomb1"))
        bus.subscribe(ExplodingObserver("Bomb2"))
        bus.subscribe(recorder)
        bus.subscribe(ExplodingObserver("Bomb3"))
        bus.publish(_make_event())
        assert recorder.event_count == 1


# ============================================================
# Event Ordering Tests
# ============================================================


class TestEventOrdering:
    """Tests verifying that events arrive in the order they were published."""

    def test_events_delivered_in_publication_order(self, bus: EventBus):
        """Events must arrive at each observer in the exact order they
        were published. Reordering FizzBuzz events would violate causality
        and the space-time continuum of modulo arithmetic."""
        recorder = RecordingObserver()
        bus.subscribe(recorder)
        types = [
            EventType.SESSION_STARTED,
            EventType.NUMBER_PROCESSING_STARTED,
            EventType.FIZZ_DETECTED,
            EventType.NUMBER_PROCESSED,
            EventType.SESSION_ENDED,
        ]
        for t in types:
            bus.publish(_make_event(t))
        assert [e.event_type for e in recorder.events] == types

    def test_event_source_preserved_in_delivery_order(self, bus: EventBus):
        """The source field of each event should be preserved in order,
        proving the bus is not shuffling events like a deck of cards."""
        recorder = RecordingObserver()
        bus.subscribe(recorder)
        for i in range(20):
            bus.publish(_make_event(source=f"Source-{i}"))
        for i, event in enumerate(recorder.events):
            assert event.source == f"Source-{i}"


# ============================================================
# Thread Safety Tests
# ============================================================


class TestThreadSafety:
    """Tests for concurrent access to the event bus.

    The event bus claims thread-safe operation via locks, and these tests
    call its bluff by hammering it from multiple threads simultaneously.
    """

    def test_concurrent_publishes_no_events_lost(self, bus: EventBus):
        """Publishing from multiple threads concurrently should not lose
        any events. Every FizzBuzz event matters, even under load."""
        recorder = RecordingObserver()
        bus.subscribe(recorder)
        num_threads = 10
        events_per_thread = 50
        barrier = threading.Barrier(num_threads)

        def publish_events():
            barrier.wait()
            for _ in range(events_per_thread):
                bus.publish(_make_event())

        threads = [threading.Thread(target=publish_events) for _ in range(num_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        assert recorder.event_count == num_threads * events_per_thread

    def test_concurrent_publishes_event_history_complete(self, bus: EventBus):
        """The event history should capture every event even under concurrent
        publishing. The audit trail must be airtight."""
        num_threads = 8
        events_per_thread = 25
        barrier = threading.Barrier(num_threads)

        def publish_events():
            barrier.wait()
            for _ in range(events_per_thread):
                bus.publish(_make_event())

        threads = [threading.Thread(target=publish_events) for _ in range(num_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        assert len(bus.get_event_history()) == num_threads * events_per_thread

    def test_concurrent_subscribe_unsubscribe_does_not_crash(self, bus: EventBus):
        """Subscribing and unsubscribing observers while events are being
        published should not crash the bus. Chaos is a ladder."""
        recorder = RecordingObserver()
        bus.subscribe(recorder)
        stop_event = threading.Event()

        def churn_observers():
            obs = RecordingObserver("Churner")
            while not stop_event.is_set():
                bus.subscribe(obs)
                bus.unsubscribe(obs)

        def publish_events():
            for _ in range(100):
                bus.publish(_make_event())

        churner = threading.Thread(target=churn_observers)
        publisher = threading.Thread(target=publish_events)
        churner.start()
        publisher.start()
        publisher.join(timeout=10)
        stop_event.set()
        churner.join(timeout=10)

        # The stable observer should have received all events
        assert recorder.event_count == 100

    def test_statistics_observer_thread_safe_counting(self, bus: EventBus):
        """The StatisticsObserver uses its own lock for thread-safe counting.
        Concurrent fizz and buzz events should all be counted accurately."""
        stats = StatisticsObserver()
        bus.subscribe(stats)
        num_threads = 8
        events_per_thread = 50
        barrier = threading.Barrier(num_threads)

        def publish_fizz():
            barrier.wait()
            for _ in range(events_per_thread):
                bus.publish(_make_event(EventType.FIZZ_DETECTED))

        threads = [threading.Thread(target=publish_fizz) for _ in range(num_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        assert stats.get_summary_data()["fizz_count"] == num_threads * events_per_thread
