"""FizzSearch configuration properties."""

from __future__ import annotations

from typing import Any


class FizzsearchConfigMixin:
    """Configuration properties for the fizzsearch subsystem."""

    @property
    def fizzsearch_enabled(self) -> bool:
        """Whether the FizzSearch full-text search engine is enabled."""
        self._ensure_loaded()
        return self._raw_config.get("fizzsearch", {}).get("enabled", False)

    @property
    def fizzsearch_refresh_interval(self) -> float:
        """Near-real-time refresh interval in seconds."""
        self._ensure_loaded()
        return float(self._raw_config.get("fizzsearch", {}).get("refresh_interval", 1.0))

    @property
    def fizzsearch_max_result_window(self) -> int:
        """Maximum offset+limit for standard pagination."""
        self._ensure_loaded()
        return int(self._raw_config.get("fizzsearch", {}).get("max_result_window", 10000))

    @property
    def fizzsearch_merge_policy(self) -> str:
        """Segment merge policy (tiered or log)."""
        self._ensure_loaded()
        return self._raw_config.get("fizzsearch", {}).get("merge_policy", "tiered")

    @property
    def fizzsearch_similarity(self) -> str:
        """Similarity model (BM25 or BM25F)."""
        self._ensure_loaded()
        return self._raw_config.get("fizzsearch", {}).get("similarity", "BM25")

    @property
    def fizzsearch_bm25_k1(self) -> float:
        """BM25 k1 term frequency saturation parameter."""
        self._ensure_loaded()
        return float(self._raw_config.get("fizzsearch", {}).get("bm25_k1", 1.2))

    @property
    def fizzsearch_bm25_b(self) -> float:
        """BM25 b document length normalization parameter."""
        self._ensure_loaded()
        return float(self._raw_config.get("fizzsearch", {}).get("bm25_b", 0.75))

    @property
    def fizzsearch_max_scroll_count(self) -> int:
        """Maximum concurrent scroll contexts."""
        self._ensure_loaded()
        return int(self._raw_config.get("fizzsearch", {}).get("max_scroll_count", 500))

    @property
    def fizzsearch_enable_highlight(self) -> bool:
        """Whether hit highlighting is enabled by default."""
        self._ensure_loaded()
        return self._raw_config.get("fizzsearch", {}).get("enable_highlight", True)

    @property
    def fizzsearch_index_evaluations(self) -> bool:
        """Whether to automatically index evaluation results."""
        self._ensure_loaded()
        return self._raw_config.get("fizzsearch", {}).get("index_evaluations", False)

    @property
    def fizzsearch_index_audit(self) -> bool:
        """Whether to automatically index audit trail entries."""
        self._ensure_loaded()
        return self._raw_config.get("fizzsearch", {}).get("index_audit", False)

    @property
    def fizzsearch_dashboard_width(self) -> int:
        """ASCII dashboard width."""
        self._ensure_loaded()
        return int(self._raw_config.get("fizzsearch", {}).get("dashboard", {}).get("width", 72))
