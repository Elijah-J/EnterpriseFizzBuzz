"""Feature descriptor for the FizzLife Flow-Lenia continuous cellular automaton engine."""

from __future__ import annotations

from typing import Any, Optional

from enterprise_fizzbuzz.infrastructure.features._registry import FeatureDescriptor


class FizzLifeFeature(FeatureDescriptor):
    name = "fizzlife"
    description = "Flow-Lenia continuous cellular automaton engine with evolutionary species discovery"
    middleware_priority = 140
    cli_flags = [
        ("--fizzlife", {"action": "store_true", "default": False,
                        "help": "Enable FizzLife: Flow-Lenia continuous cellular automaton engine for emergent FizzBuzz classification"}),
        ("--fizzlife-grid-size", {"type": int, "default": None, "metavar": "N",
                                  "help": "Grid dimensions NxN for the toroidal simulation grid (default: from config)"}),
        ("--fizzlife-generations", {"type": int, "default": None, "metavar": "N",
                                    "help": "Number of simulation generations to evolve (default: from config)"}),
        ("--fizzlife-kernel-type", {"type": str, "default": None,
                                    "choices": ["exponential", "polynomial", "rectangular"],
                                    "metavar": "TYPE",
                                    "help": "Kernel core function type: exponential, polynomial, or rectangular (default: from config)"}),
        ("--fizzlife-kernel-radius", {"type": int, "default": None, "metavar": "N",
                                      "help": "Convolution kernel radius R (default: from config)"}),
        ("--fizzlife-kernel-rank", {"type": int, "default": None, "metavar": "N",
                                    "help": "Number of concentric kernel rings for multi-ring kernels (default: from config)"}),
        ("--fizzlife-growth-mu", {"type": float, "default": None, "metavar": "FLOAT",
                                  "help": "Growth function center parameter mu (default: from config)"}),
        ("--fizzlife-growth-sigma", {"type": float, "default": None, "metavar": "FLOAT",
                                     "help": "Growth function width parameter sigma (default: from config)"}),
        ("--fizzlife-dt", {"type": float, "default": None, "metavar": "FLOAT",
                           "help": "Simulation time step dt (default: from config)"}),
        ("--fizzlife-channels", {"type": int, "default": None, "metavar": "N",
                                 "help": "Number of state channels for multi-channel Lenia (default: from config)"}),
        ("--fizzlife-mass-conservation", {"action": "store_true", "default": False,
                                          "help": "Enable mass conservation mode (Flow-Lenia divergence-free velocity field)"}),
        ("--fizzlife-species-catalog", {"action": "store_true", "default": False,
                                        "help": "Print the FizzLife species catalog and exit"}),
        ("--fizzlife-evolve", {"action": "store_true", "default": False,
                               "help": "Use genetic algorithm to discover novel Lenia species for FizzBuzz classification"}),
        ("--fizzlife-population", {"type": int, "default": None, "metavar": "N",
                                   "help": "Population size for evolutionary species discovery (default: from config)"}),
        ("--fizzlife-evo-generations", {"type": int, "default": None, "metavar": "N",
                                        "help": "Number of evolution generations for species discovery (default: from config)"}),
        ("--fizzlife-seed", {"type": int, "default": None, "metavar": "SEED",
                             "help": "Random seed for reproducible simulations and evolution (default: from config)"}),
        ("--fizzlife-dashboard", {"action": "store_true", "default": False,
                                  "help": "Display the FizzLife ASCII simulation dashboard after execution"}),
        ("--fizzlife-verbose", {"action": "store_true", "default": False,
                                "help": "Enable verbose logging of per-generation simulation telemetry in context metadata"}),
    ]

    def is_enabled(self, args: Any) -> bool:
        return any([
            getattr(args, "fizzlife", False),
            getattr(args, "fizzlife_dashboard", False),
            getattr(args, "fizzlife_species_catalog", False),
            getattr(args, "fizzlife_evolve", False),
        ])

    def create(self, config: Any, args: Any, event_bus: Any = None) -> tuple:
        from enterprise_fizzbuzz.infrastructure.fizzlife import (
            create_fizzlife_subsystem,
        )

        middleware, dashboard, catalog, fizzlife_config = create_fizzlife_subsystem(
            grid_size=getattr(args, "fizzlife_grid_size", None) or config.fizzlife_grid_width,
            generations=getattr(args, "fizzlife_generations", None) or config.fizzlife_max_generations,
            kernel_type=getattr(args, "fizzlife_kernel_type", None) or config.fizzlife_kernel_type,
            kernel_radius=getattr(args, "fizzlife_kernel_radius", None) or config.fizzlife_kernel_radius,
            kernel_rank=getattr(args, "fizzlife_kernel_rank", None) or 1,
            growth_mu=(args.fizzlife_growth_mu if getattr(args, "fizzlife_growth_mu", None) is not None
                       else config.fizzlife_growth_center),
            growth_sigma=(args.fizzlife_growth_sigma if getattr(args, "fizzlife_growth_sigma", None) is not None
                          else config.fizzlife_growth_width),
            dt=(args.fizzlife_dt if getattr(args, "fizzlife_dt", None) is not None
                else config.fizzlife_dt),
            channels=getattr(args, "fizzlife_channels", None) or 1,
            mass_conservation=getattr(args, "fizzlife_mass_conservation", False),
            seed=(args.fizzlife_seed if getattr(args, "fizzlife_seed", None) is not None
                  else config.fizzlife_seed),
            verbose=getattr(args, "fizzlife_verbose", False),
        )

        if getattr(args, "fizzlife_species_catalog", False):
            print(catalog.render())

        if getattr(args, "fizzlife_evolve", False):
            middleware.evolve(
                population_size=getattr(args, "fizzlife_population", None) or config.fizzlife_evolution_population_size,
                generations=getattr(args, "fizzlife_evo_generations", None) or config.fizzlife_evolution_generations,
                mutation_rate=config.fizzlife_evolution_mutation_rate,
                crossover_rate=config.fizzlife_evolution_crossover_rate,
                seed=(args.fizzlife_seed if getattr(args, "fizzlife_seed", None) is not None
                      else config.fizzlife_seed),
            )

        return (dashboard, catalog, fizzlife_config), middleware

    def get_banner(self, config: Any, args: Any) -> Optional[str]:
        return None  # Banner printed after subsystem creation in __main__.py with config details

    def render(self, middleware: Any, args: Any) -> Optional[str]:
        if middleware is None:
            if getattr(args, "fizzlife_dashboard", False):
                return "  FizzLife not enabled. Use --fizzlife to enable."
            return None

        parts = []

        if getattr(args, "fizzlife_dashboard", False):
            # Run a full-size showcase simulation for the dashboard.
            # The per-number middleware uses fast 16x16 grids; the
            # dashboard deserves the full 64x64 experience.
            from enterprise_fizzbuzz.infrastructure.fizzlife import (
                FizzLifeDashboard,
                FizzLifeEngine,
                SimulationConfig,
                create_default_config,
            )
            config = create_default_config()
            config.grid_size = 64
            config.generations = 200
            config.seed = 42
            engine = FizzLifeEngine(config)
            result = engine.run()
            dashboard = FizzLifeDashboard(config)
            parts.append(dashboard.render(result.reports))

        parts.append(middleware.render_stats())

        return "\n".join(parts) if parts else None
