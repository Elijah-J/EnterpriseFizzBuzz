"""Audit Dashboard & Real-Time Event Streaming properties"""

from __future__ import annotations

from typing import Any


class AuditDashboardConfigMixin:
    """Configuration properties for the audit dashboard subsystem."""

    # ----------------------------------------------------------------
    # Audit Dashboard & Real-Time Event Streaming properties
    # ----------------------------------------------------------------

    @property
    def audit_dashboard_enabled(self) -> bool:
        """Whether the audit dashboard subsystem is enabled."""
        self._ensure_loaded()
        return self._raw_config.get("audit_dashboard", {}).get("enabled", False)

    @property
    def audit_dashboard_buffer_size(self) -> int:
        """Maximum events in the rolling audit buffer."""
        self._ensure_loaded()
        return self._raw_config.get("audit_dashboard", {}).get("buffer_size", 500)

    @property
    def audit_dashboard_anomaly_enabled(self) -> bool:
        """Whether z-score anomaly detection is enabled."""
        self._ensure_loaded()
        return self._raw_config.get("audit_dashboard", {}).get("anomaly_detection", {}).get("enabled", True)

    @property
    def audit_dashboard_anomaly_window_seconds(self) -> float:
        """Tumbling window duration for anomaly rate computation."""
        self._ensure_loaded()
        return self._raw_config.get("audit_dashboard", {}).get("anomaly_detection", {}).get("window_seconds", 10.0)

    @property
    def audit_dashboard_z_score_threshold(self) -> float:
        """Z-score threshold for anomaly alerting."""
        self._ensure_loaded()
        return self._raw_config.get("audit_dashboard", {}).get("anomaly_detection", {}).get("z_score_threshold", 2.0)

    @property
    def audit_dashboard_anomaly_min_samples(self) -> int:
        """Minimum samples before z-score computation is meaningful."""
        self._ensure_loaded()
        return self._raw_config.get("audit_dashboard", {}).get("anomaly_detection", {}).get("min_samples", 5)

    @property
    def audit_dashboard_correlation_enabled(self) -> bool:
        """Whether temporal event correlation is enabled."""
        self._ensure_loaded()
        return self._raw_config.get("audit_dashboard", {}).get("correlation", {}).get("enabled", True)

    @property
    def audit_dashboard_correlation_window_seconds(self) -> float:
        """Time window for grouping correlated events."""
        self._ensure_loaded()
        return self._raw_config.get("audit_dashboard", {}).get("correlation", {}).get("window_seconds", 5.0)

    @property
    def audit_dashboard_correlation_min_events(self) -> int:
        """Minimum events to form a correlation insight."""
        self._ensure_loaded()
        return self._raw_config.get("audit_dashboard", {}).get("correlation", {}).get("min_events", 2)

    @property
    def audit_dashboard_stream_include_payload(self) -> bool:
        """Whether to include full event payload in stream output."""
        self._ensure_loaded()
        return self._raw_config.get("audit_dashboard", {}).get("stream", {}).get("include_payload", True)

    @property
    def audit_dashboard_width(self) -> int:
        """ASCII dashboard width."""
        self._ensure_loaded()
        return self._raw_config.get("audit_dashboard", {}).get("dashboard", {}).get("width", 80)

