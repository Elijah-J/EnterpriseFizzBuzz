"""
Enterprise FizzBuzz Platform - Health Check Probe Test Suite

Comprehensive tests for the Kubernetes-style health check probes,
because testing the system that tests whether FizzBuzz is healthy
is the kind of recursive quality assurance that enterprise software
demands. If the health checks themselves are unhealthy, who will
check the health of the health checks? These tests. That's who.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from config import ConfigurationManager, _SingletonMeta
from health import (
    CacheCoherenceHealthCheck,
    CircuitBreakerHealthCheck,
    ConfigHealthCheck,
    HealthCheckRegistry,
    HealthDashboard,
    LivenessProbe,
    MLEngineHealthCheck,
    ReadinessProbe,
    SelfHealingManager,
    SLABudgetHealthCheck,
    StartupProbe,
    SubsystemHealthCheck,
)
from models import (
    Event,
    EventType,
    FizzBuzzResult,
    HealthReport,
    HealthStatus,
    ProbeType,
    SubsystemCheck,
)
from observers import EventBus


# ============================================================
# Fixtures
# ============================================================


@pytest.fixture(autouse=True)
def reset_singletons():
    """Reset all singletons between tests."""
    _SingletonMeta.reset()
    HealthCheckRegistry.reset()
    yield
    HealthCheckRegistry.reset()


@pytest.fixture
def config():
    cfg = ConfigurationManager()
    cfg.load()
    return cfg


@pytest.fixture
def event_bus():
    return EventBus()


@pytest.fixture
def health_registry():
    return HealthCheckRegistry.get_instance()


# ============================================================
# ProbeType and HealthStatus Enum Tests
# ============================================================


class TestProbeType:
    def test_liveness_exists(self):
        assert ProbeType.LIVENESS is not None

    def test_readiness_exists(self):
        assert ProbeType.READINESS is not None

    def test_startup_exists(self):
        assert ProbeType.STARTUP is not None

    def test_all_values_unique(self):
        values = [p.value for p in ProbeType]
        assert len(values) == len(set(values))


class TestHealthStatus:
    def test_up_exists(self):
        assert HealthStatus.UP is not None

    def test_down_exists(self):
        assert HealthStatus.DOWN is not None

    def test_degraded_exists(self):
        assert HealthStatus.DEGRADED is not None

    def test_existential_crisis_exists(self):
        assert HealthStatus.EXISTENTIAL_CRISIS is not None

    def test_unknown_exists(self):
        assert HealthStatus.UNKNOWN is not None

    def test_all_values_unique(self):
        values = [s.value for s in HealthStatus]
        assert len(values) == len(set(values))


# ============================================================
# SubsystemCheck and HealthReport Model Tests
# ============================================================


class TestSubsystemCheck:
    def test_creation(self):
        check = SubsystemCheck(
            subsystem_name="test",
            status=HealthStatus.UP,
            response_time_ms=1.5,
            details="All good",
        )
        assert check.subsystem_name == "test"
        assert check.status == HealthStatus.UP
        assert check.response_time_ms == 1.5
        assert check.details == "All good"

    def test_frozen(self):
        check = SubsystemCheck(
            subsystem_name="test",
            status=HealthStatus.UP,
        )
        with pytest.raises(AttributeError):
            check.status = HealthStatus.DOWN

    def test_default_details(self):
        check = SubsystemCheck(
            subsystem_name="test",
            status=HealthStatus.UP,
        )
        assert check.details == ""
        assert check.response_time_ms == 0.0


class TestHealthReport:
    def test_creation(self):
        report = HealthReport(
            probe_type=ProbeType.LIVENESS,
            overall_status=HealthStatus.UP,
        )
        assert report.probe_type == ProbeType.LIVENESS
        assert report.overall_status == HealthStatus.UP
        assert report.subsystem_checks == []
        assert report.report_id is not None

    def test_with_subsystem_checks(self):
        checks = [
            SubsystemCheck(subsystem_name="config", status=HealthStatus.UP),
            SubsystemCheck(subsystem_name="cache", status=HealthStatus.DEGRADED),
        ]
        report = HealthReport(
            probe_type=ProbeType.READINESS,
            overall_status=HealthStatus.DEGRADED,
            subsystem_checks=checks,
        )
        assert len(report.subsystem_checks) == 2

    def test_canary_value(self):
        report = HealthReport(
            probe_type=ProbeType.LIVENESS,
            overall_status=HealthStatus.UP,
            canary_value="FizzBuzz",
        )
        assert report.canary_value == "FizzBuzz"


# ============================================================
# EventType Health Entries Tests
# ============================================================


class TestHealthEventTypes:
    def test_health_check_started(self):
        assert EventType.HEALTH_CHECK_STARTED is not None

    def test_health_check_completed(self):
        assert EventType.HEALTH_CHECK_COMPLETED is not None

    def test_health_liveness_passed(self):
        assert EventType.HEALTH_LIVENESS_PASSED is not None

    def test_health_liveness_failed(self):
        assert EventType.HEALTH_LIVENESS_FAILED is not None

    def test_health_readiness_passed(self):
        assert EventType.HEALTH_READINESS_PASSED is not None

    def test_health_readiness_failed(self):
        assert EventType.HEALTH_READINESS_FAILED is not None

    def test_health_startup_milestone(self):
        assert EventType.HEALTH_STARTUP_MILESTONE is not None

    def test_health_self_heal_attempted(self):
        assert EventType.HEALTH_SELF_HEAL_ATTEMPTED is not None


# ============================================================
# Health Check Exception Tests
# ============================================================


class TestHealthExceptions:
    def test_health_check_error(self):
        from exceptions import HealthCheckError
        e = HealthCheckError("test error")
        assert "EFP-HC00" in str(e)

    def test_liveness_probe_failed_error(self):
        from exceptions import LivenessProbeFailedError
        e = LivenessProbeFailedError("FizzBuzz", "Fizz")
        assert "EFP-HC01" in str(e)
        assert e.expected == "FizzBuzz"
        assert e.actual == "Fizz"

    def test_readiness_probe_failed_error(self):
        from exceptions import ReadinessProbeFailedError
        e = ReadinessProbeFailedError(["cache", "sla"])
        assert "EFP-HC02" in str(e)
        assert e.failing_subsystems == ["cache", "sla"]

    def test_startup_probe_failed_error(self):
        from exceptions import StartupProbeFailedError
        e = StartupProbeFailedError(["engine_created", "service_built"])
        assert "EFP-HC03" in str(e)
        assert e.pending_milestones == ["engine_created", "service_built"]

    def test_self_healing_failed_error(self):
        from exceptions import SelfHealingFailedError
        e = SelfHealingFailedError("cache", "cache corrupted beyond repair")
        assert "EFP-HC04" in str(e)
        assert e.subsystem_name == "cache"

    def test_health_dashboard_render_error(self):
        from exceptions import HealthDashboardRenderError
        e = HealthDashboardRenderError("terminal too narrow")
        assert "EFP-HC05" in str(e)


# ============================================================
# Config Health Check Tests
# ============================================================


class TestConfigHealthCheck:
    def test_healthy_with_no_config(self):
        check = ConfigHealthCheck(config=None)
        result = check.check()
        assert result.status == HealthStatus.UP
        assert check.get_name() == "config"

    def test_healthy_with_loaded_config(self, config):
        check = ConfigHealthCheck(config=config)
        result = check.check()
        assert result.status == HealthStatus.UP
        assert "Enterprise FizzBuzz Platform" in result.details

    def test_unhealthy_with_broken_config(self):
        mock_config = MagicMock()
        mock_config.app_name = property(lambda self: (_ for _ in ()).throw(RuntimeError("config exploded")))
        type(mock_config).app_name = property(lambda self: (_ for _ in ()).throw(RuntimeError("config exploded")))
        check = ConfigHealthCheck(config=mock_config)
        result = check.check()
        assert result.status == HealthStatus.DOWN

    def test_recover_reloads_config(self, config):
        check = ConfigHealthCheck(config=config)
        assert check.recover() is True

    def test_recover_with_no_config(self):
        check = ConfigHealthCheck(config=None)
        assert check.recover() is False


# ============================================================
# Circuit Breaker Health Check Tests
# ============================================================


class TestCircuitBreakerHealthCheck:
    def test_healthy_when_not_enabled(self):
        check = CircuitBreakerHealthCheck(registry=None)
        result = check.check()
        assert result.status == HealthStatus.UP
        assert check.get_name() == "circuit_breaker"

    def test_healthy_with_empty_registry(self):
        from circuit_breaker import CircuitBreakerRegistry
        CircuitBreakerRegistry.reset()
        registry = CircuitBreakerRegistry.get_instance()
        check = CircuitBreakerHealthCheck(registry=registry)
        result = check.check()
        assert result.status == HealthStatus.UP
        CircuitBreakerRegistry.reset()

    def test_healthy_with_closed_circuit(self):
        from circuit_breaker import CircuitBreakerRegistry
        CircuitBreakerRegistry.reset()
        registry = CircuitBreakerRegistry.get_instance()
        registry.get_or_create("TestCircuit")
        check = CircuitBreakerHealthCheck(registry=registry)
        result = check.check()
        assert result.status == HealthStatus.UP
        assert "CLOSED" in result.details
        CircuitBreakerRegistry.reset()

    def test_down_with_open_circuit(self):
        from circuit_breaker import CircuitBreaker, CircuitBreakerRegistry
        CircuitBreakerRegistry.reset()
        registry = CircuitBreakerRegistry.get_instance()
        cb = registry.get_or_create("TestCircuit", failure_threshold=1)
        # Force the circuit to open by recording failures
        for _ in range(5):
            try:
                cb.execute(lambda: (_ for _ in ()).throw(RuntimeError("boom")))
            except Exception:
                pass
        check = CircuitBreakerHealthCheck(registry=registry)
        result = check.check()
        assert result.status == HealthStatus.DOWN
        CircuitBreakerRegistry.reset()

    def test_recover_resets_circuits(self):
        from circuit_breaker import CircuitBreakerRegistry
        CircuitBreakerRegistry.reset()
        registry = CircuitBreakerRegistry.get_instance()
        cb = registry.get_or_create("TestCircuit", failure_threshold=1)
        for _ in range(5):
            try:
                cb.execute(lambda: (_ for _ in ()).throw(RuntimeError("boom")))
            except Exception:
                pass
        check = CircuitBreakerHealthCheck(registry=registry)
        assert check.recover() is True
        CircuitBreakerRegistry.reset()


# ============================================================
# Cache Coherence Health Check Tests
# ============================================================


class TestCacheCoherenceHealthCheck:
    def test_healthy_when_not_enabled(self):
        check = CacheCoherenceHealthCheck(cache_store=None)
        result = check.check()
        assert result.status == HealthStatus.UP
        assert check.get_name() == "cache"

    def test_healthy_with_mock_cache(self):
        mock_cache = MagicMock()
        mock_cache.get_statistics.return_value = {
            "total_requests": 100,
            "hits": 80,
            "current_size": 50,
            "max_size": 1024,
        }
        check = CacheCoherenceHealthCheck(cache_store=mock_cache)
        result = check.check()
        assert result.status == HealthStatus.UP
        assert "80.0%" in result.details

    def test_degraded_with_low_hit_rate(self):
        mock_cache = MagicMock()
        mock_cache.get_statistics.return_value = {
            "total_requests": 100,
            "hits": 5,
            "current_size": 50,
            "max_size": 1024,
        }
        check = CacheCoherenceHealthCheck(cache_store=mock_cache)
        result = check.check()
        assert result.status == HealthStatus.DEGRADED

    def test_recover_clears_cache(self):
        mock_cache = MagicMock()
        check = CacheCoherenceHealthCheck(cache_store=mock_cache)
        assert check.recover() is True
        mock_cache.clear.assert_called_once()

    def test_recover_when_not_enabled(self):
        check = CacheCoherenceHealthCheck(cache_store=None)
        assert check.recover() is True


# ============================================================
# SLA Budget Health Check Tests
# ============================================================


class TestSLABudgetHealthCheck:
    def test_healthy_when_not_enabled(self):
        check = SLABudgetHealthCheck(sla_monitor=None)
        result = check.check()
        assert result.status == HealthStatus.UP
        assert check.get_name() == "sla"

    def test_healthy_with_no_violations(self):
        mock_monitor = MagicMock()
        mock_monitor._violation_count = 0
        mock_monitor._total_evaluations = 100
        check = SLABudgetHealthCheck(sla_monitor=mock_monitor)
        result = check.check()
        assert result.status == HealthStatus.UP

    def test_degraded_with_high_violation_rate(self):
        mock_monitor = MagicMock()
        mock_monitor._violation_count = 5
        mock_monitor._total_evaluations = 100
        check = SLABudgetHealthCheck(sla_monitor=mock_monitor)
        result = check.check()
        assert result.status == HealthStatus.DEGRADED


# ============================================================
# ML Engine Health Check Tests
# ============================================================


class TestMLEngineHealthCheck:
    def test_healthy_when_not_configured(self):
        check = MLEngineHealthCheck(engine=None, rules=None)
        result = check.check()
        assert result.status == HealthStatus.UP
        assert check.get_name() == "ml_engine"

    def test_healthy_with_correct_engine(self):
        mock_engine = MagicMock()
        # Return correct results for all test cases
        def make_result(n, rules):
            result = MagicMock()
            outputs = {3: "Fizz", 5: "Buzz", 15: "FizzBuzz", 7: "7"}
            result.output = outputs.get(n, str(n))
            result.metadata = {"ml_confidences": {"fizz": 0.95, "buzz": 0.92}}
            return result
        mock_engine.evaluate.side_effect = make_result

        check = MLEngineHealthCheck(engine=mock_engine, rules=[])
        result = check.check()
        assert result.status == HealthStatus.UP

    def test_existential_crisis_with_wrong_results(self):
        mock_engine = MagicMock()
        # Return wrong results
        def make_result(n, rules):
            result = MagicMock()
            result.output = "42"  # Always wrong
            result.metadata = {}
            return result
        mock_engine.evaluate.side_effect = make_result

        check = MLEngineHealthCheck(engine=mock_engine, rules=[])
        result = check.check()
        assert result.status == HealthStatus.EXISTENTIAL_CRISIS
        assert "forgotten" in result.details.lower() or "lost" in result.details.lower()

    def test_existential_crisis_with_low_confidence(self):
        mock_engine = MagicMock()
        def make_result(n, rules):
            result = MagicMock()
            outputs = {3: "Fizz", 5: "Buzz", 15: "FizzBuzz", 7: "7"}
            result.output = outputs.get(n, str(n))
            result.metadata = {"ml_confidences": {"rule": 0.3}}
            return result
        mock_engine.evaluate.side_effect = make_result

        check = MLEngineHealthCheck(engine=mock_engine, rules=[])
        result = check.check()
        assert result.status == HealthStatus.EXISTENTIAL_CRISIS

    def test_degraded_with_moderate_confidence(self):
        mock_engine = MagicMock()
        def make_result(n, rules):
            result = MagicMock()
            outputs = {3: "Fizz", 5: "Buzz", 15: "FizzBuzz", 7: "7"}
            result.output = outputs.get(n, str(n))
            result.metadata = {"ml_confidences": {"rule": 0.6}}
            return result
        mock_engine.evaluate.side_effect = make_result

        check = MLEngineHealthCheck(engine=mock_engine, rules=[])
        result = check.check()
        assert result.status == HealthStatus.DEGRADED

    def test_down_when_engine_throws(self):
        mock_engine = MagicMock()
        mock_engine.evaluate.side_effect = RuntimeError("neural network on fire")

        check = MLEngineHealthCheck(engine=mock_engine, rules=[])
        result = check.check()
        assert result.status == HealthStatus.DOWN


# ============================================================
# Health Check Registry Tests
# ============================================================


class TestHealthCheckRegistry:
    def test_singleton(self):
        r1 = HealthCheckRegistry.get_instance()
        r2 = HealthCheckRegistry.get_instance()
        assert r1 is r2

    def test_reset(self):
        r1 = HealthCheckRegistry.get_instance()
        HealthCheckRegistry.reset()
        r2 = HealthCheckRegistry.get_instance()
        assert r1 is not r2

    def test_register_and_list(self, health_registry):
        check = ConfigHealthCheck()
        health_registry.register(check)
        assert "config" in health_registry.list_all()

    def test_register_chaining(self, health_registry):
        result = health_registry.register(ConfigHealthCheck())
        assert result is health_registry

    def test_get(self, health_registry):
        check = ConfigHealthCheck()
        health_registry.register(check)
        assert health_registry.get("config") is check
        assert health_registry.get("nonexistent") is None

    def test_unregister(self, health_registry):
        health_registry.register(ConfigHealthCheck())
        assert health_registry.unregister("config") is True
        assert health_registry.unregister("config") is False
        assert "config" not in health_registry.list_all()

    def test_check_all(self, health_registry):
        health_registry.register(ConfigHealthCheck())
        health_registry.register(CacheCoherenceHealthCheck())
        results = health_registry.check_all()
        assert len(results) == 2
        assert all(isinstance(r, SubsystemCheck) for r in results)

    def test_check_all_handles_exceptions(self, health_registry):
        """Verify that check_all doesn't die if a check throws."""
        class BrokenCheck(SubsystemHealthCheck):
            def get_name(self):
                return "broken"
            def check(self):
                raise RuntimeError("I am broken")

        health_registry.register(BrokenCheck())
        results = health_registry.check_all()
        assert len(results) == 1
        assert results[0].status == HealthStatus.UNKNOWN


