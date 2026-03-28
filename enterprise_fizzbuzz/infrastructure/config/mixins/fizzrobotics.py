"""FizzRobotics Robot Motion Planning properties."""

from __future__ import annotations

from typing import Any


class FizzroboticsConfigMixin:
    """Configuration properties for the FizzRobotics subsystem."""

    @property
    def fizzrobotics_enabled(self) -> bool:
        """Whether the FizzRobotics motion planning engine is enabled."""
        self._ensure_loaded()
        return self._raw_config.get("fizzrobotics", {}).get("enabled", False)

    @property
    def fizzrobotics_num_links(self) -> int:
        """Number of links in the robotic manipulator."""
        self._ensure_loaded()
        return int(self._raw_config.get("fizzrobotics", {}).get("num_links", 3))

    @property
    def fizzrobotics_link_length(self) -> float:
        """Length of each manipulator link in meters."""
        self._ensure_loaded()
        return float(self._raw_config.get("fizzrobotics", {}).get("link_length", 1.0))

    @property
    def fizzrobotics_seed(self) -> int | None:
        """Random seed for RRT planner reproducibility."""
        self._ensure_loaded()
        return self._raw_config.get("fizzrobotics", {}).get("seed", None)
