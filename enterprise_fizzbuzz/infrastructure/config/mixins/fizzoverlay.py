"""Fizzoverlay configuration properties."""

from __future__ import annotations

from typing import Any


class FizzoverlayConfigMixin:
    """Configuration properties for the fizzoverlay subsystem."""

    @property
    def fizzoverlay_enabled(self) -> bool:
        """Whether the FizzOverlay union filesystem is enabled."""
        self._ensure_loaded()
        return self._raw_config.get("fizzoverlay", {}).get("enabled", False)

    @property
    def fizzoverlay_max_layers(self) -> int:
        """Maximum layers in the content-addressable store."""
        self._ensure_loaded()
        return int(self._raw_config.get("fizzoverlay", {}).get("max_layers", 128))

    @property
    def fizzoverlay_layer_cache_size(self) -> int:
        """Maximum cached unpacked layers (LRU)."""
        self._ensure_loaded()
        return int(self._raw_config.get("fizzoverlay", {}).get("layer_cache_size", 64))

    @property
    def fizzoverlay_default_compression(self) -> str:
        """Default compression algorithm for layer archives."""
        self._ensure_loaded()
        return self._raw_config.get("fizzoverlay", {}).get("default_compression", "gzip")

    @property
    def fizzoverlay_dashboard_width(self) -> int:
        """Width of the FizzOverlay ASCII dashboard."""
        self._ensure_loaded()
        return int(self._raw_config.get("fizzoverlay", {}).get("dashboard", {}).get("width", 72))

    # ── FizzCNI: Container Network Interface Plugin System ───

