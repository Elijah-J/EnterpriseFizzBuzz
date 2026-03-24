"""FizzGate Digital Logic Circuit Simulator Properties"""

from __future__ import annotations

from typing import Any


class CircuitSimConfigMixin:
    """Configuration properties for the circuit sim subsystem."""

    # ----------------------------------------------------------------
    # FizzGate Digital Logic Circuit Simulator Properties
    # ----------------------------------------------------------------

    @property
    def circuit_enabled(self) -> bool:
        """Whether the FizzGate circuit simulator is enabled."""
        self._ensure_loaded()
        return self._raw_config.get("circuit", {}).get("enabled", False)

    @property
    def circuit_enable_waveform(self) -> bool:
        """Whether to capture and display ASCII waveform timing diagrams."""
        self._ensure_loaded()
        return self._raw_config.get("circuit", {}).get("enable_waveform", False)

    @property
    def circuit_enable_dashboard(self) -> bool:
        """Whether to display the circuit analysis dashboard."""
        self._ensure_loaded()
        return self._raw_config.get("circuit", {}).get("enable_dashboard", False)

    @property
    def circuit_max_events(self) -> int:
        """Maximum simulation events before declaring oscillation."""
        self._ensure_loaded()
        return self._raw_config.get("circuit", {}).get("max_events", 10000)

    @property
    def circuit_timing_budget_ns(self) -> float:
        """Maximum acceptable circuit settle time in nanoseconds."""
        self._ensure_loaded()
        return self._raw_config.get("circuit", {}).get("timing_budget_ns", 500.0)

    @property
    def circuit_glitch_threshold_ns(self) -> float:
        """Minimum time between transitions to avoid glitch counting."""
        self._ensure_loaded()
        return self._raw_config.get("circuit", {}).get("glitch_threshold_ns", 5.0)

    @property
    def circuit_dashboard_width(self) -> int:
        """Width of the FizzGate ASCII dashboard."""
        self._ensure_loaded()
        return self._raw_config.get("circuit", {}).get("dashboard", {}).get("width", 60)