# ============================================================
# Liveness Probe Tests
# ============================================================


class TestLivenessProbe:
    def test_passes_with_correct_canary(self):
        probe = LivenessProbe(
            evaluate_fn=lambda n: "FizzBuzz",
            canary_number=15,
            canary_expected="FizzBuzz",
        )
        report = probe.probe()
        assert report.probe_type == ProbeType.LIVENESS
        assert report.overall_status == HealthStatus.UP
        assert report.canary_value == "FizzBuzz"

    def test_fails_with_wrong_canary(self):
        probe = LivenessProbe(
            evaluate_fn=lambda n: "Fizz",
            canary_number=15,
            canary_expected="FizzBuzz",
        )
        report = probe.probe()
        assert report.overall_status == HealthStatus.DOWN
        assert report.canary_value == "Fizz"

    def test_fails_with_exception(self):
        def exploding_evaluator(n):
            raise RuntimeError("math is broken")

        probe = LivenessProbe(
            evaluate_fn=exploding_evaluator,
            canary_number=15,
            canary_expected="FizzBuzz",
        )
        report = probe.probe()
        assert report.overall_status == HealthStatus.DOWN

    def test_hardcoded_fallback(self):
        probe = LivenessProbe(
            evaluate_fn=None,
            canary_number=15,
            canary_expected="FizzBuzz",
        )
        report = probe.probe()
        assert report.overall_status == HealthStatus.UP
        assert report.canary_value == "FizzBuzz"

    def test_hardcoded_evaluate_fizz(self):
        assert LivenessProbe._hardcoded_evaluate(3) == "Fizz"

    def test_hardcoded_evaluate_buzz(self):
        assert LivenessProbe._hardcoded_evaluate(5) == "Buzz"

    def test_hardcoded_evaluate_fizzbuzz(self):
        assert LivenessProbe._hardcoded_evaluate(15) == "FizzBuzz"

    def test_hardcoded_evaluate_plain(self):
        assert LivenessProbe._hardcoded_evaluate(7) == "7"

    def test_custom_canary_number(self):
        probe = LivenessProbe(
            evaluate_fn=lambda n: "Fizz" if n % 3 == 0 else str(n),
            canary_number=3,
            canary_expected="Fizz",
        )
        report = probe.probe()
        assert report.overall_status == HealthStatus.UP

    def test_publishes_events(self, event_bus):
        received = []

        class HealthObserver:
            def on_event(self, event):
                received.append(event)
            def get_name(self):
                return "HealthObserver"

        event_bus.subscribe(HealthObserver())

        probe = LivenessProbe(
            evaluate_fn=lambda n: "FizzBuzz",
            canary_number=15,
            canary_expected="FizzBuzz",
            event_bus=event_bus,
        )
        probe.probe()

        event_types = [e.event_type for e in received]
        assert EventType.HEALTH_CHECK_STARTED in event_types
        assert EventType.HEALTH_LIVENESS_PASSED in event_types
        assert EventType.HEALTH_CHECK_COMPLETED in event_types


