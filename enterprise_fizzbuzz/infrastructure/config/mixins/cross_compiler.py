"""Cross-Compiler properties"""

from __future__ import annotations

from typing import Any


class CrossCompilerConfigMixin:
    """Configuration properties for the cross compiler subsystem."""

    # ------------------------------------------------------------------
    # Cross-Compiler properties
    # ------------------------------------------------------------------
    @property
    def cross_compiler_enabled(self) -> bool:
        self._ensure_loaded()
        return self._raw_config.get("cross_compiler", {}).get("enabled", False)

    @property
    def cross_compiler_verify_round_trip(self) -> bool:
        self._ensure_loaded()
        return self._raw_config.get("cross_compiler", {}).get("verify_round_trip", True)

    @property
    def cross_compiler_verification_range_end(self) -> int:
        self._ensure_loaded()
        return self._raw_config.get("cross_compiler", {}).get("verification_range_end", 100)

    @property
    def cross_compiler_emit_comments(self) -> bool:
        self._ensure_loaded()
        return self._raw_config.get("cross_compiler", {}).get("emit_comments", True)

    @property
    def cross_compiler_dashboard_width(self) -> int:
        self._ensure_loaded()
        return self._raw_config.get("cross_compiler", {}).get("dashboard", {}).get("width", 60)

    @property
    def cross_compiler_dashboard_show_ir(self) -> bool:
        self._ensure_loaded()
        return self._raw_config.get("cross_compiler", {}).get("dashboard", {}).get("show_ir", False)

