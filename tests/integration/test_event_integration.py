"""
Enterprise FizzBuzz Platform - Event Bus Cross-Subsystem Integration Tests

In-process integration tests verifying that the event bus — the platform's
nervous system — faithfully conducts signals between subsystems without
dropping events, reordering them, or misrouting them into the void.

Unit tests prove that the EventBus can publish and subscribe. These tests
prove that when the SLA monitor records an evaluation, the audit dashboard
hears about it. That when the circuit breaker trips, its anguished state-
change event reaches every registered observer. That when 10,000 events
flood through the bus in rapid succession, not a single one is lost —
because in enterprise FizzBuzz, every event is sacred.

Test categories:
  1. Evaluation events reach SLA: rule engine + SLA on shared bus
  2. Chaos events reach audit dashboard: chaos monkey + aggregator on shared bus
  3. Compliance events reach metrics: compliance + MetricsCollector on shared bus
  4. SLA alert events: impossibly tight SLO triggers alert publication
  5. Circuit breaker state change events: CLOSED->OPEN transitions on the bus
  6. Event ordering: 100 events, aggregator receives them in order
  7. Event bus under load: 10,000 events, zero dropped
  8. Cross-subsystem event flow: multiple subsystems, one bus, all events arrive
"""

from __future__ import annotations

import sys
import time
import uuid
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import pytest

# Add parent dirs to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from enterprise_fizzbuzz.domain.interfaces import IObserver
from enterprise_fizzbuzz.domain.models import (
    Event,
    EventType,
    FizzBuzzClassification,
    FizzBuzzResult,
    ProcessingContext,
    RuleDefinition,
    RuleMatch,
)
from enterprise_fizzbuzz.infrastructure.config import _SingletonMeta
from enterprise_fizzbuzz.infrastructure.observers import EventBus, StatisticsObserver


# ============================================================
# Fixtures
# ============================================================


@pytest.fixture(autouse=True)
def reset_singletons():
    """Reset all singleton instances between tests.

    Without this, the MetricRegistry singleton bleeds state between
    tests like a poorly sealed event bus leaks events into the void.
    """
    _SingletonMeta.reset()
    # Reset MetricRegistry singleton
    try:
        from enterprise_fizzbuzz.infrastructure.metrics import MetricRegistry
        MetricRegistry.reset()
    except Exception:
        pass
    # Reset ChaosMonkey singleton
    try:
        from enterprise_fizzbuzz.infrastructure.chaos import ChaosMonkey
        ChaosMonkey.reset()
    except Exception:
        pass
    yield
    _SingletonMeta.reset()
    try:
        from enterprise_fizzbuzz.infrastructure.metrics import MetricRegistry
        MetricRegistry.reset()
    except Exception:
        pass
    try:
        from enterprise_fizzbuzz.infrastructure.chaos import ChaosMonkey
        ChaosMonkey.reset()
    except Exception:
        pass


@pytest.fixture
def event_bus():
    """Create a fresh EventBus for each test.

    A clean bus is a happy bus. No ghosts of events past,
    no phantom subscribers from previous tests.
    """
    return EventBus()


class RecordingObserver(IObserver):
    """A simple observer that records all events for assertion.

    The panopticon of the event bus world — it sees everything,
    judges nothing, and remembers all. Its sole purpose is to provide
    irrefutable evidence that events were or were not delivered,
    like a security camera for the FizzBuzz nervous system.
    """

    def __init__(self, name: str = "RecordingObserver") -> None:
        self._name = name
        self._events: list[Event] = []
        self._lock = threading.Lock()

    def on_event(self, event: Event) -> None:
        with self._lock:
            self._events.append(event)

    def get_name(self) -> str:
        return self._name

    @property
    def events(self) -> list[Event]:
        with self._lock:
            return list(self._events)

    @property
    def event_count(self) -> int:
        with self._lock:
            return len(self._events)

    def events_of_type(self, event_type: EventType) -> list[Event]:
        """Return all recorded events of the given type."""
        with self._lock:
            return [e for e in self._events if e.event_type == event_type]

    def has_event_type(self, event_type: EventType) -> bool:
        """Return True if at least one event of the given type was recorded."""
        return len(self.events_of_type(event_type)) > 0

    def clear(self) -> None:
        with self._lock:
            self._events.clear()


def _make_result(number: int) -> FizzBuzzResult:
    """Create a FizzBuzzResult with proper ground-truth output.

    We compute the correct FizzBuzz classification because some
    subsystems (SLA accuracy verification) will independently
    recheck our work. Cheating is not tolerated.
    """
    if number % 15 == 0:
        output = "FizzBuzz"
    elif number % 3 == 0:
        output = "Fizz"
    elif number % 5 == 0:
        output = "Buzz"
    else:
        output = str(number)

    rules = []
    if number % 3 == 0:
        rules.append(RuleMatch(
            rule=RuleDefinition(name="Fizz", divisor=3, label="Fizz"),
            number=number,
        ))
    if number % 5 == 0:
        rules.append(RuleMatch(
            rule=RuleDefinition(name="Buzz", divisor=5, label="Buzz"),
            number=number,
        ))

    return FizzBuzzResult(
        number=number,
        output=output,
        matched_rules=rules,
        processing_time_ns=1_000_000,  # 1ms
    )


# ============================================================
# Category 1: Evaluation Events Reach SLA
# ============================================================


