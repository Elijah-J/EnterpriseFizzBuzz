"""FizzK8sOperator configuration properties."""

from __future__ import annotations


class Fizzk8soperatorConfigMixin:
    @property
    def fizzk8soperator_enabled(self) -> bool:
        self._ensure_loaded()
        return self._raw_config.get("fizzk8soperator", {}).get("enabled", False)

    @property
    def fizzk8soperator_dashboard_width(self) -> int:
        self._ensure_loaded()
        return int(self._raw_config.get("fizzk8soperator", {}).get("dashboard_width", 72))
