"""Feature descriptor for the FizzSwarm swarm intelligence engine."""

from __future__ import annotations

from typing import Any, Optional

from enterprise_fizzbuzz.infrastructure.features._registry import FeatureDescriptor


class FizzSwarmFeature(FeatureDescriptor):
    name = "fizzswarm"
    description = "Swarm intelligence with ant colony optimization, particle swarm optimization, and bee algorithm"
    middleware_priority = 269
    cli_flags = [
        ("--swarm", {"action": "store_true", "default": False,
                     "help": "Enable FizzSwarm: classify FizzBuzz using swarm intelligence algorithms"}),
        ("--swarm-dashboard", {"action": "store_true", "default": False,
                               "help": "Display the FizzSwarm ASCII dashboard with swarm consensus results"}),
    ]

    def is_enabled(self, args: Any) -> bool:
        return any([
            getattr(args, "swarm", False),
            getattr(args, "swarm_dashboard", False),
        ])

    def create(self, config: Any, args: Any, event_bus: Any = None) -> tuple:
        from enterprise_fizzbuzz.infrastructure.fizzswarm import (
            AntColonyOptimizer,
            BeeAlgorithm,
            ParticleSwarmOptimizer,
            SwarmClassifier,
            SwarmMiddleware,
        )

        aco = AntColonyOptimizer(
            num_ants=config.fizzswarm_num_ants,
            iterations=config.fizzswarm_aco_iterations,
            evaporation_rate=config.fizzswarm_evaporation_rate,
        )
        pso = ParticleSwarmOptimizer(
            num_particles=config.fizzswarm_num_particles,
            iterations=config.fizzswarm_pso_iterations,
            v_max=config.fizzswarm_v_max,
        )
        bee = BeeAlgorithm()
        classifier = SwarmClassifier(aco=aco, pso=pso, bee=bee)
        middleware = SwarmMiddleware(
            classifier=classifier,
            enable_dashboard=getattr(args, "swarm_dashboard", False),
        )
        return classifier, middleware

    def get_banner(self, config: Any, args: Any) -> Optional[str]:
        if getattr(args, "no_banner", False):
            return None
        return (
            "  +---------------------------------------------------------+\n"
            "  | FIZZSWARM: SWARM INTELLIGENCE ENGINE                    |\n"
            f"  |   ACO: {config.fizzswarm_num_ants} ants x {config.fizzswarm_aco_iterations} iters  "
            f"PSO: {config.fizzswarm_num_particles} particles    |\n"
            f"  |   Evaporation: {config.fizzswarm_evaporation_rate:.2f}  V_max: {config.fizzswarm_v_max:.1f}                  |\n"
            "  |   ACO + PSO + Bee -> Majority Vote                     |\n"
            "  +---------------------------------------------------------+"
        )

    def render(self, middleware: Any, args: Any) -> Optional[str]:
        if middleware is None:
            return None
        if not getattr(args, "swarm_dashboard", False):
            return None
        from enterprise_fizzbuzz.infrastructure.fizzswarm import SwarmDashboard
        from enterprise_fizzbuzz.infrastructure.config import ConfigurationManager
        config = ConfigurationManager()
        if hasattr(middleware, "last_result") and middleware.last_result:
            return SwarmDashboard.render(
                middleware.last_result,
                width=config.fizzswarm_dashboard_width,
            )
        return None
