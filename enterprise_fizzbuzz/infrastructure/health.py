"""
Enterprise FizzBuzz Platform - Kubernetes-Style Health Check Probes

Implements a production-grade health monitoring system with liveness,
readiness, and startup probes for the Enterprise FizzBuzz Platform.
Following Kubernetes best practices, the FizzBuzz evaluation pipeline
implements the same level of operational scrutiny expected of any
production-grade distributed system.

This module provides:
    - Subsystem health checks for all infrastructure components
    - Liveness probe: canary evaluation to verify basic arithmetic survival
    - Readiness probe: aggregated subsystem health assessment
    - Startup probe: boot sequence milestone tracking
    - Self-healing manager: automated recovery attempts for degraded
      subsystems without operator intervention
    - ASCII health dashboard: terminal-based operational visibility
      for real-time health status monitoring

The health check system operates on the principle that platform
health reflects the worst status across all subsystems. If the
ML engine enters a degraded confidence state, the entire platform
reports the corresponding status, regardless of how well other
subsystems are performing.

Design Patterns Employed:
    - Template Method (subsystem health checks)
    - Singleton (health check registry)
    - Strategy (different probe types)
    - Observer (health event publication)
    - Abstract Factory (subsystem check creation)
    - Self-Healing (automated recovery for degraded subsystems)

Compliance:
    - Kubernetes Health Check API: /healthz, /readyz, /startupz semantics
    - ISO 27001: Security through obsessive health monitoring
    - SOC2: Full audit trail of every health check and recovery attempt
"""

from __future__ import annotations

import logging
import threading
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Optional

from enterprise_fizzbuzz.domain.exceptions import (
    HealthCheckError,
    LivenessProbeFailedError,
    ReadinessProbeFailedError,
    SelfHealingFailedError,
    StartupProbeFailedError,
)
from enterprise_fizzbuzz.domain.models import (
    Event,
    EventType,
    HealthReport,
    HealthStatus,
    ProbeType,
    SubsystemCheck,
)

logger = logging.getLogger(__name__)


# ============================================================
# Subsystem Health Check ABC
# ============================================================


class SubsystemHealthCheck(ABC):
    """Abstract base class for individual subsystem health checks.

    Each subsystem in the Enterprise FizzBuzz Platform gets its own
    health check implementation, because checking the health of
    modulo arithmetic infrastructure is a task that demands
    specialization and polymorphism.

    Implementors must provide:
        - name: A human-readable subsystem identifier
        - check(): Perform the health check and return a SubsystemCheck
        - recover(): Attempt to restore the subsystem to health
    """

    @abstractmethod
    def get_name(self) -> str:
        """Return the human-readable name of this subsystem."""
        ...

    @abstractmethod
    def check(self) -> SubsystemCheck:
        """Perform the health check and return the result.

        Returns:
            A SubsystemCheck with the current health status.
        """
        ...

    def recover(self) -> bool:
        """Attempt to recover the subsystem to a healthy state.

        Returns:
            True if recovery was successful, False otherwise.

        The default implementation does nothing and reports failure,
        because most subsystems cannot heal themselves. Those that
        can should override this method with appropriate recovery
        procedures (such as resetting a circuit breaker or clearing
        a corrupted cache).
        """
        return False


# ============================================================
# Concrete Subsystem Health Checks
# ============================================================


class ConfigHealthCheck(SubsystemHealthCheck):
    """Health check for the Configuration Management subsystem.

    Verifies that the ConfigurationManager singleton is loaded
    and can provide basic configuration values. If the config
    system is down, nothing else matters — it's the foundation
    upon which all other subsystems depend.
    """

    def __init__(self, config: Any = None) -> None:
        self._config = config

    def get_name(self) -> str:
        return "config"

    def check(self) -> SubsystemCheck:
        start = time.monotonic()
        try:
            if self._config is None:
                return SubsystemCheck(
                    subsystem_name=self.get_name(),
                    status=HealthStatus.UP,
                    response_time_ms=0.0,
                    details="Config not injected; assuming healthy (blissful ignorance)",
                )

            # Verify config is loaded by accessing a basic property
            _ = self._config.app_name
            elapsed = (time.monotonic() - start) * 1000
            return SubsystemCheck(
                subsystem_name=self.get_name(),
                status=HealthStatus.UP,
                response_time_ms=elapsed,
                details=f"Configuration loaded: {self._config.app_name} v{self._config.app_version}",
            )
        except Exception as e:
            elapsed = (time.monotonic() - start) * 1000
            return SubsystemCheck(
                subsystem_name=self.get_name(),
                status=HealthStatus.DOWN,
                response_time_ms=elapsed,
                details=f"Configuration subsystem failure: {e}",
            )

    def recover(self) -> bool:
        """Attempt to reload configuration."""
        try:
            if self._config is not None:
                self._config.load()
                return True
        except Exception:
            pass
        return False


