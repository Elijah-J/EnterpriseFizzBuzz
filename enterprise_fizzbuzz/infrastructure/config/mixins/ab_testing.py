"""A/B Testing Framework properties"""

from __future__ import annotations

from typing import Any


class AbTestingConfigMixin:
    """Configuration properties for the ab testing subsystem."""

    # ----------------------------------------------------------------
    # A/B Testing Framework properties
    # ----------------------------------------------------------------

    @property
    def ab_testing_enabled(self) -> bool:
        self._ensure_loaded()
        return self._raw_config.get("ab_testing", {}).get("enabled", False)

    @property
    def ab_testing_significance_level(self) -> float:
        self._ensure_loaded()
        return self._raw_config.get("ab_testing", {}).get("significance_level", 0.05)

    @property
    def ab_testing_min_sample_size(self) -> int:
        self._ensure_loaded()
        return self._raw_config.get("ab_testing", {}).get("min_sample_size", 30)

    @property
    def ab_testing_safety_accuracy_threshold(self) -> float:
        self._ensure_loaded()
        return self._raw_config.get("ab_testing", {}).get("safety_accuracy_threshold", 0.95)

    @property
    def ab_testing_ramp_schedule(self) -> list[int]:
        self._ensure_loaded()
        return self._raw_config.get("ab_testing", {}).get("ramp_schedule", [10, 25, 50])

    @property
    def ab_testing_experiments(self) -> dict[str, Any]:
        self._ensure_loaded()
        return self._raw_config.get("ab_testing", {}).get("experiments", {})

    @property
    def ab_testing_dashboard_width(self) -> int:
        self._ensure_loaded()
        return self._raw_config.get("ab_testing", {}).get("dashboard", {}).get("width", 60)

