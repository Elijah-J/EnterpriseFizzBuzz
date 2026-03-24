"""Migration configuration properties."""

from __future__ import annotations

from typing import Any


class MigrationConfigMixin:
    """Configuration properties for the migration subsystem."""

    # ----------------------------------------------------------------
    # Process Migration (FizzMigrate)
    # ----------------------------------------------------------------

    @property
    def migration_enabled(self) -> bool:
        """Whether live process migration is enabled."""
        self._ensure_loaded()
        return self._raw_config.get("migration", {}).get("enabled", False)

    @property
    def migration_strategy(self) -> str:
        """Default migration strategy (pre-copy, post-copy, stop-and-copy)."""
        self._ensure_loaded()
        return self._raw_config.get("migration", {}).get("strategy", "pre-copy")

    @property
    def migration_checkpoint_interval(self) -> int:
        """Number of evaluations between automatic checkpoints."""
        self._ensure_loaded()
        return self._raw_config.get("migration", {}).get("checkpoint_interval", 10)

    @property
    def migration_max_rounds(self) -> int:
        """Maximum pre-copy rounds before convergence failure."""
        self._ensure_loaded()
        return self._raw_config.get("migration", {}).get("max_rounds", 10)

    @property
    def migration_convergence_threshold(self) -> float:
        """Dirty ratio below which pre-copy proceeds to cutover."""
        self._ensure_loaded()
        return self._raw_config.get("migration", {}).get("convergence_threshold", 0.1)

    @property
    def migration_dashboard_width(self) -> int:
        """Width of the migration ASCII dashboard."""
        self._ensure_loaded()
        return self._raw_config.get("migration", {}).get("dashboard", {}).get("width", 72)