# ============================================================
# Readiness Probe Tests
# ============================================================


class TestReadinessProbe:
    def test_all_up(self, health_registry):
        health_registry.register(ConfigHealthCheck())
        health_registry.register(CacheCoherenceHealthCheck())
        probe = ReadinessProbe(registry=health_registry)
        report = probe.probe()
        assert report.probe_type == ProbeType.READINESS
        assert report.overall_status == HealthStatus.UP

    def test_degraded_subsystem_still_ready(self, health_registry):
        mock_cache = MagicMock()
        mock_cache.get_statistics.return_value = {
            "total_requests": 100,
            "hits": 5,
            "current_size": 50,
            "max_size": 1024,
        }
        health_registry.register(CacheCoherenceHealthCheck(cache_store=mock_cache))
        probe = ReadinessProbe(registry=health_registry, degraded_is_ready=True)
        report = probe.probe()
        assert report.overall_status == HealthStatus.DEGRADED

    def test_degraded_not_ready_when_configured(self, health_registry):
        mock_cache = MagicMock()
        mock_cache.get_statistics.return_value = {
            "total_requests": 100,
            "hits": 5,
            "current_size": 50,
            "max_size": 1024,
        }
        health_registry.register(ConfigHealthCheck())
        health_registry.register(CacheCoherenceHealthCheck(cache_store=mock_cache))
        probe = ReadinessProbe(registry=health_registry, degraded_is_ready=False)
        report = probe.probe()
        assert report.overall_status == HealthStatus.DOWN

    def test_down_subsystem(self, health_registry):
        mock_engine = MagicMock()
        mock_engine.evaluate.side_effect = RuntimeError("broken")
        health_registry.register(MLEngineHealthCheck(engine=mock_engine, rules=[]))
        probe = ReadinessProbe(registry=health_registry)
        report = probe.probe()
        assert report.overall_status == HealthStatus.DOWN

    def test_existential_crisis_is_worst(self, health_registry):
        mock_engine = MagicMock()
        def make_result(n, rules):
            result = MagicMock()
            result.output = "42"
            result.metadata = {}
            return result
        mock_engine.evaluate.side_effect = make_result

        health_registry.register(ConfigHealthCheck())
        health_registry.register(MLEngineHealthCheck(engine=mock_engine, rules=[]))
        probe = ReadinessProbe(registry=health_registry)
        report = probe.probe()
        assert report.overall_status == HealthStatus.EXISTENTIAL_CRISIS

    def test_publishes_events(self, health_registry, event_bus):
        received = []

        class HealthObserver:
            def on_event(self, event):
                received.append(event)
            def get_name(self):
                return "HealthObserver"

        event_bus.subscribe(HealthObserver())

        health_registry.register(ConfigHealthCheck())
        probe = ReadinessProbe(registry=health_registry, event_bus=event_bus)
        probe.probe()

        event_types = [e.event_type for e in received]
        assert EventType.HEALTH_CHECK_STARTED in event_types
        assert EventType.HEALTH_READINESS_PASSED in event_types


