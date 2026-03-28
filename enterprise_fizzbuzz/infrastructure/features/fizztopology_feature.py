"""Feature descriptor for the FizzTopology topological data analysis engine."""

from __future__ import annotations

from typing import Any, Optional

from enterprise_fizzbuzz.infrastructure.features._registry import FeatureDescriptor


class FizzTopologyFeature(FeatureDescriptor):
    name = "fizztopology"
    description = "Topological data analysis with persistent homology, simplicial complexes, Betti numbers, and persistence diagrams"
    middleware_priority = 273
    cli_flags = [
        ("--topology", {"action": "store_true", "default": False,
                        "help": "Enable FizzTopology: classify FizzBuzz using topological data analysis"}),
        ("--topology-dashboard", {"action": "store_true", "default": False,
                                  "help": "Display the FizzTopology ASCII dashboard with persistence statistics"}),
    ]

    def is_enabled(self, args: Any) -> bool:
        return any([
            getattr(args, "topology", False),
            getattr(args, "topology_dashboard", False),
        ])

    def create(self, config: Any, args: Any, event_bus: Any = None) -> tuple:
        from enterprise_fizzbuzz.infrastructure.fizztopology import (
            TopologyClassifier,
            TopologyMiddleware,
        )

        classifier = TopologyClassifier(
            num_points=config.fizztopology_num_points,
            max_dimension=config.fizztopology_max_dimension,
            num_epsilon_steps=config.fizztopology_num_epsilon_steps,
        )
        middleware = TopologyMiddleware(
            classifier=classifier,
            enable_dashboard=getattr(args, "topology_dashboard", False),
        )
        return classifier, middleware

    def get_banner(self, config: Any, args: Any) -> Optional[str]:
        if getattr(args, "no_banner", False):
            return None
        return (
            "  +---------------------------------------------------------+\n"
            "  | FIZZTOPOLOGY: TOPOLOGICAL DATA ANALYSIS                 |\n"
            f"  |   Points: {config.fizztopology_num_points:<4}  Max dim: {config.fizztopology_max_dimension:<2}  Epsilon steps: {config.fizztopology_num_epsilon_steps:<3}|\n"
            f"  |   Max epsilon: {config.fizztopology_max_epsilon:.1f}                                |\n"
            "  |   Point Cloud -> VR Complex -> Persistence -> FizzBuzz |\n"
            "  +---------------------------------------------------------+"
        )

    def render(self, middleware: Any, args: Any) -> Optional[str]:
        if middleware is None:
            return None
        if not getattr(args, "topology_dashboard", False):
            return None
        from enterprise_fizzbuzz.infrastructure.fizztopology import TopologyDashboard
        from enterprise_fizzbuzz.infrastructure.config import ConfigurationManager
        config = ConfigurationManager()
        if hasattr(middleware, "last_result") and middleware.last_result:
            return TopologyDashboard.render(
                middleware.last_result,
                width=config.fizztopology_dashboard_width,
            )
        return None
