"""FizzHealthAggregator configuration."""
from __future__ import annotations
class FizzhealthaggregatorConfigMixin:
    @property
    def fizzhealthaggregator_enabled(self) -> bool:
        self._ensure_loaded()
        return self._raw_config.get("fizzhealthaggregator", {}).get("enabled", False)
    @property
    def fizzhealthaggregator_dashboard_width(self) -> int:
        self._ensure_loaded()
        return int(self._raw_config.get("fizzhealthaggregator", {}).get("dashboard_width", 72))