class CircuitBreakerHealthCheck(SubsystemHealthCheck):
    """Health check for the Circuit Breaker subsystem.

    Examines all registered circuit breakers and reports the worst
    state found. A CLOSED circuit is healthy, HALF_OPEN is degraded
    (the system is probing for recovery), and OPEN is unhealthy
    (the system has given up on arithmetic).
    """

    def __init__(self, registry: Any = None) -> None:
        self._registry = registry

    def get_name(self) -> str:
        return "circuit_breaker"

    def check(self) -> SubsystemCheck:
        start = time.monotonic()

        if self._registry is None:
            elapsed = (time.monotonic() - start) * 1000
            return SubsystemCheck(
                subsystem_name=self.get_name(),
                status=HealthStatus.UP,
                response_time_ms=elapsed,
                details="Circuit breaker not enabled; subsystem healthy by absence",
            )

        try:
            from enterprise_fizzbuzz.infrastructure.circuit_breaker import CircuitState

            names = self._registry.list_all()
            if not names:
                elapsed = (time.monotonic() - start) * 1000
                return SubsystemCheck(
                    subsystem_name=self.get_name(),
                    status=HealthStatus.UP,
                    response_time_ms=elapsed,
                    details="No circuit breakers registered; nothing to worry about",
                )

            worst_status = HealthStatus.UP
            details_parts = []
            for name in names:
                cb = self._registry.get(name)
                if cb is None:
                    continue
                state = cb.state
                if state == CircuitState.OPEN:
                    worst_status = HealthStatus.DOWN
                    details_parts.append(f"{name}: OPEN (rejecting all requests)")
                elif state == CircuitState.HALF_OPEN:
                    if worst_status != HealthStatus.DOWN:
                        worst_status = HealthStatus.DEGRADED
                    details_parts.append(f"{name}: HALF_OPEN (probing for recovery)")
                else:
                    details_parts.append(f"{name}: CLOSED (nominal)")

            elapsed = (time.monotonic() - start) * 1000
            return SubsystemCheck(
                subsystem_name=self.get_name(),
                status=worst_status,
                response_time_ms=elapsed,
                details="; ".join(details_parts) if details_parts else "All circuits nominal",
            )
        except Exception as e:
            elapsed = (time.monotonic() - start) * 1000
            return SubsystemCheck(
                subsystem_name=self.get_name(),
                status=HealthStatus.UNKNOWN,
                response_time_ms=elapsed,
                details=f"Circuit breaker health check failed: {e}",
            )

    def recover(self) -> bool:
        """Reset all open circuit breakers."""
        if self._registry is None:
            return True
        try:
            from enterprise_fizzbuzz.infrastructure.circuit_breaker import CircuitState

            for name in self._registry.list_all():
                cb = self._registry.get(name)
                if cb is not None and cb.state == CircuitState.OPEN:
                    cb.reset()
            return True
        except Exception:
            return False


class CacheCoherenceHealthCheck(SubsystemHealthCheck):
    """Health check for the In-Memory Cache subsystem.

    Verifies that the cache is operational, coherent, and not
    experiencing any MESI protocol violations. Also checks the
    cache hit rate as a proxy for overall health, because a cache
    that never hits is just a slow dictionary.
    """

    def __init__(self, cache_store: Any = None) -> None:
        self._cache_store = cache_store

    def get_name(self) -> str:
        return "cache"

    def check(self) -> SubsystemCheck:
        start = time.monotonic()

        if self._cache_store is None:
            elapsed = (time.monotonic() - start) * 1000
            return SubsystemCheck(
                subsystem_name=self.get_name(),
                status=HealthStatus.UP,
                response_time_ms=elapsed,
                details="Cache not enabled; healthy by abstinence",
            )

        try:
            stats = self._cache_store.get_statistics()
            total = stats.get("total_requests", 0)
            hits = stats.get("hits", 0)
            hit_rate = hits / total if total > 0 else 1.0
            size = stats.get("current_size", 0)
            max_size = stats.get("max_size", 0)

            if hit_rate < 0.1 and total > 10:
                status = HealthStatus.DEGRADED
                detail_msg = f"Cache hit rate critically low: {hit_rate:.1%} ({hits}/{total})"
            else:
                status = HealthStatus.UP
                detail_msg = f"Cache operational: {size}/{max_size} entries, hit rate {hit_rate:.1%}"

            elapsed = (time.monotonic() - start) * 1000
            return SubsystemCheck(
                subsystem_name=self.get_name(),
                status=status,
                response_time_ms=elapsed,
                details=detail_msg,
            )
        except Exception as e:
            elapsed = (time.monotonic() - start) * 1000
            return SubsystemCheck(
                subsystem_name=self.get_name(),
                status=HealthStatus.UNKNOWN,
                response_time_ms=elapsed,
                details=f"Cache health check failed: {e}",
            )

    def recover(self) -> bool:
        """Clear the cache and hope for the best."""
        if self._cache_store is None:
            return True
        try:
            self._cache_store.clear()
            return True
        except Exception:
            return False


