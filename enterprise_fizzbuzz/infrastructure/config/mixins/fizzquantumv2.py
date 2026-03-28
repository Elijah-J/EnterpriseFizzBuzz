"""FizzQuantumV2 Quantum Error Correction Configuration Properties"""

from __future__ import annotations

from typing import Any


class Fizzquantumv2ConfigMixin:
    """Configuration properties for the quantum error correction engine."""

    @property
    def fizzquantumv2_enabled(self) -> bool:
        """Whether the quantum error correction engine is enabled."""
        self._ensure_loaded()
        return self._raw_config.get("fizzquantumv2", {}).get("enabled", False)

    @property
    def fizzquantumv2_distance(self) -> int:
        """Surface code distance (must be odd, >= 3)."""
        self._ensure_loaded()
        return int(self._raw_config.get("fizzquantumv2", {}).get("distance", 3))

    @property
    def fizzquantumv2_error_rate(self) -> float:
        """Physical qubit error rate per gate."""
        self._ensure_loaded()
        return float(self._raw_config.get("fizzquantumv2", {}).get("error_rate", 0.001))

    @property
    def fizzquantumv2_correction_rounds(self) -> int:
        """Number of error correction rounds per evaluation."""
        self._ensure_loaded()
        return int(self._raw_config.get("fizzquantumv2", {}).get("correction_rounds", 3))
