"""Fizzns configuration properties."""

from __future__ import annotations

from typing import Any


class FizznsConfigMixin:
    """Configuration properties for the fizzns subsystem."""

    @property
    def fizzns_enabled(self) -> bool:
        """Whether the FizzNS namespace isolation engine is enabled."""
        self._ensure_loaded()
        return self._raw_config.get("fizzns", {}).get("enabled", False)

    @property
    def fizzns_default_hostname(self) -> str:
        """Default hostname for new UTS namespaces."""
        self._ensure_loaded()
        return self._raw_config.get("fizzns", {}).get("default_hostname", "fizzbuzz-container")

    @property
    def fizzns_default_domainname(self) -> str:
        """Default domain name for new UTS namespaces."""
        self._ensure_loaded()
        return self._raw_config.get("fizzns", {}).get("default_domainname", "enterprise.local")

    @property
    def fizzns_dashboard_width(self) -> int:
        """Width of the FizzNS ASCII dashboard."""
        self._ensure_loaded()
        return int(self._raw_config.get("fizzns", {}).get("dashboard", {}).get("width", 72))

    # ── FizzCgroup: Control Group Resource Accounting ───────────

