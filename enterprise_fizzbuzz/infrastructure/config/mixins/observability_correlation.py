"""FizzCorr Observability Correlation Engine properties"""

from __future__ import annotations

from typing import Any


class ObservabilityCorrelationConfigMixin:
    """Configuration properties for the observability correlation subsystem."""

    # ------------------------------------------------------------------
    # FizzCorr Observability Correlation Engine properties
    # ------------------------------------------------------------------

    @property
    def observability_correlation_enabled(self) -> bool:
        """Whether the FizzCorr Observability Correlation Engine is active."""
        self._ensure_loaded()
        return self._raw_config.get("observability_correlation", {}).get("enabled", False)

    @property
    def observability_correlation_temporal_window_seconds(self) -> float:
        """Maximum time delta for temporal correlation."""
        self._ensure_loaded()
        return self._raw_config.get("observability_correlation", {}).get("temporal_window_seconds", 2.0)

    @property
    def observability_correlation_confidence_threshold(self) -> float:
        """Minimum confidence score to accept a correlation."""
        self._ensure_loaded()
        return self._raw_config.get("observability_correlation", {}).get("confidence_threshold", 0.3)

    @property
    def observability_correlation_anomaly_latency_threshold_ms(self) -> float:
        """Latency threshold for anomaly detection in milliseconds."""
        self._ensure_loaded()
        return self._raw_config.get("observability_correlation", {}).get("anomaly_latency_threshold_ms", 50.0)

    @property
    def observability_correlation_anomaly_error_burst_window_s(self) -> float:
        """Window for error burst detection in seconds."""
        self._ensure_loaded()
        return self._raw_config.get("observability_correlation", {}).get("anomaly_error_burst_window_s", 5.0)

    @property
    def observability_correlation_anomaly_error_burst_threshold(self) -> int:
        """Number of errors in window to trigger burst anomaly."""
        self._ensure_loaded()
        return self._raw_config.get("observability_correlation", {}).get("anomaly_error_burst_threshold", 3)

    @property
    def observability_correlation_anomaly_metric_deviation_sigma(self) -> float:
        """Standard deviations for metric deviation anomaly."""
        self._ensure_loaded()
        return self._raw_config.get("observability_correlation", {}).get("anomaly_metric_deviation_sigma", 2.0)

    @property
    def observability_correlation_causal_patterns(self) -> list[dict]:
        """Known causal patterns for rule-based correlation."""
        self._ensure_loaded()
        return self._raw_config.get("observability_correlation", {}).get("causal_patterns", [])

    @property
    def observability_correlation_dashboard_width(self) -> int:
        """Dashboard width for the observability correlation dashboard."""
        self._ensure_loaded()
        return self._raw_config.get("observability_correlation", {}).get("dashboard", {}).get("width", 60)

