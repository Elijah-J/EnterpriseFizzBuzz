"""FizzWorkflow configuration."""
from __future__ import annotations

class FizzworkflowConfigMixin:
    @property
    def fizzworkflow_enabled(self) -> bool:
        self._ensure_loaded()
        return self._raw_config.get("fizzworkflow", {}).get("enabled", False)
    @property
    def fizzworkflow_dashboard_width(self) -> int:
        self._ensure_loaded()
        return int(self._raw_config.get("fizzworkflow", {}).get("dashboard_width", 72))
