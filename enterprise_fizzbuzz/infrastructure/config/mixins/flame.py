"""FizzFlame — Flame Graph Generator properties"""

from __future__ import annotations

from typing import Any


class FlameConfigMixin:
    """Configuration properties for the flame subsystem."""

    # ------------------------------------------------------------------
    # FizzFlame — Flame Graph Generator properties
    # ------------------------------------------------------------------

    @property
    def flame_enabled(self) -> bool:
        """Whether the FizzFlame flame graph subsystem is active."""
        self._ensure_loaded()
        return self._raw_config.get("flame", {}).get("enabled", False)

    @property
    def flame_output(self) -> str:
        """Default output path for flame graph SVG files."""
        self._ensure_loaded()
        return self._raw_config.get("flame", {}).get("output", "flamegraph.svg")

    @property
    def flame_width(self) -> int:
        """SVG width for flame graph rendering in pixels."""
        self._ensure_loaded()
        return self._raw_config.get("flame", {}).get("width", 1200)

    @property
    def flame_frame_height(self) -> int:
        """Height of each frame in the flame graph in pixels."""
        self._ensure_loaded()
        return self._raw_config.get("flame", {}).get("frame_height", 18)

    @property
    def flame_dashboard_width(self) -> int:
        """Width of the ASCII flame graph dashboard."""
        self._ensure_loaded()
        return self._raw_config.get("flame", {}).get("dashboard", {}).get("width", 72)

