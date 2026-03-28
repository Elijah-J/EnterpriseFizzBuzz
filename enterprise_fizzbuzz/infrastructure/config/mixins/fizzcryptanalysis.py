"""FizzCryptanalysis Cipher Breaking Engine properties."""

from __future__ import annotations

from typing import Any


class FizzcryptanalysisConfigMixin:
    """Configuration properties for the FizzCryptanalysis subsystem."""

    @property
    def fizzcryptanalysis_enabled(self) -> bool:
        """Whether the FizzCryptanalysis cipher breaking engine is enabled."""
        self._ensure_loaded()
        return self._raw_config.get("fizzcryptanalysis", {}).get("enabled", False)

    @property
    def fizzcryptanalysis_min_length(self) -> int:
        """Minimum ciphertext length for frequency analysis."""
        self._ensure_loaded()
        return int(self._raw_config.get("fizzcryptanalysis", {}).get("min_length", 50))
