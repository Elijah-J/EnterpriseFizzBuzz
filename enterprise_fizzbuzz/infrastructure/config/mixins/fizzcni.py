"""Fizzcni configuration properties."""

from __future__ import annotations

from typing import Any


class FizzcniConfigMixin:
    """Configuration properties for the fizzcni subsystem."""

    @property
    def fizzcni_enabled(self) -> bool:
        """Whether the FizzCNI container networking is enabled."""
        self._ensure_loaded()
        return self._raw_config.get("fizzcni", {}).get("enabled", False)

    @property
    def fizzcni_subnet(self) -> str:
        """Pod network CIDR range."""
        self._ensure_loaded()
        return self._raw_config.get("fizzcni", {}).get("subnet", "10.244.0.0/16")

    @property
    def fizzcni_gateway(self) -> str:
        """Gateway IP address."""
        self._ensure_loaded()
        return self._raw_config.get("fizzcni", {}).get("gateway", "10.244.0.1")

    @property
    def fizzcni_bridge_name(self) -> str:
        """Bridge interface name."""
        self._ensure_loaded()
        return self._raw_config.get("fizzcni", {}).get("bridge_name", "fizzbr0")

    @property
    def fizzcni_lease_duration(self) -> float:
        """DHCP lease duration in seconds."""
        self._ensure_loaded()
        return float(self._raw_config.get("fizzcni", {}).get("lease_duration", 3600.0))

    @property
    def fizzcni_mtu(self) -> int:
        """Maximum Transmission Unit."""
        self._ensure_loaded()
        return int(self._raw_config.get("fizzcni", {}).get("mtu", 1500))

    @property
    def fizzcni_dns_domain(self) -> str:
        """Container DNS domain."""
        self._ensure_loaded()
        return self._raw_config.get("fizzcni", {}).get("dns_domain", "cluster.fizz")

    @property
    def fizzcni_dns_ttl(self) -> int:
        """Default DNS record TTL in seconds."""
        self._ensure_loaded()
        return int(self._raw_config.get("fizzcni", {}).get("dns_ttl", 30))

    @property
    def fizzcni_dashboard_width(self) -> int:
        """Width of the FizzCNI ASCII dashboard."""
        self._ensure_loaded()
        return int(self._raw_config.get("fizzcni", {}).get("dashboard", {}).get("width", 72))

    @property
    def fizzcni_default_driver(self) -> str:
        """Default CNI plugin driver."""
        self._ensure_loaded()
        return self._raw_config.get("fizzcni", {}).get("default_driver", "bridge")

    # ── FizzOCI: OCI-Compliant Container Runtime ─────────────

