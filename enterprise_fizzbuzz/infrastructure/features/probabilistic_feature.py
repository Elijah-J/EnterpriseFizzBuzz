"""Feature descriptor for the FizzBloom probabilistic data structures subsystem."""

from __future__ import annotations

from typing import Any, Optional

from enterprise_fizzbuzz.infrastructure.features._registry import FeatureDescriptor


class ProbabilisticFeature(FeatureDescriptor):
    name = "probabilistic"
    description = "Probabilistic data structures for approximate FizzBuzz analytics (Bloom filter, Count-Min Sketch, HyperLogLog, T-Digest)"
    middleware_priority = 57
    cli_flags = [
        ("--probabilistic", {"action": "store_true", "default": False,
                             "help": "Enable FizzBloom: probabilistic data structures for approximate FizzBuzz analytics "
                                     "(Bloom filter, Count-Min Sketch, HyperLogLog, T-Digest)"}),
        ("--probabilistic-dashboard", {"action": "store_true", "default": False,
                                       "help": "Display the FizzBloom ASCII dashboard with Bloom density, CMS top-k, HLL cardinality, "
                                               "and T-Digest quantile estimates"}),
    ]

    def is_enabled(self, args: Any) -> bool:
        return getattr(args, "probabilistic", False) or getattr(args, "probabilistic_dashboard", False)

    def create(self, config: Any, args: Any, event_bus: Any = None) -> tuple:
        from enterprise_fizzbuzz.infrastructure.probabilistic import (
            ProbabilisticMiddleware,
            create_probabilistic_subsystem,
        )

        middleware, _, _, _, _ = create_probabilistic_subsystem(
            bloom_expected=config.probabilistic_bloom_expected_elements,
            bloom_fpr=config.probabilistic_bloom_false_positive_rate,
            cms_width=config.probabilistic_cms_width,
            cms_depth=config.probabilistic_cms_depth,
            hll_precision=config.probabilistic_hll_precision,
            tdigest_compression=config.probabilistic_tdigest_compression,
            event_bus=event_bus,
        )

        return middleware, middleware

    def render(self, middleware: Any, args: Any) -> Optional[str]:
        if middleware is None:
            return None
        if not getattr(args, "probabilistic_dashboard", False):
            return None
        from enterprise_fizzbuzz.infrastructure.probabilistic import ProbabilisticDashboard
        return ProbabilisticDashboard.render(
            middleware=middleware,
            width=60,
        )
