"""FizzIR SSA Intermediate Representation Properties"""

from __future__ import annotations

from typing import Any


class IrConfigMixin:
    """Configuration properties for the ir subsystem."""

    # ------------------------------------------------------------------
    # FizzIR SSA Intermediate Representation Properties
    # ------------------------------------------------------------------

    @property
    def ir_enabled(self) -> bool:
        """Whether the FizzIR SSA IR subsystem is enabled."""
        self._ensure_loaded()
        return self._raw_config.get("ir", {}).get("enabled", False)

    @property
    def ir_optimize(self) -> bool:
        """Whether to run the 8-pass optimization pipeline on generated IR."""
        self._ensure_loaded()
        return self._raw_config.get("ir", {}).get("optimize", True)

    @property
    def ir_print(self) -> bool:
        """Whether to print the LLVM-style textual IR to stdout."""
        self._ensure_loaded()
        return self._raw_config.get("ir", {}).get("print", False)

    @property
    def ir_dashboard_width(self) -> int:
        """Width of the FizzIR ASCII dashboard."""
        self._ensure_loaded()
        return self._raw_config.get("ir", {}).get("dashboard", {}).get("width", 60)

