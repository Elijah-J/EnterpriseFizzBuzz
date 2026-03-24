"""Blue/Green Deployment Simulation properties"""

from __future__ import annotations

from typing import Any


class BlueGreenConfigMixin:
    """Configuration properties for the blue green subsystem."""

    # ------------------------------------------------------------------
    # Blue/Green Deployment Simulation properties
    # ------------------------------------------------------------------

    @property
    def blue_green_enabled(self) -> bool:
        """Whether the Blue/Green Deployment Simulation is enabled."""
        self._ensure_loaded()
        return self._raw_config.get("blue_green", {}).get("enabled", False)

    @property
    def blue_green_shadow_traffic_count(self) -> int:
        """Number of evaluations for shadow traffic comparison."""
        self._ensure_loaded()
        return self._raw_config.get("blue_green", {}).get("shadow_traffic_count", 10)

    @property
    def blue_green_smoke_test_numbers(self) -> list[int]:
        """Canary numbers for deployment smoke testing."""
        self._ensure_loaded()
        return self._raw_config.get("blue_green", {}).get("smoke_test_numbers", [3, 5, 15, 42, 97])

    @property
    def blue_green_bake_period_ms(self) -> int:
        """Post-cutover observation window in milliseconds."""
        self._ensure_loaded()
        return self._raw_config.get("blue_green", {}).get("bake_period_ms", 50)

    @property
    def blue_green_bake_period_evaluations(self) -> int:
        """Number of evaluations during the bake period."""
        self._ensure_loaded()
        return self._raw_config.get("blue_green", {}).get("bake_period_evaluations", 5)

    @property
    def blue_green_cutover_delay_ms(self) -> int:
        """Dramatic pause before the atomic variable assignment."""
        self._ensure_loaded()
        return self._raw_config.get("blue_green", {}).get("cutover_delay_ms", 10)

    @property
    def blue_green_rollback_auto(self) -> bool:
        """Whether to automatically rollback on bake period failure."""
        self._ensure_loaded()
        return self._raw_config.get("blue_green", {}).get("rollback_auto", False)

    @property
    def blue_green_dashboard_width(self) -> int:
        """ASCII dashboard width for the Blue/Green Deployment dashboard."""
        self._ensure_loaded()
        return self._raw_config.get("blue_green", {}).get("dashboard", {}).get("width", 60)

