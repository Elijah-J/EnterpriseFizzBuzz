"""Prometheus-Style Metrics Exporter configuration properties"""

from __future__ import annotations

from typing import Any


class MetricsConfigMixin:
    """Configuration properties for the metrics subsystem."""

    # --------------------------------------------------------
    # Prometheus-Style Metrics Exporter configuration properties
    # --------------------------------------------------------

    @property
    def metrics_enabled(self) -> bool:
        """Whether the Prometheus-style metrics exporter is enabled."""
        self._ensure_loaded()
        return self._raw_config.get("metrics", {}).get("enabled", False)

    @property
    def metrics_export_format(self) -> str:
        """Export format for metrics. Currently only 'prometheus'."""
        self._ensure_loaded()
        return self._raw_config.get("metrics", {}).get("export_format", "prometheus")

    @property
    def metrics_cardinality_threshold(self) -> int:
        """Warn when unique label combos exceed this threshold."""
        self._ensure_loaded()
        return self._raw_config.get("metrics", {}).get("cardinality_threshold", 100)

    @property
    def metrics_default_buckets(self) -> list[float]:
        """Default histogram bucket boundaries."""
        self._ensure_loaded()
        return self._raw_config.get("metrics", {}).get(
            "default_buckets",
            [0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0],
        )

    @property
    def metrics_dashboard_width(self) -> int:
        """ASCII dashboard width in characters."""
        self._ensure_loaded()
        return self._raw_config.get("metrics", {}).get("dashboard", {}).get("width", 60)

    @property
    def metrics_dashboard_sparkline_length(self) -> int:
        """Number of data points in sparkline charts."""
        self._ensure_loaded()
        return self._raw_config.get("metrics", {}).get("dashboard", {}).get("sparkline_length", 20)

    @property
    def metrics_bob_stress_level(self) -> float:
        """Bob McFizzington's initial stress level. It's always 42."""
        self._ensure_loaded()
        return self._raw_config.get("metrics", {}).get("bob_mcfizzington", {}).get("initial_stress_level", 42.0)

