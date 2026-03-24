"""Feature descriptor for the Recommendation Engine."""

from __future__ import annotations

from typing import Any, Optional

from enterprise_fizzbuzz.infrastructure.features._registry import FeatureDescriptor


class RecommendationsFeature(FeatureDescriptor):
    name = "recommendations"
    description = "Integer affinity analytics with collaborative filtering, content-based, and hybrid blend"
    middleware_priority = 59
    cli_flags = [
        ("--recommend", {"action": "store_true",
                         "help": "Enable the Recommendation Engine: suggest numbers you might enjoy evaluating next"}),
        ("--recommend-for", {"type": int, "metavar": "N", "default": None,
                             "help": "Get recommendations similar to a specific number (e.g. --recommend-for 15)"}),
        ("--recommend-dashboard", {"action": "store_true",
                                   "help": "Display the Recommendation Engine ASCII dashboard after execution"}),
    ]

    def is_enabled(self, args: Any) -> bool:
        return any([
            getattr(args, "recommend", False),
            getattr(args, "recommend_for", None) is not None,
            getattr(args, "recommend_dashboard", False),
        ])

    def create(self, config: Any, args: Any, event_bus: Any = None) -> tuple:
        from enterprise_fizzbuzz.infrastructure.recommendations import (
            RecommendationEngine,
        )

        engine = RecommendationEngine(
            collaborative_weight=config.recommendation_collaborative_weight,
            content_weight=config.recommendation_content_weight,
            serendipity_factor=config.recommendation_serendipity_factor,
            num_recommendations=config.recommendation_num_recommendations,
            min_evaluations=config.recommendation_min_evaluations,
            max_similar_users=config.recommendation_max_similar_users,
            popular_items_fallback_size=config.recommendation_popular_items_fallback_size,
            seed=config.recommendation_seed,
        )

        return engine, None

    def render(self, middleware: Any, args: Any) -> Optional[str]:
        if not getattr(args, "recommend_dashboard", False):
            return None
        if middleware is None:
            return None
        from enterprise_fizzbuzz.infrastructure.recommendations import RecommendationDashboard
        return RecommendationDashboard.render(
            middleware,
            recommendations=None,
            target_number=getattr(args, "recommend_for", None),
            width=60,
        )
