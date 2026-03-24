"""Reverse Proxy & Load Balancer properties"""

from __future__ import annotations

from typing import Any


class ProxyConfigMixin:
    """Configuration properties for the proxy subsystem."""

    # ------------------------------------------------------------------
    # Reverse Proxy & Load Balancer properties
    # ------------------------------------------------------------------

    @property
    def proxy_enabled(self) -> bool:
        """Whether the reverse proxy subsystem is enabled."""
        self._ensure_loaded()
        return self._raw_config.get("proxy", {}).get("enabled", False)

    @property
    def proxy_num_backends(self) -> int:
        """Number of backend engine instances in the proxy pool."""
        self._ensure_loaded()
        return self._raw_config.get("proxy", {}).get("num_backends", 5)

    @property
    def proxy_algorithm(self) -> str:
        """Load balancing algorithm name."""
        self._ensure_loaded()
        return self._raw_config.get("proxy", {}).get("algorithm", "round_robin")

    @property
    def proxy_enable_sticky_sessions(self) -> bool:
        """Whether sticky sessions are enabled."""
        self._ensure_loaded()
        return self._raw_config.get("proxy", {}).get("enable_sticky_sessions", True)

    @property
    def proxy_enable_health_check(self) -> bool:
        """Whether health checking is enabled."""
        self._ensure_loaded()
        return self._raw_config.get("proxy", {}).get("enable_health_check", True)

    @property
    def proxy_health_check_interval(self) -> int:
        """Health check interval in requests."""
        self._ensure_loaded()
        return self._raw_config.get("proxy", {}).get("health_check_interval", 10)

    @property
    def proxy_dashboard_width(self) -> int:
        """Dashboard width for the proxy dashboard."""
        self._ensure_loaded()
        return self._raw_config.get("proxy", {}).get("dashboard", {}).get("width", 60)

