"""Feature descriptor for the FizzUSB USB Protocol Stack."""

from __future__ import annotations

from typing import Any, Optional

from enterprise_fizzbuzz.infrastructure.features._registry import FeatureDescriptor


class FizzusbFeature(FeatureDescriptor):
    name = "fizzusb"
    description = "USB host controller with device enumeration, control/bulk/interrupt/isochronous transfers, descriptor parsing, and endpoint management for hardware-attached FizzBuzz peripherals"
    middleware_priority = 244
    cli_flags = [
        ("--usb", {"action": "store_true", "default": False,
                   "help": "Enable the FizzUSB host controller"}),
        ("--usb-speed", {"type": str, "default": "high", "metavar": "SPEED",
                         "help": "USB speed mode (low, full, high, super)"}),
        ("--usb-dashboard", {"action": "store_true", "default": False,
                             "help": "Display the FizzUSB ASCII dashboard with device tree"}),
    ]

    def is_enabled(self, args: Any) -> bool:
        return any([
            getattr(args, "usb", False),
            getattr(args, "usb_dashboard", False),
        ])

    def has_early_exit(self, args: Any) -> bool:
        return False

    def run_early_exit(self, args: Any, config: Any) -> int:
        return 0

    def create(self, config: Any, args: Any, event_bus: Any = None) -> tuple:
        from enterprise_fizzbuzz.infrastructure.fizzusb import (
            USBSpeed,
            create_fizzusb_subsystem,
        )

        speed_str = getattr(args, "usb_speed", "high")
        speed_map = {"low": USBSpeed.LOW, "full": USBSpeed.FULL,
                     "high": USBSpeed.HIGH, "super": USBSpeed.SUPER}
        speed = speed_map.get(speed_str, USBSpeed.HIGH)

        controller, middleware = create_fizzusb_subsystem(speed=speed)
        return controller, middleware

    def render(self, middleware: Any, args: Any) -> Optional[str]:
        if not getattr(args, "usb_dashboard", False):
            return None
        if middleware is None:
            return "\n  FizzUSB not enabled. Use --usb to enable.\n"

        from enterprise_fizzbuzz.infrastructure.fizzusb import USBDashboard

        controller = middleware.controller if hasattr(middleware, "controller") else None
        if controller is not None:
            return USBDashboard.render(controller)
        return None
