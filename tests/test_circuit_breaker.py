"""
Enterprise FizzBuzz Platform - Circuit Breaker Test Suite

Comprehensive tests for the circuit breaker with exponential backoff.
Because fault tolerance for modulo arithmetic deserves thorough validation.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path
from unittest.mock import MagicMock

import pytest

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerDashboard,
    CircuitBreakerMetrics,
    CircuitBreakerMiddleware,
    CircuitBreakerRegistry,
    CircuitState,
    ExponentialBackoffCalculator,
    SlidingWindow,
    SlidingWindowEntry,
)
from config import ConfigurationManager, _SingletonMeta
from exceptions import (
    CircuitBreakerTimeoutError,
    CircuitOpenError,
    DownstreamFizzBuzzDegradationError,
)
from models import Event, EventType, ProcessingContext


# ============================================================
# Fixtures
# ============================================================


@pytest.fixture(autouse=True)
def reset_singletons():
    """Reset all singletons between tests."""
    _SingletonMeta.reset()
    CircuitBreakerRegistry.reset()
    yield


@pytest.fixture
def event_bus():
    """Create a mock event bus for testing."""
    bus = MagicMock()
    return bus


@pytest.fixture
def backoff():
    """Create a standard exponential backoff calculator."""
    return ExponentialBackoffCalculator(base_ms=100.0, multiplier=2.0, max_ms=5000.0)


@pytest.fixture
def circuit_breaker(event_bus, backoff):
    """Create a circuit breaker with low thresholds for testing."""
    return CircuitBreaker(
        name="TestCircuit",
        failure_threshold=3,
        success_threshold=2,
        timeout_ms=5000.0,
        sliding_window_size=10,
        half_open_max_calls=2,
        backoff_calculator=backoff,
        ml_confidence_threshold=0.7,
        call_timeout_ms=5000.0,
        event_bus=event_bus,
    )


# ============================================================
# CircuitState Tests
# ============================================================


class TestCircuitState:
    def test_enum_members_exist(self):
        assert CircuitState.CLOSED.name == "CLOSED"
        assert CircuitState.OPEN.name == "OPEN"
        assert CircuitState.HALF_OPEN.name == "HALF_OPEN"

    def test_enum_values_are_unique(self):
        values = [s.value for s in CircuitState]
        assert len(values) == len(set(values))


# ============================================================
# SlidingWindowEntry Tests
# ============================================================


class TestSlidingWindowEntry:
    def test_creation_with_defaults(self):
        entry = SlidingWindowEntry(timestamp=1.0, success=True)
        assert entry.timestamp == 1.0
        assert entry.success is True
        assert entry.duration_ms == 0.0
        assert entry.ml_confidence is None

    def test_creation_with_all_fields(self):
        entry = SlidingWindowEntry(
            timestamp=1.0, success=False, duration_ms=42.5, ml_confidence=0.95
        )
        assert entry.success is False
        assert entry.duration_ms == 42.5
        assert entry.ml_confidence == 0.95


# ============================================================
# SlidingWindow Tests
# ============================================================


class TestSlidingWindow:
    def test_empty_window(self):
        window = SlidingWindow(max_size=5)
        assert window.get_failure_count() == 0
        assert window.get_success_count() == 0
        assert window.get_failure_rate() == 0.0
        assert window.get_entry_count() == 0
        assert window.get_average_confidence() is None

    def test_record_success(self):
        window = SlidingWindow(max_size=5)
        window.record(SlidingWindowEntry(timestamp=1.0, success=True))
        assert window.get_success_count() == 1
        assert window.get_failure_count() == 0
        assert window.get_failure_rate() == 0.0

    def test_record_failure(self):
        window = SlidingWindow(max_size=5)
        window.record(SlidingWindowEntry(timestamp=1.0, success=False))
        assert window.get_failure_count() == 1
        assert window.get_failure_rate() == 1.0

    def test_sliding_eviction(self):
        window = SlidingWindow(max_size=3)
        for i in range(5):
            window.record(SlidingWindowEntry(timestamp=float(i), success=(i >= 3)))
        # Only the last 3 entries should remain: indices 2(fail), 3(success), 4(success)
        assert window.get_entry_count() == 3
        assert window.get_success_count() == 2
        assert window.get_failure_count() == 1

    def test_failure_rate_calculation(self):
        window = SlidingWindow(max_size=10)
        for i in range(4):
            window.record(SlidingWindowEntry(timestamp=float(i), success=True))
        window.record(SlidingWindowEntry(timestamp=5.0, success=False))
        assert window.get_failure_rate() == pytest.approx(0.2)

    def test_average_confidence(self):
        window = SlidingWindow(max_size=10)
        window.record(SlidingWindowEntry(timestamp=1.0, success=True, ml_confidence=0.8))
        window.record(SlidingWindowEntry(timestamp=2.0, success=True, ml_confidence=0.6))
        assert window.get_average_confidence() == pytest.approx(0.7)

    def test_average_confidence_ignores_none(self):
        window = SlidingWindow(max_size=10)
        window.record(SlidingWindowEntry(timestamp=1.0, success=True, ml_confidence=0.8))
        window.record(SlidingWindowEntry(timestamp=2.0, success=True))  # no confidence
        assert window.get_average_confidence() == pytest.approx(0.8)

    def test_clear(self):
        window = SlidingWindow(max_size=5)
        window.record(SlidingWindowEntry(timestamp=1.0, success=True))
        window.clear()
        assert window.get_entry_count() == 0

    def test_get_entries_returns_copy(self):
        window = SlidingWindow(max_size=5)
        window.record(SlidingWindowEntry(timestamp=1.0, success=True))
        entries = window.get_entries()
        entries.clear()
        assert window.get_entry_count() == 1  # original not affected


# ============================================================
# ExponentialBackoffCalculator Tests
# ============================================================


class TestExponentialBackoffCalculator:
    def test_first_attempt(self, backoff):
        assert backoff.calculate(0) == 100.0

    def test_second_attempt(self, backoff):
        assert backoff.calculate(1) == 200.0

    def test_third_attempt(self, backoff):
        assert backoff.calculate(2) == 400.0

    def test_cap_at_max(self, backoff):
        # With base=100, multiplier=2, attempt=20 would be huge
        result = backoff.calculate(20)
        assert result == 5000.0

    def test_properties(self, backoff):
        assert backoff.base_ms == 100.0
        assert backoff.multiplier == 2.0
        assert backoff.max_ms == 5000.0

    def test_custom_multiplier(self):
        calc = ExponentialBackoffCalculator(base_ms=50, multiplier=3.0, max_ms=10000)
        assert calc.calculate(0) == 50.0
        assert calc.calculate(1) == 150.0
        assert calc.calculate(2) == 450.0


# ============================================================
# CircuitBreakerMetrics Tests
# ============================================================


class TestCircuitBreakerMetrics:
    def test_default_values(self):
        metrics = CircuitBreakerMetrics()
        assert metrics.total_calls == 0
        assert metrics.total_successes == 0
        assert metrics.total_failures == 0
        assert metrics.total_rejections == 0
        assert metrics.total_timeouts == 0
        assert metrics.consecutive_failures == 0
        assert metrics.consecutive_successes == 0
        assert metrics.trip_count == 0
        assert metrics.current_backoff_attempt == 0
        assert metrics.last_failure_time is None
        assert metrics.last_success_time is None


# ============================================================
# CircuitBreaker Tests
# ============================================================


class TestCircuitBreaker:
    def test_initial_state_is_closed(self, circuit_breaker):
        assert circuit_breaker.state == CircuitState.CLOSED

    def test_successful_call(self, circuit_breaker):
        result = circuit_breaker.execute(lambda: 42)
        assert result == 42
        assert circuit_breaker.metrics.total_calls == 1
        assert circuit_breaker.metrics.total_successes == 1

    def test_failed_call_increments_failures(self, circuit_breaker):
        with pytest.raises(ValueError):
            circuit_breaker.execute(lambda: (_ for _ in ()).throw(ValueError("boom")))
        assert circuit_breaker.metrics.total_failures == 1
        assert circuit_breaker.metrics.consecutive_failures == 1

    def test_trips_after_threshold(self, circuit_breaker):
        # Threshold is 3 failures
        for i in range(3):
            with pytest.raises(ValueError):
                circuit_breaker.execute(lambda: (_ for _ in ()).throw(ValueError("fail")))

        assert circuit_breaker.state == CircuitState.OPEN
        assert circuit_breaker.metrics.trip_count == 1

    def test_open_circuit_rejects_calls(self, circuit_breaker):
        # Trip the circuit
        for i in range(3):
            with pytest.raises(ValueError):
                circuit_breaker.execute(lambda: (_ for _ in ()).throw(ValueError("fail")))

        # Next call should be rejected
        with pytest.raises(CircuitOpenError):
            circuit_breaker.execute(lambda: 42)

        assert circuit_breaker.metrics.total_rejections == 1

    def test_reset_returns_to_closed(self, circuit_breaker):
        # Trip the circuit
        for i in range(3):
            with pytest.raises(ValueError):
                circuit_breaker.execute(lambda: (_ for _ in ()).throw(ValueError("fail")))

        assert circuit_breaker.state == CircuitState.OPEN
        circuit_breaker.reset()
        assert circuit_breaker.state == CircuitState.CLOSED

    def test_successful_calls_reset_consecutive_failures(self, circuit_breaker):
        # 2 failures then a success
        for i in range(2):
            with pytest.raises(ValueError):
                circuit_breaker.execute(lambda: (_ for _ in ()).throw(ValueError("fail")))
        circuit_breaker.execute(lambda: "ok")

        assert circuit_breaker.metrics.consecutive_failures == 0
        assert circuit_breaker.metrics.consecutive_successes == 1

    def test_name_property(self, circuit_breaker):
        assert circuit_breaker.name == "TestCircuit"

    def test_get_status_report(self, circuit_breaker):
        circuit_breaker.execute(lambda: 42)
        report = circuit_breaker.get_status_report()
        assert report["name"] == "TestCircuit"
        assert report["state"] == "CLOSED"
        assert report["metrics"]["total_calls"] == 1
        assert report["metrics"]["total_successes"] == 1

    def test_event_published_on_trip(self, circuit_breaker, event_bus):
        for i in range(3):
            with pytest.raises(ValueError):
                circuit_breaker.execute(lambda: (_ for _ in ()).throw(ValueError("fail")))

        # Should have published events
        assert event_bus.publish.called

        # Find the TRIPPED event
        tripped_calls = [
            call for call in event_bus.publish.call_args_list
            if call[0][0].event_type == EventType.CIRCUIT_BREAKER_TRIPPED
        ]
        assert len(tripped_calls) == 1

    def test_event_published_on_recovery(self, circuit_breaker, event_bus):
        circuit_breaker.reset()
        # reset publishes RECOVERED and STATE_CHANGED
        recovered_calls = [
            call for call in event_bus.publish.call_args_list
            if call[0][0].event_type == EventType.CIRCUIT_BREAKER_RECOVERED
        ]
        # Reset from CLOSED to CLOSED doesn't publish (same state)
        # Let's trip then reset
        event_bus.reset_mock()
        for i in range(3):
            with pytest.raises(ValueError):
                circuit_breaker.execute(lambda: (_ for _ in ()).throw(ValueError("fail")))
        event_bus.reset_mock()

        circuit_breaker.reset()
        recovered_calls = [
            call for call in event_bus.publish.call_args_list
            if call[0][0].event_type == EventType.CIRCUIT_BREAKER_RECOVERED
        ]
        assert len(recovered_calls) == 1

    def test_half_open_after_backoff_timeout(self):
        """Test that circuit transitions to HALF_OPEN after backoff expires."""
        backoff = ExponentialBackoffCalculator(base_ms=10.0, multiplier=2.0, max_ms=100.0)
        cb = CircuitBreaker(
            name="FastCircuit",
            failure_threshold=2,
            success_threshold=1,
            backoff_calculator=backoff,
            call_timeout_ms=50000.0,
        )

        # Trip it
        for i in range(2):
            with pytest.raises(ValueError):
                cb.execute(lambda: (_ for _ in ()).throw(ValueError("fail")))

        assert cb.state == CircuitState.OPEN

        # Wait for backoff (10ms for first attempt)
        time.sleep(0.02)

        # Should transition to HALF_OPEN on state check
        assert cb.state == CircuitState.HALF_OPEN

    def test_half_open_success_closes_circuit(self):
        """Test that enough successes in HALF_OPEN closes the circuit."""
        backoff = ExponentialBackoffCalculator(base_ms=10.0, multiplier=2.0, max_ms=100.0)
        cb = CircuitBreaker(
            name="RecoveryCircuit",
            failure_threshold=2,
            success_threshold=2,
            backoff_calculator=backoff,
            call_timeout_ms=50000.0,
        )

        # Trip it
        for i in range(2):
            with pytest.raises(ValueError):
                cb.execute(lambda: (_ for _ in ()).throw(ValueError("fail")))

        time.sleep(0.02)
        assert cb.state == CircuitState.HALF_OPEN

        # Two successes should close the circuit
        cb.execute(lambda: "ok")
        cb.execute(lambda: "ok")

        assert cb.state == CircuitState.CLOSED

    def test_half_open_failure_reopens_circuit(self):
        """Test that failure in HALF_OPEN re-opens the circuit."""
        backoff = ExponentialBackoffCalculator(base_ms=10.0, multiplier=2.0, max_ms=100.0)
        cb = CircuitBreaker(
            name="RelapseCircuit",
            failure_threshold=2,
            success_threshold=2,
            backoff_calculator=backoff,
            call_timeout_ms=50000.0,
        )

        # Trip it
        for i in range(2):
            with pytest.raises(ValueError):
                cb.execute(lambda: (_ for _ in ()).throw(ValueError("fail")))

        time.sleep(0.02)
        assert cb.state == CircuitState.HALF_OPEN

        # Fail again
        with pytest.raises(ValueError):
            cb.execute(lambda: (_ for _ in ()).throw(ValueError("relapse")))

        assert cb.state == CircuitState.OPEN

    def test_backoff_attempt_increments_on_reopen(self):
        """Test that the backoff attempt counter increases when re-opening."""
        backoff = ExponentialBackoffCalculator(base_ms=10.0, multiplier=2.0, max_ms=1000.0)
        cb = CircuitBreaker(
            name="BackoffCircuit",
            failure_threshold=1,
            success_threshold=1,
            backoff_calculator=backoff,
            call_timeout_ms=50000.0,
        )

        # First trip
        with pytest.raises(ValueError):
            cb.execute(lambda: (_ for _ in ()).throw(ValueError("fail")))
        assert cb.metrics.current_backoff_attempt == 0

        # Wait and go to half-open
        time.sleep(0.02)
        assert cb.state == CircuitState.HALF_OPEN

        # Fail again in half-open -> should increment backoff attempt
        with pytest.raises(ValueError):
            cb.execute(lambda: (_ for _ in ()).throw(ValueError("fail again")))
        assert cb.state == CircuitState.OPEN
        assert cb.metrics.current_backoff_attempt == 1

    def test_metrics_copy_is_independent(self, circuit_breaker):
        """Ensure metrics property returns a copy, not the internal object."""
        m1 = circuit_breaker.metrics
        m1.total_calls = 999
        m2 = circuit_breaker.metrics
        assert m2.total_calls == 0  # internal not affected


# ============================================================
# CircuitBreakerRegistry Tests
# ============================================================


class TestCircuitBreakerRegistry:
    def test_singleton(self):
        r1 = CircuitBreakerRegistry.get_instance()
        r2 = CircuitBreakerRegistry.get_instance()
        assert r1 is r2

    def test_reset(self):
        r1 = CircuitBreakerRegistry.get_instance()
        CircuitBreakerRegistry.reset()
        r2 = CircuitBreakerRegistry.get_instance()
        assert r1 is not r2

    def test_get_or_create(self):
        registry = CircuitBreakerRegistry.get_instance()
        cb = registry.get_or_create("TestCB", failure_threshold=3)
        assert cb.name == "TestCB"

    def test_get_or_create_returns_same_instance(self):
        registry = CircuitBreakerRegistry.get_instance()
        cb1 = registry.get_or_create("TestCB", failure_threshold=3)
        cb2 = registry.get_or_create("TestCB", failure_threshold=5)  # different params
        assert cb1 is cb2  # returns existing

    def test_get_returns_none_for_unknown(self):
        registry = CircuitBreakerRegistry.get_instance()
        assert registry.get("NonExistent") is None

    def test_list_all(self):
        registry = CircuitBreakerRegistry.get_instance()
        registry.get_or_create("CB1")
        registry.get_or_create("CB2")
        names = registry.list_all()
        assert "CB1" in names
        assert "CB2" in names

    def test_remove(self):
        registry = CircuitBreakerRegistry.get_instance()
        registry.get_or_create("ToRemove")
        assert registry.remove("ToRemove") is True
        assert registry.get("ToRemove") is None

    def test_remove_nonexistent(self):
        registry = CircuitBreakerRegistry.get_instance()
        assert registry.remove("DoesNotExist") is False

    def test_get_all_status_reports(self):
        registry = CircuitBreakerRegistry.get_instance()
        registry.get_or_create("CB1")
        registry.get_or_create("CB2")
        reports = registry.get_all_status_reports()
        assert len(reports) == 2
        names = {r["name"] for r in reports}
        assert "CB1" in names
        assert "CB2" in names


# ============================================================
# CircuitBreakerMiddleware Tests
# ============================================================


class TestCircuitBreakerMiddleware:
    def test_passes_through_on_closed_circuit(self):
        middleware = CircuitBreakerMiddleware(failure_threshold=5)
        context = ProcessingContext(number=42, session_id="test")

        def handler(ctx):
            ctx.metadata["processed"] = True
            return ctx

        result = middleware.process(context, handler)
        assert result.metadata.get("processed") is True

    def test_rejects_on_open_circuit(self):
        middleware = CircuitBreakerMiddleware(failure_threshold=2, call_timeout_ms=50000.0)

        # Trip the circuit by causing failures
        for i in range(2):
            context = ProcessingContext(number=i, session_id="test")
            with pytest.raises(RuntimeError):
                middleware.process(
                    context,
                    lambda ctx: (_ for _ in ()).throw(RuntimeError("downstream fail")),
                )

        # Now it should reject
        context = ProcessingContext(number=99, session_id="test")
        with pytest.raises(CircuitOpenError):
            middleware.process(context, lambda ctx: ctx)

    def test_get_name(self):
        middleware = CircuitBreakerMiddleware()
        assert middleware.get_name() == "CircuitBreakerMiddleware"

    def test_get_priority(self):
        middleware = CircuitBreakerMiddleware()
        assert middleware.get_priority() == -1  # highest priority

    def test_circuit_breaker_accessible(self):
        middleware = CircuitBreakerMiddleware()
        assert middleware.circuit_breaker is not None
        assert isinstance(middleware.circuit_breaker, CircuitBreaker)

    def test_custom_circuit_breaker_injection(self, circuit_breaker):
        middleware = CircuitBreakerMiddleware(circuit_breaker=circuit_breaker)
        assert middleware.circuit_breaker is circuit_breaker


# ============================================================
# CircuitBreakerDashboard Tests
# ============================================================


class TestCircuitBreakerDashboard:
    def test_render_closed_circuit(self, circuit_breaker):
        output = CircuitBreakerDashboard.render(circuit_breaker)
        assert "CIRCUIT BREAKER STATUS DASHBOARD" in output
        assert "TestCircuit" in output
        assert "CLOSED" in output

    def test_render_open_circuit(self, circuit_breaker):
        # Trip the circuit
        for i in range(3):
            with pytest.raises(ValueError):
                circuit_breaker.execute(lambda: (_ for _ in ()).throw(ValueError("fail")))

        output = CircuitBreakerDashboard.render(circuit_breaker)
        assert "OPEN" in output
        assert "Trip Count" in output

    def test_render_shows_metrics(self, circuit_breaker):
        circuit_breaker.execute(lambda: 42)
        circuit_breaker.execute(lambda: 43)
        output = CircuitBreakerDashboard.render(circuit_breaker)
        assert "Total Calls" in output

    def test_render_sliding_window_visualization(self, circuit_breaker):
        circuit_breaker.execute(lambda: 1)
        with pytest.raises(ValueError):
            circuit_breaker.execute(lambda: (_ for _ in ()).throw(ValueError("fail")))
        circuit_breaker.execute(lambda: 3)

        output = CircuitBreakerDashboard.render(circuit_breaker)
        assert "Sliding Window" in output
        # Should show + for success and X for failure
        assert "+" in output
        assert "X" in output

    def test_render_all_empty_registry(self):
        registry = CircuitBreakerRegistry.get_instance()
        output = CircuitBreakerDashboard.render_all(registry)
        assert "No circuit breakers registered" in output

    def test_render_all_with_circuits(self):
        registry = CircuitBreakerRegistry.get_instance()
        registry.get_or_create("TestCB1")
        registry.get_or_create("TestCB2")
        output = CircuitBreakerDashboard.render_all(registry)
        assert "TestCB1" in output
        assert "TestCB2" in output


# ============================================================
# Exception Tests
# ============================================================


class TestCircuitBreakerExceptions:
    def test_circuit_open_error(self):
        err = CircuitOpenError("TestCircuit", 5000.0)
        assert "EFP-CB00" in str(err)
        assert "TestCircuit" in str(err)
        assert err.circuit_name == "TestCircuit"
        assert err.retry_after_ms == 5000.0

    def test_circuit_breaker_timeout_error(self):
        err = CircuitBreakerTimeoutError("TestCircuit", 1000.0, 1500.0)
        assert "EFP-CB01" in str(err)
        assert "timed out" in str(err)

    def test_downstream_degradation_error(self):
        err = DownstreamFizzBuzzDegradationError("ml_confidence", 0.3, 0.7)
        assert "EFP-CB02" in str(err)
        assert "degradation" in str(err)


# ============================================================
# EventType Tests
# ============================================================


class TestCircuitBreakerEventTypes:
    def test_new_event_types_exist(self):
        assert EventType.CIRCUIT_BREAKER_STATE_CHANGED.name == "CIRCUIT_BREAKER_STATE_CHANGED"
        assert EventType.CIRCUIT_BREAKER_TRIPPED.name == "CIRCUIT_BREAKER_TRIPPED"
        assert EventType.CIRCUIT_BREAKER_RECOVERED.name == "CIRCUIT_BREAKER_RECOVERED"
        assert EventType.CIRCUIT_BREAKER_HALF_OPEN.name == "CIRCUIT_BREAKER_HALF_OPEN"
        assert EventType.CIRCUIT_BREAKER_CALL_REJECTED.name == "CIRCUIT_BREAKER_CALL_REJECTED"


# ============================================================
# Config Tests
# ============================================================


class TestCircuitBreakerConfig:
    def test_config_defaults(self):
        config = ConfigurationManager()
        config.load()
        assert config.circuit_breaker_enabled is False
        assert config.circuit_breaker_failure_threshold == 5
        assert config.circuit_breaker_success_threshold == 3
        assert config.circuit_breaker_timeout_ms == 30000
        assert config.circuit_breaker_sliding_window_size == 10
        assert config.circuit_breaker_half_open_max_calls == 3
        assert config.circuit_breaker_backoff_base_ms == 1000
        assert config.circuit_breaker_backoff_max_ms == 60000
        assert config.circuit_breaker_backoff_multiplier == 2.0
        assert config.circuit_breaker_ml_confidence_threshold == 0.7
        assert config.circuit_breaker_call_timeout_ms == 5000


# ============================================================
# Integration Tests
# ============================================================


class TestCircuitBreakerIntegration:
    def test_full_lifecycle_closed_to_open_to_half_open_to_closed(self):
        """Test the complete circuit breaker lifecycle."""
        backoff = ExponentialBackoffCalculator(base_ms=10.0, multiplier=2.0, max_ms=100.0)
        cb = CircuitBreaker(
            name="LifecycleCircuit",
            failure_threshold=2,
            success_threshold=2,
            backoff_calculator=backoff,
            call_timeout_ms=50000.0,
        )

        # Phase 1: CLOSED - successful calls
        for i in range(3):
            cb.execute(lambda: "ok")
        assert cb.state == CircuitState.CLOSED
        assert cb.metrics.total_successes == 3

        # Phase 2: CLOSED -> OPEN via failures
        for i in range(2):
            with pytest.raises(RuntimeError):
                cb.execute(lambda: (_ for _ in ()).throw(RuntimeError("fail")))
        assert cb.state == CircuitState.OPEN

        # Phase 3: OPEN - calls rejected
        with pytest.raises(CircuitOpenError):
            cb.execute(lambda: "should not execute")

        # Phase 4: OPEN -> HALF_OPEN after backoff
        time.sleep(0.02)
        assert cb.state == CircuitState.HALF_OPEN

        # Phase 5: HALF_OPEN -> CLOSED via successes
        cb.execute(lambda: "probe1")
        cb.execute(lambda: "probe2")
        assert cb.state == CircuitState.CLOSED

        # Verify final metrics
        metrics = cb.metrics
        assert metrics.total_calls >= 8  # 3 ok + 2 fail + 1 rejected + 2 probe
        assert metrics.trip_count == 1

    def test_middleware_in_pipeline(self):
        """Test circuit breaker middleware in a real pipeline."""
        from middleware import MiddlewarePipeline

        cb_middleware = CircuitBreakerMiddleware(
            failure_threshold=3,
            call_timeout_ms=50000.0,
        )

        pipeline = MiddlewarePipeline()
        pipeline.add(cb_middleware)

        # Process through pipeline
        context = ProcessingContext(number=42, session_id="test")
        result = pipeline.execute(context, lambda ctx: ctx)
        assert result.number == 42

        # Verify circuit breaker recorded the call
        assert cb_middleware.circuit_breaker.metrics.total_calls == 1

    def test_exponential_backoff_progression(self):
        """Verify backoff delays increase exponentially."""
        calc = ExponentialBackoffCalculator(base_ms=100, multiplier=2.0, max_ms=10000)
        delays = [calc.calculate(i) for i in range(7)]
        assert delays == [100, 200, 400, 800, 1600, 3200, 6400]

    def test_exponential_backoff_caps_at_max(self):
        """Verify backoff never exceeds max."""
        calc = ExponentialBackoffCalculator(base_ms=100, multiplier=2.0, max_ms=500)
        delays = [calc.calculate(i) for i in range(10)]
        assert all(d <= 500 for d in delays)
        assert delays[-1] == 500