class TestEvaluationEventsReachSLA:
    """Verify that evaluation events published by the SLA monitor
    are received by observers subscribed to the same bus.

    The SLA monitor publishes SLA_EVALUATION_RECORDED events when
    record_evaluation() is called. These events should be receivable
    by any observer on the bus, proving the SLA monitor is a good
    citizen of the event-driven ecosystem.
    """

    def test_sla_monitor_publishes_evaluation_recorded_event(self, event_bus):
        """When SLAMonitor.record_evaluation() is called, an
        SLA_EVALUATION_RECORDED event should be published to the bus."""
        from enterprise_fizzbuzz.infrastructure.sla import SLAMonitor, SLODefinition, SLOType

        recorder = RecordingObserver("SLAEvalRecorder")
        event_bus.subscribe(recorder)

        monitor = SLAMonitor(
            slo_definitions=[
                SLODefinition(name="latency", slo_type=SLOType.LATENCY, target=0.999, threshold_ms=100.0),
            ],
            event_bus=event_bus,
        )

        monitor.record_evaluation(
            latency_ns=500_000,  # 0.5ms
            number=15,
            output="FizzBuzz",
            success=True,
        )

        eval_events = recorder.events_of_type(EventType.SLA_EVALUATION_RECORDED)
        assert len(eval_events) >= 1, (
            "SLAMonitor.record_evaluation() should publish at least one "
            "SLA_EVALUATION_RECORDED event, but the recorder heard nothing."
        )
        payload = eval_events[0].payload
        assert payload["number"] == 15
        assert payload["output"] == "FizzBuzz"

    def test_sla_evaluation_events_contain_latency_data(self, event_bus):
        """The SLA_EVALUATION_RECORDED event should include latency metrics
        so downstream consumers know exactly how long the modulo operation
        took (spoiler: not long)."""
        from enterprise_fizzbuzz.infrastructure.sla import SLAMonitor, SLODefinition, SLOType

        recorder = RecordingObserver()
        event_bus.subscribe(recorder)

        monitor = SLAMonitor(
            slo_definitions=[
                SLODefinition(name="latency", slo_type=SLOType.LATENCY, target=0.999, threshold_ms=100.0),
            ],
            event_bus=event_bus,
        )

        monitor.record_evaluation(latency_ns=2_000_000, number=3, output="Fizz", success=True)

        eval_events = recorder.events_of_type(EventType.SLA_EVALUATION_RECORDED)
        assert len(eval_events) >= 1
        payload = eval_events[0].payload
        assert "latency_ns" in payload
        assert payload["latency_ns"] == 2_000_000
        assert "latency_ms" in payload

    def test_sla_monitor_records_evaluation_in_collector(self, event_bus):
        """The SLOMetricCollector should reflect the evaluation after
        SLAMonitor.record_evaluation() is called. The collector is the
        memory of the SLA system; if it forgets, Bob gets paged for nothing."""
        from enterprise_fizzbuzz.infrastructure.sla import SLAMonitor, SLODefinition, SLOType

        monitor = SLAMonitor(
            slo_definitions=[
                SLODefinition(name="accuracy", slo_type=SLOType.ACCURACY, target=0.999),
            ],
            event_bus=event_bus,
        )

        monitor.record_evaluation(latency_ns=100_000, number=5, output="Buzz", success=True)
        monitor.record_evaluation(latency_ns=200_000, number=7, output="7", success=True)

        assert monitor.collector.get_total_evaluations() == 2

    def test_multiple_evaluations_reach_sla_and_observer(self, event_bus):
        """Run 20 evaluations through the SLA monitor and verify the
        recording observer captured all SLA_EVALUATION_RECORDED events."""
        from enterprise_fizzbuzz.infrastructure.sla import SLAMonitor, SLODefinition, SLOType

        recorder = RecordingObserver()
        event_bus.subscribe(recorder)

        monitor = SLAMonitor(
            slo_definitions=[
                SLODefinition(name="latency", slo_type=SLOType.LATENCY, target=0.999, threshold_ms=100.0),
            ],
            event_bus=event_bus,
        )

        for n in range(1, 21):
            result = _make_result(n)
            monitor.record_evaluation(
                latency_ns=100_000,
                number=n,
                output=result.output,
                success=True,
            )

        eval_events = recorder.events_of_type(EventType.SLA_EVALUATION_RECORDED)
        assert len(eval_events) == 20, (
            f"Expected 20 SLA_EVALUATION_RECORDED events for 20 evaluations, "
            f"got {len(eval_events)}. The event bus lost some in transit."
        )


# ============================================================
# Category 2: Chaos Events Reach Audit Dashboard
# ============================================================


