"""FizzReservoir Echo State Network properties."""

from __future__ import annotations

from typing import Any


class FizzreservoirConfigMixin:
    """Configuration properties for the FizzReservoir subsystem."""

    @property
    def fizzreservoir_size(self) -> int:
        """Number of neurons in the reservoir."""
        self._ensure_loaded()
        return self._raw_config.get("fizzreservoir", {}).get("size", 100)

    @property
    def fizzreservoir_spectral_radius(self) -> float:
        """Target spectral radius for the reservoir weight matrix."""
        self._ensure_loaded()
        return self._raw_config.get("fizzreservoir", {}).get("spectral_radius", 0.9)

    @property
    def fizzreservoir_sparsity(self) -> float:
        """Connection density of the reservoir (fraction)."""
        self._ensure_loaded()
        return self._raw_config.get("fizzreservoir", {}).get("sparsity", 0.1)

    @property
    def fizzreservoir_leak_rate(self) -> float:
        """Leaky integration constant."""
        self._ensure_loaded()
        return self._raw_config.get("fizzreservoir", {}).get("leak_rate", 0.3)

    @property
    def fizzreservoir_ridge_alpha(self) -> float:
        """Ridge regression regularization parameter."""
        self._ensure_loaded()
        return self._raw_config.get("fizzreservoir", {}).get("ridge_alpha", 1e-6)

    @property
    def fizzreservoir_dashboard_width(self) -> int:
        """Width of the FizzReservoir ASCII dashboard."""
        self._ensure_loaded()
        return self._raw_config.get("fizzreservoir", {}).get("dashboard_width", 60)
