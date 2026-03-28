"""FizzBPF configuration."""
from __future__ import annotations
class FizzbpfConfigMixin:
    @property
    def fizzbpf_enabled(self) -> bool:
        self._ensure_loaded()
        return self._raw_config.get("fizzbpf", {}).get("enabled", False)
    @property
    def fizzbpf_dashboard_width(self) -> int:
        self._ensure_loaded()
        return int(self._raw_config.get("fizzbpf", {}).get("dashboard_width", 72))
