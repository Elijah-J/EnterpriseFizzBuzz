"""Change Data Capture (FizzCDC) configuration properties"""

from __future__ import annotations

from typing import Any


class CdcConfigMixin:
    """Configuration properties for the cdc subsystem."""

    # ----------------------------------------------------------------
    # Change Data Capture (FizzCDC) configuration properties
    # ----------------------------------------------------------------

    @property
    def cdc_enabled(self) -> bool:
        """Whether the Change Data Capture subsystem is active."""
        self._ensure_loaded()
        return self._raw_config.get("cdc", {}).get("enabled", False)

    @property
    def cdc_relay_interval_s(self) -> float:
        """Background relay sweep interval in seconds."""
        self._ensure_loaded()
        return self._raw_config.get("cdc", {}).get("relay_interval_s", 0.5)

    @property
    def cdc_outbox_capacity(self) -> int:
        """Maximum number of events in the outbox before back-pressure."""
        self._ensure_loaded()
        return self._raw_config.get("cdc", {}).get("outbox_capacity", 10000)

    @property
    def cdc_schema_compatibility(self) -> str:
        """Schema compatibility mode: full, forward, or backward."""
        self._ensure_loaded()
        return self._raw_config.get("cdc", {}).get("schema_compatibility", "full")

    @property
    def cdc_sinks(self) -> list[str]:
        """List of enabled sink connector names."""
        self._ensure_loaded()
        return self._raw_config.get("cdc", {}).get("sinks", ["log", "metrics"])

    @property
    def cdc_dashboard_width(self) -> int:
        """Dashboard width for the CDC dashboard."""
        self._ensure_loaded()
        return self._raw_config.get("cdc", {}).get("dashboard", {}).get("width", 60)