# ============================================================
# Startup Probe Tests
# ============================================================


class TestStartupProbe:
    def test_all_milestones_complete(self):
        probe = StartupProbe(milestones=["a", "b", "c"])
        probe.record_milestone("a")
        probe.record_milestone("b")
        probe.record_milestone("c")
        assert probe.is_complete() is True
        report = probe.probe()
        assert report.overall_status == HealthStatus.UP

    def test_pending_milestones(self):
        probe = StartupProbe(milestones=["a", "b", "c"])
        probe.record_milestone("a")
        assert probe.is_complete() is False
        pending = probe.get_pending_milestones()
        assert "b" in pending
        assert "c" in pending

    def test_completed_milestones(self):
        probe = StartupProbe(milestones=["a", "b"])
        probe.record_milestone("a")
        completed = probe.get_completed_milestones()
        assert "a" in completed
        assert "b" not in completed

    def test_degraded_when_in_progress(self):
        probe = StartupProbe(milestones=["a", "b"], timeout_seconds=9999)
        probe.record_milestone("a")
        report = probe.probe()
        assert report.overall_status == HealthStatus.DEGRADED

    def test_down_when_timed_out(self):
        probe = StartupProbe(milestones=["a", "b"], timeout_seconds=0)
        # Let time pass
        report = probe.probe()
        assert report.overall_status == HealthStatus.DOWN

    def test_duplicate_milestone_ignored(self):
        probe = StartupProbe(milestones=["a"])
        probe.record_milestone("a")
        probe.record_milestone("a")
        assert len(probe.get_completed_milestones()) == 1

    def test_subsystem_checks_reflect_milestones(self):
        probe = StartupProbe(milestones=["a", "b"])
        probe.record_milestone("a")
        report = probe.probe()
        checks_by_name = {c.subsystem_name: c for c in report.subsystem_checks}
        assert checks_by_name["startup:a"].status == HealthStatus.UP
        assert checks_by_name["startup:b"].status == HealthStatus.DOWN

    def test_publishes_milestone_events(self, event_bus):
        received = []

        class HealthObserver:
            def on_event(self, event):
                received.append(event)
            def get_name(self):
                return "HealthObserver"

        event_bus.subscribe(HealthObserver())

        probe = StartupProbe(milestones=["a"], event_bus=event_bus)
        probe.record_milestone("a")

        event_types = [e.event_type for e in received]
        assert EventType.HEALTH_STARTUP_MILESTONE in event_types

    def test_probe_type_is_startup(self):
        probe = StartupProbe(milestones=["a"])
        probe.record_milestone("a")
        report = probe.probe()
        assert report.probe_type == ProbeType.STARTUP


