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

import pytest

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from config import ConfigurationManager, _SingletonMeta
from models import Event, EventType, ProcessingContext, FizzBuzzResult
from observers import EventBus
from sla import (
    Alert,
    AlertManager,
    AlertSeverity,
    AlertStatus,
    ErrorBudget,
    EscalationPolicy,
    OnCallSchedule,
    SLADashboard,
    SLAMiddleware,
    SLAMonitor,
    SLODefinition,
    SLOMetricCollector,
    SLOType,
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
        assert SLOType.LATENCY is not None

    def test_accuracy_exists(self):
        assert SLOType.ACCURACY is not None

    def test_availability_exists(self):
        assert SLOType.AVAILABILITY is not None


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
        assert AlertStatus.FIRING is not None

    def test_acknowledged_exists(self):
        assert AlertStatus.ACKNOWLEDGED is not None

    def test_resolved_exists(self):
        assert AlertStatus.RESOLVED is not None


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
