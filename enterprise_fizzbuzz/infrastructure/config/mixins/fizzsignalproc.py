"""FizzSignalProc Digital Signal Processing properties."""

from __future__ import annotations

from typing import Any


class FizzsignalprocConfigMixin:
    """Configuration properties for the FizzSignalProc subsystem."""

    @property
    def fizzsignalproc_enabled(self) -> bool:
        """Whether the FizzSignalProc DSP engine is enabled."""
        self._ensure_loaded()
        return self._raw_config.get("fizzsignalproc", {}).get("enabled", False)

    @property
    def fizzsignalproc_buffer_size(self) -> int:
        """Size of the DSP analysis buffer in samples."""
        self._ensure_loaded()
        return int(self._raw_config.get("fizzsignalproc", {}).get("buffer_size", 256))

    @property
    def fizzsignalproc_sample_rate(self) -> float:
        """Normalized sample rate for spectral analysis."""
        self._ensure_loaded()
        return float(self._raw_config.get("fizzsignalproc", {}).get("sample_rate", 1.0))
