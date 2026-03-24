"""FizzCRDT — Conflict-Free Replicated Data Types properties"""

from __future__ import annotations

from typing import Any


class CrdtConfigMixin:
    """Configuration properties for the crdt subsystem."""

    # ------------------------------------------------------------------
    # FizzCRDT — Conflict-Free Replicated Data Types properties
    # ------------------------------------------------------------------

    @property
    def crdt_enabled(self) -> bool:
        """Whether the FizzCRDT subsystem is active."""
        self._ensure_loaded()
        return self._raw_config.get("crdt", {}).get("enabled", False)

    @property
    def crdt_replica_count(self) -> int:
        """Number of simulated replicas for CRDT replication."""
        self._ensure_loaded()
        return self._raw_config.get("crdt", {}).get("replica_count", 3)

    @property
    def crdt_anti_entropy_interval(self) -> int:
        """Number of evaluations between anti-entropy rounds."""
        self._ensure_loaded()
        return self._raw_config.get("crdt", {}).get("anti_entropy_interval", 1)

    @property
    def crdt_dashboard_width(self) -> int:
        """Dashboard width for the FizzCRDT dashboard."""
        self._ensure_loaded()
        return self._raw_config.get("crdt", {}).get("dashboard", {}).get("width", 60)

