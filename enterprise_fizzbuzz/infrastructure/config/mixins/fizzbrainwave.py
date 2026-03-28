"""FizzBrainwave Brain-Computer Interface properties."""

from __future__ import annotations

from typing import Any


class FizzbrainwaveConfigMixin:
    """Configuration properties for the FizzBrainwave subsystem."""

    @property
    def fizzbrainwave_num_channels(self) -> int:
        """Number of EEG electrode channels."""
        self._ensure_loaded()
        return self._raw_config.get("fizzbrainwave", {}).get("num_channels", 8)

    @property
    def fizzbrainwave_sample_rate(self) -> int:
        """EEG sampling rate in Hz."""
        self._ensure_loaded()
        return self._raw_config.get("fizzbrainwave", {}).get("sample_rate", 256)

    @property
    def fizzbrainwave_snr_threshold(self) -> float:
        """Minimum signal-to-noise ratio in dB."""
        self._ensure_loaded()
        return self._raw_config.get("fizzbrainwave", {}).get("snr_threshold", 3.0)

    @property
    def fizzbrainwave_artifact_max_rate(self) -> float:
        """Maximum artifact rejection rate before failure."""
        self._ensure_loaded()
        return self._raw_config.get("fizzbrainwave", {}).get("artifact_max_rate", 0.5)

    @property
    def fizzbrainwave_confidence_threshold(self) -> float:
        """Minimum confidence for neural decoding."""
        self._ensure_loaded()
        return self._raw_config.get("fizzbrainwave", {}).get("confidence_threshold", 0.25)

    @property
    def fizzbrainwave_dashboard_width(self) -> int:
        """Width of the FizzBrainwave ASCII dashboard."""
        self._ensure_loaded()
        return self._raw_config.get("fizzbrainwave", {}).get("dashboard_width", 60)
