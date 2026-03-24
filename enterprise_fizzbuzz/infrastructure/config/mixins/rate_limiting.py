"""Rate Limiting & API Quota Management configuration properties"""

from __future__ import annotations

from typing import Any


class RateLimitingConfigMixin:
    """Configuration properties for the rate limiting subsystem."""

    # ----------------------------------------------------------------
    # Rate Limiting & API Quota Management configuration properties
    # ----------------------------------------------------------------

    @property
    def rate_limiting_enabled(self) -> bool:
        """Whether Rate Limiting & API Quota Management is enabled."""
        self._ensure_loaded()
        return self._raw_config.get("rate_limiting", {}).get("enabled", False)

    @property
    def rate_limiting_algorithm(self) -> str:
        """The rate limiting algorithm: token_bucket, sliding_window, or fixed_window."""
        self._ensure_loaded()
        return self._raw_config.get("rate_limiting", {}).get("algorithm", "token_bucket")

    @property
    def rate_limiting_rpm(self) -> int:
        """Maximum FizzBuzz evaluations per minute."""
        self._ensure_loaded()
        return self._raw_config.get("rate_limiting", {}).get("requests_per_minute", 60)

    @property
    def rate_limiting_burst_credits_enabled(self) -> bool:
        """Whether burst credits are enabled."""
        self._ensure_loaded()
        return self._raw_config.get("rate_limiting", {}).get("burst_credits", {}).get("enabled", True)

    @property
    def rate_limiting_burst_credits_max(self) -> int:
        """Maximum burst credits that can be accumulated."""
        self._ensure_loaded()
        return self._raw_config.get("rate_limiting", {}).get("burst_credits", {}).get("max_credits", 30)

    @property
    def rate_limiting_burst_credits_earn_rate(self) -> float:
        """Credits earned per unused evaluation slot."""
        self._ensure_loaded()
        return self._raw_config.get("rate_limiting", {}).get("burst_credits", {}).get("earn_rate", 0.5)

    @property
    def rate_limiting_reservations_enabled(self) -> bool:
        """Whether evaluation capacity reservations are enabled."""
        self._ensure_loaded()
        return self._raw_config.get("rate_limiting", {}).get("reservations", {}).get("enabled", True)

    @property
    def rate_limiting_reservations_max(self) -> int:
        """Maximum concurrent active reservations."""
        self._ensure_loaded()
        return self._raw_config.get("rate_limiting", {}).get("reservations", {}).get("max_reservations", 10)

    @property
    def rate_limiting_reservations_ttl_seconds(self) -> int:
        """How long a reservation remains valid in seconds."""
        self._ensure_loaded()
        return self._raw_config.get("rate_limiting", {}).get("reservations", {}).get("ttl_seconds", 30)

    @property
    def rate_limiting_dashboard_width(self) -> int:
        """ASCII dashboard width in characters."""
        self._ensure_loaded()
        return self._raw_config.get("rate_limiting", {}).get("dashboard", {}).get("width", 60)

