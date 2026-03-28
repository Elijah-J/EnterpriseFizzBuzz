"""FizzAVX — SIMD/AVX Instruction Engine properties"""

from __future__ import annotations


class FizzavxConfigMixin:
    """Configuration properties for the FizzAVX subsystem."""

    @property
    def fizzavx_enabled(self) -> bool:
        """Whether the FizzAVX SIMD instruction engine is active."""
        self._ensure_loaded()
        return self._raw_config.get("fizzavx", {}).get("enabled", False)

    @property
    def fizzavx_vector_width(self) -> int:
        """Vector width in bits (256 for AVX2, 512 for AVX-512)."""
        self._ensure_loaded()
        return self._raw_config.get("fizzavx", {}).get("vector_width", 256)

    @property
    def fizzavx_dashboard_width(self) -> int:
        """Dashboard width for the FizzAVX ASCII dashboard."""
        self._ensure_loaded()
        return self._raw_config.get("fizzavx", {}).get("dashboard", {}).get("width", 72)
