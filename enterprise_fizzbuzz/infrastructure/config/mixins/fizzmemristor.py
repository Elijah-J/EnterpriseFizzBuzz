"""FizzMemristor Memristive Computing properties."""

from __future__ import annotations

from typing import Any


class FizzmemristorConfigMixin:
    """Configuration properties for the FizzMemristor subsystem."""

    @property
    def fizzmemristor_rows(self) -> int:
        """Number of rows (wordlines) in the crossbar array."""
        self._ensure_loaded()
        return self._raw_config.get("fizzmemristor", {}).get("rows", 8)

    @property
    def fizzmemristor_cols(self) -> int:
        """Number of columns (bitlines) in the crossbar array."""
        self._ensure_loaded()
        return self._raw_config.get("fizzmemristor", {}).get("cols", 4)

    @property
    def fizzmemristor_g_min(self) -> float:
        """Minimum conductance (HRS) in Siemens."""
        self._ensure_loaded()
        return self._raw_config.get("fizzmemristor", {}).get("g_min", 1e-7)

    @property
    def fizzmemristor_g_max(self) -> float:
        """Maximum conductance (LRS) in Siemens."""
        self._ensure_loaded()
        return self._raw_config.get("fizzmemristor", {}).get("g_max", 1e-4)

    @property
    def fizzmemristor_variability(self) -> float:
        """Cycle-to-cycle conductance variability (fraction)."""
        self._ensure_loaded()
        return self._raw_config.get("fizzmemristor", {}).get("variability", 0.05)

    @property
    def fizzmemristor_dashboard_width(self) -> int:
        """Width of the FizzMemristor ASCII dashboard."""
        self._ensure_loaded()
        return self._raw_config.get("fizzmemristor", {}).get("dashboard_width", 60)