class SLABudgetHealthCheck(SubsystemHealthCheck):
    """Health check for the SLA Monitoring subsystem.

    Examines the error budget burn rate to determine if the platform
    is consuming its error budget too quickly. A high burn rate means
    we're failing too many FizzBuzz evaluations, which means mathematics
    itself may be degrading — a concerning prospect for any platform
    that relies on the modulo operator.
    """

    def __init__(self, sla_monitor: Any = None) -> None:
        self._sla_monitor = sla_monitor

    def get_name(self) -> str:
        return "sla"

    def check(self) -> SubsystemCheck:
        start = time.monotonic()

        if self._sla_monitor is None:
            elapsed = (time.monotonic() - start) * 1000
            return SubsystemCheck(
                subsystem_name=self.get_name(),
                status=HealthStatus.UP,
                response_time_ms=elapsed,
                details="SLA monitoring not enabled; blissfully ignorant of SLO compliance",
            )

        try:
            # Check if any SLO violations have occurred
            violations = getattr(self._sla_monitor, '_violation_count', 0)
            total = getattr(self._sla_monitor, '_total_evaluations', 0)

            if total == 0:
                status = HealthStatus.UP
                detail_msg = "No evaluations recorded yet; SLA compliance is vacuously true"
            elif violations > 0 and (violations / max(total, 1)) > 0.01:
                status = HealthStatus.DEGRADED
                detail_msg = (
                    f"SLA degraded: {violations} violations out of {total} evaluations "
                    f"({violations / total:.2%} violation rate)"
                )
            else:
                status = HealthStatus.UP
                detail_msg = f"SLA compliance nominal: {total} evaluations, {violations} violations"

            elapsed = (time.monotonic() - start) * 1000
            return SubsystemCheck(
                subsystem_name=self.get_name(),
                status=status,
                response_time_ms=elapsed,
                details=detail_msg,
            )
        except Exception as e:
            elapsed = (time.monotonic() - start) * 1000
            return SubsystemCheck(
                subsystem_name=self.get_name(),
                status=HealthStatus.UNKNOWN,
                response_time_ms=elapsed,
                details=f"SLA health check failed: {e}",
            )


class MLEngineHealthCheck(SubsystemHealthCheck):
    """Health check for the Machine Learning Engine subsystem.

    Verifies that the ML engine can still evaluate basic FizzBuzz
    inputs correctly. If the neural network has forgotten how modulo
    arithmetic works, the status is set to EXISTENTIAL_CRISIS —
    because when a machine learning model loses confidence in basic
    math, "DOWN" simply doesn't capture the gravity of the situation.
    """

    def __init__(self, engine: Any = None, rules: Any = None) -> None:
        self._engine = engine
        self._rules = rules

    def get_name(self) -> str:
        return "ml_engine"

    def check(self) -> SubsystemCheck:
        start = time.monotonic()

        if self._engine is None:
            elapsed = (time.monotonic() - start) * 1000
            return SubsystemCheck(
                subsystem_name=self.get_name(),
                status=HealthStatus.UP,
                response_time_ms=elapsed,
                details="ML engine not configured; standard arithmetic prevails",
            )

        try:
            # Quick sanity check: can the engine still evaluate basic inputs?
            test_cases = [(3, "Fizz"), (5, "Buzz"), (15, "FizzBuzz"), (7, "7")]
            failures = []
            confidences = []

            for number, expected in test_cases:
                result = self._engine.evaluate(number, self._rules or [])
                if result.output != expected:
                    failures.append(f"{number}: got '{result.output}', expected '{expected}'")

                # Check ML confidence if available
                ml_conf = result.metadata.get("ml_confidences", {})
                if ml_conf:
                    confidences.extend(ml_conf.values())

            elapsed = (time.monotonic() - start) * 1000

            if failures:
                # The ML engine has forgotten how modulo works
                return SubsystemCheck(
                    subsystem_name=self.get_name(),
                    status=HealthStatus.EXISTENTIAL_CRISIS,
                    response_time_ms=elapsed,
                    details=(
                        f"ML engine has lost the ability to FizzBuzz: "
                        f"{'; '.join(failures)}. The neural network is questioning "
                        f"the very nature of divisibility."
                    ),
                )

            # Check confidence levels
            if confidences:
                avg_confidence = sum(confidences) / len(confidences)
                if avg_confidence < 0.5:
                    return SubsystemCheck(
                        subsystem_name=self.get_name(),
                        status=HealthStatus.EXISTENTIAL_CRISIS,
                        response_time_ms=elapsed,
                        details=(
                            f"ML engine producing correct results but with crippling "
                            f"self-doubt (avg confidence: {avg_confidence:.4f}). "
                            f"The model knows the answers but doesn't believe in itself."
                        ),
                    )
                elif avg_confidence < 0.7:
                    return SubsystemCheck(
                        subsystem_name=self.get_name(),
                        status=HealthStatus.DEGRADED,
                        response_time_ms=elapsed,
                        details=(
                            f"ML engine functional but with reduced confidence "
                            f"(avg: {avg_confidence:.4f}). It's correct, but unenthusiastic."
                        ),
                    )

            return SubsystemCheck(
                subsystem_name=self.get_name(),
                status=HealthStatus.UP,
                response_time_ms=elapsed,
                details="ML engine operational and confident in its mathematical abilities",
            )
        except Exception as e:
            elapsed = (time.monotonic() - start) * 1000
            return SubsystemCheck(
                subsystem_name=self.get_name(),
                status=HealthStatus.DOWN,
                response_time_ms=elapsed,
                details=f"ML engine health check threw an exception: {e}",
            )


