"""Succession configuration properties."""

from __future__ import annotations

from typing import Any


class SuccessionConfigMixin:
    """Configuration properties for the succession subsystem."""

    @property
    def succession_enabled(self) -> bool:
        """Whether the FizzSuccession succession planning engine is enabled."""
        self._ensure_loaded()
        return self._raw_config.get("fizz_succession", {}).get("enabled", False)

    @property
    def succession_operator(self) -> str:
        """The sole operator for succession planning analysis."""
        self._ensure_loaded()
        return self._raw_config.get("fizz_succession", {}).get("operator", "Bob")

    @property
    def succession_dashboard_width(self) -> int:
        """Width of the FizzSuccession ASCII dashboard."""
        self._ensure_loaded()
        return int(self._raw_config.get("fizz_succession", {}).get("dashboard", {}).get("width", 72))

    # ── FizzPerf: Operator Performance Review ──────────────────

