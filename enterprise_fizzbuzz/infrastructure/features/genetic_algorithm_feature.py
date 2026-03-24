"""Feature descriptor for the Genetic Algorithm rule discovery engine."""

from __future__ import annotations

from typing import Any, Optional

from enterprise_fizzbuzz.infrastructure.features._registry import FeatureDescriptor


class GeneticAlgorithmFeature(FeatureDescriptor):
    name = "genetic_algorithm"
    description = "Evolutionary genetic algorithm that rediscovers optimal FizzBuzz rules from scratch"
    middleware_priority = 127
    cli_flags = [
        ("--genetic", {"action": "store_true", "default": False,
                       "help": "Enable the Genetic Algorithm to evolve the optimal FizzBuzz rules (spoiler: it rediscovers {3:Fizz, 5:Buzz})"}),
        ("--genetic-generations", {"type": int, "default": None, "metavar": "N",
                                   "help": "Number of generations for the genetic algorithm (default: from config)"}),
        ("--genetic-dashboard", {"action": "store_true", "default": False,
                                 "help": "Display the Genetic Algorithm evolution dashboard after execution"}),
    ]

    def is_enabled(self, args: Any) -> bool:
        return getattr(args, "genetic", False)

    def create(self, config: Any, args: Any, event_bus: Any = None) -> tuple:
        from enterprise_fizzbuzz.infrastructure.genetic_algorithm import (
            GeneticAlgorithmEngine,
        )

        ga_generations = getattr(args, "genetic_generations", None) or config.genetic_algorithm_generations

        ga_engine = GeneticAlgorithmEngine(
            population_size=config.genetic_algorithm_population_size,
            generations=ga_generations,
            mutation_rate=config.genetic_algorithm_mutation_rate,
            crossover_rate=config.genetic_algorithm_crossover_rate,
            tournament_size=config.genetic_algorithm_tournament_size,
            elitism_count=config.genetic_algorithm_elitism_count,
            max_genes=config.genetic_algorithm_max_genes,
            min_genes=config.genetic_algorithm_min_genes,
            canonical_seed_pct=config.genetic_algorithm_canonical_seed_pct,
            convergence_threshold=config.genetic_algorithm_convergence_threshold,
            diversity_floor=config.genetic_algorithm_diversity_floor,
            mass_extinction_survivor_pct=config.genetic_algorithm_mass_extinction_survivor_pct,
            hall_of_fame_size=config.genetic_algorithm_hall_of_fame_size,
            fitness_weights=config.genetic_algorithm_fitness_weights,
            seed=config.genetic_algorithm_seed,
            event_callback=event_bus.publish if event_bus else None,
        )

        return ga_engine, None

    def render(self, middleware: Any, args: Any) -> Optional[str]:
        if not getattr(args, "genetic_dashboard", False):
            return None
        # The GA engine is passed as the service (first element), not middleware.
        # Rendering requires the engine to have already run.
        return None
