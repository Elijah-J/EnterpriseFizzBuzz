"""Model Check configuration properties."""

from __future__ import annotations

from typing import Any


class ModelCheckConfigMixin:
    """Configuration properties for the model check subsystem."""

    # ----------------------------------------------------------------
    # FizzCheck — Formal Model Checking
    # ----------------------------------------------------------------

    @property
    def model_check_enabled(self) -> bool:
        """Whether the FizzCheck model checking subsystem is active."""
        self._ensure_loaded()
        return self._raw_config.get("model_check", {}).get("enabled", False)

    @property
    def model_check_max_states(self) -> int:
        """Maximum number of states to explore before raising StateSpaceError."""
        self._ensure_loaded()
        return self._raw_config.get("model_check", {}).get("max_states", 100000)

    @property
    def model_check_dashboard_width(self) -> int:
        """Dashboard width for the FizzCheck model checking dashboard."""
        self._ensure_loaded()
        return self._raw_config.get("model_check", {}).get("dashboard", {}).get("width", 60)

