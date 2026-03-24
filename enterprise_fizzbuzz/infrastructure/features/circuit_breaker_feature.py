"""Feature descriptor for the Circuit Breaker fault tolerance subsystem."""

from __future__ import annotations

from typing import Any, Optional

from enterprise_fizzbuzz.infrastructure.features._registry import FeatureDescriptor


class CircuitBreakerFeature(FeatureDescriptor):
    name = "circuit_breaker"
    description = "Circuit breaker with exponential backoff for fault-tolerant evaluation"
    middleware_priority = 10
    cli_flags = [
        ("--circuit-breaker", {"action": "store_true",
                               "help": "Enable circuit breaker with exponential backoff for fault-tolerant FizzBuzz evaluation"}),
        ("--circuit-status", {"action": "store_true",
                              "help": "Display the circuit breaker status dashboard after execution"}),
    ]

    def is_enabled(self, args: Any) -> bool:
        return getattr(args, "circuit_breaker", False)

    def create(self, config: Any, args: Any, event_bus: Any = None) -> tuple:
        from enterprise_fizzbuzz.infrastructure.circuit_breaker import (
            CircuitBreakerDashboard,
            CircuitBreakerMiddleware,
            CircuitBreakerRegistry,
        )

        cb_middleware = CircuitBreakerMiddleware(
            event_bus=event_bus,
            failure_threshold=config.circuit_breaker_failure_threshold,
            success_threshold=config.circuit_breaker_success_threshold,
            timeout_ms=config.circuit_breaker_timeout_ms,
            sliding_window_size=config.circuit_breaker_sliding_window_size,
            half_open_max_calls=config.circuit_breaker_half_open_max_calls,
            backoff_base_ms=config.circuit_breaker_backoff_base_ms,
            backoff_max_ms=config.circuit_breaker_backoff_max_ms,
            backoff_multiplier=config.circuit_breaker_backoff_multiplier,
            ml_confidence_threshold=config.circuit_breaker_ml_confidence_threshold,
            call_timeout_ms=config.circuit_breaker_call_timeout_ms,
        )
        registry = CircuitBreakerRegistry.get_instance()
        registry.get_or_create(cb_middleware.circuit_breaker.name)

        return cb_middleware, cb_middleware

    def get_banner(self, config: Any, args: Any) -> Optional[str]:
        timeout_str = f"{config.circuit_breaker_timeout_ms}ms"
        return (
            "  +---------------------------------------------------------+\n"
            "  | CIRCUIT BREAKER: Fault-Tolerant FizzBuzz ENABLED        |\n"
            f"  | Failure Threshold: {config.circuit_breaker_failure_threshold:<36}|\n"
            f"  | Success Threshold: {config.circuit_breaker_success_threshold:<36}|\n"
            f"  | Timeout: {timeout_str:<47}|\n"
            "  | Backoff: Exponential with jitter.                       |\n"
            "  | Because even FizzBuzz deserves graceful degradation.    |\n"
            "  +---------------------------------------------------------+"
        )

    def render(self, middleware: Any, args: Any) -> Optional[str]:
        if not getattr(args, "circuit_status", False):
            return None
        from enterprise_fizzbuzz.infrastructure.circuit_breaker import (
            CircuitBreakerDashboard,
            CircuitBreakerRegistry,
        )
        registry = CircuitBreakerRegistry.get_instance()
        return CircuitBreakerDashboard.render_all(registry)
