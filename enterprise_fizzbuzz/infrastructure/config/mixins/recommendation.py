"""Recommendation configuration properties."""

from __future__ import annotations

from typing import Any


class RecommendationConfigMixin:
    """Configuration properties for the recommendation subsystem."""

    # ------------------------------------------------------------------

    @property
    def recommendation_enabled(self) -> bool:
        self._ensure_loaded()
        return self._raw_config.get("recommendation", {}).get("enabled", False)

    @property
    def recommendation_collaborative_weight(self) -> float:
        self._ensure_loaded()
        return self._raw_config.get("recommendation", {}).get("collaborative_weight", 0.6)

    @property
    def recommendation_content_weight(self) -> float:
        self._ensure_loaded()
        return self._raw_config.get("recommendation", {}).get("content_weight", 0.4)

    @property
    def recommendation_serendipity_factor(self) -> float:
        self._ensure_loaded()
        return self._raw_config.get("recommendation", {}).get("serendipity_factor", 0.1)

    @property
    def recommendation_num_recommendations(self) -> int:
        self._ensure_loaded()
        return self._raw_config.get("recommendation", {}).get("num_recommendations", 5)

    @property
    def recommendation_min_evaluations(self) -> int:
        self._ensure_loaded()
        return self._raw_config.get("recommendation", {}).get("min_evaluations_for_personalization", 3)

    @property
    def recommendation_max_similar_users(self) -> int:
        self._ensure_loaded()
        return self._raw_config.get("recommendation", {}).get("max_similar_users", 10)

    @property
    def recommendation_popular_items_fallback_size(self) -> int:
        self._ensure_loaded()
        return self._raw_config.get("recommendation", {}).get("popular_items_fallback_size", 10)

    @property
    def recommendation_seed(self) -> int | None:
        self._ensure_loaded()
        return self._raw_config.get("recommendation", {}).get("seed", None)

    @property
    def recommendation_dashboard_width(self) -> int:
        self._ensure_loaded()
        return self._raw_config.get("recommendation", {}).get("dashboard", {}).get("width", 60)

    @property
    def recommendation_dashboard_show_feature_vectors(self) -> bool:
        self._ensure_loaded()
        return self._raw_config.get("recommendation", {}).get("dashboard", {}).get("show_feature_vectors", True)

    @property
    def recommendation_dashboard_show_user_profiles(self) -> bool:
        self._ensure_loaded()
        return self._raw_config.get("recommendation", {}).get("dashboard", {}).get("show_user_profiles", True)

    @property
    def recommendation_dashboard_show_similarity_matrix(self) -> bool:
        self._ensure_loaded()
        return self._raw_config.get("recommendation", {}).get("dashboard", {}).get("show_similarity_matrix", True)

