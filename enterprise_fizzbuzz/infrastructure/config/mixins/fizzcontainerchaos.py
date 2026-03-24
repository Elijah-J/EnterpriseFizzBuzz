"""Fizzcontainerchaos configuration properties."""

from __future__ import annotations

from typing import Any


class FizzcontainerchaosConfigMixin:
    """Configuration properties for the fizzcontainerchaos subsystem."""

    @property
    def fizzcontainerchaos_enabled(self) -> bool:
        """Whether container chaos engineering is enabled."""
        self._ensure_loaded()
        return self._raw_config.get("fizzcontainerchaos", {}).get("enabled", False)

    @property
    def fizzcontainerchaos_cognitive_load_threshold(self) -> float:
        """NASA-TLX threshold for chaos experiment gating."""
        self._ensure_loaded()
        return float(self._raw_config.get("fizzcontainerchaos", {}).get("cognitive_load_threshold", 60.0))

    @property
    def fizzcontainerchaos_blast_radius_limit(self) -> float:
        """Maximum fraction of containers affected simultaneously."""
        self._ensure_loaded()
        return float(self._raw_config.get("fizzcontainerchaos", {}).get("blast_radius_limit", 0.50))

    @property
    def fizzcontainerchaos_blast_radius_scope(self) -> str:
        """Scope for blast radius calculation."""
        self._ensure_loaded()
        return self._raw_config.get("fizzcontainerchaos", {}).get("blast_radius_scope", "global")

    @property
    def fizzcontainerchaos_observation_interval(self) -> float:
        """Seconds between abort condition checks."""
        self._ensure_loaded()
        return float(self._raw_config.get("fizzcontainerchaos", {}).get("observation_interval", 5.0))

    @property
    def fizzcontainerchaos_steady_state_tolerance(self) -> float:
        """Tolerance band for steady-state metric comparison."""
        self._ensure_loaded()
        return float(self._raw_config.get("fizzcontainerchaos", {}).get("steady_state_tolerance", 0.15))

    @property
    def fizzcontainerchaos_experiment_timeout(self) -> float:
        """Default experiment timeout in seconds."""
        self._ensure_loaded()
        return float(self._raw_config.get("fizzcontainerchaos", {}).get("experiment_timeout", 300.0))

    @property
    def fizzcontainerchaos_gameday_timeout(self) -> float:
        """Default game day timeout in seconds."""
        self._ensure_loaded()
        return float(self._raw_config.get("fizzcontainerchaos", {}).get("gameday_timeout", 1800.0))

    @property
    def fizzcontainerchaos_dashboard_width(self) -> int:
        """ASCII dashboard width."""
        self._ensure_loaded()
        return int(self._raw_config.get("fizzcontainerchaos", {}).get("dashboard", {}).get("width", 72))

    @property
    def fizzcontainerchaos_default_latency_ms(self) -> float:
        """Default network latency injection in milliseconds."""
        self._ensure_loaded()
        return float(self._raw_config.get("fizzcontainerchaos", {}).get("default_latency_ms", 200.0))

