"""FizzAPIGateway2 configuration properties."""

from __future__ import annotations


class Fizzapigateway2ConfigMixin:
    """Configuration properties for the FizzAPIGateway2 API gateway."""

    @property
    def fizzapigateway2_enabled(self) -> bool:
        """Whether the FizzAPIGateway2 is enabled."""
        self._ensure_loaded()
        return self._raw_config.get("fizzapigateway2", {}).get("enabled", False)

    @property
    def fizzapigateway2_default_rate_limit(self) -> int:
        """Default rate limit per route (requests/minute)."""
        self._ensure_loaded()
        return int(self._raw_config.get("fizzapigateway2", {}).get("default_rate_limit", 100))

    @property
    def fizzapigateway2_dashboard_width(self) -> int:
        """Dashboard rendering width."""
        self._ensure_loaded()
        return int(self._raw_config.get("fizzapigateway2", {}).get("dashboard_width", 72))
