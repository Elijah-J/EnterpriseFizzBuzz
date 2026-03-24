"""── Self-Modifying Code properties ────────────────────────"""

from __future__ import annotations

from typing import Any


class KnowledgeGraphConfigMixin:
    """Configuration properties for the knowledge graph subsystem."""

    @property
    def knowledge_graph_enabled(self) -> bool:
        self._ensure_loaded()
        return self._raw_config.get("knowledge_graph", {}).get("enabled", False)

    @property
    def knowledge_graph_max_inference_iterations(self) -> int:
        self._ensure_loaded()
        return self._raw_config.get("knowledge_graph", {}).get("max_inference_iterations", 100)

    @property
    def knowledge_graph_domain_range_start(self) -> int:
        self._ensure_loaded()
        return self._raw_config.get("knowledge_graph", {}).get("domain_range_start", 1)

    @property
    def knowledge_graph_domain_range_end(self) -> int:
        self._ensure_loaded()
        return self._raw_config.get("knowledge_graph", {}).get("domain_range_end", 100)

    @property
    def knowledge_graph_enable_owl_reasoning(self) -> bool:
        self._ensure_loaded()
        return self._raw_config.get("knowledge_graph", {}).get("enable_owl_reasoning", True)

    @property
    def knowledge_graph_enable_visualization(self) -> bool:
        self._ensure_loaded()
        return self._raw_config.get("knowledge_graph", {}).get("enable_visualization", True)

    @property
    def knowledge_graph_dashboard_width(self) -> int:
        self._ensure_loaded()
        return self._raw_config.get("knowledge_graph", {}).get("dashboard", {}).get("width", 60)

    @property
    def knowledge_graph_dashboard_show_class_hierarchy(self) -> bool:
        self._ensure_loaded()
        return self._raw_config.get("knowledge_graph", {}).get("dashboard", {}).get("show_class_hierarchy", True)

    @property
    def knowledge_graph_dashboard_show_triple_stats(self) -> bool:
        self._ensure_loaded()
        return self._raw_config.get("knowledge_graph", {}).get("dashboard", {}).get("show_triple_stats", True)

    @property
    def knowledge_graph_dashboard_show_inference_stats(self) -> bool:
        self._ensure_loaded()
        return self._raw_config.get("knowledge_graph", {}).get("dashboard", {}).get("show_inference_stats", True)

    # ── Self-Modifying Code properties ────────────────────────