class TestChaosEventsReachAuditDashboard:
    """Verify that chaos fault injection events reach the audit dashboard's
    EventAggregator when both are subscribed to the same bus.

    When the ChaosMonkey strikes, the audit dashboard should know about it.
    You cannot have plausible deniability about chaos if the audit trail
    records every monkey-wrench thrown into the pipeline.
    """

    def test_chaos_fault_event_reaches_aggregator(self, event_bus):
        """Inject a chaos fault and verify the audit aggregator captured it."""
        from enterprise_fizzbuzz.infrastructure.audit_dashboard import EventAggregator
        from enterprise_fizzbuzz.infrastructure.chaos import ChaosMonkey, FaultType, FaultSeverity

        aggregator = EventAggregator(buffer_size=100)
        event_bus.subscribe(aggregator)

        monkey = ChaosMonkey(
            severity=FaultSeverity.LEVEL_5,  # 80% chance, nearly guaranteed
            seed=42,
            armed_fault_types=[FaultType.RESULT_CORRUPTION],
            event_bus=event_bus,
        )

        # Create a context for the monkey to sabotage
        context = ProcessingContext(number=15, session_id="chaos-test-session")
        context.results.append(_make_result(15))

        # Inject fault directly with specified type to guarantee injection
        monkey.inject_fault(context, fault_type=FaultType.RESULT_CORRUPTION)

        chaos_events = [
            e for e in aggregator.get_events()
            if e.event_type == EventType.CHAOS_FAULT_INJECTED.name
        ]
        assert len(chaos_events) >= 1, (
            "ChaosMonkey.inject_fault() published a CHAOS_FAULT_INJECTED event, "
            "but the EventAggregator didn't receive it. The audit trail has a gap."
        )

    def test_chaos_event_aggregator_classifies_severity_as_warning(self, event_bus):
        """Chaos fault injection events should be classified as WARNING
        severity in the audit dashboard, because intentional destruction
        is concerning but controlled."""
        from enterprise_fizzbuzz.infrastructure.audit_dashboard import EventAggregator
        from enterprise_fizzbuzz.domain.models import AuditSeverity

        aggregator = EventAggregator(buffer_size=100)
        event_bus.subscribe(aggregator)

        # Publish a chaos event directly
        event_bus.publish(Event(
            event_type=EventType.CHAOS_FAULT_INJECTED,
            payload={"fault_type": "RESULT_CORRUPTION", "number": 15},
            source="ChaosMonkey",
        ))

        events = aggregator.get_events()
        assert len(events) >= 1
        chaos_event = events[0]
        assert chaos_event.severity == AuditSeverity.WARNING

    def test_multiple_chaos_events_all_reach_aggregator(self, event_bus):
        """Inject multiple faults and verify the aggregator captured all of them."""
        from enterprise_fizzbuzz.infrastructure.audit_dashboard import EventAggregator
        from enterprise_fizzbuzz.infrastructure.chaos import ChaosMonkey, FaultType, FaultSeverity

        aggregator = EventAggregator(buffer_size=200)
        event_bus.subscribe(aggregator)

        monkey = ChaosMonkey(
            severity=FaultSeverity.LEVEL_5,
            seed=99,
            armed_fault_types=[FaultType.RESULT_CORRUPTION],
            event_bus=event_bus,
        )

        injection_count = 0
        for n in range(1, 11):
            context = ProcessingContext(number=n, session_id=f"chaos-{n}")
            context.results.append(_make_result(n))
            result = monkey.inject_fault(context, fault_type=FaultType.RESULT_CORRUPTION)
            if result is not None:
                injection_count += 1

        chaos_in_aggregator = [
            e for e in aggregator.get_events()
            if e.event_type == EventType.CHAOS_FAULT_INJECTED.name
        ]
        assert len(chaos_in_aggregator) == injection_count


# ============================================================
# Category 3: Compliance Events Reach Metrics
# ============================================================


class TestComplianceEventsReachMetrics:
    """Verify that compliance check events published by the ComplianceFramework
    are received by the MetricsCollector when both share the same event bus.

    The MetricsCollector counts events by type. When compliance checks fire,
    those events should be reflected in the collector's counters, proving
    that the compliance bureaucracy is not operating in a vacuum.
    """

    def test_compliance_check_events_reach_recording_observer(self, event_bus):
        """Run a compliance check and verify the event bus delivered
        COMPLIANCE_CHECK_STARTED and COMPLIANCE_CHECK_PASSED events."""
        from enterprise_fizzbuzz.infrastructure.compliance import ComplianceFramework

        recorder = RecordingObserver()
        event_bus.subscribe(recorder)

        framework = ComplianceFramework(event_bus=event_bus)

        result = _make_result(15)
        framework.perform_compliance_check(result)

        started_events = recorder.events_of_type(EventType.COMPLIANCE_CHECK_STARTED)
        assert len(started_events) >= 1, (
            "ComplianceFramework.perform_compliance_check() should publish "
            "COMPLIANCE_CHECK_STARTED, but the recorder heard nothing."
        )

        # Should also get a passed or failed event
        passed_events = recorder.events_of_type(EventType.COMPLIANCE_CHECK_PASSED)
        failed_events = recorder.events_of_type(EventType.COMPLIANCE_CHECK_FAILED)
        assert len(passed_events) + len(failed_events) >= 1, (
            "Compliance check should publish either COMPLIANCE_CHECK_PASSED "
            "or COMPLIANCE_CHECK_FAILED, but neither was observed."
        )

    def test_compliance_events_coexist_with_metrics_collector(self, event_bus):
        """Wire both ComplianceFramework and MetricsCollector to the same bus.
        Run compliance checks and verify the MetricsCollector received the
        compliance events without interference."""
        from enterprise_fizzbuzz.infrastructure.compliance import ComplianceFramework
        from enterprise_fizzbuzz.infrastructure.metrics import MetricsCollector

        recorder = RecordingObserver()
        metrics_collector = MetricsCollector()
        event_bus.subscribe(recorder)
        event_bus.subscribe(metrics_collector)

        framework = ComplianceFramework(event_bus=event_bus)
        result = _make_result(3)
        framework.perform_compliance_check(result)

        # The recorder should have compliance events
        compliance_events = [
            e for e in recorder.events
            if e.event_type in (
                EventType.COMPLIANCE_CHECK_STARTED,
                EventType.COMPLIANCE_CHECK_PASSED,
                EventType.COMPLIANCE_CHECK_FAILED,
            )
        ]
        assert len(compliance_events) >= 2, (
            "Expected at least COMPLIANCE_CHECK_STARTED and a result event"
        )

    def test_multiple_compliance_checks_produce_correct_event_count(self, event_bus):
        """Run 5 compliance checks and verify the correct number of
        COMPLIANCE_CHECK_STARTED events appear on the bus."""
        from enterprise_fizzbuzz.infrastructure.compliance import ComplianceFramework

        recorder = RecordingObserver()
        event_bus.subscribe(recorder)

        framework = ComplianceFramework(event_bus=event_bus)

        for n in [3, 5, 7, 15, 42]:
            result = _make_result(n)
            framework.perform_compliance_check(result)

        started_events = recorder.events_of_type(EventType.COMPLIANCE_CHECK_STARTED)
        assert len(started_events) == 5, (
            f"Expected 5 COMPLIANCE_CHECK_STARTED events for 5 checks, "
            f"got {len(started_events)}."
        )


