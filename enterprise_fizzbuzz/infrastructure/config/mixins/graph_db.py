"""Graph Database properties"""

from __future__ import annotations

from typing import Any


class GraphDbConfigMixin:
    """Configuration properties for the graph db subsystem."""

    # ----------------------------------------------------------------
    # Graph Database properties
    # ----------------------------------------------------------------

    @property
    def graph_db_enabled(self) -> bool:
        """Whether the graph database subsystem is enabled."""
        self._ensure_loaded()
        return self._raw_config.get("graph_db", {}).get("enabled", False)

    @property
    def graph_db_auto_populate(self) -> bool:
        """Whether to auto-populate the graph on startup."""
        self._ensure_loaded()
        return self._raw_config.get("graph_db", {}).get("auto_populate", True)

    @property
    def graph_db_max_visualization_nodes(self) -> int:
        """Maximum number of nodes to display in ASCII visualization."""
        self._ensure_loaded()
        return self._raw_config.get("graph_db", {}).get("max_visualization_nodes", 20)

    @property
    def graph_db_community_max_iterations(self) -> int:
        """Maximum iterations for community detection label propagation."""
        self._ensure_loaded()
        return self._raw_config.get("graph_db", {}).get("community_max_iterations", 20)

    @property
    def graph_db_dashboard_width(self) -> int:
        """ASCII dashboard width for the Graph Database dashboard."""
        self._ensure_loaded()
        return self._raw_config.get("graph_db", {}).get("dashboard", {}).get("width", 60)

