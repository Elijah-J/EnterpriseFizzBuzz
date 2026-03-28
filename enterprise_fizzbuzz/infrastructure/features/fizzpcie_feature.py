"""Feature descriptor for the FizzPCIe Bus Emulator."""

from __future__ import annotations

from typing import Any, Optional

from enterprise_fizzbuzz.infrastructure.features._registry import FeatureDescriptor


class FizzpcieFeature(FeatureDescriptor):
    name = "fizzpcie"
    description = "PCIe bus emulator with configuration space, BAR mapping, MSI/MSI-X interrupts, link training, and TLP packet routing for high-throughput FizzBuzz device interconnects"
    middleware_priority = 245
    cli_flags = [
        ("--pcie", {"action": "store_true", "default": False,
                    "help": "Enable the FizzPCIe bus emulator"}),
        ("--pcie-gen", {"type": int, "default": 3, "metavar": "GEN",
                        "help": "PCIe generation (1-5)"}),
        ("--pcie-dashboard", {"action": "store_true", "default": False,
                              "help": "Display the FizzPCIe ASCII dashboard with bus topology"}),
    ]

    def is_enabled(self, args: Any) -> bool:
        return any([
            getattr(args, "pcie", False),
            getattr(args, "pcie_dashboard", False),
        ])

    def has_early_exit(self, args: Any) -> bool:
        return False

    def run_early_exit(self, args: Any, config: Any) -> int:
        return 0

    def create(self, config: Any, args: Any, event_bus: Any = None) -> tuple:
        from enterprise_fizzbuzz.infrastructure.fizzpcie import create_fizzpcie_subsystem

        gen = getattr(args, "pcie_gen", 3)
        bus, middleware = create_fizzpcie_subsystem(generation=gen)
        return bus, middleware

    def render(self, middleware: Any, args: Any) -> Optional[str]:
        if not getattr(args, "pcie_dashboard", False):
            return None
        if middleware is None:
            return "\n  FizzPCIe not enabled. Use --pcie to enable.\n"

        from enterprise_fizzbuzz.infrastructure.fizzpcie import PCIeDashboard

        bus = middleware.bus if hasattr(middleware, "bus") else None
        if bus is not None:
            return PCIeDashboard.render(bus)
        return None