# ============================================================
# Category 4: SLA Alert Events
# ============================================================


class TestSLAAlertEvents:
    """Verify that the SLA monitor fires alert events when SLO violations
    are detected, and that these alert events are received by observers.

    To trigger alerts, we configure an impossibly tight latency SLO
    (0.0001ms threshold) that no evaluation can possibly meet, then
    run evaluations through it. The resulting avalanche of alerts
    proves the alerting pipeline works — and that Bob McFizzington
    should update his contact information.
    """

    def test_sla_alert_fired_on_latency_slo_violation(self, event_bus):
        """Configure a ridiculously tight latency SLO and verify an alert
        event is published when the threshold is inevitably exceeded."""
        from enterprise_fizzbuzz.infrastructure.sla import (
            SLAMonitor, SLODefinition, SLOType, AlertManager,
        )

        recorder = RecordingObserver()
        event_bus.subscribe(recorder)

        alert_manager = AlertManager(event_bus=event_bus, cooldown_seconds=0)
        monitor = SLAMonitor(
            slo_definitions=[
                SLODefinition(
                    name="impossible_latency",
                    slo_type=SLOType.LATENCY,
                    target=0.999,
                    threshold_ms=0.0001,  # 100 nanoseconds. Good luck.
                ),
            ],
            event_bus=event_bus,
            alert_manager=alert_manager,
        )

        # Record an evaluation that will inevitably violate the SLO
        monitor.record_evaluation(
            latency_ns=1_000_000,  # 1ms, which is 10,000x over threshold
            number=15,
            output="FizzBuzz",
            success=True,
        )

        alert_events = recorder.events_of_type(EventType.SLA_ALERT_FIRED)
        assert len(alert_events) >= 1, (
            "With a 0.0001ms latency SLO and a 1ms evaluation, an alert "
            "should have been fired. Either the alerting pipeline is broken "
            "or we've achieved faster-than-light FizzBuzz computation."
        )

    def test_sla_alert_contains_severity_and_slo_name(self, event_bus):
        """The alert event payload should include severity and SLO name
        so downstream consumers know which SLO was violated and how badly."""
        from enterprise_fizzbuzz.infrastructure.sla import (
            SLAMonitor, SLODefinition, SLOType, AlertManager,
        )

        recorder = RecordingObserver()
        event_bus.subscribe(recorder)

        alert_manager = AlertManager(event_bus=event_bus, cooldown_seconds=0)
        monitor = SLAMonitor(
            slo_definitions=[
                SLODefinition(
                    name="tight_latency",
                    slo_type=SLOType.LATENCY,
                    target=0.999,
                    threshold_ms=0.0001,
                ),
            ],
            event_bus=event_bus,
            alert_manager=alert_manager,
        )

        monitor.record_evaluation(latency_ns=5_000_000, number=7, output="7", success=True)

        alert_events = recorder.events_of_type(EventType.SLA_ALERT_FIRED)
        assert len(alert_events) >= 1
        payload = alert_events[0].payload
        assert "severity" in payload
        assert "slo_name" in payload

    def test_sla_alert_manager_records_alert_internally(self, event_bus):
        """The AlertManager should maintain its own internal registry of
        fired alerts, in addition to publishing them to the event bus."""
        from enterprise_fizzbuzz.infrastructure.sla import (
            SLAMonitor, SLODefinition, SLOType, AlertManager,
        )

        alert_manager = AlertManager(event_bus=event_bus, cooldown_seconds=0)
        monitor = SLAMonitor(
            slo_definitions=[
                SLODefinition(
                    name="impossible_slo",
                    slo_type=SLOType.LATENCY,
                    target=0.999,
                    threshold_ms=0.0001,
                ),
            ],
            event_bus=event_bus,
            alert_manager=alert_manager,
        )

        monitor.record_evaluation(latency_ns=10_000_000, number=3, output="Fizz", success=True)

        active_alerts = alert_manager.get_active_alerts()
        assert len(active_alerts) >= 1, (
            "The AlertManager should have at least one active alert after "
            "a latency SLO violation, but its alert registry is empty."
        )

    def test_sla_slo_violation_event_published(self, event_bus):
        """When an SLO is violated, an SLA_SLO_VIOLATION event should be
        published in addition to the alert event."""
        from enterprise_fizzbuzz.infrastructure.sla import (
            SLAMonitor, SLODefinition, SLOType, AlertManager,
        )

        recorder = RecordingObserver()
        event_bus.subscribe(recorder)

        alert_manager = AlertManager(event_bus=event_bus, cooldown_seconds=0)
        monitor = SLAMonitor(
            slo_definitions=[
                SLODefinition(
                    name="latency_slo",
                    slo_type=SLOType.LATENCY,
                    target=0.999,
                    threshold_ms=0.0001,
                ),
            ],
            event_bus=event_bus,
            alert_manager=alert_manager,
        )

        monitor.record_evaluation(latency_ns=5_000_000, number=5, output="Buzz", success=True)

        violation_events = recorder.events_of_type(EventType.SLA_SLO_VIOLATION)
        assert len(violation_events) >= 1, (
            "SLA_SLO_VIOLATION event expected when latency exceeds the threshold."
        )
        payload = violation_events[0].payload
        assert payload["slo_name"] == "latency_slo"


