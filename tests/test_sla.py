"""
Enterprise FizzBuzz Platform - SLA Monitoring Test Suite

Comprehensive tests for the SLA Monitoring and PagerDuty-Style
Alerting subsystem. Because even the system that monitors whether
FizzBuzz is working correctly needs to be tested to ensure it
correctly monitors whether FizzBuzz is working correctly.

Meta-testing: it's turtles all the way down.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from config import ConfigurationManager, _SingletonMeta
from exceptions import (
    SLIBudgetExhaustionError,
    SLIDefinitionError,
    SLIError,
    SLIFeatureGateError,
)
from models import Event, EventType, ProcessingContext, FizzBuzzResult
from observers import EventBus
from sla import (
    Alert,
    AlertManager,
    AlertSeverity,
    AlertStatus,
    AttributionCategory,
    BudgetAttributor,
    BudgetTier,
    BurnRateAlert,
    BurnRateCalculator,
    ErrorBudget,
    ErrorBudgetPolicy,
    EscalationPolicy,
    OnCallSchedule,
    SLADashboard,
    SLAMiddleware,
    SLAMonitor,
    SLIDashboard,
    SLIDefinition,
    SLIEvent,
    SLIFeatureGate,
    SLIMiddleware,
    SLIRegistry,
    SLIType,
    SLODefinition,
    SLOMetricCollector,
    SLOType,
    bootstrap_sli_registry,
    create_default_slis,
)


# ============================================================
# Fixtures
# ============================================================


@pytest.fixture(autouse=True)
def reset_singletons():
    """Reset singletons between tests."""
    _SingletonMeta.reset()
    yield


@pytest.fixture
def event_bus() -> EventBus:
    return EventBus()


@pytest.fixture
def collector() -> SLOMetricCollector:
    return SLOMetricCollector()


@pytest.fixture
def latency_slo() -> SLODefinition:
    return SLODefinition(
        name="latency",
        slo_type=SLOType.LATENCY,
        target=0.999,
        threshold_ms=100.0,
    )


@pytest.fixture
def accuracy_slo() -> SLODefinition:
    return SLODefinition(
        name="accuracy",
        slo_type=SLOType.ACCURACY,
        target=0.99999,
    )


@pytest.fixture
def availability_slo() -> SLODefinition:
    return SLODefinition(
        name="availability",
        slo_type=SLOType.AVAILABILITY,
        target=0.9999,
    )


@pytest.fixture
def all_slos(latency_slo, accuracy_slo, availability_slo) -> list[SLODefinition]:
    return [latency_slo, accuracy_slo, availability_slo]


@pytest.fixture
def sla_monitor(all_slos, event_bus) -> SLAMonitor:
    return SLAMonitor(
        slo_definitions=all_slos,
        event_bus=event_bus,
        burn_rate_threshold=2.0,
    )


# ============================================================
# SLOType Enum Tests
# ============================================================


class TestSLOType:
    def test_has_three_types(self):
        assert len(SLOType) == 3

    def test_latency_exists(self):
        assert SLOType.LATENCY.name == "LATENCY"

    def test_accuracy_exists(self):
        assert SLOType.ACCURACY.name == "ACCURACY"

    def test_availability_exists(self):
        assert SLOType.AVAILABILITY.name == "AVAILABILITY"


# ============================================================
# AlertSeverity Enum Tests
# ============================================================


class TestAlertSeverity:
    def test_has_four_levels(self):
        assert len(AlertSeverity) == 4

    def test_p1_is_critical(self):
        assert AlertSeverity.P1.label == "CRITICAL"

    def test_p2_is_high(self):
        assert AlertSeverity.P2.label == "HIGH"

    def test_p3_is_medium(self):
        assert AlertSeverity.P3.label == "MEDIUM"

    def test_p4_is_low(self):
        assert AlertSeverity.P4.label == "LOW"


# ============================================================
# AlertStatus Enum Tests
# ============================================================


class TestAlertStatus:
    def test_has_three_statuses(self):
        assert len(AlertStatus) == 3

    def test_firing_exists(self):
        assert AlertStatus.FIRING.name == "FIRING"

    def test_acknowledged_exists(self):
        assert AlertStatus.ACKNOWLEDGED.name == "ACKNOWLEDGED"

    def test_resolved_exists(self):
        assert AlertStatus.RESOLVED.name == "RESOLVED"


# ============================================================
# SLODefinition Tests
# ============================================================


class TestSLODefinition:
    def test_is_frozen(self, latency_slo):
        with pytest.raises(AttributeError):
            latency_slo.name = "modified"  # type: ignore

    def test_latency_slo_has_threshold(self, latency_slo):
        assert latency_slo.threshold_ms == 100.0

    def test_accuracy_slo_target(self, accuracy_slo):
        assert accuracy_slo.target == 0.99999

    def test_availability_slo_type(self, availability_slo):
        assert availability_slo.slo_type == SLOType.AVAILABILITY


# ============================================================
# SLOMetricCollector Tests
# ============================================================


class TestSLOMetricCollector:
    def test_empty_collector_returns_perfect_compliance(self, collector):
        assert collector.get_latency_compliance(100.0) == 1.0
        assert collector.get_accuracy_compliance() == 1.0
        assert collector.get_availability_compliance() == 1.0

    def test_record_latency(self, collector):
        collector.record_latency(50_000_000)  # 50ms
        assert collector.get_total_evaluations() == 1

    def test_latency_compliance_all_under_threshold(self, collector):
        for _ in range(10):
            collector.record_latency(50_000_000)  # 50ms
        assert collector.get_latency_compliance(100.0) == 1.0

    def test_latency_compliance_some_over_threshold(self, collector):
        for _ in range(9):
            collector.record_latency(50_000_000)  # 50ms under threshold
        collector.record_latency(200_000_000)  # 200ms over threshold
        compliance = collector.get_latency_compliance(100.0)
        assert compliance == 0.9

    def test_accuracy_compliance_all_correct(self, collector):
        for _ in range(10):
            collector.record_accuracy(True)
        assert collector.get_accuracy_compliance() == 1.0

    def test_accuracy_compliance_some_incorrect(self, collector):
        for _ in range(8):
            collector.record_accuracy(True)
        for _ in range(2):
            collector.record_accuracy(False)
        assert collector.get_accuracy_compliance() == 0.8

    def test_availability_compliance(self, collector):
        for _ in range(9):
            collector.record_availability(True)
        collector.record_availability(False)
        assert collector.get_availability_compliance() == 0.9

    def test_total_failures(self, collector):
        collector.record_availability(True)
        collector.record_availability(False)
        collector.record_availability(False)
        assert collector.get_total_failures() == 2

    def test_total_inaccuracies(self, collector):
        collector.record_accuracy(True)
        collector.record_accuracy(False)
        assert collector.get_total_inaccuracies() == 1

    def test_p50_latency(self, collector):
        for i in range(1, 101):
            collector.record_latency(i * 1_000_000)  # 1ms to 100ms
        p50 = collector.get_p50_latency_ms()
        assert 49.0 <= p50 <= 51.0

    def test_p99_latency(self, collector):
        for i in range(1, 101):
            collector.record_latency(i * 1_000_000)
        p99 = collector.get_p99_latency_ms()
        assert p99 >= 98.0

    def test_reset(self, collector):
        collector.record_latency(50_000_000)
        collector.record_accuracy(True)
        collector.record_availability(True)
        collector.reset()
        assert collector.get_total_evaluations() == 0

    def test_p50_empty(self, collector):
        assert collector.get_p50_latency_ms() == 0.0


# ============================================================
# ErrorBudget Tests
# ============================================================


class TestErrorBudget:
    def test_initial_state(self):
        budget = ErrorBudget(name="test", target=0.999, window_days=30)
        assert budget.name == "test"
        assert budget.target == 0.999
        assert budget.window_days == 30

    def test_record_good_event_does_not_consume_budget(self):
        budget = ErrorBudget(name="test", target=0.999)
        budget.record_event(bad=False)
        assert budget.get_consumed() == 0.0

    def test_record_bad_event_consumes_budget(self):
        budget = ErrorBudget(name="test", target=0.999)
        budget.record_event(bad=True)
        consumed = budget.get_consumed()
        assert consumed > 0.0

    def test_budget_exhaustion(self):
        budget = ErrorBudget(name="test", target=0.9)
        # 10% error budget. With 10 events, budget = 1 event.
        for _ in range(9):
            budget.record_event(bad=False)
        # Add 2 bad events to guarantee exhaustion even with float imprecision
        budget.record_event(bad=True)
        budget.record_event(bad=True)
        assert budget.is_exhausted()

    def test_budget_not_exhausted(self):
        budget = ErrorBudget(name="test", target=0.99)
        for _ in range(100):
            budget.record_event(bad=False)
        assert not budget.is_exhausted()

    def test_remaining(self):
        budget = ErrorBudget(name="test", target=0.999)
        for _ in range(10):
            budget.record_event(bad=False)
        remaining = budget.get_remaining()
        assert remaining == 1.0  # No bad events = 100% remaining

    def test_burn_rate_zero_when_no_failures(self):
        budget = ErrorBudget(name="test", target=0.999)
        budget.record_event(bad=False)
        assert budget.get_burn_rate() == 0.0

    def test_burn_rate_one_at_ideal(self):
        budget = ErrorBudget(name="test", target=0.999)
        # Ideal: 0.1% failure rate
        for _ in range(999):
            budget.record_event(bad=False)
        budget.record_event(bad=True)
        burn_rate = budget.get_burn_rate()
        assert 0.9 <= burn_rate <= 1.1  # approximately 1.0

    def test_burn_rate_high_when_many_failures(self):
        budget = ErrorBudget(name="test", target=0.999)
        for _ in range(90):
            budget.record_event(bad=False)
        for _ in range(10):
            budget.record_event(bad=True)
        assert budget.get_burn_rate() > 1.0

    def test_status_dict(self):
        budget = ErrorBudget(name="test", target=0.999, window_days=30)
        budget.record_event(bad=False)
        status = budget.get_status()
        assert status["name"] == "test"
        assert status["target"] == 0.999
        assert "consumed" in status
        assert "remaining" in status
        assert "burn_rate" in status

    def test_burn_rate_no_events(self):
        budget = ErrorBudget(name="test", target=0.999)
        assert budget.get_burn_rate() == 0.0

    def test_projected_exhaustion_no_failures(self):
        budget = ErrorBudget(name="test", target=0.999)
        budget.record_event(bad=False)
        assert budget.get_projected_exhaustion_evaluations() is None


# ============================================================
# OnCallSchedule Tests
# ============================================================


class TestOnCallSchedule:
    def test_default_team_name(self):
        schedule = OnCallSchedule()
        assert schedule.team_name == "FizzBuzz Reliability Engineering"

    def test_current_on_call_returns_bob(self):
        schedule = OnCallSchedule()
        on_call = schedule.get_current_on_call()
        assert on_call["name"] == "Bob McFizzington"
        assert "email" in on_call
        assert "phone" in on_call

    def test_on_call_always_returns_same_person_for_team_of_one(self):
        schedule = OnCallSchedule()
        # Call multiple times — same person every time
        for _ in range(10):
            assert schedule.get_current_on_call()["name"] == "Bob McFizzington"

    def test_escalation_contacts_all_same_person(self):
        schedule = OnCallSchedule()
        contacts = schedule.get_escalation_contacts()
        assert len(contacts) == 4
        names = {c["name"] for c in contacts}
        assert len(names) == 1  # All the same person

    def test_escalation_levels(self):
        schedule = OnCallSchedule()
        contacts = schedule.get_escalation_contacts()
        levels = [c["level"] for c in contacts]
        assert levels == ["L1", "L2", "L3", "L4"]

    def test_escalation_titles_get_more_dramatic(self):
        schedule = OnCallSchedule()
        contacts = schedule.get_escalation_contacts()
        # L1 is humble, L4 is dramatic
        assert "On-Call Engineer" in contacts[0]["title"]
        assert "VP" in contacts[3]["title"]

    def test_custom_team(self):
        schedule = OnCallSchedule(
            team_name="Custom Team",
            engineers=[{"name": "Alice", "email": "a@b.com", "phone": "123", "title": "Eng"}],
        )
        assert schedule.team_name == "Custom Team"
        assert schedule.get_current_on_call()["name"] == "Alice"

    def test_empty_engineers_raises(self):
        from exceptions import OnCallNotFoundError
        with pytest.raises(OnCallNotFoundError):
            OnCallSchedule(engineers=[])

    def test_schedule_info(self):
        schedule = OnCallSchedule()
        info = schedule.get_schedule_info()
        assert info["team_size"] == 1
        assert info["total_unique_engineers"] == 1
        assert info["diversity_index"] == 0.0


# ============================================================
# EscalationPolicy Tests
# ============================================================


class TestEscalationPolicy:
    def test_p1_actions(self):
        actions = EscalationPolicy.get_actions(AlertSeverity.P1)
        assert "PAGE" in actions["action"]
        assert "5 minutes" in actions["response_time"]

    def test_p4_actions(self):
        actions = EscalationPolicy.get_actions(AlertSeverity.P4)
        assert "LOG" in actions["action"]
        assert "Next business day" in actions["response_time"]

    def test_all_policies(self):
        policies = EscalationPolicy.get_all_policies()
        assert "CRITICAL" in policies
        assert "HIGH" in policies
        assert "MEDIUM" in policies
        assert "LOW" in policies


# ============================================================
# AlertManager Tests
# ============================================================


class TestAlertManager:
    def test_fire_alert(self):
        mgr = AlertManager(cooldown_seconds=0)
        alert = mgr.fire_alert(AlertSeverity.P1, "latency", "Too slow")
        assert alert is not None
        assert alert.severity == AlertSeverity.P1
        assert alert.slo_name == "latency"
        assert alert.status == AlertStatus.FIRING

    def test_cooldown_suppresses_duplicate(self):
        mgr = AlertManager(cooldown_seconds=3600)
        alert1 = mgr.fire_alert(AlertSeverity.P1, "latency", "Too slow")
        alert2 = mgr.fire_alert(AlertSeverity.P1, "latency", "Still too slow")
        assert alert1 is not None
        assert alert2 is None  # suppressed

    def test_different_slos_not_suppressed(self):
        mgr = AlertManager(cooldown_seconds=3600)
        alert1 = mgr.fire_alert(AlertSeverity.P1, "latency", "Slow")
        alert2 = mgr.fire_alert(AlertSeverity.P2, "accuracy", "Wrong")
        assert alert1 is not None
        assert alert2 is not None

    def test_acknowledge_alert(self):
        mgr = AlertManager(cooldown_seconds=0)
        alert = mgr.fire_alert(AlertSeverity.P1, "latency", "Slow")
        acked = mgr.acknowledge_alert(alert.alert_id)
        assert acked is not None
        assert acked.status == AlertStatus.ACKNOWLEDGED
        assert acked.acknowledged_at is not None

    def test_resolve_alert(self):
        mgr = AlertManager(cooldown_seconds=0)
        alert = mgr.fire_alert(AlertSeverity.P1, "latency", "Slow")
        resolved = mgr.resolve_alert(alert.alert_id)
        assert resolved is not None
        assert resolved.status == AlertStatus.RESOLVED
        assert resolved.resolved_at is not None

    def test_acknowledge_nonexistent(self):
        mgr = AlertManager()
        result = mgr.acknowledge_alert("nonexistent-id")
        assert result is None

    def test_resolve_nonexistent(self):
        mgr = AlertManager()
        result = mgr.resolve_alert("nonexistent-id")
        assert result is None

    def test_active_alerts(self):
        mgr = AlertManager(cooldown_seconds=0)
        mgr.fire_alert(AlertSeverity.P1, "latency", "Slow")
        mgr.fire_alert(AlertSeverity.P2, "accuracy", "Wrong")
        active = mgr.get_active_alerts()
        assert len(active) == 2

    def test_active_alerts_excludes_resolved(self):
        mgr = AlertManager(cooldown_seconds=0)
        alert = mgr.fire_alert(AlertSeverity.P1, "latency", "Slow")
        mgr.resolve_alert(alert.alert_id)
        active = mgr.get_active_alerts()
        assert len(active) == 0

    def test_alert_counts(self):
        mgr = AlertManager(cooldown_seconds=0)
        a1 = mgr.fire_alert(AlertSeverity.P1, "slo1", "msg1")
        a2 = mgr.fire_alert(AlertSeverity.P2, "slo2", "msg2")
        mgr.acknowledge_alert(a1.alert_id)
        mgr.resolve_alert(a2.alert_id)
        counts = mgr.get_alert_counts()
        assert counts["firing"] == 0
        assert counts["acknowledged"] == 1
        assert counts["resolved"] == 1

    def test_fire_alert_publishes_event(self, event_bus):
        mgr = AlertManager(event_bus=event_bus, cooldown_seconds=0)
        mgr.fire_alert(AlertSeverity.P1, "latency", "Slow")
        history = event_bus.get_event_history()
        alert_events = [e for e in history if e.event_type == EventType.SLA_ALERT_FIRED]
        assert len(alert_events) == 1

    def test_resolve_already_resolved(self):
        mgr = AlertManager(cooldown_seconds=0)
        alert = mgr.fire_alert(AlertSeverity.P1, "latency", "Slow")
        mgr.resolve_alert(alert.alert_id)
        result = mgr.resolve_alert(alert.alert_id)
        assert result is None  # Already resolved


# ============================================================
# SLAMonitor Tests
# ============================================================


class TestSLAMonitor:
    def test_record_correct_evaluation(self, sla_monitor):
        sla_monitor.record_evaluation(
            latency_ns=50_000_000,  # 50ms
            number=3,
            output="Fizz",
            success=True,
        )
        assert sla_monitor.collector.get_total_evaluations() == 1

    def test_accuracy_verification_fizz(self, sla_monitor):
        sla_monitor.record_evaluation(
            latency_ns=1_000_000,
            number=3,
            output="Fizz",
            success=True,
        )
        assert sla_monitor.collector.get_accuracy_compliance() == 1.0

    def test_accuracy_verification_buzz(self, sla_monitor):
        sla_monitor.record_evaluation(
            latency_ns=1_000_000,
            number=5,
            output="Buzz",
            success=True,
        )
        assert sla_monitor.collector.get_accuracy_compliance() == 1.0

    def test_accuracy_verification_fizzbuzz(self, sla_monitor):
        sla_monitor.record_evaluation(
            latency_ns=1_000_000,
            number=15,
            output="FizzBuzz",
            success=True,
        )
        assert sla_monitor.collector.get_accuracy_compliance() == 1.0

    def test_accuracy_verification_plain_number(self, sla_monitor):
        sla_monitor.record_evaluation(
            latency_ns=1_000_000,
            number=7,
            output="7",
            success=True,
        )
        assert sla_monitor.collector.get_accuracy_compliance() == 1.0

    def test_accuracy_verification_wrong_output(self, sla_monitor):
        sla_monitor.record_evaluation(
            latency_ns=1_000_000,
            number=3,
            output="Buzz",  # Wrong! 3 should be Fizz
            success=True,
        )
        assert sla_monitor.collector.get_accuracy_compliance() == 0.0

    def test_compliance_summary(self, sla_monitor):
        sla_monitor.record_evaluation(
            latency_ns=1_000_000,
            number=1,
            output="1",
            success=True,
        )
        summary = sla_monitor.get_compliance_summary()
        assert "slos" in summary
        assert "total_evaluations" in summary
        assert summary["total_evaluations"] == 1
        assert "latency" in summary["slos"]
        assert "accuracy" in summary["slos"]
        assert "availability" in summary["slos"]

    def test_slo_violation_triggers_alert(self, all_slos, event_bus):
        # Use an impossibly high accuracy target
        strict_slo = SLODefinition(
            name="strict_accuracy",
            slo_type=SLOType.ACCURACY,
            target=1.0,  # 100% accuracy — any failure = violation
        )
        monitor = SLAMonitor(
            slo_definitions=[strict_slo],
            event_bus=event_bus,
            burn_rate_threshold=2.0,
        )
        # Record a wrong result
        monitor.record_evaluation(
            latency_ns=1_000_000,
            number=3,
            output="Buzz",  # Wrong
            success=True,
        )
        active = monitor.alert_manager.get_active_alerts()
        assert len(active) > 0

    def test_error_budget_tracking(self, sla_monitor):
        for i in range(1, 11):
            sla_monitor.record_evaluation(
                latency_ns=1_000_000,
                number=i,
                output=str(i) if i % 3 != 0 and i % 5 != 0
                    else ("FizzBuzz" if i % 15 == 0 else ("Fizz" if i % 3 == 0 else "Buzz")),
                success=True,
            )
        for budget in sla_monitor.error_budgets.values():
            # All correct, so consumed should be 0
            if budget.name == "accuracy":
                assert budget.get_consumed() == 0.0

    def test_publishes_sla_events(self, sla_monitor, event_bus):
        sla_monitor.record_evaluation(
            latency_ns=1_000_000,
            number=1,
            output="1",
            success=True,
        )
        history = event_bus.get_event_history()
        event_types = {e.event_type for e in history}
        assert EventType.SLA_EVALUATION_RECORDED in event_types
        assert EventType.SLA_SLO_CHECKED in event_types

    def test_on_call_schedule_accessible(self, sla_monitor):
        on_call = sla_monitor.on_call_schedule.get_current_on_call()
        assert on_call["name"] == "Bob McFizzington"


# ============================================================
# SLAMiddleware Tests
# ============================================================


class TestSLAMiddleware:
    def test_middleware_name(self, sla_monitor):
        mw = SLAMiddleware(sla_monitor=sla_monitor)
        assert mw.get_name() == "SLAMiddleware"

    def test_middleware_priority(self, sla_monitor):
        mw = SLAMiddleware(sla_monitor=sla_monitor)
        assert mw.get_priority() == 55

    def test_middleware_records_evaluation(self, sla_monitor):
        mw = SLAMiddleware(sla_monitor=sla_monitor)
        ctx = ProcessingContext(number=3, session_id="test")
        result = FizzBuzzResult(number=3, output="Fizz")
        ctx.results.append(result)

        def handler(c):
            return c

        mw.process(ctx, handler)
        assert sla_monitor.collector.get_total_evaluations() == 1

    def test_middleware_adds_latency_metadata(self, sla_monitor):
        mw = SLAMiddleware(sla_monitor=sla_monitor)
        ctx = ProcessingContext(number=3, session_id="test")

        def handler(c):
            c.results.append(FizzBuzzResult(number=3, output="Fizz"))
            return c

        result = mw.process(ctx, handler)
        assert "sla_latency_ns" in result.metadata
        assert "sla_latency_ms" in result.metadata

    def test_middleware_handles_exception(self, sla_monitor):
        mw = SLAMiddleware(sla_monitor=sla_monitor)
        ctx = ProcessingContext(number=3, session_id="test")

        def handler(c):
            raise RuntimeError("Modulo operator on fire")

        with pytest.raises(RuntimeError):
            mw.process(ctx, handler)

        # Failure should still be recorded
        assert sla_monitor.collector.get_total_evaluations() == 1
        assert sla_monitor.collector.get_availability_compliance() == 0.0


# ============================================================
# SLADashboard Tests
# ============================================================


class TestSLADashboard:
    def test_render_produces_output(self, sla_monitor):
        sla_monitor.record_evaluation(
            latency_ns=1_000_000,
            number=1,
            output="1",
            success=True,
        )
        output = SLADashboard.render(sla_monitor)
        assert "SLA MONITORING DASHBOARD" in output
        assert "SLO COMPLIANCE" in output
        assert "ERROR BUDGETS" in output
        assert "ON-CALL STATUS" in output

    def test_render_on_call(self, sla_monitor):
        output = SLADashboard.render_on_call(sla_monitor)
        assert "ON-CALL STATUS" in output
        assert "Bob McFizzington" in output
        assert "ESCALATION CHAIN" in output
        assert "no escape" in output.lower() or "alpha and omega" in output.lower()

    def test_budget_bar_empty(self):
        bar = SLADashboard._render_budget_bar(0.0)
        assert "[" in bar and "]" in bar
        assert "." in bar

    def test_budget_bar_half(self):
        bar = SLADashboard._render_budget_bar(0.5)
        assert "=" in bar

    def test_budget_bar_high(self):
        bar = SLADashboard._render_budget_bar(0.85)
        assert "#" in bar

    def test_budget_bar_exhausted(self):
        bar = SLADashboard._render_budget_bar(1.0)
        assert "X" in bar

    def test_render_with_active_alerts(self, all_slos, event_bus):
        monitor = SLAMonitor(
            slo_definitions=all_slos,
            event_bus=event_bus,
        )
        # Force an alert by recording a wrong evaluation
        monitor.record_evaluation(
            latency_ns=1_000_000,
            number=3,
            output="WRONG",
            success=True,
        )
        output = SLADashboard.render(monitor)
        assert "ACTIVE ALERTS" in output

    def test_render_with_no_evaluations(self, sla_monitor):
        output = SLADashboard.render(sla_monitor)
        assert "SLA MONITORING DASHBOARD" in output


# ============================================================
# Alert Frozen Dataclass Tests
# ============================================================


class TestAlert:
    def test_alert_is_frozen(self):
        alert = Alert(
            alert_id="test",
            severity=AlertSeverity.P1,
            slo_name="latency",
            message="Too slow",
        )
        with pytest.raises(AttributeError):
            alert.message = "modified"  # type: ignore

    def test_alert_defaults(self):
        alert = Alert(
            alert_id="test",
            severity=AlertSeverity.P1,
            slo_name="latency",
            message="Test",
        )
        assert alert.status == AlertStatus.FIRING
        assert alert.acknowledged_at is None
        assert alert.resolved_at is None


# ============================================================
# Ground Truth Accuracy Verification Tests
# ============================================================


class TestGroundTruthVerification:
    """Tests that the SLA monitor correctly verifies FizzBuzz accuracy
    against independently computed ground truth."""

    def test_all_1_to_100_correct(self, sla_monitor):
        for n in range(1, 101):
            div3 = n % 3 == 0
            div5 = n % 5 == 0
            if div3 and div5:
                output = "FizzBuzz"
            elif div3:
                output = "Fizz"
            elif div5:
                output = "Buzz"
            else:
                output = str(n)

            sla_monitor.record_evaluation(
                latency_ns=1_000_000,
                number=n,
                output=output,
                success=True,
            )

        assert sla_monitor.collector.get_accuracy_compliance() == 1.0

    def test_wrong_fizz_detected(self, sla_monitor):
        sla_monitor.record_evaluation(
            latency_ns=1_000_000,
            number=4,
            output="Fizz",  # 4 is not divisible by 3
            success=True,
        )
        assert sla_monitor.collector.get_accuracy_compliance() == 0.0

    def test_wrong_buzz_detected(self, sla_monitor):
        sla_monitor.record_evaluation(
            latency_ns=1_000_000,
            number=7,
            output="Buzz",  # 7 is not divisible by 5
            success=True,
        )
        assert sla_monitor.collector.get_accuracy_compliance() == 0.0

    def test_missing_fizzbuzz_detected(self, sla_monitor):
        sla_monitor.record_evaluation(
            latency_ns=1_000_000,
            number=15,
            output="Fizz",  # Should be FizzBuzz
            success=True,
        )
        assert sla_monitor.collector.get_accuracy_compliance() == 0.0


# ============================================================
# FizzSLI Service Level Indicator Framework Tests
# (Merged from test_sli_framework.py)
# ============================================================


# ============================================================
# SLIType Tests
# ============================================================


class TestSLIType:
    """Tests for the SLIType enum."""

    def test_all_types_defined(self):
        assert len(SLIType) == 6

    def test_availability(self):
        assert SLIType.AVAILABILITY.name == "AVAILABILITY"

    def test_latency(self):
        assert SLIType.LATENCY.name == "LATENCY"

    def test_correctness(self):
        assert SLIType.CORRECTNESS.name == "CORRECTNESS"

    def test_freshness(self):
        assert SLIType.FRESHNESS.name == "FRESHNESS"

    def test_durability(self):
        assert SLIType.DURABILITY.name == "DURABILITY"

    def test_compliance(self):
        assert SLIType.COMPLIANCE.name == "COMPLIANCE"


# ============================================================
# BudgetTier Tests
# ============================================================


class TestBudgetTier:
    """Tests for the BudgetTier enum."""

    def test_all_tiers_defined(self):
        assert len(BudgetTier) == 5

    def test_normal_value(self):
        assert BudgetTier.NORMAL.value == "NORMAL"

    def test_caution_value(self):
        assert BudgetTier.CAUTION.value == "CAUTION"

    def test_elevated_value(self):
        assert BudgetTier.ELEVATED.value == "ELEVATED"

    def test_critical_value(self):
        assert BudgetTier.CRITICAL.value == "CRITICAL"

    def test_exhausted_value(self):
        assert BudgetTier.EXHAUSTED.value == "EXHAUSTED"


# ============================================================
# AttributionCategory Tests
# ============================================================


class TestAttributionCategory:
    """Tests for the AttributionCategory enum."""

    def test_all_categories_defined(self):
        assert len(AttributionCategory) == 5

    def test_chaos(self):
        assert AttributionCategory.CHAOS.value == "CHAOS"

    def test_ml(self):
        assert AttributionCategory.ML.value == "ML"

    def test_circuit_breaker(self):
        assert AttributionCategory.CIRCUIT_BREAKER.value == "CIRCUIT_BREAKER"

    def test_compliance(self):
        assert AttributionCategory.COMPLIANCE.value == "COMPLIANCE"

    def test_infra(self):
        assert AttributionCategory.INFRA.value == "INFRA"


# ============================================================
# SLIDefinition Tests
# ============================================================


class TestSLIDefinition:
    """Tests for the SLIDefinition dataclass."""

    def test_valid_definition(self):
        defn = SLIDefinition(
            name="test_sli",
            sli_type=SLIType.AVAILABILITY,
            target_slo=0.999,
            measurement_window_seconds=3600,
        )
        assert defn.name == "test_sli"
        assert defn.sli_type == SLIType.AVAILABILITY
        assert defn.target_slo == 0.999
        assert defn.measurement_window_seconds == 3600

    def test_default_window(self):
        defn = SLIDefinition(
            name="test_sli",
            sli_type=SLIType.LATENCY,
            target_slo=0.99,
        )
        assert defn.measurement_window_seconds == 3600

    def test_frozen(self):
        defn = SLIDefinition(
            name="test_sli",
            sli_type=SLIType.CORRECTNESS,
            target_slo=0.999,
        )
        with pytest.raises(AttributeError):
            defn.name = "changed"  # type: ignore[misc]

    def test_empty_name_raises(self):
        with pytest.raises(SLIDefinitionError) as exc_info:
            SLIDefinition(name="", sli_type=SLIType.AVAILABILITY, target_slo=0.999)
        assert "EFP-SLI1" in str(exc_info.value)

    def test_target_too_high_raises(self):
        with pytest.raises(SLIDefinitionError):
            SLIDefinition(name="bad", sli_type=SLIType.AVAILABILITY, target_slo=1.0)

    def test_target_too_low_raises(self):
        with pytest.raises(SLIDefinitionError):
            SLIDefinition(name="bad", sli_type=SLIType.AVAILABILITY, target_slo=0.0)

    def test_negative_target_raises(self):
        with pytest.raises(SLIDefinitionError):
            SLIDefinition(name="bad", sli_type=SLIType.AVAILABILITY, target_slo=-0.5)

    def test_target_above_one_raises(self):
        with pytest.raises(SLIDefinitionError):
            SLIDefinition(name="bad", sli_type=SLIType.AVAILABILITY, target_slo=1.5)

    def test_zero_window_raises(self):
        with pytest.raises(SLIDefinitionError):
            SLIDefinition(
                name="bad",
                sli_type=SLIType.AVAILABILITY,
                target_slo=0.999,
                measurement_window_seconds=0,
            )

    def test_negative_window_raises(self):
        with pytest.raises(SLIDefinitionError):
            SLIDefinition(
                name="bad",
                sli_type=SLIType.AVAILABILITY,
                target_slo=0.999,
                measurement_window_seconds=-100,
            )


# ============================================================
# SLIEvent Tests
# ============================================================


class TestSLIEvent:
    """Tests for the SLIEvent dataclass."""

    def test_good_event(self):
        evt = SLIEvent(timestamp=1.0, good=True)
        assert evt.good is True
        assert evt.attribution is None

    def test_bad_event_with_attribution(self):
        evt = SLIEvent(
            timestamp=1.0,
            good=False,
            attribution=AttributionCategory.CHAOS,
        )
        assert evt.good is False
        assert evt.attribution == AttributionCategory.CHAOS

    def test_event_with_metadata(self):
        evt = SLIEvent(
            timestamp=1.0,
            good=True,
            metadata={"number": 42},
        )
        assert evt.metadata["number"] == 42

    def test_default_metadata_empty(self):
        evt = SLIEvent(timestamp=1.0, good=True)
        assert evt.metadata == {}


# ============================================================
# BurnRateCalculator Tests
# ============================================================


class TestBurnRateCalculator:
    """Tests for the BurnRateCalculator."""

    def test_no_events_returns_zero(self):
        calc = BurnRateCalculator()
        result = calc.calculate_burn_rate([], 0.999, 3600)
        assert result == 0.0

    def test_all_good_events(self):
        now = time.monotonic()
        events = [SLIEvent(timestamp=now, good=True) for _ in range(100)]
        calc = BurnRateCalculator()
        result = calc.calculate_burn_rate(events, 0.999, 3600)
        assert result == 0.0

    def test_burn_rate_at_sustainable(self):
        """1 bad out of 1000 with target 0.999 = burn rate 1.0."""
        now = time.monotonic()
        events = [SLIEvent(timestamp=now, good=True) for _ in range(999)]
        events.append(SLIEvent(timestamp=now, good=False))
        calc = BurnRateCalculator()
        result = calc.calculate_burn_rate(events, 0.999, 3600)
        assert abs(result - 1.0) < 0.01

    def test_burn_rate_high(self):
        """10 bad out of 1000 with target 0.999 = burn rate 10.0."""
        now = time.monotonic()
        events = [SLIEvent(timestamp=now, good=True) for _ in range(990)]
        events.extend([SLIEvent(timestamp=now, good=False) for _ in range(10)])
        calc = BurnRateCalculator()
        result = calc.calculate_burn_rate(events, 0.999, 3600)
        assert abs(result - 10.0) < 0.1

    def test_all_bad_events(self):
        now = time.monotonic()
        events = [SLIEvent(timestamp=now, good=False) for _ in range(100)]
        calc = BurnRateCalculator()
        result = calc.calculate_burn_rate(events, 0.999, 3600)
        assert result > 100.0  # 1.0 / 0.001 = 1000

    def test_windowed_events_old_excluded(self):
        """Events outside the window should be excluded."""
        now = time.monotonic()
        old_events = [SLIEvent(timestamp=now - 7200, good=False) for _ in range(10)]
        new_events = [SLIEvent(timestamp=now, good=True) for _ in range(10)]
        calc = BurnRateCalculator()
        result = calc.calculate_burn_rate(old_events + new_events, 0.999, 3600)
        # Only new_events are in window, all good
        assert result == 0.0

    def test_get_all_burn_rates(self):
        now = time.monotonic()
        events = [SLIEvent(timestamp=now, good=True) for _ in range(100)]
        calc = BurnRateCalculator()
        rates = calc.get_all_burn_rates(events, 0.999)
        assert "short" in rates
        assert "medium" in rates
        assert "long" in rates

    def test_multi_window_alert_no_fire(self):
        """Alert should not fire when burn rates are below thresholds."""
        now = time.monotonic()
        events = [SLIEvent(timestamp=now, good=True) for _ in range(1000)]
        events.append(SLIEvent(timestamp=now, good=False))
        calc = BurnRateCalculator()
        result = calc.check_multi_window_alert(events, 0.999)
        assert result is None

    def test_multi_window_alert_fires(self):
        """Alert should fire when both short and long window exceed thresholds."""
        now = time.monotonic()
        # With 0.999 target, threshold 14.4x means error rate > 14.4 * 0.001 = 0.0144
        # Need > 1.44% bad events. Use 5% bad = 50x burn rate.
        events = [SLIEvent(timestamp=now, good=True) for _ in range(950)]
        events.extend([SLIEvent(timestamp=now, good=False) for _ in range(50)])
        calc = BurnRateCalculator()
        result = calc.check_multi_window_alert(events, 0.999)
        assert result is not None
        short_rate, long_rate = result
        assert short_rate >= 14.4
        assert long_rate >= 6.0


# ============================================================
# ErrorBudgetPolicy Tests
# ============================================================


class TestErrorBudgetPolicy:
    """Tests for the ErrorBudgetPolicy."""

    def test_no_events_full_budget(self):
        remaining = ErrorBudgetPolicy.calculate_budget_remaining([], 0.999)
        assert remaining == 1.0

    def test_all_good_full_budget(self):
        events = [SLIEvent(timestamp=0, good=True) for _ in range(100)]
        remaining = ErrorBudgetPolicy.calculate_budget_remaining(events, 0.999)
        assert remaining == 1.0

    def test_budget_at_target(self):
        """Exactly at target: 1 bad out of 1000 with 0.999 target."""
        events = [SLIEvent(timestamp=0, good=True) for _ in range(999)]
        events.append(SLIEvent(timestamp=0, good=False))
        remaining = ErrorBudgetPolicy.calculate_budget_remaining(events, 0.999)
        assert abs(remaining) < 0.01  # Budget essentially consumed

    def test_budget_half_consumed(self):
        """Half the allowed bad events consumed."""
        # 0.999 target, 2000 events => allowed 2 bad. 1 bad => 50% remaining.
        events = [SLIEvent(timestamp=0, good=True) for _ in range(1999)]
        events.append(SLIEvent(timestamp=0, good=False))
        remaining = ErrorBudgetPolicy.calculate_budget_remaining(events, 0.999)
        assert 0.45 < remaining < 0.55

    def test_budget_exhausted(self):
        """More bad events than budget allows."""
        events = [SLIEvent(timestamp=0, good=True) for _ in range(990)]
        events.extend([SLIEvent(timestamp=0, good=False) for _ in range(10)])
        remaining = ErrorBudgetPolicy.calculate_budget_remaining(events, 0.999)
        assert remaining == 0.0

    def test_tier_normal(self):
        assert ErrorBudgetPolicy.get_tier(0.75) == BudgetTier.NORMAL

    def test_tier_normal_boundary(self):
        assert ErrorBudgetPolicy.get_tier(0.51) == BudgetTier.NORMAL

    def test_tier_caution(self):
        assert ErrorBudgetPolicy.get_tier(0.50) == BudgetTier.CAUTION

    def test_tier_caution_boundary(self):
        assert ErrorBudgetPolicy.get_tier(0.25) == BudgetTier.CAUTION

    def test_tier_elevated(self):
        assert ErrorBudgetPolicy.get_tier(0.20) == BudgetTier.ELEVATED

    def test_tier_elevated_boundary(self):
        assert ErrorBudgetPolicy.get_tier(0.10) == BudgetTier.ELEVATED

    def test_tier_critical(self):
        assert ErrorBudgetPolicy.get_tier(0.09) == BudgetTier.CRITICAL

    def test_tier_critical_boundary(self):
        assert ErrorBudgetPolicy.get_tier(0.01) == BudgetTier.CRITICAL

    def test_tier_exhausted(self):
        assert ErrorBudgetPolicy.get_tier(0.0) == BudgetTier.EXHAUSTED

    def test_tier_negative_exhausted(self):
        assert ErrorBudgetPolicy.get_tier(-0.1) == BudgetTier.EXHAUSTED


# ============================================================
# BudgetAttributor Tests
# ============================================================


class TestBudgetAttributor:
    """Tests for the BudgetAttributor."""

    def _make_context(self, metadata: dict[str, Any]) -> MagicMock:
        ctx = MagicMock()
        ctx.metadata = metadata
        return ctx

    def test_chaos_attribution(self):
        ctx = self._make_context({"chaos_injected": True})
        assert BudgetAttributor.attribute(ctx) == AttributionCategory.CHAOS

    def test_ml_attribution(self):
        ctx = self._make_context({"ml_strategy": True})
        assert BudgetAttributor.attribute(ctx) == AttributionCategory.ML

    def test_circuit_breaker_attribution(self):
        ctx = self._make_context({"circuit_breaker_tripped": True})
        assert BudgetAttributor.attribute(ctx) == AttributionCategory.CIRCUIT_BREAKER

    def test_compliance_attribution(self):
        ctx = self._make_context({"compliance_violation": True})
        assert BudgetAttributor.attribute(ctx) == AttributionCategory.COMPLIANCE

    def test_infra_default(self):
        ctx = self._make_context({})
        assert BudgetAttributor.attribute(ctx) == AttributionCategory.INFRA

    def test_priority_chaos_over_ml(self):
        ctx = self._make_context({"chaos_injected": True, "ml_strategy": True})
        assert BudgetAttributor.attribute(ctx) == AttributionCategory.CHAOS

    def test_attribute_from_metadata(self):
        assert BudgetAttributor.attribute_from_metadata({"chaos_injected": True}) == AttributionCategory.CHAOS

    def test_attribute_from_metadata_default(self):
        assert BudgetAttributor.attribute_from_metadata({}) == AttributionCategory.INFRA


# ============================================================
# SLIFeatureGate Tests
# ============================================================


class TestSLIFeatureGate:
    """Tests for the SLIFeatureGate."""

    def test_chaos_allowed_above_threshold(self):
        gate = SLIFeatureGate()
        assert gate.check_chaos_allowed(0.15) is True

    def test_chaos_blocked_below_threshold(self):
        gate = SLIFeatureGate()
        assert gate.check_chaos_allowed(0.05) is False

    def test_chaos_blocked_at_threshold(self):
        gate = SLIFeatureGate()
        assert gate.check_chaos_allowed(0.10) is True

    def test_flags_allowed_above_threshold(self):
        gate = SLIFeatureGate()
        assert gate.check_flags_allowed(0.60) is True

    def test_flags_blocked_below_threshold(self):
        gate = SLIFeatureGate()
        assert gate.check_flags_allowed(0.40) is False

    def test_flags_allowed_at_threshold(self):
        gate = SLIFeatureGate()
        assert gate.check_flags_allowed(0.50) is True

    def test_deploy_allowed_above_threshold(self):
        gate = SLIFeatureGate()
        assert gate.check_deploy_allowed(0.30) is True

    def test_deploy_blocked_below_threshold(self):
        gate = SLIFeatureGate()
        assert gate.check_deploy_allowed(0.20) is False

    def test_deploy_allowed_at_threshold(self):
        gate = SLIFeatureGate()
        assert gate.check_deploy_allowed(0.25) is True

    def test_enforce_chaos_raises(self):
        gate = SLIFeatureGate()
        with pytest.raises(SLIFeatureGateError) as exc_info:
            gate.enforce_chaos(0.05)
        assert "EFP-SLI3" in str(exc_info.value)

    def test_enforce_chaos_passes(self):
        gate = SLIFeatureGate()
        gate.enforce_chaos(0.15)  # Should not raise

    def test_enforce_flags_raises(self):
        gate = SLIFeatureGate()
        with pytest.raises(SLIFeatureGateError):
            gate.enforce_flags(0.40)

    def test_enforce_deploy_raises(self):
        gate = SLIFeatureGate()
        with pytest.raises(SLIFeatureGateError):
            gate.enforce_deploy(0.20)

    def test_get_gate_status_all_open(self):
        gate = SLIFeatureGate()
        status = gate.get_gate_status(0.60)
        assert all(status.values())

    def test_get_gate_status_all_blocked(self):
        gate = SLIFeatureGate()
        status = gate.get_gate_status(0.0)
        assert not any(status.values())

    def test_get_gate_status_partial(self):
        gate = SLIFeatureGate()
        status = gate.get_gate_status(0.15)
        assert status["chaos_allowed"] is True
        assert status["flags_allowed"] is False
        assert status["deploy_allowed"] is False


# ============================================================
# SLIRegistry Tests
# ============================================================


class TestSLIRegistry:
    """Tests for the SLIRegistry."""

    def _make_registry(self) -> SLIRegistry:
        return bootstrap_sli_registry(target=0.999)

    def test_register_definition(self):
        registry = SLIRegistry()
        defn = SLIDefinition(name="test", sli_type=SLIType.AVAILABILITY, target_slo=0.999)
        registry.register(defn)
        assert registry.get_definition("test") is not None

    def test_get_unknown_definition(self):
        registry = SLIRegistry()
        assert registry.get_definition("nonexistent") is None

    def test_record_good_event(self):
        registry = self._make_registry()
        alert = registry.record_event("fizzbuzz_availability", good=True)
        assert alert is None
        assert len(registry.get_events("fizzbuzz_availability")) == 1

    def test_record_bad_event(self):
        registry = self._make_registry()
        registry.record_event(
            "fizzbuzz_availability",
            good=False,
            attribution=AttributionCategory.INFRA,
        )
        events = registry.get_events("fizzbuzz_availability")
        assert len(events) == 1
        assert events[0].good is False

    def test_record_unknown_sli_ignored(self):
        registry = SLIRegistry()
        result = registry.record_event("nonexistent", good=True)
        assert result is None

    def test_get_sli_value_no_events(self):
        registry = self._make_registry()
        assert registry.get_sli_value("fizzbuzz_availability") == 1.0

    def test_get_sli_value_all_good(self):
        registry = self._make_registry()
        for _ in range(10):
            registry.record_event("fizzbuzz_availability", good=True)
        assert registry.get_sli_value("fizzbuzz_availability") == 1.0

    def test_get_sli_value_mixed(self):
        registry = self._make_registry()
        for _ in range(9):
            registry.record_event("fizzbuzz_availability", good=True)
        registry.record_event("fizzbuzz_availability", good=False, attribution=AttributionCategory.INFRA)
        value = registry.get_sli_value("fizzbuzz_availability")
        assert abs(value - 0.9) < 0.01

    def test_get_budget_remaining_no_events(self):
        registry = self._make_registry()
        assert registry.get_budget_remaining("fizzbuzz_availability") == 1.0

    def test_get_tier(self):
        registry = self._make_registry()
        assert registry.get_tier("fizzbuzz_availability") == BudgetTier.NORMAL

    def test_get_all_definitions(self):
        registry = self._make_registry()
        defs = registry.get_all_definitions()
        assert len(defs) == 6

    def test_total_events_zero(self):
        registry = self._make_registry()
        assert registry.total_events == 0

    def test_total_alerts_zero(self):
        registry = self._make_registry()
        assert registry.total_alerts == 0

    def test_attribution_breakdown_initial(self):
        registry = self._make_registry()
        breakdown = registry.get_attribution_breakdown("fizzbuzz_availability")
        assert all(v == 0 for v in breakdown.values())

    def test_attribution_breakdown_after_bad_event(self):
        registry = self._make_registry()
        registry.record_event(
            "fizzbuzz_availability",
            good=False,
            attribution=AttributionCategory.CHAOS,
        )
        breakdown = registry.get_attribution_breakdown("fizzbuzz_availability")
        assert breakdown["CHAOS"] == 1

    def test_feature_gate_accessible(self):
        registry = self._make_registry()
        assert isinstance(registry.feature_gate, SLIFeatureGate)

    def test_definitions_property(self):
        registry = self._make_registry()
        defs = registry.definitions
        assert "fizzbuzz_availability" in defs


# ============================================================
# create_default_slis Tests
# ============================================================


class TestCreateDefaultSLIs:
    """Tests for the create_default_slis helper."""

    def test_returns_six_slis(self):
        slis = create_default_slis()
        assert len(slis) == 6

    def test_custom_target(self):
        slis = create_default_slis(target=0.99)
        assert all(s.target_slo == 0.99 for s in slis)

    def test_custom_window(self):
        slis = create_default_slis(window_seconds=7200)
        assert all(s.measurement_window_seconds == 7200 for s in slis)

    def test_all_types_covered(self):
        slis = create_default_slis()
        types = {s.sli_type for s in slis}
        assert types == {
            SLIType.AVAILABILITY,
            SLIType.LATENCY,
            SLIType.CORRECTNESS,
            SLIType.FRESHNESS,
            SLIType.DURABILITY,
            SLIType.COMPLIANCE,
        }

    def test_names_unique(self):
        slis = create_default_slis()
        names = [s.name for s in slis]
        assert len(names) == len(set(names))


# ============================================================
# bootstrap_sli_registry Tests
# ============================================================


class TestBootstrapSLIRegistry:
    """Tests for the bootstrap_sli_registry function."""

    def test_returns_registry(self):
        registry = bootstrap_sli_registry()
        assert isinstance(registry, SLIRegistry)

    def test_six_definitions_registered(self):
        registry = bootstrap_sli_registry()
        assert len(registry.get_all_definitions()) == 6

    def test_custom_parameters(self):
        registry = bootstrap_sli_registry(
            target=0.95,
            window_seconds=7200,
            short_window=1800,
            medium_window=10800,
            long_window=86400,
            short_threshold=10.0,
            long_threshold=5.0,
        )
        defn = registry.get_definition("fizzbuzz_availability")
        assert defn is not None
        assert defn.target_slo == 0.95


# ============================================================
# BurnRateAlert Tests
# ============================================================


class TestBurnRateAlert:
    """Tests for the BurnRateAlert dataclass."""

    def test_alert_creation(self):
        alert = BurnRateAlert(
            alert_id="test-123",
            sli_name="fizzbuzz_availability",
            short_burn_rate=15.0,
            long_burn_rate=7.0,
            budget_remaining=0.05,
            tier=BudgetTier.CRITICAL,
        )
        assert alert.alert_id == "test-123"
        assert alert.sli_name == "fizzbuzz_availability"
        assert alert.short_burn_rate == 15.0
        assert alert.long_burn_rate == 7.0
        assert alert.budget_remaining == 0.05
        assert alert.tier == BudgetTier.CRITICAL

    def test_alert_has_timestamp(self):
        alert = BurnRateAlert(
            alert_id="test",
            sli_name="test",
            short_burn_rate=1.0,
            long_burn_rate=1.0,
            budget_remaining=0.5,
            tier=BudgetTier.NORMAL,
        )
        assert alert.timestamp is not None


# ============================================================
# SLIMiddleware Tests
# ============================================================


class TestSLIMiddleware:
    """Tests for the SLIMiddleware."""

    def _make_context(self, number: int = 15) -> MagicMock:
        ctx = MagicMock()
        ctx.number = number
        ctx.metadata = {}
        ctx.results = []
        return ctx

    def test_get_name(self):
        registry = bootstrap_sli_registry()
        mw = SLIMiddleware(registry)
        assert mw.get_name() == "SLIMiddleware"

    def test_get_priority(self):
        registry = bootstrap_sli_registry()
        mw = SLIMiddleware(registry)
        assert mw.get_priority() == 54

    def test_successful_evaluation_records_good(self):
        registry = bootstrap_sli_registry()
        mw = SLIMiddleware(registry)
        ctx = self._make_context()

        def handler(c):
            return c

        mw.process(ctx, handler)
        events = registry.get_events("fizzbuzz_availability")
        assert len(events) == 1
        assert events[0].good is True

    def test_failed_evaluation_records_bad(self):
        registry = bootstrap_sli_registry()
        mw = SLIMiddleware(registry)
        ctx = self._make_context()

        def handler(c):
            raise RuntimeError("boom")

        with pytest.raises(RuntimeError):
            mw.process(ctx, handler)

        events = registry.get_events("fizzbuzz_availability")
        assert len(events) == 1
        assert events[0].good is False

    def test_failed_evaluation_records_correctness_bad(self):
        registry = bootstrap_sli_registry()
        mw = SLIMiddleware(registry)
        ctx = self._make_context()

        def handler(c):
            raise RuntimeError("boom")

        with pytest.raises(RuntimeError):
            mw.process(ctx, handler)

        events = registry.get_events("fizzbuzz_correctness")
        assert len(events) == 1
        assert events[0].good is False


# ============================================================
# SLIDashboard Tests
# ============================================================


class TestSLIDashboard:
    """Tests for the SLIDashboard."""

    def test_empty_registry(self):
        registry = SLIRegistry()
        output = SLIDashboard.render(registry)
        assert "No SLIs registered" in output

    def test_dashboard_with_slis(self):
        registry = bootstrap_sli_registry()
        output = SLIDashboard.render(registry)
        assert "FIZZSLI SERVICE LEVEL INDICATOR DASHBOARD" in output
        assert "fizzbuzz_availability" in output
        assert "SLI INVENTORY" in output

    def test_dashboard_burn_rates_section(self):
        registry = bootstrap_sli_registry()
        output = SLIDashboard.render(registry)
        assert "BURN RATES" in output

    def test_dashboard_attribution_section(self):
        registry = bootstrap_sli_registry()
        output = SLIDashboard.render(registry)
        assert "ERROR BUDGET ATTRIBUTION" in output

    def test_dashboard_feature_gate_section(self):
        registry = bootstrap_sli_registry()
        output = SLIDashboard.render(registry)
        assert "FEATURE GATE STATUS" in output

    def test_dashboard_alerts_section(self):
        registry = bootstrap_sli_registry()
        output = SLIDashboard.render(registry)
        assert "ALERTS" in output

    def test_dashboard_custom_width(self):
        registry = bootstrap_sli_registry()
        output = SLIDashboard.render(registry, width=80)
        # Just verify it renders without error at different width
        assert "FIZZSLI" in output

    def test_dashboard_with_events(self):
        registry = bootstrap_sli_registry()
        for _ in range(10):
            registry.record_event("fizzbuzz_availability", good=True)
        registry.record_event(
            "fizzbuzz_availability",
            good=False,
            attribution=AttributionCategory.CHAOS,
        )
        output = SLIDashboard.render(registry)
        assert "Events: 11" in output

    def test_dashboard_no_alerts_message(self):
        registry = bootstrap_sli_registry()
        output = SLIDashboard.render(registry)
        assert "No alerts" in output


# ============================================================
# SLI Exception Hierarchy Tests
# ============================================================


class TestSLIExceptions:
    """Tests for the SLI exception hierarchy."""

    def test_sli_error_is_fizzbuzz_error(self):
        from enterprise_fizzbuzz.domain.exceptions import FizzBuzzError
        err = SLIError("test")
        assert isinstance(err, FizzBuzzError)

    def test_sli_error_code(self):
        err = SLIError("test")
        assert "EFP-SLI0" in str(err)

    def test_sli_definition_error_inherits(self):
        err = SLIDefinitionError("test", "field", "reason")
        assert isinstance(err, SLIError)

    def test_sli_definition_error_code(self):
        err = SLIDefinitionError("test", "field", "reason")
        assert "EFP-SLI1" in str(err)

    def test_sli_budget_exhaustion_error_inherits(self):
        err = SLIBudgetExhaustionError("test", 15.0)
        assert isinstance(err, SLIError)

    def test_sli_budget_exhaustion_error_code(self):
        err = SLIBudgetExhaustionError("test", 15.0)
        assert "EFP-SLI2" in str(err)

    def test_sli_feature_gate_error_inherits(self):
        err = SLIFeatureGateError("deploy", 0.05, 0.25)
        assert isinstance(err, SLIError)

    def test_sli_feature_gate_error_code(self):
        err = SLIFeatureGateError("deploy", 0.05, 0.25)
        assert "EFP-SLI3" in str(err)

    def test_sli_feature_gate_error_attributes(self):
        err = SLIFeatureGateError("deploy", 0.05, 0.25)
        assert err.operation == "deploy"
        assert err.budget_remaining == 0.05
        assert err.threshold == 0.25
