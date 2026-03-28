"""FizzArchaeology2 Digital Archaeology v2 properties."""

from __future__ import annotations

from typing import Any


class Fizzarchaeology2ConfigMixin:
    """Configuration properties for the FizzArchaeology2 subsystem."""

    @property
    def fizzarchaeology2_enabled(self) -> bool:
        """Whether the FizzArchaeology2 engine is enabled."""
        self._ensure_loaded()
        return self._raw_config.get("fizzarchaeology2", {}).get("enabled", False)

    @property
    def fizzarchaeology2_grid_rows(self) -> int:
        """Number of rows in the excavation grid."""
        self._ensure_loaded()
        return int(self._raw_config.get("fizzarchaeology2", {}).get("grid_rows", 8))

    @property
    def fizzarchaeology2_grid_cols(self) -> int:
        """Number of columns in the excavation grid."""
        self._ensure_loaded()
        return int(self._raw_config.get("fizzarchaeology2", {}).get("grid_cols", 8))

    @property
    def fizzarchaeology2_seed(self) -> int | None:
        """Random seed for dating simulation reproducibility."""
        self._ensure_loaded()
        return self._raw_config.get("fizzarchaeology2", {}).get("seed", None)