# ============================================================
# Self-Healing Manager Tests
# ============================================================


class TestSelfHealingManager:
    def test_successful_recovery(self, health_registry):
        class HealableCheck(SubsystemHealthCheck):
            def get_name(self):
                return "healable"
            def check(self):
                return SubsystemCheck(
                    subsystem_name="healable",
                    status=HealthStatus.DOWN,
                )
            def recover(self):
                return True

        health_registry.register(HealableCheck())
        healer = SelfHealingManager(registry=health_registry, max_retries=3)
        assert healer.attempt_recovery("healable") is True

    def test_failed_recovery(self, health_registry):
        class UnhealableCheck(SubsystemHealthCheck):
            def get_name(self):
                return "unhealable"
            def check(self):
                return SubsystemCheck(
                    subsystem_name="unhealable",
                    status=HealthStatus.DOWN,
                )
            def recover(self):
                return False

        health_registry.register(UnhealableCheck())
        healer = SelfHealingManager(registry=health_registry, max_retries=3)
        assert healer.attempt_recovery("unhealable") is False

    def test_max_retries_exhausted(self, health_registry):
        class FailingCheck(SubsystemHealthCheck):
            def get_name(self):
                return "failing"
            def check(self):
                return SubsystemCheck(
                    subsystem_name="failing",
                    status=HealthStatus.DOWN,
                )
            def recover(self):
                return False

        health_registry.register(FailingCheck())
        healer = SelfHealingManager(registry=health_registry, max_retries=2)

        healer.attempt_recovery("failing")
        healer.attempt_recovery("failing")
        # Third attempt should be blocked by max_retries
        assert healer.attempt_recovery("failing") is False

    def test_successful_recovery_resets_counter(self, health_registry):
        call_count = 0

        class EventuallyHealable(SubsystemHealthCheck):
            def get_name(self):
                return "eventually"
            def check(self):
                return SubsystemCheck(
                    subsystem_name="eventually",
                    status=HealthStatus.DOWN,
                )
            def recover(self):
                nonlocal call_count
                call_count += 1
                return call_count >= 2

        health_registry.register(EventuallyHealable())
        healer = SelfHealingManager(registry=health_registry, max_retries=3)

        # First attempt fails
        healer.attempt_recovery("eventually")
        # Second attempt succeeds and resets counter
        healer.attempt_recovery("eventually")
        assert healer.get_attempt_counts().get("eventually", -1) == 0

    def test_heal_all_unhealthy(self, health_registry):
        class DownCheck(SubsystemHealthCheck):
            def get_name(self):
                return "down_system"
            def check(self):
                return SubsystemCheck(
                    subsystem_name="down_system",
                    status=HealthStatus.DOWN,
                )
            def recover(self):
                return True

        health_registry.register(DownCheck())
        healer = SelfHealingManager(registry=health_registry)

        checks = [
            SubsystemCheck(subsystem_name="down_system", status=HealthStatus.DOWN),
            SubsystemCheck(subsystem_name="healthy_system", status=HealthStatus.UP),
        ]
        results = healer.heal_all_unhealthy(checks)
        assert results["down_system"] is True
        assert "healthy_system" not in results

    def test_nonexistent_subsystem(self, health_registry):
        healer = SelfHealingManager(registry=health_registry)
        assert healer.attempt_recovery("nonexistent") is False

    def test_reset(self, health_registry):
        class FailCheck(SubsystemHealthCheck):
            def get_name(self):
                return "fail"
            def check(self):
                return SubsystemCheck(subsystem_name="fail", status=HealthStatus.DOWN)
            def recover(self):
                return False

        health_registry.register(FailCheck())
        healer = SelfHealingManager(registry=health_registry, max_retries=2)
        healer.attempt_recovery("fail")
        assert healer.get_attempt_counts()["fail"] == 1
        healer.reset()
        assert healer.get_attempt_counts() == {}


