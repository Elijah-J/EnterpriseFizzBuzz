"""Typeset configuration properties."""

from __future__ import annotations

from typing import Any


class TypesetConfigMixin:
    """Configuration properties for the typeset subsystem."""

    # ------------------------------------------------------------------
    # FizzPrint Typesetting Engine
    # ------------------------------------------------------------------

    @property
    def typeset_enabled(self) -> bool:
        """Whether the FizzPrint typesetting engine is active."""
        self._ensure_loaded()
        return self._raw_config.get("typeset", {}).get("enabled", False)

    @property
    def typeset_output_path(self) -> Optional[str]:
        """Path for PostScript output file."""
        self._ensure_loaded()
        return self._raw_config.get("typeset", {}).get("output_path", None)

    @property
    def typeset_font_name(self) -> str:
        """Font family for typeset output."""
        self._ensure_loaded()
        return self._raw_config.get("typeset", {}).get("font_name", "Courier")

    @property
    def typeset_font_size(self) -> float:
        """Font size in points for typeset output."""
        self._ensure_loaded()
        return float(self._raw_config.get("typeset", {}).get("font_size", 10.0))

    @property
    def typeset_line_width(self) -> float:
        """Line width in points for the Knuth-Plass breaker."""
        self._ensure_loaded()
        return float(self._raw_config.get("typeset", {}).get("line_width", 468.0))

    @property
    def typeset_page_width(self) -> float:
        """Page width in PostScript points."""
        self._ensure_loaded()
        return float(self._raw_config.get("typeset", {}).get("page_width", 612.0))

    @property
    def typeset_page_height(self) -> float:
        """Page height in PostScript points."""
        self._ensure_loaded()
        return float(self._raw_config.get("typeset", {}).get("page_height", 792.0))

    @property
    def typeset_dashboard_width(self) -> int:
        """ASCII dashboard width for the FizzPrint dashboard."""
        self._ensure_loaded()
        return self._raw_config.get("typeset", {}).get("dashboard", {}).get("width", 72)

