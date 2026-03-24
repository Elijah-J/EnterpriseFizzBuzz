"""Archaeological Recovery System properties"""

from __future__ import annotations

from typing import Any


class ArchaeologyConfigMixin:
    """Configuration properties for the archaeology subsystem."""

    # ------------------------------------------------------------------
    # Archaeological Recovery System properties
    # ------------------------------------------------------------------

    @property
    def archaeology_enabled(self) -> bool:
        self._ensure_loaded()
        return self._raw_config.get("archaeology", {}).get("enabled", False)

    @property
    def archaeology_corruption_rate(self) -> float:
        self._ensure_loaded()
        return self._raw_config.get("archaeology", {}).get("corruption_rate", 0.15)

    @property
    def archaeology_min_fragments(self) -> int:
        self._ensure_loaded()
        return self._raw_config.get("archaeology", {}).get("min_fragments_for_reconstruction", 2)

    @property
    def archaeology_confidence_threshold(self) -> float:
        self._ensure_loaded()
        return self._raw_config.get("archaeology", {}).get("confidence_threshold", 0.6)

    @property
    def archaeology_enable_corruption(self) -> bool:
        self._ensure_loaded()
        return self._raw_config.get("archaeology", {}).get("enable_corruption_simulation", True)

    @property
    def archaeology_seed(self) -> int | None:
        self._ensure_loaded()
        return self._raw_config.get("archaeology", {}).get("seed", None)

    @property
    def archaeology_strata_weights(self) -> dict[str, float]:
        self._ensure_loaded()
        defaults = {
            "blockchain": 1.0,
            "event_store": 0.9,
            "cache_coherence": 0.7,
            "rule_engine": 0.8,
            "middleware_pipeline": 0.6,
            "metrics": 0.5,
            "cache_eulogies": 0.4,
        }
        return self._raw_config.get("archaeology", {}).get("strata_weights", defaults)

    @property
    def archaeology_dashboard_width(self) -> int:
        self._ensure_loaded()
        return self._raw_config.get("archaeology", {}).get("dashboard", {}).get("width", 60)

    @property
    def archaeology_dashboard_show_strata(self) -> bool:
        self._ensure_loaded()
        return self._raw_config.get("archaeology", {}).get("dashboard", {}).get("show_strata_reliability", True)

    @property
    def archaeology_dashboard_show_bayesian(self) -> bool:
        self._ensure_loaded()
        return self._raw_config.get("archaeology", {}).get("dashboard", {}).get("show_bayesian_posterior", True)

    @property
    def archaeology_dashboard_show_corruption(self) -> bool:
        self._ensure_loaded()
        return self._raw_config.get("archaeology", {}).get("dashboard", {}).get("show_corruption_report", True)

    # Recommendation Engine properties
