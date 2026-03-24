"""FizzSynth Digital Audio Synthesizer Properties"""

from __future__ import annotations

from typing import Any


class SynthConfigMixin:
    """Configuration properties for the synth subsystem."""

    # ----------------------------------------------------------------
    # FizzSynth Digital Audio Synthesizer Properties
    # ----------------------------------------------------------------

    @property
    def synth_enabled(self) -> bool:
        """Whether the FizzSynth audio synthesizer is enabled."""
        self._ensure_loaded()
        return self._raw_config.get("synth", {}).get("enabled", False)

    @property
    def synth_bpm(self) -> float:
        """Composition tempo in beats per minute."""
        self._ensure_loaded()
        return float(self._raw_config.get("synth", {}).get("bpm", 120.0))

    @property
    def synth_reverb_wet(self) -> float:
        """Schroeder reverb wet/dry mix ratio (0.0 = dry, 1.0 = full reverb)."""
        self._ensure_loaded()
        return float(self._raw_config.get("synth", {}).get("reverb_wet", 0.2))

    @property
    def synth_filter_cutoff(self) -> float:
        """Low-pass filter cutoff frequency in Hz."""
        self._ensure_loaded()
        return float(self._raw_config.get("synth", {}).get("filter_cutoff", 8000.0))

    @property
    def synth_dashboard_width(self) -> int:
        """Width of the FizzSynth ASCII dashboard."""
        self._ensure_loaded()
        return self._raw_config.get("synth", {}).get("dashboard", {}).get("width", 60)

