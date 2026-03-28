"""Feature descriptor for the FizzIOMMU I/O Memory Management Unit."""

from __future__ import annotations

from typing import Any, Optional

from enterprise_fizzbuzz.infrastructure.features._registry import FeatureDescriptor


class FizziommuFeature(FeatureDescriptor):
    name = "fizziommu"
    description = "IOMMU with DMA remapping, multi-level page table walks, device isolation, and interrupt remapping for secure FizzBuzz I/O"
    middleware_priority = 243
    cli_flags = [
        ("--iommu", {"action": "store_true", "default": False,
                     "help": "Enable the FizzIOMMU I/O memory management unit"}),
        ("--iommu-dashboard", {"action": "store_true", "default": False,
                               "help": "Display the FizzIOMMU ASCII dashboard"}),
    ]

    def is_enabled(self, args: Any) -> bool:
        return any([
            getattr(args, "iommu", False),
            getattr(args, "iommu_dashboard", False),
        ])

    def has_early_exit(self, args: Any) -> bool:
        return False

    def run_early_exit(self, args: Any, config: Any) -> int:
        return 0

    def create(self, config: Any, args: Any, event_bus: Any = None) -> tuple:
        from enterprise_fizzbuzz.infrastructure.fizziommu import (
            create_fizziommu_subsystem,
        )

        iommu, middleware = create_fizziommu_subsystem()
        return iommu, middleware

    def render(self, middleware: Any, args: Any) -> Optional[str]:
        if not getattr(args, "iommu_dashboard", False):
            return None
        if middleware is None:
            return "\n  FizzIOMMU not enabled. Use --iommu to enable.\n"

        from enterprise_fizzbuzz.infrastructure.fizziommu import IOMMUDashboard

        iommu = middleware.iommu if hasattr(middleware, "iommu") else None
        if iommu is not None:
            return IOMMUDashboard.render(iommu)
        return None