# ============================================================
# Health Dashboard Tests
# ============================================================


class TestHealthDashboard:
    def test_render_liveness_report(self):
        report = HealthReport(
            probe_type=ProbeType.LIVENESS,
            overall_status=HealthStatus.UP,
            subsystem_checks=[
                SubsystemCheck(
                    subsystem_name="liveness_canary",
                    status=HealthStatus.UP,
                    response_time_ms=0.5,
                    details="FizzBuzz confirmed",
                ),
            ],
            canary_value="FizzBuzz",
        )
        dashboard = HealthDashboard.render(report)
        assert "HEALTH CHECK DASHBOARD" in dashboard
        assert "LIVENESS" in dashboard
        assert "UP" in dashboard
        assert "FizzBuzz" in dashboard

    def test_render_readiness_with_multiple_checks(self):
        report = HealthReport(
            probe_type=ProbeType.READINESS,
            overall_status=HealthStatus.DEGRADED,
            subsystem_checks=[
                SubsystemCheck(subsystem_name="config", status=HealthStatus.UP),
                SubsystemCheck(subsystem_name="cache", status=HealthStatus.DEGRADED),
                SubsystemCheck(subsystem_name="ml_engine", status=HealthStatus.UP),
            ],
        )
        dashboard = HealthDashboard.render(report)
        assert "READINESS" in dashboard
        assert "DEGRADED" in dashboard
        assert "config" in dashboard
        assert "cache" in dashboard

    def test_render_empty_report(self):
        report = HealthReport(
            probe_type=ProbeType.READINESS,
            overall_status=HealthStatus.UP,
        )
        dashboard = HealthDashboard.render(report)
        assert "no subsystem checks" in dashboard.lower()

    def test_render_existential_crisis(self):
        report = HealthReport(
            probe_type=ProbeType.READINESS,
            overall_status=HealthStatus.EXISTENTIAL_CRISIS,
            subsystem_checks=[
                SubsystemCheck(
                    subsystem_name="ml_engine",
                    status=HealthStatus.EXISTENTIAL_CRISIS,
                    details="The ML engine has doubts",
                ),
            ],
        )
        dashboard = HealthDashboard.render(report)
        assert "CRISIS" in dashboard

    def test_render_without_details(self):
        report = HealthReport(
            probe_type=ProbeType.LIVENESS,
            overall_status=HealthStatus.DOWN,
            subsystem_checks=[
                SubsystemCheck(
                    subsystem_name="test",
                    status=HealthStatus.DOWN,
                    details="something broke",
                ),
            ],
        )
        dashboard = HealthDashboard.render(report, show_details=False)
        assert "HEALTH CHECK DASHBOARD" in dashboard
        # details should not be shown
        assert "something broke" not in dashboard

    def test_render_compact(self):
        report = HealthReport(
            probe_type=ProbeType.LIVENESS,
            overall_status=HealthStatus.UP,
            subsystem_checks=[
                SubsystemCheck(subsystem_name="config", status=HealthStatus.UP),
            ],
        )
        compact = HealthDashboard.render_compact(report)
        assert "LIVENESS" in compact
        assert "config=UP" in compact

    def test_all_status_indicators_exist(self):
        for status in HealthStatus:
            assert status in HealthDashboard.STATUS_INDICATORS
            assert status in HealthDashboard.STATUS_LABELS


