"""Feature descriptor for the FizzFPGA synthesis engine."""

from __future__ import annotations

from typing import Any, Optional

from enterprise_fizzbuzz.infrastructure.features._registry import FeatureDescriptor


class FizzFPGAFeature(FeatureDescriptor):
    name = "fizzfpga"
    description = "FPGA synthesis engine with LUTs, flip-flops, routing fabric, clock domains, and bitstream generation"
    middleware_priority = 256
    cli_flags = [
        ("--fizzfpga", {"action": "store_true", "default": False,
                        "help": "Enable FizzFPGA: hardware-accelerated FizzBuzz via FPGA synthesis"}),
        ("--fizzfpga-grid-width", {"type": int, "default": 8, "metavar": "N",
                                    "help": "FPGA fabric grid width in CLB columns (default: 8)"}),
        ("--fizzfpga-grid-height", {"type": int, "default": 8, "metavar": "N",
                                     "help": "FPGA fabric grid height in CLB rows (default: 8)"}),
        ("--fizzfpga-clock-mhz", {"type": float, "default": 100.0, "metavar": "F",
                                   "help": "System clock frequency in MHz (default: 100)"}),
    ]

    def is_enabled(self, args: Any) -> bool:
        return getattr(args, "fizzfpga", False)

    def create(self, config: Any, args: Any, event_bus: Any = None) -> tuple:
        from enterprise_fizzbuzz.infrastructure.fizzfpga import (
            FPGASynthesisEngine,
            FizzFPGAMiddleware,
        )

        engine = FPGASynthesisEngine(
            grid_width=getattr(args, "fizzfpga_grid_width", config.fizzfpga_grid_width),
            grid_height=getattr(args, "fizzfpga_grid_height", config.fizzfpga_grid_height),
            system_clock_mhz=getattr(args, "fizzfpga_clock_mhz", config.fizzfpga_system_clock_mhz),
        )
        middleware = FizzFPGAMiddleware(engine=engine)
        return engine, middleware

    def get_banner(self, config: Any, args: Any) -> Optional[str]:
        if getattr(args, "no_banner", False):
            return None
        w = getattr(args, "fizzfpga_grid_width", 8)
        h = getattr(args, "fizzfpga_grid_height", 8)
        return (
            "  +---------------------------------------------------------+\n"
            "  | FIZZFPGA: FPGA SYNTHESIS ENGINE                         |\n"
            f"  |   Fabric: {w}x{h} CLBs  4-input LUTs                    |\n"
            "  |   Clock domains: SYSTEM, FIZZ, BUZZ, IO                 |\n"
            "  |   Bitstream CRC32 integrity verification enabled         |\n"
            "  +---------------------------------------------------------+"
        )

    def render(self, middleware: Any, args: Any) -> Optional[str]:
        return None
