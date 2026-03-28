"""FizzEpidemiology Disease Spread Modeler properties."""

from __future__ import annotations

from typing import Any


class FizzepidemiologyConfigMixin:
    """Configuration properties for the FizzEpidemiology subsystem."""

    @property
    def fizzepidemiology_enabled(self) -> bool:
        """Whether the FizzEpidemiology disease spread modeler is enabled."""
        self._ensure_loaded()
        return self._raw_config.get("fizzepidemiology", {}).get("enabled", False)

    @property
    def fizzepidemiology_population(self) -> int:
        """Population size for SIR/SEIR simulations."""
        self._ensure_loaded()
        return int(self._raw_config.get("fizzepidemiology", {}).get("population", 1000))

    @property
    def fizzepidemiology_contact_radius(self) -> int:
        """Contact tracing radius (integer distance)."""
        self._ensure_loaded()
        return int(self._raw_config.get("fizzepidemiology", {}).get("contact_radius", 5))
