"""Feature descriptor for the FizzBoot x86 bootloader simulation."""

from __future__ import annotations

from typing import Any, Optional

from enterprise_fizzbuzz.infrastructure.features._registry import FeatureDescriptor


class BootloaderFeature(FeatureDescriptor):
    name = "bootloader"
    description = "x86 bootloader simulation with BIOS POST, MBR, GDT, and Protected Mode transition"
    middleware_priority = -20  # Runs before everything, matching __main__.py
    cli_flags = [
        ("--boot", {"action": "store_true", "default": False,
                    "help": "Enable FizzBoot x86 bootloader simulation (POST, MBR, GDT, Protected Mode)"}),
        ("--boot-verbose", {"action": "store_true", "default": False,
                            "help": "Display detailed boot sequence log with timestamps"}),
        ("--boot-dashboard", {"action": "store_true", "default": False,
                              "help": "Display the FizzBoot x86 bootloader dashboard after execution"}),
    ]

    def is_enabled(self, args: Any) -> bool:
        return any([
            getattr(args, "boot", False),
            getattr(args, "boot_verbose", False),
            getattr(args, "boot_dashboard", False),
        ])

    def create(self, config: Any, args: Any, event_bus: Any = None) -> tuple:
        from enterprise_fizzbuzz.infrastructure.bootloader import (
            BootMiddleware,
        )

        boot_middleware = BootMiddleware(
            verbose=getattr(args, "boot_verbose", False),
            show_dashboard=False,  # Dashboard is rendered post-execution
            event_bus=event_bus,
        )

        return boot_middleware, boot_middleware

    def get_banner(self, config: Any, args: Any) -> Optional[str]:
        return (
            "  +---------------------------------------------------------+\n"
            "  | FIZZBOOT: x86 BOOTLOADER SIMULATION                     |\n"
            "  |   BIOS POST | MBR | A20 Gate | GDT | Protected Mode    |\n"
            "  |   Kernel loaded at 0x00100000 (1 MB boundary)           |\n"
            "  +---------------------------------------------------------+"
        )

    def render(self, middleware: Any, args: Any) -> Optional[str]:
        if middleware is None:
            if getattr(args, "boot_dashboard", False):
                return "  FizzBoot not enabled. Use --boot to enable."
            return None

        from enterprise_fizzbuzz.infrastructure.bootloader import (
            BootDashboard,
        )

        parts = []

        if getattr(args, "boot_dashboard", False):
            loader = getattr(middleware, "loader", None)
            if loader is not None:
                parts.append(BootDashboard.render(loader))

        return "\n".join(parts) if parts else None
