"""Bob configuration properties."""

from __future__ import annotations

from typing import Any


class BobConfigMixin:
    """Configuration properties for the bob subsystem."""

    @property
    def bob_enabled(self) -> bool:
        """Whether the FizzBob operator cognitive load engine is enabled."""
        self._ensure_loaded()
        return self._raw_config.get("fizzbob", {}).get("enabled", False)

    @property
    def bob_hours_awake(self) -> float:
        """Initial hours-awake for Bob at the start of his shift."""
        self._ensure_loaded()
        return float(self._raw_config.get("fizzbob", {}).get("hours_awake", 0.0))

    @property
    def bob_shift_start_hour(self) -> float:
        """Wall-clock hour at which Bob's shift begins."""
        self._ensure_loaded()
        return float(self._raw_config.get("fizzbob", {}).get("shift_start_hour", 8.0))

    @property
    def bob_tau_rise(self) -> float:
        """Sleep pressure time constant (hours) for the Borbely model."""
        self._ensure_loaded()
        return float(self._raw_config.get("fizzbob", {}).get("tau_rise", 18.18))

    @property
    def bob_c_amplitude(self) -> float:
        """Circadian oscillation amplitude."""
        self._ensure_loaded()
        return float(self._raw_config.get("fizzbob", {}).get("c_amplitude", 0.12))

    @property
    def bob_alert_halflife_hours(self) -> float:
        """Alert fatigue decay half-life in hours."""
        self._ensure_loaded()
        return float(self._raw_config.get("fizzbob", {}).get("alert_halflife_hours", 2.0))

    @property
    def bob_burnout_threshold(self) -> float:
        """MBI composite burnout threshold."""
        self._ensure_loaded()
        return float(self._raw_config.get("fizzbob", {}).get("burnout_threshold", 0.60))

    @property
    def bob_tlx_activate(self) -> float:
        """Weighted TLX threshold for overload activation."""
        self._ensure_loaded()
        return float(self._raw_config.get("fizzbob", {}).get("tlx_activate", 80.0))

    @property
    def bob_auto_assess_interval(self) -> int:
        """Number of evaluations between automatic TLX re-assessments."""
        self._ensure_loaded()
        return int(self._raw_config.get("fizzbob", {}).get("auto_assess_interval", 10))

    @property
    def bob_generate_synthetic_alerts(self) -> bool:
        """Whether to generate synthetic alerts from evaluation results."""
        self._ensure_loaded()
        return self._raw_config.get("fizzbob", {}).get("generate_synthetic_alerts", True)

    @property
    def bob_dashboard_width(self) -> int:
        """Width of the FizzBob ASCII dashboard."""
        self._ensure_loaded()
        return int(self._raw_config.get("fizzbob", {}).get("dashboard", {}).get("width", 72))

    # ── FizzRegistry: OCI Distribution-Compliant Image Registry ─

