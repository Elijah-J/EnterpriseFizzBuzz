"""Digital Twin Simulation properties"""

from __future__ import annotations

from typing import Any


class DigitalTwinConfigMixin:
    """Configuration properties for the digital twin subsystem."""

    # ------------------------------------------------------------------
    # Digital Twin Simulation properties
    # ------------------------------------------------------------------

    @property
    def digital_twin_enabled(self) -> bool:
        self._ensure_loaded()
        return self._raw_config.get("digital_twin", {}).get("enabled", False)

    @property
    def digital_twin_monte_carlo_runs(self) -> int:
        self._ensure_loaded()
        return self._raw_config.get("digital_twin", {}).get("monte_carlo_runs", 1000)

    @property
    def digital_twin_jitter_stddev(self) -> float:
        self._ensure_loaded()
        return self._raw_config.get("digital_twin", {}).get("jitter_stddev", 0.05)

    @property
    def digital_twin_failure_jitter(self) -> float:
        self._ensure_loaded()
        return self._raw_config.get("digital_twin", {}).get("failure_jitter", 0.02)

    @property
    def digital_twin_drift_threshold_fdu(self) -> float:
        self._ensure_loaded()
        return self._raw_config.get("digital_twin", {}).get("drift_threshold_fdu", 5.0)

    @property
    def digital_twin_anomaly_sigma(self) -> float:
        self._ensure_loaded()
        return self._raw_config.get("digital_twin", {}).get("anomaly_sigma", 2.0)

    @property
    def digital_twin_dashboard_width(self) -> int:
        self._ensure_loaded()
        return self._raw_config.get("digital_twin", {}).get("dashboard", {}).get("width", 60)

    @property
    def digital_twin_dashboard_show_histogram(self) -> bool:
        self._ensure_loaded()
        return self._raw_config.get("digital_twin", {}).get("dashboard", {}).get("show_histogram", True)

    @property
    def digital_twin_dashboard_show_drift_gauge(self) -> bool:
        self._ensure_loaded()
        return self._raw_config.get("digital_twin", {}).get("dashboard", {}).get("show_drift_gauge", True)

    @property
    def digital_twin_histogram_buckets(self) -> int:
        self._ensure_loaded()
        return self._raw_config.get("digital_twin", {}).get("dashboard", {}).get("histogram_buckets", 20)

