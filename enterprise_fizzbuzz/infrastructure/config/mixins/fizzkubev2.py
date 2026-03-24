"""Fizzkubev2 configuration properties."""

from __future__ import annotations

from typing import Any


class Fizzkubev2ConfigMixin:
    """Configuration properties for the fizzkubev2 subsystem."""

    @property
    def fizzkubev2_enabled(self) -> bool:
        """Whether the FizzKubeV2 CRI-integrated orchestrator is enabled."""
        self._ensure_loaded()
        return self._raw_config.get("fizzkubev2", {}).get("enabled", False)

    @property
    def fizzkubev2_default_pull_policy(self) -> str:
        """Default image pull policy."""
        self._ensure_loaded()
        return self._raw_config.get("fizzkubev2", {}).get("default_pull_policy", "IfNotPresent")

    @property
    def fizzkubev2_probe_initial_delay(self) -> float:
        """Probe initial delay in seconds."""
        self._ensure_loaded()
        return float(self._raw_config.get("fizzkubev2", {}).get("probe_initial_delay", 0.0))

    @property
    def fizzkubev2_probe_period(self) -> float:
        """Probe period in seconds."""
        self._ensure_loaded()
        return float(self._raw_config.get("fizzkubev2", {}).get("probe_period", 10.0))

    @property
    def fizzkubev2_probe_failure_threshold(self) -> int:
        """Consecutive failures for probe fail."""
        self._ensure_loaded()
        return int(self._raw_config.get("fizzkubev2", {}).get("probe_failure_threshold", 3))

    @property
    def fizzkubev2_termination_grace_period(self) -> float:
        """Seconds to wait after SIGTERM before SIGKILL."""
        self._ensure_loaded()
        return float(self._raw_config.get("fizzkubev2", {}).get("termination_grace_period", 30.0))

    @property
    def fizzkubev2_restart_backoff_base(self) -> float:
        """Base restart backoff in seconds."""
        self._ensure_loaded()
        return float(self._raw_config.get("fizzkubev2", {}).get("restart_backoff_base", 10.0))

    @property
    def fizzkubev2_restart_backoff_cap(self) -> float:
        """Maximum restart backoff in seconds."""
        self._ensure_loaded()
        return float(self._raw_config.get("fizzkubev2", {}).get("restart_backoff_cap", 300.0))

    @property
    def fizzkubev2_inject_sidecars(self) -> bool:
        """Whether to inject default sidecars."""
        self._ensure_loaded()
        return self._raw_config.get("fizzkubev2", {}).get("inject_sidecars", True)

    @property
    def fizzkubev2_storage_pool_bytes(self) -> int:
        """Total storage pool for volumes in bytes."""
        self._ensure_loaded()
        return int(self._raw_config.get("fizzkubev2", {}).get("storage_pool_bytes", 10485760))

    @property
    def fizzkubev2_max_init_retries(self) -> int:
        """Maximum init container restart attempts."""
        self._ensure_loaded()
        return int(self._raw_config.get("fizzkubev2", {}).get("max_init_retries", 3))

    @property
    def fizzkubev2_dashboard_width(self) -> int:
        """Width of the FizzKubeV2 ASCII dashboard."""
        self._ensure_loaded()
        return int(self._raw_config.get("fizzkubev2", {}).get("dashboard_width", 72))