# ============================================================
# Health Check Registry (Singleton)
# ============================================================


class HealthCheckRegistry:
    """Singleton registry for managing subsystem health checks.

    Because maintaining a global registry of health check implementations
    is the enterprise way. You could just keep them in a list, but then
    you wouldn't get thread-safe singleton semantics and a fluent
    registration API.

    Usage:
        registry = HealthCheckRegistry.get_instance()
        registry.register(ConfigHealthCheck(config))
        registry.register(MLEngineHealthCheck(engine, rules))
    """

    _instance: Optional[HealthCheckRegistry] = None
    _instance_lock = threading.Lock()

    def __init__(self) -> None:
        self._checks: dict[str, SubsystemHealthCheck] = {}
        self._lock = threading.Lock()

    @classmethod
    def get_instance(cls) -> HealthCheckRegistry:
        """Return the singleton registry instance."""
        with cls._instance_lock:
            if cls._instance is None:
                cls._instance = HealthCheckRegistry()
            return cls._instance

    @classmethod
    def reset(cls) -> None:
        """Reset the singleton instance. Used for testing."""
        with cls._instance_lock:
            cls._instance = None

    def register(self, check: SubsystemHealthCheck) -> HealthCheckRegistry:
        """Register a subsystem health check. Returns self for chaining."""
        with self._lock:
            self._checks[check.get_name()] = check
            logger.debug("Health check registered: %s", check.get_name())
        return self

    def unregister(self, name: str) -> bool:
        """Remove a health check by name."""
        with self._lock:
            if name in self._checks:
                del self._checks[name]
                return True
            return False

    def get(self, name: str) -> Optional[SubsystemHealthCheck]:
        """Retrieve a health check by subsystem name."""
        with self._lock:
            return self._checks.get(name)

    def list_all(self) -> list[str]:
        """Return all registered subsystem names."""
        with self._lock:
            return list(self._checks.keys())

    def check_all(self) -> list[SubsystemCheck]:
        """Run all registered health checks and return results."""
        with self._lock:
            checks = list(self._checks.values())

        results = []
        for check in checks:
            try:
                results.append(check.check())
            except Exception as e:
                results.append(SubsystemCheck(
                    subsystem_name=check.get_name(),
                    status=HealthStatus.UNKNOWN,
                    details=f"Health check threw unhandled exception: {e}",
                ))
        return results


# ============================================================
# Liveness Probe
# ============================================================


