"""
Enterprise FizzBuzz Platform - Circuit Breaker with Exponential Backoff

Implements a production-grade circuit breaker pattern to protect the
FizzBuzz evaluation pipeline from cascading failures. Because when
computing n % 3 starts failing, the last thing you want is to keep
hammering the modulo operator until the entire arithmetic subsystem
collapses.

The circuit breaker monitors failure rates across a sliding window,
trips when the threshold is exceeded, and uses exponential backoff
to gradually restore service. It also integrates with ML confidence
scores to detect "degraded FizzBuzz" — a condition where the system
is technically producing results, but without sufficient mathematical
conviction.

Design Patterns Employed:
    - Circuit Breaker (Nygard, "Release It!")
    - State Machine (GoF)
    - Sliding Window (distributed systems)
    - Exponential Backoff (network protocols)
    - Singleton Registry (enterprise tradition)
    - Middleware Pipeline (ASP.NET-inspired)
    - Observer/Event Bus (reactive architecture)

Compliance:
    - ISO 27001: Information security through failure isolation
    - SLA: 99.999% FizzBuzz availability (five nines of Fizz)
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Callable, Optional

from enterprise_fizzbuzz.domain.exceptions import (
    CircuitBreakerTimeoutError,
    CircuitOpenError,
    DownstreamFizzBuzzDegradationError,
)
from enterprise_fizzbuzz.domain.interfaces import IEventBus, IMiddleware
from enterprise_fizzbuzz.domain.models import Event, EventType, ProcessingContext

logger = logging.getLogger(__name__)


# ============================================================
# Circuit State Machine
# ============================================================


class CircuitState(Enum):
    """The three canonical states of a circuit breaker.

    CLOSED: All systems nominal. FizzBuzz requests flow freely,
            like numbers through a modulo operator.
    OPEN:   Circuit has tripped. All requests are rejected immediately
            to prevent further damage to the arithmetic pipeline.
    HALF_OPEN: Tentative recovery. A limited number of probe requests
               are allowed through to test if the downstream FizzBuzz
               service has regained its composure.
    """

    CLOSED = auto()
    OPEN = auto()
    HALF_OPEN = auto()


# ============================================================
# Sliding Window
# ============================================================


@dataclass
class SlidingWindowEntry:
    """A single entry in the circuit breaker's sliding observation window.

    Records whether a FizzBuzz evaluation succeeded or failed, along
    with timing data and optional ML confidence scores for degradation
    detection.

    Attributes:
        timestamp: When this evaluation occurred (monotonic clock).
        success: Whether the evaluation completed without error.
        duration_ms: How long the evaluation took in milliseconds.
        ml_confidence: The ML engine's confidence score, if available.
    """

    timestamp: float
    success: bool
    duration_ms: float = 0.0
    ml_confidence: Optional[float] = None


class SlidingWindow:
    """Thread-safe sliding window for tracking recent FizzBuzz outcomes.

    Maintains a fixed-size circular buffer of evaluation results,
    enabling the circuit breaker to make trip decisions based on
    recent failure rates rather than ancient history.

    The window slides forward as new entries are added, discarding
    the oldest observations — because in the fast-paced world of
    enterprise FizzBuzz, yesterday's modulo failures are no longer
    relevant.
    """

    def __init__(self, max_size: int = 10) -> None:
        self._max_size = max_size
        self._entries: list[SlidingWindowEntry] = []
        self._lock = threading.Lock()

    def record(self, entry: SlidingWindowEntry) -> None:
        """Record a new observation in the sliding window. Thread-safe."""
        with self._lock:
            self._entries.append(entry)
            if len(self._entries) > self._max_size:
                self._entries = self._entries[-self._max_size:]

    def get_failure_count(self) -> int:
        """Return the number of failures in the current window."""
        with self._lock:
            return sum(1 for e in self._entries if not e.success)

    def get_success_count(self) -> int:
        """Return the number of successes in the current window."""
        with self._lock:
            return sum(1 for e in self._entries if e.success)

    def get_failure_rate(self) -> float:
        """Return the failure rate as a fraction in [0.0, 1.0]."""
        with self._lock:
            if not self._entries:
                return 0.0
            failures = sum(1 for e in self._entries if not e.success)
            return failures / len(self._entries)

    def get_average_confidence(self) -> Optional[float]:
        """Return the average ML confidence across windowed entries."""
        with self._lock:
            scores = [e.ml_confidence for e in self._entries if e.ml_confidence is not None]
            if not scores:
                return None
            return sum(scores) / len(scores)

    def get_entry_count(self) -> int:
        """Return the total number of entries in the window."""
        with self._lock:
            return len(self._entries)

    def clear(self) -> None:
        """Clear all entries from the window."""
        with self._lock:
            self._entries.clear()

    def get_entries(self) -> list[SlidingWindowEntry]:
        """Return a copy of all current entries."""
        with self._lock:
            return list(self._entries)


# ============================================================
# Exponential Backoff
# ============================================================


class ExponentialBackoffCalculator:
    """Calculates exponential backoff delays for circuit breaker recovery.

    Implements the classic exponential backoff algorithm with configurable
    base delay, multiplier, and maximum cap. Each consecutive failure
    increases the wait time exponentially, giving the downstream FizzBuzz
    service more time to recover from whatever existential crisis caused
    it to forget how modulo arithmetic works.

    The formula: delay = min(base * (multiplier ^ attempt), max_delay)
    """

    def __init__(
        self,
        base_ms: float = 1000.0,
        multiplier: float = 2.0,
        max_ms: float = 60000.0,
    ) -> None:
        self._base_ms = base_ms
        self._multiplier = multiplier
        self._max_ms = max_ms

    def calculate(self, attempt: int) -> float:
        """Calculate the backoff delay for the given attempt number.

        Args:
            attempt: Zero-based attempt counter (0 = first failure).

        Returns:
            Delay in milliseconds, capped at max_ms.
        """
        delay = self._base_ms * (self._multiplier ** attempt)
        return min(delay, self._max_ms)

    @property
    def base_ms(self) -> float:
        return self._base_ms

    @property
    def max_ms(self) -> float:
        return self._max_ms

    @property
    def multiplier(self) -> float:
        return self._multiplier


# ============================================================
# Circuit Breaker Metrics
# ============================================================


@dataclass
class CircuitBreakerMetrics:
    """Comprehensive metrics for circuit breaker observability.

    Tracks every aspect of circuit breaker behavior for dashboarding,
    alerting, and post-incident review. Because when your FizzBuzz
    circuit trips at 3 AM, you need detailed telemetry to explain
    to the on-call engineer what went wrong.

    Attributes:
        total_calls: Total number of calls attempted through this circuit.
        total_successes: Calls that completed successfully.
        total_failures: Calls that resulted in failure.
        total_rejections: Calls rejected due to open circuit.
        total_timeouts: Calls that exceeded the timeout threshold.
        consecutive_failures: Current streak of consecutive failures.
        consecutive_successes: Current streak of consecutive successes.
        last_failure_time: Monotonic timestamp of the most recent failure.
        last_success_time: Monotonic timestamp of the most recent success.
        last_state_change_time: When the circuit last transitioned states.
        trip_count: Number of times the circuit has tripped (CLOSED -> OPEN).
        current_backoff_attempt: Current exponential backoff attempt counter.
    """

    total_calls: int = 0
    total_successes: int = 0
    total_failures: int = 0
    total_rejections: int = 0
    total_timeouts: int = 0
    consecutive_failures: int = 0
    consecutive_successes: int = 0
    last_failure_time: Optional[float] = None
    last_success_time: Optional[float] = None
    last_state_change_time: Optional[float] = None
    trip_count: int = 0
    current_backoff_attempt: int = 0


# ============================================================
# Circuit Breaker (State Machine)
# ============================================================


class CircuitBreaker:
    """Enterprise-grade circuit breaker for FizzBuzz fault tolerance.

    Implements a full state machine with three states (CLOSED, OPEN,
    HALF_OPEN) and transitions driven by failure/success thresholds.
    Integrates with ML confidence scores for proactive degradation
    detection and uses exponential backoff for recovery timing.

    State Transitions:
        CLOSED -> OPEN:      When failure_count >= failure_threshold
        OPEN -> HALF_OPEN:   When backoff timeout expires
        HALF_OPEN -> CLOSED: When success_count >= success_threshold
        HALF_OPEN -> OPEN:   When any call fails during probe phase

    Thread Safety:
        All state mutations are protected by a reentrant lock to ensure
        consistency under concurrent FizzBuzz evaluation workloads.
    """

    def __init__(
        self,
        name: str = "FizzBuzzCircuit",
        failure_threshold: int = 5,
        success_threshold: int = 3,
        timeout_ms: float = 30000.0,
        sliding_window_size: int = 10,
        half_open_max_calls: int = 3,
        backoff_calculator: Optional[ExponentialBackoffCalculator] = None,
        ml_confidence_threshold: float = 0.7,
        call_timeout_ms: float = 5000.0,
        event_bus: Optional[IEventBus] = None,
    ) -> None:
        self._name = name
        self._failure_threshold = failure_threshold
        self._success_threshold = success_threshold
        self._timeout_ms = timeout_ms
        self._half_open_max_calls = half_open_max_calls
        self._ml_confidence_threshold = ml_confidence_threshold
        self._call_timeout_ms = call_timeout_ms
        self._event_bus = event_bus

        self._state = CircuitState.CLOSED
        self._window = SlidingWindow(max_size=sliding_window_size)
        self._backoff = backoff_calculator or ExponentialBackoffCalculator()
        self._metrics = CircuitBreakerMetrics()
        self._lock = threading.Lock()

        self._half_open_calls_in_progress = 0
        self._opened_at: Optional[float] = None

        logger.info(
            "Circuit breaker '%s' initialized: failure_threshold=%d, "
            "success_threshold=%d, timeout_ms=%.0f, window_size=%d",
            name, failure_threshold, success_threshold, timeout_ms,
            sliding_window_size,
        )

    @property
    def name(self) -> str:
        return self._name

    @property
    def state(self) -> CircuitState:
        with self._lock:
            # Check if we should transition from OPEN to HALF_OPEN
            if self._state == CircuitState.OPEN and self._opened_at is not None:
                elapsed = (time.monotonic() - self._opened_at) * 1000
                backoff_delay = self._backoff.calculate(self._metrics.current_backoff_attempt)
                if elapsed >= backoff_delay:
                    self._transition_to(CircuitState.HALF_OPEN)
            return self._state

    @property
    def metrics(self) -> CircuitBreakerMetrics:
        with self._lock:
            # Return a copy to prevent external mutation
            return CircuitBreakerMetrics(
                total_calls=self._metrics.total_calls,
                total_successes=self._metrics.total_successes,
                total_failures=self._metrics.total_failures,
                total_rejections=self._metrics.total_rejections,
                total_timeouts=self._metrics.total_timeouts,
                consecutive_failures=self._metrics.consecutive_failures,
                consecutive_successes=self._metrics.consecutive_successes,
                last_failure_time=self._metrics.last_failure_time,
                last_success_time=self._metrics.last_success_time,
                last_state_change_time=self._metrics.last_state_change_time,
                trip_count=self._metrics.trip_count,
                current_backoff_attempt=self._metrics.current_backoff_attempt,
            )

    @property
    def window(self) -> SlidingWindow:
        return self._window

    def _transition_to(self, new_state: CircuitState) -> None:
        """Execute a state transition with full event publication.

        This method must be called while holding self._lock.
        """
        old_state = self._state
        if old_state == new_state:
            return

        self._state = new_state
        now = time.monotonic()
        self._metrics.last_state_change_time = now

        logger.info(
            "Circuit breaker '%s' state transition: %s -> %s",
            self._name, old_state.name, new_state.name,
        )

        if new_state == CircuitState.OPEN:
            self._opened_at = now
            self._metrics.trip_count += 1
            self._half_open_calls_in_progress = 0
            self._publish_event(EventType.CIRCUIT_BREAKER_TRIPPED, {
                "circuit_name": self._name,
                "previous_state": old_state.name,
                "trip_count": self._metrics.trip_count,
                "failure_count": self._metrics.consecutive_failures,
                "backoff_ms": self._backoff.calculate(self._metrics.current_backoff_attempt),
            })

        elif new_state == CircuitState.HALF_OPEN:
            self._half_open_calls_in_progress = 0
            self._publish_event(EventType.CIRCUIT_BREAKER_HALF_OPEN, {
                "circuit_name": self._name,
                "previous_state": old_state.name,
                "backoff_attempt": self._metrics.current_backoff_attempt,
            })

        elif new_state == CircuitState.CLOSED:
            self._metrics.current_backoff_attempt = 0
            self._metrics.consecutive_failures = 0
            self._opened_at = None
            self._window.clear()
            self._publish_event(EventType.CIRCUIT_BREAKER_RECOVERED, {
                "circuit_name": self._name,
                "previous_state": old_state.name,
                "total_trips": self._metrics.trip_count,
            })

        self._publish_event(EventType.CIRCUIT_BREAKER_STATE_CHANGED, {
            "circuit_name": self._name,
            "old_state": old_state.name,
            "new_state": new_state.name,
        })

    def _publish_event(self, event_type: EventType, payload: dict[str, Any]) -> None:
        """Publish an event to the event bus, if available."""
        if self._event_bus is not None:
            self._event_bus.publish(Event(
                event_type=event_type,
                payload=payload,
                source=f"CircuitBreaker:{self._name}",
            ))

    def execute(
        self,
        operation: Callable[[], Any],
    ) -> Any:
        """Execute an operation through the circuit breaker.

        If the circuit is CLOSED, the operation proceeds normally.
        If OPEN, the call is rejected immediately with CircuitOpenError.
        If HALF_OPEN, a limited number of probe calls are allowed.

        Args:
            operation: The callable to execute (typically a FizzBuzz evaluation).

        Returns:
            The result of the operation if successful.

        Raises:
            CircuitOpenError: If the circuit is open and rejecting calls.
        """
        current_state = self.state  # triggers OPEN->HALF_OPEN check

        with self._lock:
            self._metrics.total_calls += 1

            if current_state == CircuitState.OPEN:
                self._metrics.total_rejections += 1
                backoff_delay = self._backoff.calculate(self._metrics.current_backoff_attempt)
                elapsed = 0.0
                if self._opened_at is not None:
                    elapsed = (time.monotonic() - self._opened_at) * 1000
                retry_after = max(0.0, backoff_delay - elapsed)

                self._publish_event(EventType.CIRCUIT_BREAKER_CALL_REJECTED, {
                    "circuit_name": self._name,
                    "retry_after_ms": retry_after,
                    "total_rejections": self._metrics.total_rejections,
                })

                raise CircuitOpenError(self._name, retry_after)

            if current_state == CircuitState.HALF_OPEN:
                if self._half_open_calls_in_progress >= self._half_open_max_calls:
                    self._metrics.total_rejections += 1
                    raise CircuitOpenError(self._name, 0.0)
                self._half_open_calls_in_progress += 1

        # Execute the operation outside the lock
        start_time = time.monotonic()
        try:
            result = operation()
            elapsed_ms = (time.monotonic() - start_time) * 1000

            # Check for timeout (even if the call succeeded)
            if elapsed_ms > self._call_timeout_ms:
                self._record_failure(elapsed_ms)
                raise CircuitBreakerTimeoutError(
                    self._name, self._call_timeout_ms, elapsed_ms
                )

            # Check ML confidence degradation
            ml_confidence = self._extract_ml_confidence(result)
            if ml_confidence is not None and ml_confidence < self._ml_confidence_threshold:
                logger.warning(
                    "Circuit '%s': ML confidence %.4f below threshold %.4f",
                    self._name, ml_confidence, self._ml_confidence_threshold,
                )

            self._record_success(elapsed_ms, ml_confidence)
            return result

        except (CircuitOpenError, CircuitBreakerTimeoutError):
            raise
        except Exception:
            elapsed_ms = (time.monotonic() - start_time) * 1000
            self._record_failure(elapsed_ms)
            raise

    def _extract_ml_confidence(self, result: Any) -> Optional[float]:
        """Extract ML confidence from a ProcessingContext or result."""
        if isinstance(result, ProcessingContext) and result.results:
            latest = result.results[-1]
            confidences = latest.metadata.get("ml_confidences", {})
            if confidences:
                return min(confidences.values())
        return None

    def _record_success(self, duration_ms: float, ml_confidence: Optional[float] = None) -> None:
        """Record a successful call and evaluate state transitions."""
        entry = SlidingWindowEntry(
            timestamp=time.monotonic(),
            success=True,
            duration_ms=duration_ms,
            ml_confidence=ml_confidence,
        )
        self._window.record(entry)

        with self._lock:
            self._metrics.total_successes += 1
            self._metrics.consecutive_successes += 1
            self._metrics.consecutive_failures = 0
            self._metrics.last_success_time = time.monotonic()

            if self._state == CircuitState.HALF_OPEN:
                if self._metrics.consecutive_successes >= self._success_threshold:
                    self._transition_to(CircuitState.CLOSED)

    def _record_failure(self, duration_ms: float) -> None:
        """Record a failed call and evaluate state transitions."""
        entry = SlidingWindowEntry(
            timestamp=time.monotonic(),
            success=False,
            duration_ms=duration_ms,
        )
        self._window.record(entry)

        with self._lock:
            self._metrics.total_failures += 1
            self._metrics.consecutive_failures += 1
            self._metrics.consecutive_successes = 0
            self._metrics.last_failure_time = time.monotonic()

            if self._state == CircuitState.HALF_OPEN:
                # Any failure in half-open immediately re-opens
                self._metrics.current_backoff_attempt += 1
                self._transition_to(CircuitState.OPEN)
            elif self._state == CircuitState.CLOSED:
                if self._metrics.consecutive_failures >= self._failure_threshold:
                    self._transition_to(CircuitState.OPEN)

    def reset(self) -> None:
        """Manually reset the circuit breaker to CLOSED state."""
        with self._lock:
            self._transition_to(CircuitState.CLOSED)
            self._metrics = CircuitBreakerMetrics()
            self._window.clear()
            self._opened_at = None
            logger.info("Circuit breaker '%s' manually reset", self._name)

    def get_status_report(self) -> dict[str, Any]:
        """Generate a comprehensive status report for monitoring."""
        with self._lock:
            return {
                "name": self._name,
                "state": self._state.name,
                "metrics": {
                    "total_calls": self._metrics.total_calls,
                    "total_successes": self._metrics.total_successes,
                    "total_failures": self._metrics.total_failures,
                    "total_rejections": self._metrics.total_rejections,
                    "total_timeouts": self._metrics.total_timeouts,
                    "consecutive_failures": self._metrics.consecutive_failures,
                    "consecutive_successes": self._metrics.consecutive_successes,
                    "trip_count": self._metrics.trip_count,
                    "current_backoff_attempt": self._metrics.current_backoff_attempt,
                },
                "window": {
                    "failure_rate": self._window.get_failure_rate(),
                    "entry_count": self._window.get_entry_count(),
                    "avg_confidence": self._window.get_average_confidence(),
                },
                "config": {
                    "failure_threshold": self._failure_threshold,
                    "success_threshold": self._success_threshold,
                    "timeout_ms": self._timeout_ms,
                    "call_timeout_ms": self._call_timeout_ms,
                    "ml_confidence_threshold": self._ml_confidence_threshold,
                },
            }


# ============================================================
# Circuit Breaker Registry (Singleton)
# ============================================================


class CircuitBreakerRegistry:
    """Singleton registry for managing named circuit breaker instances.

    In a microservices architecture, each downstream dependency would
    have its own circuit breaker. In the Enterprise FizzBuzz Platform,
    we have one dependency — arithmetic — but the registry pattern
    is implemented anyway because enterprise software demands it.

    Usage:
        registry = CircuitBreakerRegistry.get_instance()
        cb = registry.get_or_create("FizzBuzzCircuit", failure_threshold=5)
    """

    _instance: Optional[CircuitBreakerRegistry] = None
    _instance_lock = threading.Lock()

    def __init__(self) -> None:
        self._breakers: dict[str, CircuitBreaker] = {}
        self._lock = threading.Lock()

    @classmethod
    def get_instance(cls) -> CircuitBreakerRegistry:
        """Return the singleton registry instance."""
        with cls._instance_lock:
            if cls._instance is None:
                cls._instance = CircuitBreakerRegistry()
            return cls._instance

    @classmethod
    def reset(cls) -> None:
        """Reset the singleton instance. Used for testing."""
        with cls._instance_lock:
            cls._instance = None

    def get_or_create(
        self,
        name: str,
        **kwargs: Any,
    ) -> CircuitBreaker:
        """Get an existing circuit breaker or create a new one."""
        with self._lock:
            if name not in self._breakers:
                self._breakers[name] = CircuitBreaker(name=name, **kwargs)
                logger.info(
                    "Circuit breaker '%s' registered in global registry", name
                )
            return self._breakers[name]

    def get(self, name: str) -> Optional[CircuitBreaker]:
        """Retrieve a circuit breaker by name, or None if not found."""
        with self._lock:
            return self._breakers.get(name)

    def list_all(self) -> list[str]:
        """Return a list of all registered circuit breaker names."""
        with self._lock:
            return list(self._breakers.keys())

    def remove(self, name: str) -> bool:
        """Remove a circuit breaker from the registry."""
        with self._lock:
            if name in self._breakers:
                del self._breakers[name]
                return True
            return False

    def get_all_status_reports(self) -> list[dict[str, Any]]:
        """Get status reports from all registered circuit breakers."""
        with self._lock:
            return [cb.get_status_report() for cb in self._breakers.values()]


# ============================================================
# Circuit Breaker Middleware
# ============================================================


class CircuitBreakerMiddleware(IMiddleware):
    """Middleware that wraps FizzBuzz evaluation in a circuit breaker.

    Intercepts all FizzBuzz evaluation requests passing through the
    middleware pipeline and routes them through the circuit breaker
    state machine. Failed evaluations are tracked, and when the
    failure threshold is breached, subsequent requests are rejected
    immediately — saving precious CPU cycles that would otherwise
    be wasted on doomed modulo operations.

    Integration Points:
        - ML confidence scores: Monitors prediction confidence for
          proactive degradation detection
        - Event Bus: Publishes circuit state change events for
          observability and alerting
        - Exponential Backoff: Manages recovery timing with
          progressively longer wait periods
    """

    def __init__(
        self,
        circuit_breaker: Optional[CircuitBreaker] = None,
        event_bus: Optional[IEventBus] = None,
        failure_threshold: int = 5,
        success_threshold: int = 3,
        timeout_ms: float = 30000.0,
        sliding_window_size: int = 10,
        half_open_max_calls: int = 3,
        backoff_base_ms: float = 1000.0,
        backoff_max_ms: float = 60000.0,
        backoff_multiplier: float = 2.0,
        ml_confidence_threshold: float = 0.7,
        call_timeout_ms: float = 5000.0,
    ) -> None:
        if circuit_breaker is not None:
            self._circuit_breaker = circuit_breaker
        else:
            backoff = ExponentialBackoffCalculator(
                base_ms=backoff_base_ms,
                multiplier=backoff_multiplier,
                max_ms=backoff_max_ms,
            )
            self._circuit_breaker = CircuitBreaker(
                name="FizzBuzzPipelineCircuit",
                failure_threshold=failure_threshold,
                success_threshold=success_threshold,
                timeout_ms=timeout_ms,
                sliding_window_size=sliding_window_size,
                half_open_max_calls=half_open_max_calls,
                backoff_calculator=backoff,
                ml_confidence_threshold=ml_confidence_threshold,
                call_timeout_ms=call_timeout_ms,
                event_bus=event_bus,
            )

    @property
    def circuit_breaker(self) -> CircuitBreaker:
        """Access the underlying circuit breaker instance."""
        return self._circuit_breaker

    def process(
        self,
        context: ProcessingContext,
        next_handler: Callable[[ProcessingContext], ProcessingContext],
    ) -> ProcessingContext:
        """Process the context through the circuit breaker.

        Wraps the downstream handler invocation in a circuit breaker
        call, tracking successes and failures to manage circuit state.
        """
        def guarded_call() -> ProcessingContext:
            return next_handler(context)

        try:
            return self._circuit_breaker.execute(guarded_call)
        except CircuitOpenError:
            # When circuit is open, we still need to return a context
            # Mark it as degraded in metadata
            context.metadata["circuit_breaker_rejected"] = True
            context.metadata["circuit_breaker_state"] = self._circuit_breaker.state.name
            logger.warning(
                "Circuit breaker rejected processing for number %d",
                context.number,
            )
            raise

    def get_name(self) -> str:
        return "CircuitBreakerMiddleware"

    def get_priority(self) -> int:
        # Execute before validation but after nothing — highest priority
        # so circuit checks happen first in the pipeline
        return -1


# ============================================================
# Circuit Breaker Dashboard
# ============================================================


class CircuitBreakerDashboard:
    """ASCII-art dashboard for circuit breaker status visualization.

    Renders a beautiful, enterprise-grade terminal dashboard showing
    the current state of all circuit breakers, complete with metrics,
    sliding window visualizations, and exponential backoff status.

    Because what good is a circuit breaker if you can't display its
    state in monospace font?
    """

    @staticmethod
    def render(circuit_breaker: CircuitBreaker) -> str:
        """Render a single circuit breaker's status as an ASCII dashboard."""
        report = circuit_breaker.get_status_report()
        metrics = report["metrics"]
        window = report["window"]
        config = report["config"]

        state = report["state"]
        state_indicator = {
            "CLOSED": "[  CLOSED  ]  All systems nominal",
            "OPEN": "[   OPEN   ]  REJECTING REQUESTS",
            "HALF_OPEN": "[HALF_OPEN ]  Probe phase active",
        }.get(state, "[  UNKNOWN ]")

        # Build the sliding window visualization
        entries = circuit_breaker.window.get_entries()
        window_viz_chars = []
        for entry in entries:
            window_viz_chars.append("+" if entry.success else "X")
        window_viz = " ".join(window_viz_chars) if window_viz_chars else "(empty)"

        avg_conf = window["avg_confidence"]
        avg_conf_str = f"{avg_conf:.4f}" if avg_conf is not None else "N/A"

        lines = [
            "",
            "  +===========================================================+",
            "  |           CIRCUIT BREAKER STATUS DASHBOARD                |",
            "  +===========================================================+",
            f"  |  Circuit Name   : {report['name']:<39}|",
            f"  |  State          : {state_indicator:<39}|",
            "  |-----------------------------------------------------------|",
            f"  |  Total Calls    : {metrics['total_calls']:<39}|",
            f"  |  Successes      : {metrics['total_successes']:<39}|",
            f"  |  Failures       : {metrics['total_failures']:<39}|",
            f"  |  Rejections     : {metrics['total_rejections']:<39}|",
            f"  |  Trip Count     : {metrics['trip_count']:<39}|",
            "  |-----------------------------------------------------------|",
            f"  |  Failure Rate   : {window['failure_rate']:<35.2%}    |",
            f"  |  Avg ML Conf    : {avg_conf_str:<39}|",
            f"  |  Backoff Attempt: {metrics['current_backoff_attempt']:<39}|",
            "  |-----------------------------------------------------------|",
            f"  |  Sliding Window : [{window_viz:<37}]|",
            "  |-----------------------------------------------------------|",
            f"  |  Fail Threshold : {config['failure_threshold']:<39}|",
            f"  |  Recovery Thresh: {config['success_threshold']:<39}|",
            f"  |  Call Timeout   : {config['call_timeout_ms']:<35.0f} ms |",
            "  +===========================================================+",
            "",
        ]
        return "\n".join(lines)

    @staticmethod
    def render_all(registry: CircuitBreakerRegistry) -> str:
        """Render status for all circuit breakers in the registry."""
        names = registry.list_all()
        if not names:
            return (
                "\n  +===========================================================+\n"
                "  |           CIRCUIT BREAKER STATUS DASHBOARD                |\n"
                "  +===========================================================+\n"
                "  |  No circuit breakers registered.                          |\n"
                "  +===========================================================+\n"
            )

        parts = []
        for name in names:
            cb = registry.get(name)
            if cb is not None:
                parts.append(CircuitBreakerDashboard.render(cb))
        return "\n".join(parts)