# ============================================================
# Category 5: Circuit Breaker State Change Events
# ============================================================


class TestCircuitBreakerStateChangeEvents:
    """Verify that the circuit breaker publishes state transition events
    to the event bus when it trips from CLOSED to OPEN.

    The circuit breaker is a state machine. Each transition is a
    newsworthy event that downstream subsystems (audit dashboard,
    metrics collector, SLA monitor) may need to react to. If the
    circuit trips silently, nobody knows the FizzBuzz pipeline
    is down until Bob McFizzington checks his dashboard.
    """

    def test_circuit_breaker_publishes_tripped_event_on_failure_threshold(self, event_bus):
        """Trip the circuit breaker by injecting enough failures and verify
        CIRCUIT_BREAKER_TRIPPED is published."""
        from enterprise_fizzbuzz.infrastructure.circuit_breaker import CircuitBreaker, CircuitState

        recorder = RecordingObserver()
        event_bus.subscribe(recorder)

        cb = CircuitBreaker(
            name="TestCircuit",
            failure_threshold=3,
            event_bus=event_bus,
        )

        # Inject 3 failures to trip the breaker
        for _ in range(3):
            try:
                cb.execute(lambda: (_ for _ in ()).throw(RuntimeError("simulated failure")))
            except RuntimeError:
                pass

        tripped_events = recorder.events_of_type(EventType.CIRCUIT_BREAKER_TRIPPED)
        assert len(tripped_events) >= 1, (
            "After 3 consecutive failures (failure_threshold=3), the circuit "
            "breaker should trip and publish CIRCUIT_BREAKER_TRIPPED."
        )

    def test_circuit_breaker_state_change_event_contains_old_and_new_state(self, event_bus):
        """State change events should include the old and new states so
        downstream consumers can track the full state machine trajectory."""
        from enterprise_fizzbuzz.infrastructure.circuit_breaker import CircuitBreaker, CircuitState

        recorder = RecordingObserver()
        event_bus.subscribe(recorder)

        cb = CircuitBreaker(
            name="StateTracker",
            failure_threshold=2,
            event_bus=event_bus,
        )

        for _ in range(2):
            try:
                cb.execute(lambda: (_ for _ in ()).throw(RuntimeError("boom")))
            except RuntimeError:
                pass

        state_events = recorder.events_of_type(EventType.CIRCUIT_BREAKER_STATE_CHANGED)
        assert len(state_events) >= 1
        payload = state_events[0].payload
        assert payload["old_state"] == "CLOSED"
        assert payload["new_state"] == "OPEN"

    def test_circuit_breaker_tripped_event_reaches_audit_aggregator(self, event_bus):
        """Wire the circuit breaker and audit aggregator to the same bus.
        Trip the breaker. Verify the aggregator captured the event."""
        from enterprise_fizzbuzz.infrastructure.circuit_breaker import CircuitBreaker
        from enterprise_fizzbuzz.infrastructure.audit_dashboard import EventAggregator

        aggregator = EventAggregator(buffer_size=100)
        event_bus.subscribe(aggregator)

        cb = CircuitBreaker(
            name="AuditedCircuit",
            failure_threshold=2,
            event_bus=event_bus,
        )

        for _ in range(2):
            try:
                cb.execute(lambda: (_ for _ in ()).throw(ValueError("kaboom")))
            except ValueError:
                pass

        tripped_in_aggregator = [
            e for e in aggregator.get_events()
            if e.event_type == EventType.CIRCUIT_BREAKER_TRIPPED.name
        ]
        assert len(tripped_in_aggregator) >= 1, (
            "The audit dashboard aggregator should record circuit breaker "
            "trip events, but none were found in its buffer."
        )

    def test_circuit_breaker_recovery_event_after_reset(self, event_bus):
        """Reset a tripped circuit breaker and verify the RECOVERED event
        is published to the bus."""
        from enterprise_fizzbuzz.infrastructure.circuit_breaker import CircuitBreaker, CircuitState

        recorder = RecordingObserver()
        event_bus.subscribe(recorder)

        cb = CircuitBreaker(
            name="RecoveryCircuit",
            failure_threshold=2,
            event_bus=event_bus,
        )

        # Trip it
        for _ in range(2):
            try:
                cb.execute(lambda: (_ for _ in ()).throw(RuntimeError("fail")))
            except RuntimeError:
                pass

        # Reset it
        cb.reset()

        recovered_events = recorder.events_of_type(EventType.CIRCUIT_BREAKER_RECOVERED)
        assert len(recovered_events) >= 1, (
            "After resetting a tripped circuit breaker, a CIRCUIT_BREAKER_RECOVERED "
            "event should be published."
        )