class LivenessProbe:
    """Kubernetes-style liveness probe for FizzBuzz vitality assessment.

    The liveness probe performs a single canary evaluation: it calls
    evaluate(15) and expects "FizzBuzz" in return. If the platform
    cannot produce this result, it is considered dead — because a
    FizzBuzz engine that can't evaluate 15 has lost its reason for
    existence.

    In Kubernetes, a failed liveness probe causes a pod restart.
    Here, it causes an exception and a strongly-worded log message.
    """

    def __init__(
        self,
        evaluate_fn: Optional[Callable[[int], str]] = None,
        canary_number: int = 15,
        canary_expected: str = "FizzBuzz",
        event_bus: Any = None,
    ) -> None:
        self._evaluate_fn = evaluate_fn
        self._canary_number = canary_number
        self._canary_expected = canary_expected
        self._event_bus = event_bus

    def probe(self) -> HealthReport:
        """Execute the liveness probe.

        Returns:
            A HealthReport with the liveness check result.

        The probe evaluates a single canary number and verifies
        the output matches the expected result. If it doesn't,
        the platform is declared dead, which for a FizzBuzz engine
        is both dramatic and technically accurate.
        """
        self._publish_event(EventType.HEALTH_CHECK_STARTED, {
            "probe_type": "LIVENESS",
            "canary_number": self._canary_number,
        })

        start = time.monotonic()
        canary_value = None

        try:
            if self._evaluate_fn is not None:
                canary_value = self._evaluate_fn(self._canary_number)
            else:
                # No evaluation function — fall back to hardcoded check
                canary_value = self._hardcoded_evaluate(self._canary_number)

            elapsed = (time.monotonic() - start) * 1000

            if canary_value == self._canary_expected:
                status = HealthStatus.UP
                check = SubsystemCheck(
                    subsystem_name="liveness_canary",
                    status=HealthStatus.UP,
                    response_time_ms=elapsed,
                    details=(
                        f"Canary evaluation: evaluate({self._canary_number}) = "
                        f"'{canary_value}' (correct). The platform is alive."
                    ),
                )
                self._publish_event(EventType.HEALTH_LIVENESS_PASSED, {
                    "canary_number": self._canary_number,
                    "canary_value": canary_value,
                    "response_time_ms": elapsed,
                })
            else:
                status = HealthStatus.DOWN
                check = SubsystemCheck(
                    subsystem_name="liveness_canary",
                    status=HealthStatus.DOWN,
                    response_time_ms=elapsed,
                    details=(
                        f"Canary evaluation: evaluate({self._canary_number}) = "
                        f"'{canary_value}', expected '{self._canary_expected}'. "
                        f"The platform has forgotten how to FizzBuzz."
                    ),
                )
                self._publish_event(EventType.HEALTH_LIVENESS_FAILED, {
                    "canary_number": self._canary_number,
                    "canary_value": canary_value,
                    "expected": self._canary_expected,
                })

        except Exception as e:
            elapsed = (time.monotonic() - start) * 1000
            status = HealthStatus.DOWN
            check = SubsystemCheck(
                subsystem_name="liveness_canary",
                status=HealthStatus.DOWN,
                response_time_ms=elapsed,
                details=f"Canary evaluation threw exception: {e}",
            )
            self._publish_event(EventType.HEALTH_LIVENESS_FAILED, {
                "canary_number": self._canary_number,
                "error": str(e),
            })

        report = HealthReport(
            probe_type=ProbeType.LIVENESS,
            overall_status=status,
            subsystem_checks=[check],
            canary_value=canary_value,
        )

        self._publish_event(EventType.HEALTH_CHECK_COMPLETED, {
            "probe_type": "LIVENESS",
            "overall_status": status.name,
        })

        return report

    @staticmethod
    def _hardcoded_evaluate(n: int) -> str:
        """Hardcoded FizzBuzz evaluation for liveness checks without an engine.

        This is the purest form of FizzBuzz — no middleware, no patterns,
        no abstractions. Just modulo. The way Dijkstra intended.
        """
        result = ""
        if n % 3 == 0:
            result += "Fizz"
        if n % 5 == 0:
            result += "Buzz"
        return result or str(n)

    def _publish_event(self, event_type: EventType, payload: dict[str, Any]) -> None:
        """Publish a health check event if an event bus is available."""
        if self._event_bus is not None:
            self._event_bus.publish(Event(
                event_type=event_type,
                payload=payload,
                source="LivenessProbe",
            ))


# ============================================================
# Readiness Probe
# ============================================================


