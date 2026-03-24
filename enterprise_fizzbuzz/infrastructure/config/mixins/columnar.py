"""Columnar configuration properties."""

from __future__ import annotations

from typing import Any


class ColumnarConfigMixin:
    """Configuration properties for the columnar subsystem."""

    # ----------------------------------------------------------------
    # FizzColumn — Columnar Storage Engine
    # ----------------------------------------------------------------

    @property
    def columnar_enabled(self) -> bool:
        """Whether the FizzColumn columnar storage engine is active."""
        self._ensure_loaded()
        return self._raw_config.get("columnar_storage", {}).get("enabled", False)

    @property
    def columnar_row_group_size(self) -> int:
        """Maximum rows per row group before automatic sealing."""
        self._ensure_loaded()
        return self._raw_config.get("columnar_storage", {}).get("row_group_size", 1024)

    @property
    def columnar_encoding_sample_size(self) -> int:
        """Number of values to sample when auto-selecting column encoding."""
        self._ensure_loaded()
        return self._raw_config.get("columnar_storage", {}).get("encoding_sample_size", 1024)

    @property
    def columnar_dictionary_cardinality_limit(self) -> int:
        """Maximum distinct values before dictionary encoding is rejected."""
        self._ensure_loaded()
        return self._raw_config.get("columnar_storage", {}).get("dictionary_cardinality_limit", 256)

    @property
    def columnar_dashboard_width(self) -> int:
        """Dashboard width for the FizzColumn dashboard."""
        self._ensure_loaded()
        return self._raw_config.get("columnar_storage", {}).get("dashboard", {}).get("width", 60)

