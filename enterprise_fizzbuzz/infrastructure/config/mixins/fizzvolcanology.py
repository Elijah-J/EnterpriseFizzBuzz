"""FizzVolcanology Volcanic Eruption Simulator Properties"""

from __future__ import annotations

from typing import Any


class FizzvolcanologyConfigMixin:
    """Configuration properties for the FizzVolcanology subsystem."""

    @property
    def fizzvolcanology_enabled(self) -> bool:
        """Whether the FizzVolcanology eruption simulator is enabled."""
        self._ensure_loaded()
        return self._raw_config.get("fizzvolcanology", {}).get("enabled", False)

    @property
    def fizzvolcanology_default_depth_km(self) -> float:
        """Default magma chamber depth in kilometers."""
        self._ensure_loaded()
        return float(self._raw_config.get("fizzvolcanology", {}).get("default_depth_km", 5.0))

    @property
    def fizzvolcanology_default_volume_km3(self) -> float:
        """Default magma chamber volume in cubic kilometers."""
        self._ensure_loaded()
        return float(self._raw_config.get("fizzvolcanology", {}).get("default_volume_km3", 10.0))