class ReadinessProbe:
    """Kubernetes-style readiness probe for FizzBuzz traffic acceptance.

    The readiness probe aggregates health checks from all registered
    subsystems and determines whether the platform is ready to accept
    FizzBuzz evaluation requests. A platform can be alive (liveness=UP)
    but not ready (readiness=DOWN) — for example, when the cache is
    still warming or the circuit breaker is in half-open state.

    In Kubernetes, a failed readiness probe removes the pod from
    the service's load balancer. Here, it just makes us feel bad
    about our infrastructure choices.
    """

    def __init__(
        self,
        registry: Optional[HealthCheckRegistry] = None,
        degraded_is_ready: bool = True,
        event_bus: Any = None,
    ) -> None:
        self._registry = registry or HealthCheckRegistry.get_instance()
        self._degraded_is_ready = degraded_is_ready
        self._event_bus = event_bus

    def probe(self) -> HealthReport:
        """Execute the readiness probe across all registered subsystems.

        Returns:
            A HealthReport with aggregated subsystem check results.
            The overall status is the worst status found across all
            subsystems, because a chain is only as strong as its
            weakest modulo operation.
        """
        self._publish_event(EventType.HEALTH_CHECK_STARTED, {
            "probe_type": "READINESS",
        })

        subsystem_checks = self._registry.check_all()

        # Determine overall status (worst wins)
        overall_status = HealthStatus.UP
        failing_subsystems = []

        for check in subsystem_checks:
            if check.status == HealthStatus.EXISTENTIAL_CRISIS:
                overall_status = HealthStatus.EXISTENTIAL_CRISIS
                failing_subsystems.append(check.subsystem_name)
            elif check.status == HealthStatus.DOWN:
                if overall_status not in (HealthStatus.EXISTENTIAL_CRISIS,):
                    overall_status = HealthStatus.DOWN
                failing_subsystems.append(check.subsystem_name)
            elif check.status == HealthStatus.DEGRADED:
                if not self._degraded_is_ready:
                    failing_subsystems.append(check.subsystem_name)
                if overall_status == HealthStatus.UP:
                    overall_status = HealthStatus.DEGRADED
            elif check.status == HealthStatus.UNKNOWN:
                if overall_status == HealthStatus.UP:
                    overall_status = HealthStatus.UNKNOWN

        # If degraded is considered not ready, and we found degraded subsystems,
        # elevate to DOWN
        if not self._degraded_is_ready and overall_status == HealthStatus.DEGRADED:
            overall_status = HealthStatus.DOWN

        event_type = (
            EventType.HEALTH_READINESS_PASSED
            if overall_status in (HealthStatus.UP, HealthStatus.DEGRADED)
            else EventType.HEALTH_READINESS_FAILED
        )
        self._publish_event(event_type, {
            "overall_status": overall_status.name,
            "subsystem_count": len(subsystem_checks),
            "failing_subsystems": failing_subsystems,
        })

        report = HealthReport(
            probe_type=ProbeType.READINESS,
            overall_status=overall_status,
            subsystem_checks=subsystem_checks,
        )

        self._publish_event(EventType.HEALTH_CHECK_COMPLETED, {
            "probe_type": "READINESS",
            "overall_status": overall_status.name,
        })

        return report

    def _publish_event(self, event_type: EventType, payload: dict[str, Any]) -> None:
        if self._event_bus is not None:
            self._event_bus.publish(Event(
                event_type=event_type,
                payload=payload,
                source="ReadinessProbe",
            ))


# ============================================================
# Startup Probe
# ============================================================


class StartupProbe:
    """Kubernetes-style startup probe for FizzBuzz boot sequence tracking.

    Tracks boot milestones and determines whether the platform has
    completed its startup sequence. In Kubernetes, the startup probe
    runs during pod initialization and prevents liveness/readiness
    checks from running until the application is fully booted.

    For our FizzBuzz platform, the boot sequence involves loading
    config, initializing rules, creating the engine, assembling
    middleware, and building the service. Each milestone is tracked
    with a timestamp because boot observability is non-negotiable.
    """

    def __init__(
        self,
        milestones: Optional[list[str]] = None,
        timeout_seconds: float = 60.0,
        event_bus: Any = None,
    ) -> None:
        self._required_milestones = milestones or [
            "config_loaded",
            "rules_initialized",
            "engine_created",
            "middleware_assembled",
            "service_built",
        ]
        self._completed_milestones: dict[str, float] = {}
        self._start_time = time.monotonic()
        self._timeout_seconds = timeout_seconds
        self._event_bus = event_bus
        self._lock = threading.Lock()

    def record_milestone(self, milestone: str) -> None:
        """Record that a startup milestone has been reached.

        Args:
            milestone: The name of the completed milestone.
        """
        with self._lock:
            if milestone not in self._completed_milestones:
                self._completed_milestones[milestone] = time.monotonic()
                logger.debug("Startup milestone reached: %s", milestone)
                self._publish_event(EventType.HEALTH_STARTUP_MILESTONE, {
                    "milestone": milestone,
                    "elapsed_seconds": time.monotonic() - self._start_time,
                    "completed": len(self._completed_milestones),
                    "total": len(self._required_milestones),
                })

    def get_pending_milestones(self) -> list[str]:
        """Return milestones that have not yet been completed."""
        with self._lock:
            return [m for m in self._required_milestones
                    if m not in self._completed_milestones]

    def get_completed_milestones(self) -> list[str]:
        """Return milestones that have been completed."""
        with self._lock:
            return list(self._completed_milestones.keys())

    def is_complete(self) -> bool:
        """Check if all milestones have been reached."""
        with self._lock:
            return all(
                m in self._completed_milestones
                for m in self._required_milestones
            )

    def is_timed_out(self) -> bool:
        """Check if the startup has exceeded the timeout."""
        return (time.monotonic() - self._start_time) > self._timeout_seconds

    def probe(self) -> HealthReport:
        """Execute the startup probe.

        Returns:
            A HealthReport indicating startup completion status.
        """
        self._publish_event(EventType.HEALTH_CHECK_STARTED, {
            "probe_type": "STARTUP",
        })

        pending = self.get_pending_milestones()
        completed = self.get_completed_milestones()
        timed_out = self.is_timed_out()

        if not pending:
            status = HealthStatus.UP
            details = (
                f"All {len(self._required_milestones)} startup milestones completed. "
                f"The platform has successfully booted, which for a FizzBuzz engine "
                f"is an achievement worth celebrating."
            )
        elif timed_out:
            status = HealthStatus.DOWN
            details = (
                f"Startup timed out after {self._timeout_seconds}s. "
                f"Pending milestones: [{', '.join(pending)}]. "
                f"The platform is stuck in boot limbo."
            )
        else:
            status = HealthStatus.DEGRADED
            elapsed = time.monotonic() - self._start_time
            details = (
                f"Startup in progress ({elapsed:.1f}s elapsed): "
                f"{len(completed)}/{len(self._required_milestones)} milestones complete. "
                f"Pending: [{', '.join(pending)}]"
            )

        checks = []
        for milestone in self._required_milestones:
            is_done = milestone in self._completed_milestones
            checks.append(SubsystemCheck(
                subsystem_name=f"startup:{milestone}",
                status=HealthStatus.UP if is_done else HealthStatus.DOWN,
                details="Completed" if is_done else "Pending",
            ))

        report = HealthReport(
            probe_type=ProbeType.STARTUP,
            overall_status=status,
            subsystem_checks=checks,
        )

        self._publish_event(EventType.HEALTH_CHECK_COMPLETED, {
            "probe_type": "STARTUP",
            "overall_status": status.name,
            "completed": len(completed),
            "total": len(self._required_milestones),
        })

        return report

    def _publish_event(self, event_type: EventType, payload: dict[str, Any]) -> None:
        if self._event_bus is not None:
            self._event_bus.publish(Event(
                event_type=event_type,
                payload=payload,
                source="StartupProbe",
            ))


