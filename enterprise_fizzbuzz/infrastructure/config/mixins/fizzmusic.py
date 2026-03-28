"""FizzMusic Music Theory Engine Properties"""

from __future__ import annotations

from typing import Any


class FizzMusicConfigMixin:
    """Configuration properties for the FizzMusic subsystem."""

    # ----------------------------------------------------------------
    # FizzMusic Music Theory Properties
    # ----------------------------------------------------------------

    @property
    def fizzmusic_enabled(self) -> bool:
        """Whether the FizzMusic music theory engine is enabled."""
        self._ensure_loaded()
        return self._raw_config.get("fizzmusic", {}).get("enabled", False)

    @property
    def fizzmusic_key_confidence_threshold(self) -> float:
        """Minimum correlation for key detection acceptance."""
        self._ensure_loaded()
        return float(self._raw_config.get("fizzmusic", {}).get("key_confidence_threshold", 0.3))

    @property
    def fizzmusic_default_scale(self) -> str:
        """Default scale type for analysis."""
        self._ensure_loaded()
        return self._raw_config.get("fizzmusic", {}).get("default_scale", "major")

    @property
    def fizzmusic_ticks_per_beat(self) -> int:
        """MIDI ticks per quarter note beat."""
        self._ensure_loaded()
        return int(self._raw_config.get("fizzmusic", {}).get("ticks_per_beat", 480))
