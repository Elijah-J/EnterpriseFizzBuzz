"""FizzProfiler configuration properties."""
from __future__ import annotations

class FizzprofilerConfigMixin:
    @property
    def fizzprofiler_enabled(self) -> bool:
        self._ensure_loaded()
        return self._raw_config.get("fizzprofiler", {}).get("enabled", False)
    @property
    def fizzprofiler_sample_rate(self) -> int:
        self._ensure_loaded()
        return int(self._raw_config.get("fizzprofiler", {}).get("sample_rate", 100))
    @property
    def fizzprofiler_dashboard_width(self) -> int:
        self._ensure_loaded()
        return int(self._raw_config.get("fizzprofiler", {}).get("dashboard_width", 72))