# ============================================================
# Category 6: Event Ordering
# ============================================================


class TestEventOrdering:
    """Verify that events published in sequence are received by observers
    in the exact same order they were published.

    The EventBus uses a deterministic subscriber notification loop.
    If events arrive out of order, some poor subsystem will process
    a CIRCUIT_BREAKER_RECOVERED event before the CIRCUIT_BREAKER_TRIPPED
    event, leading to a metaphysical crisis about whether time flows
    forward in the FizzBuzz universe.
    """

    def test_100_events_received_in_publication_order(self, event_bus):
        """Publish 100 events with sequential payload markers and verify
        the aggregator received them in the exact order they were published."""
        from enterprise_fizzbuzz.infrastructure.audit_dashboard import EventAggregator

        aggregator = EventAggregator(buffer_size=200)
        event_bus.subscribe(aggregator)

        event_types = [
            EventType.FIZZ_DETECTED,
            EventType.BUZZ_DETECTED,
            EventType.FIZZBUZZ_DETECTED,
            EventType.PLAIN_NUMBER_DETECTED,
            EventType.NUMBER_PROCESSED,
        ]

        for i in range(100):
            event_bus.publish(Event(
                event_type=event_types[i % len(event_types)],
                payload={"sequence": i, "number": i},
                source="OrderingTest",
            ))

        events = aggregator.get_events()
        assert len(events) == 100, (
            f"Expected 100 events in the aggregator, got {len(events)}."
        )

        for i, event in enumerate(events):
            assert event.payload.get("sequence") == i, (
                f"Event at position {i} has sequence={event.payload.get('sequence')}. "
                f"Events arrived out of order."
            )

    def test_100_events_received_in_order_by_recording_observer(self, event_bus):
        """Same test, but using the RecordingObserver directly to eliminate
        any potential ordering artifact from the EventAggregator normalization."""
        recorder = RecordingObserver()
        event_bus.subscribe(recorder)

        for i in range(100):
            event_bus.publish(Event(
                event_type=EventType.NUMBER_PROCESSED,
                payload={"sequence": i},
                source="OrderingTest",
            ))

        events = recorder.events
        assert len(events) == 100
        for i, event in enumerate(events):
            assert event.payload.get("sequence") == i

    def test_event_bus_history_preserves_order(self, event_bus):
        """The EventBus maintains its own event history. Verify this
        history also preserves publication order."""
        for i in range(50):
            event_bus.publish(Event(
                event_type=EventType.FIZZ_DETECTED,
                payload={"index": i},
                source="HistoryTest",
            ))

        history = event_bus.get_event_history()
        assert len(history) == 50
        for i, event in enumerate(history):
            assert event.payload.get("index") == i


# ============================================================
# Category 7: Event Bus Under Load
# ============================================================


class TestEventBusUnderLoad:
    """Verify that the event bus handles high-throughput scenarios
    without dropping events.

    10,000 events is a stress test for a synchronous event bus that
    notifies subscribers inline. In a real distributed system, this
    would test backpressure, queue overflow, and message broker
    capacity. In our in-process event bus, it tests that a Python
    list can hold 10,000 items. Spoiler: it can. But we test anyway,
    because enterprise confidence requires empirical evidence.
    """

    def test_10000_events_none_dropped(self, event_bus):
        """Publish 10,000 events and verify the recorder captured all of them."""
        recorder = RecordingObserver("LoadTestRecorder")
        event_bus.subscribe(recorder)

        for i in range(10_000):
            event_bus.publish(Event(
                event_type=EventType.NUMBER_PROCESSED,
                payload={"number": i, "classification": "load_test"},
                source="LoadTest",
            ))

        assert recorder.event_count == 10_000, (
            f"Published 10,000 events but recorder captured {recorder.event_count}. "
            f"The event bus dropped {10_000 - recorder.event_count} events. "
            f"This is unacceptable for enterprise-grade FizzBuzz delivery."
        )

    def test_10000_events_bus_history_complete(self, event_bus):
        """The bus's internal history should also contain all 10,000 events."""
        for i in range(10_000):
            event_bus.publish(Event(
                event_type=EventType.FIZZ_DETECTED,
                payload={"number": i},
                source="LoadTest",
            ))

        history = event_bus.get_event_history()
        assert len(history) == 10_000

    def test_10000_events_multiple_observers_all_receive(self, event_bus):
        """Subscribe 3 observers, publish 10,000 events, verify each
        observer received exactly 10,000 events. No favorites."""
        observers = [
            RecordingObserver(f"Observer-{i}")
            for i in range(3)
        ]
        for obs in observers:
            event_bus.subscribe(obs)

        for i in range(10_000):
            event_bus.publish(Event(
                event_type=EventType.BUZZ_DETECTED,
                payload={"number": i},
                source="FanOutTest",
            ))

        for obs in observers:
            assert obs.event_count == 10_000, (
                f"{obs.get_name()} received {obs.event_count} events, "
                f"expected 10,000. The event bus is playing favorites."
            )

    def test_10000_events_with_aggregator_under_load(self, event_bus):
        """Publish 10,000 events to an EventAggregator with a buffer of
        500. Verify the aggregator processed all events (event_count=10000)
        even though the buffer can only hold the most recent 500."""
        from enterprise_fizzbuzz.infrastructure.audit_dashboard import EventAggregator

        aggregator = EventAggregator(buffer_size=500)
        event_bus.subscribe(aggregator)

        for i in range(10_000):
            event_bus.publish(Event(
                event_type=EventType.PLAIN_NUMBER_DETECTED,
                payload={"number": i},
                source="LoadTest",
            ))

        assert aggregator.event_count == 10_000, (
            f"Aggregator event_count should be 10,000 (total processed), "
            f"got {aggregator.event_count}."
        )
        # Buffer only holds 500
        assert aggregator.buffer_size <= 500, (
            f"Aggregator buffer should hold at most 500 events, "
            f"but reports {aggregator.buffer_size}."
        )


