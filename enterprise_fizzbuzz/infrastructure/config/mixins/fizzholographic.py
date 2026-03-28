"""FizzHolographic Holographic Data Storage properties."""

from __future__ import annotations

from typing import Any


class FizzholographicConfigMixin:
    """Configuration properties for the FizzHolographic subsystem."""

    @property
    def fizzholographic_m_number(self) -> float:
        """M/# of the photorefractive crystal."""
        self._ensure_loaded()
        return self._raw_config.get("fizzholographic", {}).get("m_number", 5.0)

    @property
    def fizzholographic_max_pages(self) -> int:
        """Maximum number of holographic pages in the crystal."""
        self._ensure_loaded()
        return self._raw_config.get("fizzholographic", {}).get("max_pages", 1000)

    @property
    def fizzholographic_page_width(self) -> int:
        """Holographic page width in pixels."""
        self._ensure_loaded()
        return self._raw_config.get("fizzholographic", {}).get("page_width", 64)

    @property
    def fizzholographic_page_height(self) -> int:
        """Holographic page height in pixels."""
        self._ensure_loaded()
        return self._raw_config.get("fizzholographic", {}).get("page_height", 64)

    @property
    def fizzholographic_dashboard_width(self) -> int:
        """Width of the FizzHolographic ASCII dashboard."""
        self._ensure_loaded()
        return self._raw_config.get("fizzholographic", {}).get("dashboard_width", 60)
