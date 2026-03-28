"""FizzAcoustics Acoustic Propagation Engine Properties"""

from __future__ import annotations

from typing import Any


class FizzacousticsConfigMixin:
    """Configuration properties for the FizzAcoustics subsystem."""

    @property
    def fizzacoustics_enabled(self) -> bool:
        """Whether the FizzAcoustics acoustic propagation engine is enabled."""
        self._ensure_loaded()
        return self._raw_config.get("fizzacoustics", {}).get("enabled", False)

    @property
    def fizzacoustics_temperature_celsius(self) -> float:
        """Ambient temperature for sound speed computation."""
        self._ensure_loaded()
        return float(self._raw_config.get("fizzacoustics", {}).get("temperature_celsius", 20.0))

    @property
    def fizzacoustics_room_length_m(self) -> float:
        """Room length in meters for reverberation computation."""
        self._ensure_loaded()
        return float(self._raw_config.get("fizzacoustics", {}).get("room_length_m", 10.0))

    @property
    def fizzacoustics_room_width_m(self) -> float:
        """Room width in meters."""
        self._ensure_loaded()
        return float(self._raw_config.get("fizzacoustics", {}).get("room_width_m", 8.0))

    @property
    def fizzacoustics_room_height_m(self) -> float:
        """Room height in meters."""
        self._ensure_loaded()
        return float(self._raw_config.get("fizzacoustics", {}).get("room_height_m", 3.0))