# ============================================================
# Config Properties Tests
# ============================================================


class TestHealthConfigProperties:
    def test_health_check_enabled_default(self, config):
        assert config.health_check_enabled is False

    def test_canary_number_default(self, config):
        assert config.health_check_canary_number == 15

    def test_canary_expected_default(self, config):
        assert config.health_check_canary_expected == "FizzBuzz"

    def test_required_subsystems_default(self, config):
        subs = config.health_check_required_subsystems
        assert "config" in subs
        assert "circuit_breaker" in subs

    def test_degraded_is_ready_default(self, config):
        assert config.health_check_degraded_is_ready is True

    def test_startup_milestones_default(self, config):
        milestones = config.health_check_startup_milestones
        assert "config_loaded" in milestones
        assert "service_built" in milestones

    def test_self_healing_enabled_default(self, config):
        assert config.health_check_self_healing_enabled is True

    def test_self_healing_max_retries_default(self, config):
        assert config.health_check_self_healing_max_retries == 3

    def test_dashboard_width_default(self, config):
        assert config.health_check_dashboard_width == 60

    def test_dashboard_show_details_default(self, config):
        assert config.health_check_dashboard_show_details is True


# ============================================================
# Integration Tests
# ============================================================


class TestHealthIntegration:
    def test_full_readiness_probe_with_all_subsystems(self, config, health_registry):
        """Verify that a full readiness probe works with all subsystem checks registered."""
        health_registry.register(ConfigHealthCheck(config=config))
        health_registry.register(CircuitBreakerHealthCheck(registry=None))
        health_registry.register(CacheCoherenceHealthCheck(cache_store=None))
        health_registry.register(SLABudgetHealthCheck(sla_monitor=None))
        health_registry.register(MLEngineHealthCheck(engine=None, rules=None))

        probe = ReadinessProbe(registry=health_registry)
        report = probe.probe()

        assert report.overall_status == HealthStatus.UP
        assert len(report.subsystem_checks) == 5

    def test_liveness_then_readiness_then_startup(self, health_registry):
        """All three probes should be independently runnable."""
        health_registry.register(ConfigHealthCheck())

        liveness = LivenessProbe(evaluate_fn=lambda n: "FizzBuzz")
        readiness = ReadinessProbe(registry=health_registry)
        startup = StartupProbe(milestones=["boot"])
        startup.record_milestone("boot")

        l_report = liveness.probe()
        r_report = readiness.probe()
        s_report = startup.probe()

        assert l_report.probe_type == ProbeType.LIVENESS
        assert r_report.probe_type == ProbeType.READINESS
        assert s_report.probe_type == ProbeType.STARTUP
        assert l_report.overall_status == HealthStatus.UP
        assert r_report.overall_status == HealthStatus.UP
        assert s_report.overall_status == HealthStatus.UP

    def test_self_healing_after_readiness_failure(self, health_registry):
        """Self-healing should recover failing subsystems after readiness check."""
        healed = False

        class HealableSubsystem(SubsystemHealthCheck):
            def get_name(self):
                return "healable"
            def check(self):
                if healed:
                    return SubsystemCheck(subsystem_name="healable", status=HealthStatus.UP)
                return SubsystemCheck(subsystem_name="healable", status=HealthStatus.DOWN)
            def recover(self):
                nonlocal healed
                healed = True
                return True

        health_registry.register(HealableSubsystem())
        readiness = ReadinessProbe(registry=health_registry)
        healer = SelfHealingManager(registry=health_registry)

        # First check: DOWN
        report1 = readiness.probe()
        assert report1.overall_status == HealthStatus.DOWN

        # Heal
        healer.heal_all_unhealthy(report1.subsystem_checks)

        # Second check: UP
        report2 = readiness.probe()
        assert report2.overall_status == HealthStatus.UP

    def test_dashboard_renders_all_statuses(self):
        """Every HealthStatus should render without error."""
        for status in HealthStatus:
            report = HealthReport(
                probe_type=ProbeType.READINESS,
                overall_status=status,
                subsystem_checks=[
                    SubsystemCheck(subsystem_name="test", status=status),
                ],
            )
            dashboard = HealthDashboard.render(report)
            assert "HEALTH CHECK DASHBOARD" in dashboard