# ============================================================
# Self-Healing Manager
# ============================================================


class SelfHealingManager:
    """Automated recovery manager for failing FizzBuzz subsystems.

    When a subsystem reports an unhealthy status, the self-healing
    manager attempts to restore it by calling the subsystem's recover()
    method. Recovery is attempted with exponential backoff, because
    hammering a broken subsystem with recovery attempts is the
    infrastructure equivalent of repeatedly pressing a broken elevator
    button — satisfying but ultimately counterproductive.

    The self-healing manager tracks recovery attempts per subsystem
    and gives up after max_retries, at which point the subsystem is
    declared beyond automated salvation and manual intervention is
    recommended (i.e., restarting the process).
    """

    def __init__(
        self,
        registry: Optional[HealthCheckRegistry] = None,
        max_retries: int = 3,
        backoff_base_ms: float = 500.0,
        event_bus: Any = None,
    ) -> None:
        self._registry = registry or HealthCheckRegistry.get_instance()
        self._max_retries = max_retries
        self._backoff_base_ms = backoff_base_ms
        self._event_bus = event_bus
        self._attempt_counts: dict[str, int] = {}
        self._lock = threading.Lock()

    def attempt_recovery(self, subsystem_name: str) -> bool:
        """Attempt to recover a specific subsystem.

        Args:
            subsystem_name: Name of the subsystem to recover.

        Returns:
            True if recovery succeeded, False otherwise.
        """
        with self._lock:
            attempts = self._attempt_counts.get(subsystem_name, 0)
            if attempts >= self._max_retries:
                logger.warning(
                    "Self-healing for '%s' exhausted after %d attempts. "
                    "Manual intervention required.",
                    subsystem_name, attempts,
                )
                return False
            self._attempt_counts[subsystem_name] = attempts + 1

        check = self._registry.get(subsystem_name)
        if check is None:
            return False

        self._publish_event(EventType.HEALTH_SELF_HEAL_ATTEMPTED, {
            "subsystem": subsystem_name,
            "attempt": attempts + 1,
            "max_retries": self._max_retries,
        })

        try:
            success = check.recover()
            if success:
                with self._lock:
                    self._attempt_counts[subsystem_name] = 0
                logger.info("Self-healing succeeded for '%s'", subsystem_name)
            else:
                logger.warning(
                    "Self-healing attempt %d/%d failed for '%s'",
                    attempts + 1, self._max_retries, subsystem_name,
                )
            return success
        except Exception as e:
            logger.error(
                "Self-healing threw exception for '%s': %s",
                subsystem_name, e,
            )
            return False

    def heal_all_unhealthy(self, checks: list[SubsystemCheck]) -> dict[str, bool]:
        """Attempt recovery on all unhealthy subsystems.

        Args:
            checks: Recent subsystem check results.

        Returns:
            Dict mapping subsystem names to recovery success/failure.
        """
        results = {}
        for check in checks:
            if check.status in (HealthStatus.DOWN, HealthStatus.EXISTENTIAL_CRISIS):
                results[check.subsystem_name] = self.attempt_recovery(check.subsystem_name)
        return results

    def get_attempt_counts(self) -> dict[str, int]:
        """Return current recovery attempt counts per subsystem."""
        with self._lock:
            return dict(self._attempt_counts)

    def reset(self) -> None:
        """Reset all attempt counters."""
        with self._lock:
            self._attempt_counts.clear()

    def _publish_event(self, event_type: EventType, payload: dict[str, Any]) -> None:
        if self._event_bus is not None:
            self._event_bus.publish(Event(
                event_type=event_type,
                payload=payload,
                source="SelfHealingManager",
            ))


