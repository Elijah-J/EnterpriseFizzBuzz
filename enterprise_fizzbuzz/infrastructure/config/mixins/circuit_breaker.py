"""Circuit Breaker configuration properties."""

from __future__ import annotations

from typing import Any


class CircuitBreakerConfigMixin:
    """Configuration properties for the circuit breaker subsystem."""

    @property
    def circuit_breaker_enabled(self) -> bool:
        self._ensure_loaded()
        return self._raw_config.get("circuit_breaker", {}).get("enabled", False)

    @property
    def circuit_breaker_failure_threshold(self) -> int:
        self._ensure_loaded()
        return self._raw_config.get("circuit_breaker", {}).get("failure_threshold", 5)

    @property
    def circuit_breaker_success_threshold(self) -> int:
        self._ensure_loaded()
        return self._raw_config.get("circuit_breaker", {}).get("success_threshold", 3)

    @property
    def circuit_breaker_timeout_ms(self) -> int:
        self._ensure_loaded()
        return self._raw_config.get("circuit_breaker", {}).get("timeout_ms", 30000)

    @property
    def circuit_breaker_sliding_window_size(self) -> int:
        self._ensure_loaded()
        return self._raw_config.get("circuit_breaker", {}).get("sliding_window_size", 10)

    @property
    def circuit_breaker_half_open_max_calls(self) -> int:
        self._ensure_loaded()
        return self._raw_config.get("circuit_breaker", {}).get("half_open_max_calls", 3)

    @property
    def circuit_breaker_backoff_base_ms(self) -> int:
        self._ensure_loaded()
        return self._raw_config.get("circuit_breaker", {}).get("backoff_base_ms", 1000)

    @property
    def circuit_breaker_backoff_max_ms(self) -> int:
        self._ensure_loaded()
        return self._raw_config.get("circuit_breaker", {}).get("backoff_max_ms", 60000)

    @property
    def circuit_breaker_backoff_multiplier(self) -> float:
        self._ensure_loaded()
        return self._raw_config.get("circuit_breaker", {}).get("backoff_multiplier", 2.0)

    @property
    def circuit_breaker_ml_confidence_threshold(self) -> float:
        self._ensure_loaded()
        return self._raw_config.get("circuit_breaker", {}).get("ml_confidence_threshold", 0.7)

    @property
    def circuit_breaker_call_timeout_ms(self) -> int:
        self._ensure_loaded()
        return self._raw_config.get("circuit_breaker", {}).get("call_timeout_ms", 5000)

