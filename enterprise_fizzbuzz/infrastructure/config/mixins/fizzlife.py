"""Fizzlife configuration properties."""

from __future__ import annotations

from typing import Any


class FizzlifeConfigMixin:
    """Configuration properties for the fizzlife subsystem."""

    # ----------------------------------------------------------------
    # FizzLife — Continuous Cellular Automaton (Lenia) Simulation
    # ----------------------------------------------------------------

    @property
    def fizzlife_enabled(self) -> bool:
        """Whether the FizzLife simulation subsystem is enabled."""
        self._ensure_loaded()
        return self._raw_config.get("fizzlife", {}).get("enabled", False)

    @property
    def fizzlife_grid_width(self) -> int:
        """Width of the simulation grid."""
        self._ensure_loaded()
        return int(self._raw_config.get("fizzlife", {}).get("grid_width", 64))

    @property
    def fizzlife_grid_height(self) -> int:
        """Height of the simulation grid."""
        self._ensure_loaded()
        return int(self._raw_config.get("fizzlife", {}).get("grid_height", 64))

    @property
    def fizzlife_dt(self) -> float:
        """Time step for state updates."""
        self._ensure_loaded()
        return float(self._raw_config.get("fizzlife", {}).get("dt", 0.1))

    @property
    def fizzlife_max_generations(self) -> int:
        """Maximum simulation generations."""
        self._ensure_loaded()
        return int(self._raw_config.get("fizzlife", {}).get("max_generations", 500))

    @property
    def fizzlife_convergence_threshold(self) -> float:
        """Delta below which simulation is considered converged."""
        self._ensure_loaded()
        return float(self._raw_config.get("fizzlife", {}).get("convergence_threshold", 0.001))

    @property
    def fizzlife_mass_tolerance(self) -> float:
        """Maximum allowed mass deviation fraction."""
        self._ensure_loaded()
        return float(self._raw_config.get("fizzlife", {}).get("mass_tolerance", 0.05))

    @property
    def fizzlife_seed(self) -> int | None:
        """Random seed for reproducibility."""
        self._ensure_loaded()
        return self._raw_config.get("fizzlife", {}).get("seed", None)

    @property
    def fizzlife_kernel_type(self) -> str:
        """Kernel type: polynomial, exponential, gaussian, or step."""
        self._ensure_loaded()
        return self._raw_config.get("fizzlife", {}).get("kernel", {}).get("type", "polynomial")

    @property
    def fizzlife_kernel_radius(self) -> int:
        """Kernel support radius in cells."""
        self._ensure_loaded()
        return int(self._raw_config.get("fizzlife", {}).get("kernel", {}).get("radius", 13))

    @property
    def fizzlife_kernel_alpha(self) -> float:
        """Kernel shape parameter alpha."""
        self._ensure_loaded()
        return float(self._raw_config.get("fizzlife", {}).get("kernel", {}).get("alpha", 4.0))

    @property
    def fizzlife_kernel_peaks(self) -> list[float]:
        """Beta peak parameters for multi-ring kernels."""
        self._ensure_loaded()
        return self._raw_config.get("fizzlife", {}).get("kernel", {}).get("peaks", [1.0])

    @property
    def fizzlife_kernel_normalize(self) -> bool:
        """Whether to normalize kernel to sum to 1.0."""
        self._ensure_loaded()
        return self._raw_config.get("fizzlife", {}).get("kernel", {}).get("normalize", True)

    @property
    def fizzlife_growth_type(self) -> str:
        """Growth function type: gaussian, polynomial, step, or sine."""
        self._ensure_loaded()
        return self._raw_config.get("fizzlife", {}).get("growth", {}).get("type", "gaussian")

    @property
    def fizzlife_growth_center(self) -> float:
        """Growth function center (mu)."""
        self._ensure_loaded()
        return float(self._raw_config.get("fizzlife", {}).get("growth", {}).get("center", 0.15))

    @property
    def fizzlife_growth_width(self) -> float:
        """Growth function width (sigma)."""
        self._ensure_loaded()
        return float(self._raw_config.get("fizzlife", {}).get("growth", {}).get("width", 0.015))

    @property
    def fizzlife_species_min_mass(self) -> float:
        """Minimum mass to qualify as a species."""
        self._ensure_loaded()
        return float(self._raw_config.get("fizzlife", {}).get("species", {}).get("min_mass", 0.01))

    @property
    def fizzlife_species_stability_window(self) -> int:
        """Generations to observe before classifying a species."""
        self._ensure_loaded()
        return int(self._raw_config.get("fizzlife", {}).get("species", {}).get("stability_window", 10))

    @property
    def fizzlife_species_similarity_threshold(self) -> float:
        """Cosine similarity threshold for species matching."""
        self._ensure_loaded()
        return float(self._raw_config.get("fizzlife", {}).get("species", {}).get("similarity_threshold", 0.85))

    @property
    def fizzlife_evolution_enabled(self) -> bool:
        """Whether evolutionary parameter search is enabled."""
        self._ensure_loaded()
        return self._raw_config.get("fizzlife", {}).get("evolution", {}).get("enabled", False)

    @property
    def fizzlife_evolution_population_size(self) -> int:
        """Number of candidate configurations in evolution."""
        self._ensure_loaded()
        return int(self._raw_config.get("fizzlife", {}).get("evolution", {}).get("population_size", 20))

    @property
    def fizzlife_evolution_generations(self) -> int:
        """Evolution generations."""
        self._ensure_loaded()
        return int(self._raw_config.get("fizzlife", {}).get("evolution", {}).get("generations", 50))

    @property
    def fizzlife_evolution_mutation_rate(self) -> float:
        """Parameter mutation probability."""
        self._ensure_loaded()
        return float(self._raw_config.get("fizzlife", {}).get("evolution", {}).get("mutation_rate", 0.2))

    @property
    def fizzlife_evolution_crossover_rate(self) -> float:
        """Crossover probability."""
        self._ensure_loaded()
        return float(self._raw_config.get("fizzlife", {}).get("evolution", {}).get("crossover_rate", 0.7))

    @property
    def fizzlife_evolution_fitness_weights(self) -> dict[str, float]:
        """Multi-objective fitness weights for evolution."""
        self._ensure_loaded()
        return self._raw_config.get("fizzlife", {}).get("evolution", {}).get("fitness_weights", {
            "diversity": 0.40,
            "longevity": 0.30,
            "complexity": 0.30,
        })

    @property
    def fizzlife_dashboard_width(self) -> int:
        """ASCII dashboard width for FizzLife."""
        self._ensure_loaded()
        return int(self._raw_config.get("fizzlife", {}).get("dashboard", {}).get("width", 72))

    @property
    def fizzlife_dashboard_grid_display_size(self) -> int:
        """Grid rendering size (downsampled if larger)."""
        self._ensure_loaded()
        return int(self._raw_config.get("fizzlife", {}).get("dashboard", {}).get("grid_display_size", 32))

    def get_raw(self, key: str, default: Any = None) -> Any:
        """Get a raw configuration value by dot-separated key path."""
        self._ensure_loaded()
        keys = key.split(".")
        value: Any = self._raw_config
        for k in keys:
            if isinstance(value, dict):
                value = value.get(k)
            else:
                return default
            if value is None:
                return default
        return value
