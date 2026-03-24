"""Database Migration Framework configuration properties"""

from __future__ import annotations

from typing import Any


class MigrationsConfigMixin:
    """Configuration properties for the migrations subsystem."""

    # ----------------------------------------------------------------
    # Database Migration Framework configuration properties
    # ----------------------------------------------------------------

    @property
    def migrations_enabled(self) -> bool:
        """Whether the Database Migration Framework is enabled."""
        self._ensure_loaded()
        return self._raw_config.get("migrations", {}).get("enabled", False)

    @property
    def migrations_auto_apply(self) -> bool:
        """Whether to automatically apply pending migrations on startup."""
        self._ensure_loaded()
        return self._raw_config.get("migrations", {}).get("auto_apply", False)

    @property
    def migrations_seed_range_start(self) -> int:
        """Start of the range for FizzBuzz seed data generation."""
        self._ensure_loaded()
        return self._raw_config.get("migrations", {}).get("seed_range_start", 1)

    @property
    def migrations_seed_range_end(self) -> int:
        """End of the range for FizzBuzz seed data generation."""
        self._ensure_loaded()
        return self._raw_config.get("migrations", {}).get("seed_range_end", 50)

    @property
    def migrations_log_fake_sql(self) -> bool:
        """Whether to log fake SQL statements during schema operations."""
        self._ensure_loaded()
        return self._raw_config.get("migrations", {}).get("log_fake_sql", True)

    @property
    def migrations_visualize_schema(self) -> bool:
        """Whether to render ASCII ER diagrams after migration operations."""
        self._ensure_loaded()
        return self._raw_config.get("migrations", {}).get("visualize_schema", True)

