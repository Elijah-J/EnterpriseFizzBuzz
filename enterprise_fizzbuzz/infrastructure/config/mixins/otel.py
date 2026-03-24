"""FizzOTel — OpenTelemetry-Compatible Distributed Tracing properties"""

from __future__ import annotations

from typing import Any


class OtelConfigMixin:
    """Configuration properties for the otel subsystem."""

    # ------------------------------------------------------------------
    # FizzOTel — OpenTelemetry-Compatible Distributed Tracing properties
    # ------------------------------------------------------------------

    @property
    def otel_enabled(self) -> bool:
        """Whether the FizzOTel distributed tracing subsystem is active."""
        self._ensure_loaded()
        return self._raw_config.get("otel", {}).get("enabled", False)

    @property
    def otel_export_format(self) -> str:
        """Export format for OTel traces: otlp, zipkin, or console."""
        self._ensure_loaded()
        return self._raw_config.get("otel", {}).get("export_format", "otlp")

    @property
    def otel_sampling_rate(self) -> float:
        """Probabilistic sampling rate (0.0 to 1.0)."""
        self._ensure_loaded()
        return float(self._raw_config.get("otel", {}).get("sampling_rate", 1.0))

    @property
    def otel_batch_mode(self) -> bool:
        """Whether to use BatchSpanProcessor instead of SimpleSpanProcessor."""
        self._ensure_loaded()
        return self._raw_config.get("otel", {}).get("batch_mode", False)

    @property
    def otel_max_queue_size(self) -> int:
        """Maximum spans in the batch queue."""
        self._ensure_loaded()
        return self._raw_config.get("otel", {}).get("max_queue_size", 2048)

    @property
    def otel_max_batch_size(self) -> int:
        """Maximum spans per export batch."""
        self._ensure_loaded()
        return self._raw_config.get("otel", {}).get("max_batch_size", 512)

    @property
    def otel_dashboard_width(self) -> int:
        """Dashboard width for the FizzOTel dashboard."""
        self._ensure_loaded()
        return self._raw_config.get("otel", {}).get("dashboard", {}).get("width", 60)

