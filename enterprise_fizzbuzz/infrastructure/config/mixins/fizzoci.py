"""Fizzoci configuration properties."""

from __future__ import annotations

from typing import Any


class FizzociConfigMixin:
    """Configuration properties for the fizzoci subsystem."""

    @property
    def fizzoci_enabled(self) -> bool:
        """Whether the FizzOCI container runtime is enabled."""
        self._ensure_loaded()
        return self._raw_config.get("fizzoci", {}).get("enabled", False)

    @property
    def fizzoci_default_seccomp_profile(self) -> str:
        """Default seccomp profile for new containers."""
        self._ensure_loaded()
        return self._raw_config.get("fizzoci", {}).get("default_seccomp_profile", "default")

    @property
    def fizzoci_default_hook_timeout(self) -> float:
        """Default lifecycle hook timeout in seconds."""
        self._ensure_loaded()
        return float(self._raw_config.get("fizzoci", {}).get("default_hook_timeout", 30.0))

    @property
    def fizzoci_max_containers(self) -> int:
        """Maximum concurrent containers."""
        self._ensure_loaded()
        return int(self._raw_config.get("fizzoci", {}).get("max_containers", 256))

    @property
    def fizzoci_dashboard_width(self) -> int:
        """Width of the FizzOCI ASCII dashboard."""
        self._ensure_loaded()
        return int(self._raw_config.get("fizzoci", {}).get("dashboard", {}).get("width", 72))

    # ── FizzContainerd: High-Level Container Daemon ─────────────

