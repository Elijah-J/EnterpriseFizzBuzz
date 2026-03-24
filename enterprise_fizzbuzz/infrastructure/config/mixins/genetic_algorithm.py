"""Genetic Algorithm properties"""

from __future__ import annotations

from typing import Any


class GeneticAlgorithmConfigMixin:
    """Configuration properties for the genetic algorithm subsystem."""

    # ----------------------------------------------------------------
    # Genetic Algorithm properties
    # ----------------------------------------------------------------

    @property
    def genetic_algorithm_enabled(self) -> bool:
        """Whether the Genetic Algorithm subsystem is enabled."""
        self._ensure_loaded()
        return self._raw_config.get("genetic_algorithm", {}).get("enabled", False)

    @property
    def genetic_algorithm_population_size(self) -> int:
        """Number of chromosomes per generation."""
        self._ensure_loaded()
        return self._raw_config.get("genetic_algorithm", {}).get("population_size", 50)

    @property
    def genetic_algorithm_generations(self) -> int:
        """Maximum generations before termination."""
        self._ensure_loaded()
        return self._raw_config.get("genetic_algorithm", {}).get("generations", 100)

    @property
    def genetic_algorithm_mutation_rate(self) -> float:
        """Probability of mutation per gene."""
        self._ensure_loaded()
        return self._raw_config.get("genetic_algorithm", {}).get("mutation_rate", 0.15)

    @property
    def genetic_algorithm_crossover_rate(self) -> float:
        """Probability of crossover per mating."""
        self._ensure_loaded()
        return self._raw_config.get("genetic_algorithm", {}).get("crossover_rate", 0.7)

    @property
    def genetic_algorithm_tournament_size(self) -> int:
        """Tournament selection pool size."""
        self._ensure_loaded()
        return self._raw_config.get("genetic_algorithm", {}).get("tournament_size", 5)

    @property
    def genetic_algorithm_elitism_count(self) -> int:
        """Number of top chromosomes preserved each generation."""
        self._ensure_loaded()
        return self._raw_config.get("genetic_algorithm", {}).get("elitism_count", 2)

    @property
    def genetic_algorithm_max_genes(self) -> int:
        """Maximum genes (rules) per chromosome."""
        self._ensure_loaded()
        return self._raw_config.get("genetic_algorithm", {}).get("max_genes", 8)

    @property
    def genetic_algorithm_min_genes(self) -> int:
        """Minimum genes (rules) per chromosome."""
        self._ensure_loaded()
        return self._raw_config.get("genetic_algorithm", {}).get("min_genes", 1)

    @property
    def genetic_algorithm_canonical_seed_pct(self) -> float:
        """Fraction of initial population seeded with canonical rules."""
        self._ensure_loaded()
        return self._raw_config.get("genetic_algorithm", {}).get("canonical_seed_pct", 0.10)

    @property
    def genetic_algorithm_convergence_threshold(self) -> float:
        """Fitness above which we declare victory."""
        self._ensure_loaded()
        return self._raw_config.get("genetic_algorithm", {}).get("convergence_threshold", 0.95)

    @property
    def genetic_algorithm_diversity_floor(self) -> float:
        """Diversity below which mass extinction is triggered."""
        self._ensure_loaded()
        return self._raw_config.get("genetic_algorithm", {}).get("diversity_floor", 0.05)

    @property
    def genetic_algorithm_mass_extinction_survivor_pct(self) -> float:
        """Fraction of population that survives mass extinction."""
        self._ensure_loaded()
        return self._raw_config.get("genetic_algorithm", {}).get("mass_extinction_survivor_pct", 0.20)

    @property
    def genetic_algorithm_hall_of_fame_size(self) -> int:
        """Number of all-time best chromosomes to remember."""
        self._ensure_loaded()
        return self._raw_config.get("genetic_algorithm", {}).get("hall_of_fame_size", 10)

    @property
    def genetic_algorithm_fitness_weights(self) -> dict[str, float]:
        """Multi-objective fitness function weights."""
        self._ensure_loaded()
        return self._raw_config.get("genetic_algorithm", {}).get("fitness_weights", {
            "accuracy": 0.50,
            "coverage": 0.15,
            "distinctness": 0.10,
            "phonetic_harmony": 0.10,
            "mathematical_elegance": 0.15,
        })

    @property
    def genetic_algorithm_seed(self) -> int | None:
        """Random seed for reproducibility."""
        self._ensure_loaded()
        return self._raw_config.get("genetic_algorithm", {}).get("seed", None)

    @property
    def genetic_algorithm_dashboard_width(self) -> int:
        """ASCII dashboard width for the GA dashboard."""
        self._ensure_loaded()
        return self._raw_config.get("genetic_algorithm", {}).get("dashboard", {}).get("width", 60)

    @property
    def genetic_algorithm_fitness_chart_height(self) -> int:
        """Height of the fitness sparkline chart."""
        self._ensure_loaded()
        return self._raw_config.get("genetic_algorithm", {}).get("dashboard", {}).get("fitness_chart_height", 10)