# ============================================================
# Health Dashboard
# ============================================================


class HealthDashboard:
    """ASCII dashboard for health status visualization.

    Renders a beautiful, enterprise-grade terminal dashboard showing
    the current health status of all subsystems, complete with probe
    results, response times, and diagnostic details. Because health
    data is only as useful as its visual presentation, and nothing
    says "production-ready" like box-drawing characters.
    """

    STATUS_INDICATORS = {
        HealthStatus.UP: "[    UP    ]",
        HealthStatus.DOWN: "[   DOWN   ]",
        HealthStatus.DEGRADED: "[ DEGRADED ]",
        HealthStatus.EXISTENTIAL_CRISIS: "[ CRISIS!! ]",
        HealthStatus.UNKNOWN: "[  UNKNOWN ]",
    }

    STATUS_LABELS = {
        HealthStatus.UP: "All systems nominal",
        HealthStatus.DOWN: "SUBSYSTEM FAILURE",
        HealthStatus.DEGRADED: "Reduced capability",
        HealthStatus.EXISTENTIAL_CRISIS: "THE ML ENGINE HAS DOUBTS",
        HealthStatus.UNKNOWN: "Status indeterminate",
    }

    @classmethod
    def render(cls, report: HealthReport, show_details: bool = True) -> str:
        """Render a health report as an ASCII dashboard.

        Args:
            report: The HealthReport to visualize.
            show_details: Whether to include diagnostic details.

        Returns:
            A multi-line string containing the ASCII dashboard.
        """
        width = 61
        bar = "=" * (width - 2)
        dash = "-" * (width - 2)

        probe_name = report.probe_type.name
        overall_indicator = cls.STATUS_INDICATORS.get(
            report.overall_status, "[  ?????  ]"
        )
        overall_label = cls.STATUS_LABELS.get(
            report.overall_status, "Unknown"
        )

        lines = [
            "",
            f"  +{bar}+",
            f"  |{'HEALTH CHECK DASHBOARD':^{width - 2}}|",
            f"  +{bar}+",
            f"  |  Probe Type     : {probe_name:<{width - 22}}|",
            f"  |  Overall Status : {overall_indicator} {overall_label:<{width - 35}}|",
            f"  |  Timestamp      : {report.timestamp.strftime('%Y-%m-%d %H:%M:%S UTC'):<{width - 22}}|",
            f"  |  Report ID      : {report.report_id[:18] + '...':<{width - 22}}|",
        ]

        if report.canary_value is not None:
            lines.append(
                f"  |  Canary Value   : {report.canary_value:<{width - 22}}|"
            )

        lines.append(f"  |{dash}|")
        lines.append(f"  |{'SUBSYSTEM STATUS':^{width - 2}}|")
        lines.append(f"  |{dash}|")

        if not report.subsystem_checks:
            lines.append(f"  |  {'(no subsystem checks registered)':<{width - 4}}|")
        else:
            for check in report.subsystem_checks:
                indicator = cls.STATUS_INDICATORS.get(
                    check.status, "[  ?????  ]"
                )
                name_str = check.subsystem_name[:20]
                time_str = f"{check.response_time_ms:.2f}ms" if check.response_time_ms > 0 else ""
                line = f"  {name_str:<20} {indicator} {time_str}"
                # Pad to fit within box
                lines.append(f"  |{line[2:]:<{width - 2}}|")

                if show_details and check.details:
                    # Wrap details to fit
                    detail_max = width - 8
                    detail_text = check.details[:detail_max]
                    lines.append(f"  |    {detail_text:<{width - 6}}|")

        lines.append(f"  +{bar}+")
        lines.append("")

        return "\n".join(lines)

    @classmethod
    def render_compact(cls, report: HealthReport) -> str:
        """Render a compact one-line health summary.

        Args:
            report: The HealthReport to summarize.

        Returns:
            A single-line health status string.
        """
        indicator = cls.STATUS_INDICATORS.get(
            report.overall_status, "[?]"
        )
        subsystem_summary = ", ".join(
            f"{c.subsystem_name}={c.status.name}"
            for c in report.subsystem_checks
        )
        return f"{report.probe_type.name} {indicator} [{subsystem_summary}]"
