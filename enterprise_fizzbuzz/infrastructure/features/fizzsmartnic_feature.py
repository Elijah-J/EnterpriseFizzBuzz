"""Feature descriptor for the FizzSmartNIC Offload Engine."""

from __future__ import annotations

from typing import Any, Optional

from enterprise_fizzbuzz.infrastructure.features._registry import FeatureDescriptor


class FizzsmartnicFeature(FeatureDescriptor):
    name = "fizzsmartnic"
    description = "Programmable Smart NIC with offload programs, flow tables, hardware acceleration, packet classification, and checksum offload for wire-speed FizzBuzz evaluation"
    middleware_priority = 255
    cli_flags = [
        ("--smartnic", {"action": "store_true", "default": False,
                        "help": "Enable the FizzSmartNIC offload engine"}),
        ("--smartnic-queues", {"type": int, "default": 4, "metavar": "N",
                               "help": "Number of TX/RX queue pairs on the Smart NIC"}),
        ("--smartnic-dashboard", {"action": "store_true", "default": False,
                                  "help": "Display the FizzSmartNIC ASCII dashboard"}),
    ]

    def is_enabled(self, args: Any) -> bool:
        return any([
            getattr(args, "smartnic", False),
            getattr(args, "smartnic_dashboard", False),
        ])

    def has_early_exit(self, args: Any) -> bool:
        return False

    def run_early_exit(self, args: Any, config: Any) -> int:
        return 0

    def create(self, config: Any, args: Any, event_bus: Any = None) -> tuple:
        from enterprise_fizzbuzz.infrastructure.fizzsmartnic import create_fizzsmartnic_subsystem

        num_queues = getattr(args, "smartnic_queues", 4)
        nic, middleware = create_fizzsmartnic_subsystem(num_queues=num_queues)
        return nic, middleware

    def render(self, middleware: Any, args: Any) -> Optional[str]:
        if not getattr(args, "smartnic_dashboard", False):
            return None
        if middleware is None:
            return "\n  FizzSmartNIC not enabled. Use --smartnic to enable.\n"

        from enterprise_fizzbuzz.infrastructure.fizzsmartnic import SmartNICDashboard

        nic = middleware.nic if hasattr(middleware, "nic") else None
        if nic is not None:
            return SmartNICDashboard.render(nic)
        return None
