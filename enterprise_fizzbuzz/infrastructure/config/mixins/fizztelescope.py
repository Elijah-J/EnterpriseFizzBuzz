"""FizzTelescope Telescope Control System Properties"""

from __future__ import annotations

from typing import Any


class FizztelescopeConfigMixin:
    """Configuration properties for the FizzTelescope subsystem."""

    @property
    def fizztelescope_enabled(self) -> bool:
        """Whether the FizzTelescope telescope control system is enabled."""
        self._ensure_loaded()
        return self._raw_config.get("fizztelescope", {}).get("enabled", False)

    @property
    def fizztelescope_mount_type(self) -> str:
        """Telescope mount type: EQUATORIAL or ALT_AZIMUTH."""
        self._ensure_loaded()
        return str(self._raw_config.get("fizztelescope", {}).get("mount_type", "EQUATORIAL"))

    @property
    def fizztelescope_latitude_deg(self) -> float:
        """Observatory latitude in degrees for tracking computations."""
        self._ensure_loaded()
        return float(self._raw_config.get("fizztelescope", {}).get("latitude_deg", 45.0))

    @property
    def fizztelescope_guide_camera_fov_arcmin(self) -> float:
        """Guide camera field of view in arcminutes."""
        self._ensure_loaded()
        return float(self._raw_config.get("fizztelescope", {}).get("guide_camera_fov_arcmin", 10.0))
