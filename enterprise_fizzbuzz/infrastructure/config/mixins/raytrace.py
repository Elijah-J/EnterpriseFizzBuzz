"""FizzTrace Ray Tracer properties"""

from __future__ import annotations

from typing import Any


class RaytraceConfigMixin:
    """Configuration properties for the raytrace subsystem."""

    # ------------------------------------------------------------------
    # FizzTrace Ray Tracer properties
    # ------------------------------------------------------------------

    @property
    def raytrace_width(self) -> int:
        """Render output width in pixels."""
        self._ensure_loaded()
        return self._raw_config.get("raytrace", {}).get("width", 320)

    @property
    def raytrace_height(self) -> int:
        """Render output height in pixels."""
        self._ensure_loaded()
        return self._raw_config.get("raytrace", {}).get("height", 240)

    @property
    def raytrace_samples(self) -> int:
        """Samples per pixel for Monte Carlo path tracing."""
        self._ensure_loaded()
        return self._raw_config.get("raytrace", {}).get("samples", 10)

    @property
    def raytrace_max_depth(self) -> int:
        """Maximum ray bounce depth."""
        self._ensure_loaded()
        return self._raw_config.get("raytrace", {}).get("max_depth", 50)

    @property
    def raytrace_dashboard_width(self) -> int:
        """Width of the FizzTrace ASCII dashboard."""
        self._ensure_loaded()
        return self._raw_config.get("raytrace", {}).get("dashboard", {}).get("width", 60)