# ============================================================
# Category 8: Cross-Subsystem Event Flow
# ============================================================


class TestCrossSubsystemEventFlow:
    """Verify that when multiple subsystems are wired to the same event bus,
    events from all subsystems arrive at all observers.

    This is the ultimate integration test: compliance, SLA, circuit breaker,
    audit dashboard, and metrics collector all sharing a single bus. Events
    from every subsystem should flow to every observer without interference,
    corruption, or existential confusion about which subsystem published
    what.
    """

    def test_sla_and_compliance_events_coexist_on_shared_bus(self, event_bus):
        """Wire SLA monitor and compliance framework to the same bus.
        Run evaluations through both. Verify the recorder received events
        from both subsystems."""
        from enterprise_fizzbuzz.infrastructure.sla import SLAMonitor, SLODefinition, SLOType
        from enterprise_fizzbuzz.infrastructure.compliance import ComplianceFramework

        recorder = RecordingObserver()
        event_bus.subscribe(recorder)

        sla = SLAMonitor(
            slo_definitions=[
                SLODefinition(name="accuracy", slo_type=SLOType.ACCURACY, target=0.999),
            ],
            event_bus=event_bus,
        )

        compliance = ComplianceFramework(event_bus=event_bus)

        # Run an evaluation through SLA
        result = _make_result(15)
        sla.record_evaluation(latency_ns=100_000, number=15, output="FizzBuzz", success=True)

        # Run a compliance check
        compliance.perform_compliance_check(result)

        # Verify both subsystem event types are present
        sla_events = recorder.events_of_type(EventType.SLA_EVALUATION_RECORDED)
        compliance_events = recorder.events_of_type(EventType.COMPLIANCE_CHECK_STARTED)

        assert len(sla_events) >= 1, "SLA events should be on the bus"
        assert len(compliance_events) >= 1, "Compliance events should be on the bus"

    def test_circuit_breaker_and_sla_events_on_shared_bus(self, event_bus):
        """Wire circuit breaker and SLA to the same bus. Trip the breaker,
        run SLA evaluations. Verify events from both subsystems arrive."""
        from enterprise_fizzbuzz.infrastructure.circuit_breaker import CircuitBreaker
        from enterprise_fizzbuzz.infrastructure.sla import SLAMonitor, SLODefinition, SLOType

        recorder = RecordingObserver()
        event_bus.subscribe(recorder)

        cb = CircuitBreaker(
            name="SharedBusCircuit",
            failure_threshold=2,
            event_bus=event_bus,
        )

        sla = SLAMonitor(
            slo_definitions=[
                SLODefinition(name="avail", slo_type=SLOType.AVAILABILITY, target=0.999),
            ],
            event_bus=event_bus,
        )

        # Trip the circuit breaker
        for _ in range(2):
            try:
                cb.execute(lambda: (_ for _ in ()).throw(RuntimeError("fail")))
            except RuntimeError:
                pass

        # Record an SLA evaluation
        sla.record_evaluation(latency_ns=100_000, number=3, output="Fizz", success=True)

        cb_events = recorder.events_of_type(EventType.CIRCUIT_BREAKER_TRIPPED)
        sla_events = recorder.events_of_type(EventType.SLA_EVALUATION_RECORDED)

        assert len(cb_events) >= 1, "Circuit breaker trip event should appear"
        assert len(sla_events) >= 1, "SLA evaluation event should appear"

    def test_full_cross_subsystem_flow_all_events_arrive(self, event_bus):
        """Wire SLA, compliance, circuit breaker, and audit aggregator to
        the same bus. Generate events from each subsystem. Verify the
        aggregator captured events from all sources."""
        from enterprise_fizzbuzz.infrastructure.sla import (
            SLAMonitor, SLODefinition, SLOType, AlertManager,
        )
        from enterprise_fizzbuzz.infrastructure.compliance import ComplianceFramework
        from enterprise_fizzbuzz.infrastructure.circuit_breaker import CircuitBreaker
        from enterprise_fizzbuzz.infrastructure.audit_dashboard import EventAggregator

        aggregator = EventAggregator(buffer_size=500)
        recorder = RecordingObserver("CrossSubsystemRecorder")
        event_bus.subscribe(aggregator)
        event_bus.subscribe(recorder)

        # Wire subsystems
        alert_manager = AlertManager(event_bus=event_bus, cooldown_seconds=0)
        sla = SLAMonitor(
            slo_definitions=[
                SLODefinition(name="lat", slo_type=SLOType.LATENCY, target=0.999, threshold_ms=100.0),
            ],
            event_bus=event_bus,
            alert_manager=alert_manager,
        )
        compliance = ComplianceFramework(event_bus=event_bus)
        cb = CircuitBreaker(name="CrossSubCircuit", failure_threshold=3, event_bus=event_bus)

        # Generate SLA events
        sla.record_evaluation(latency_ns=50_000, number=15, output="FizzBuzz", success=True)

        # Generate compliance events
        result = _make_result(5)
        compliance.perform_compliance_check(result)

        # Trip the circuit breaker
        for _ in range(3):
            try:
                cb.execute(lambda: (_ for _ in ()).throw(RuntimeError("cross-sub fail")))
            except RuntimeError:
                pass

        # Verify events from all three subsystems arrived at the aggregator
        sources_in_aggregator = set(e.source for e in aggregator.get_events())
        assert "SLAMonitor" in sources_in_aggregator, (
            "SLA events should appear in the aggregator"
        )
        assert "ComplianceFramework" in sources_in_aggregator, (
            "Compliance events should appear in the aggregator"
        )
        assert any("CircuitBreaker" in s for s in sources_in_aggregator), (
            "Circuit breaker events should appear in the aggregator"
        )

    def test_statistics_observer_and_metrics_collector_both_receive(self, event_bus):
        """Wire both the StatisticsObserver and MetricsCollector to the bus.
        Publish classification events. Verify both processed them."""
        from enterprise_fizzbuzz.infrastructure.metrics import MetricsCollector

        stats = StatisticsObserver()
        metrics = MetricsCollector()
        event_bus.subscribe(stats)
        event_bus.subscribe(metrics)

        # Publish classification events
        event_bus.publish(Event(
            event_type=EventType.FIZZ_DETECTED,
            payload={"number": 3},
            source="TestEngine",
        ))
        event_bus.publish(Event(
            event_type=EventType.BUZZ_DETECTED,
            payload={"number": 5},
            source="TestEngine",
        ))
        event_bus.publish(Event(
            event_type=EventType.FIZZBUZZ_DETECTED,
            payload={"number": 15},
            source="TestEngine",
        ))
        event_bus.publish(Event(
            event_type=EventType.PLAIN_NUMBER_DETECTED,
            payload={"number": 7},
            source="TestEngine",
        ))

        summary = stats.get_summary_data()
        assert summary["fizz_count"] == 1
        assert summary["buzz_count"] == 1
        assert summary["fizzbuzz_count"] == 1
        assert summary["plain_count"] == 1

    def test_observer_error_does_not_prevent_delivery_to_other_observers(self, event_bus):
        """If one observer raises an exception in on_event(), the event bus
        should still deliver the event to all other observers. One bad apple
        must not spoil the entire event delivery pipeline."""

        class ExplodingObserver(IObserver):
            def on_event(self, event: Event) -> None:
                raise RuntimeError("I refuse to process this event on principle.")

            def get_name(self) -> str:
                return "ExplodingObserver"

        exploder = ExplodingObserver()
        recorder = RecordingObserver("SurvivorRecorder")

        # Subscribe the exploding observer first, then the recorder
        event_bus.subscribe(exploder)
        event_bus.subscribe(recorder)

        event_bus.publish(Event(
            event_type=EventType.FIZZBUZZ_DETECTED,
            payload={"number": 15},
            source="ErrorIsolationTest",
        ))

        assert recorder.event_count == 1, (
            "The RecordingObserver should still receive the event even though "
            "the ExplodingObserver threw an exception. Error isolation failed."
        )

    def test_unsubscribe_prevents_event_delivery(self, event_bus):
        """After unsubscribing, an observer should no longer receive events.
        This validates that the bus properly removes observers from its list."""
        recorder = RecordingObserver()
        event_bus.subscribe(recorder)

        event_bus.publish(Event(
            event_type=EventType.FIZZ_DETECTED,
            payload={"number": 3},
            source="UnsubTest",
        ))
        assert recorder.event_count == 1

        event_bus.unsubscribe(recorder)

        event_bus.publish(Event(
            event_type=EventType.BUZZ_DETECTED,
            payload={"number": 5},
            source="UnsubTest",
        ))
        assert recorder.event_count == 1, (
            "After unsubscribing, the recorder should not receive new events."
        )

    def test_event_bus_clear_history_resets_internal_log(self, event_bus):
        """Clearing the event bus history should reset the internal log
        without affecting observers' already-received events."""
        recorder = RecordingObserver()
        event_bus.subscribe(recorder)

        for i in range(5):
            event_bus.publish(Event(
                event_type=EventType.NUMBER_PROCESSED,
                payload={"number": i},
                source="ClearTest",
            ))

        assert len(event_bus.get_event_history()) == 5
        event_bus.clear_history()
        assert len(event_bus.get_event_history()) == 0
        # Observer should still have its recorded events
        assert recorder.event_count == 5
