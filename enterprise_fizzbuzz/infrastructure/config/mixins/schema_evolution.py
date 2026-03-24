"""Schema Evolution configuration properties."""

from __future__ import annotations

from typing import Any


class SchemaEvolutionConfigMixin:
    """Configuration properties for the schema evolution subsystem."""

    # ----------------------------------------------------------------
    # FizzSchema — Consensus-Based Schema Evolution
    # ----------------------------------------------------------------

    @property
    def schema_evolution_enabled(self) -> bool:
        """Whether the FizzSchema schema evolution subsystem is active."""
        self._ensure_loaded()
        return self._raw_config.get("schema_evolution", {}).get("enabled", False)

    @property
    def schema_evolution_compatibility_mode(self) -> str:
        """Active compatibility mode for schema evolution (BACKWARD/FORWARD/FULL/NONE)."""
        self._ensure_loaded()
        return self._raw_config.get("schema_evolution", {}).get("compatibility_mode", "BACKWARD")

    @property
    def schema_evolution_consensus_nodes(self) -> int:
        """Number of Paxos consensus nodes for schema approval."""
        self._ensure_loaded()
        return self._raw_config.get("schema_evolution", {}).get("consensus_nodes", 5)

    @property
    def schema_evolution_consensus_quorum(self) -> int:
        """Minimum approvals required for schema change consensus."""
        self._ensure_loaded()
        return self._raw_config.get("schema_evolution", {}).get("consensus_quorum", 3)

    @property
    def schema_evolution_dashboard_width(self) -> int:
        """Dashboard width for the FizzSchema dashboard."""
        self._ensure_loaded()
        return self._raw_config.get("schema_evolution", {}).get("dashboard", {}).get("width", 60)

