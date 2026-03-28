"""FizzTelemetry configuration properties."""
from __future__ import annotations

class FizztelemetryConfigMixin:
    @property
    def fizztelemetry_enabled(self) -> bool:
        self._ensure_loaded()
        return self._raw_config.get("fizztelemetry", {}).get("enabled", False)
    @property
    def fizztelemetry_sample_rate(self) -> float:
        self._ensure_loaded()
        return float(self._raw_config.get("fizztelemetry", {}).get("sample_rate", 1.0))
    @property
    def fizztelemetry_dashboard_width(self) -> int:
        self._ensure_loaded()
        return int(self._raw_config.get("fizztelemetry", {}).get("dashboard_width", 72))
