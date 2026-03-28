"""Feature descriptor for the FizzHypervisor Type-1 Hypervisor."""

from __future__ import annotations

from typing import Any, Optional

from enterprise_fizzbuzz.infrastructure.features._registry import FeatureDescriptor


class FizzhypervisorFeature(FeatureDescriptor):
    name = "fizzhypervisor"
    description = "Type-1 bare-metal hypervisor with VM creation, vCPU scheduling, EPT/NPT memory virtualization, VMCS management, and VM-exit handling for hardware-isolated FizzBuzz evaluation"
    middleware_priority = 250
    cli_flags = [
        ("--hypervisor", {"action": "store_true", "default": False,
                          "help": "Enable the FizzHypervisor Type-1 hypervisor"}),
        ("--hypervisor-pcpus", {"type": int, "default": 4, "metavar": "N",
                                "help": "Number of physical CPU cores for the hypervisor"}),
        ("--hypervisor-dashboard", {"action": "store_true", "default": False,
                                    "help": "Display the FizzHypervisor ASCII dashboard"}),
    ]

    def is_enabled(self, args: Any) -> bool:
        return any([
            getattr(args, "hypervisor", False),
            getattr(args, "hypervisor_dashboard", False),
        ])

    def has_early_exit(self, args: Any) -> bool:
        return False

    def run_early_exit(self, args: Any, config: Any) -> int:
        return 0

    def create(self, config: Any, args: Any, event_bus: Any = None) -> tuple:
        from enterprise_fizzbuzz.infrastructure.fizzhypervisor import create_fizzhypervisor_subsystem

        pcpu_count = getattr(args, "hypervisor_pcpus", 4)
        hypervisor, middleware = create_fizzhypervisor_subsystem(pcpu_count=pcpu_count)
        return hypervisor, middleware

    def render(self, middleware: Any, args: Any) -> Optional[str]:
        if not getattr(args, "hypervisor_dashboard", False):
            return None
        if middleware is None:
            return "\n  FizzHypervisor not enabled. Use --hypervisor to enable.\n"

        from enterprise_fizzbuzz.infrastructure.fizzhypervisor import HypervisorDashboard

        hypervisor = middleware.hypervisor if hasattr(middleware, "hypervisor") else None
        if hypervisor is not None:
            return HypervisorDashboard.render(hypervisor)
        return None
