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

        print(f"\n  [GA] Starting Genetic Algorithm for Optimal FizzBuzz Rule Discovery...")
        print(f"  [GA] Population: {config.genetic_algorithm_population_size} | Generations: {ga_generations}")
        print(f"  [GA] Evolving...\n")

        best_chromosome = ga_engine.evolve()

        rules = best_chromosome.to_rules_dict()
        rules_str = ", ".join(f"{d}:{l!r}" for d, l in sorted(rules.items()))
        print(f"  [GA] Evolution complete in {ga_engine.elapsed_ms:.1f}ms")
        print(f"  [GA] Best rules discovered: {{{rules_str}}}")
        print(f"  [GA] Fitness: {best_chromosome.fitness.overall:.6f}")
        print(f"  [GA] Converged: {'YES' if ga_engine.converged else 'NO'}")
        print(f"  [GA] Generations run: {ga_engine.generation}")
        print(f"  [GA] Mass extinctions: {ga_engine.convergence_monitor.extinction_count}")

        is_canonical = (rules == {3: "Fizz", 5: "Buzz"})
        if is_canonical:
            print()
            print("  [GA] PUNCHLINE: After all that evolutionary computation,")
            print("  [GA] the algorithm rediscovered {3:'Fizz', 5:'Buzz'} --")
            print("  [GA] the exact same rules from the original 5-line solution.")
            print("  [GA] Darwin would be proud. Or embarrassed.")
        print()

        self._ga_engine = ga_engine
        self._config = config

        return ga_engine, None

    def get_banner(self, config: Any, args: Any) -> Optional[str]:
        return None

    def render(self, middleware: Any, args: Any) -> Optional[str]:
        if not getattr(args, "genetic_dashboard", False):
            return None
        engine = getattr(self, "_ga_engine", None)
        if engine is None:
            return None
        from enterprise_fizzbuzz.infrastructure.genetic_algorithm import EvolutionDashboard
        config = getattr(self, "_config", None)
        if config is None:
            return None
        return EvolutionDashboard.render(
            engine,
            width=config.genetic_algorithm_dashboard_width,
            chart_height=config.genetic_algorithm_fitness_chart_height,
        )
