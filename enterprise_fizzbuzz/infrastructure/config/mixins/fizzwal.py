"""FizzWAL — Write-Ahead Intent Log properties"""

from __future__ import annotations

from typing import Any


class FizzwalConfigMixin:
    """Configuration properties for the fizzwal subsystem."""

    # ------------------------------------------------------------------
    # FizzWAL — Write-Ahead Intent Log properties
    # ------------------------------------------------------------------

    @property
    def fizzwal_enabled(self) -> bool:
        """Whether the FizzWAL Write-Ahead Intent Log subsystem is active."""
        self._ensure_loaded()
        return self._raw_config.get("fizzwal", {}).get("enabled", False)

    @property
    def fizzwal_mode(self) -> str:
        """Execution mode: optimistic, pessimistic, or speculative."""
        self._ensure_loaded()
        return self._raw_config.get("fizzwal", {}).get("mode", "optimistic")

    @property
    def fizzwal_checkpoint_interval(self) -> int:
        """Number of log records between automatic fuzzy checkpoints."""
        self._ensure_loaded()
        return self._raw_config.get("fizzwal", {}).get("checkpoint_interval", 100)

    @property
    def fizzwal_crash_recovery_on_startup(self) -> bool:
        """Whether to run ARIES 3-phase recovery on startup."""
        self._ensure_loaded()
        return self._raw_config.get("fizzwal", {}).get("crash_recovery_on_startup", False)

    @property
    def fizzwal_dashboard_width(self) -> int:
        """Dashboard width for the FizzWAL dashboard."""
        self._ensure_loaded()
        return self._raw_config.get("fizzwal", {}).get("dashboard", {}).get("width", 60)

