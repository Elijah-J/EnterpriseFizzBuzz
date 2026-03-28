"""FizzCostOptimizer configuration."""
from __future__ import annotations
class FizzcostoptimizerConfigMixin:
    @property
    def fizzcostoptimizer_enabled(self) -> bool:
        self._ensure_loaded()
        return self._raw_config.get("fizzcostoptimizer", {}).get("enabled", False)
    @property
    def fizzcostoptimizer_dashboard_width(self) -> int:
        self._ensure_loaded()
        return int(self._raw_config.get("fizzcostoptimizer", {}).get("dashboard_width", 72))
