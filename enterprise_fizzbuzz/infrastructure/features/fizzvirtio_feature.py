"""Feature descriptor for the FizzVirtIO paravirtualized I/O framework."""

from __future__ import annotations

from typing import Any, Optional

from enterprise_fizzbuzz.infrastructure.features._registry import FeatureDescriptor


class FizzvirtioFeature(FeatureDescriptor):
    name = "fizzvirtio"
    description = "VirtIO paravirtualized I/O framework with virtqueues, descriptor chains, and available/used ring buffers for high-performance FizzBuzz data transfer"
    middleware_priority = 239
    cli_flags = [
        ("--virtio", {"action": "store_true", "default": False,
                      "help": "Enable the FizzVirtIO paravirtualized I/O framework"}),
        ("--virtio-devices", {"type": int, "default": 1, "metavar": "N",
                              "help": "Number of VirtIO FIZZBUZZ devices to attach (default: 1)"}),
        ("--virtio-queue-size", {"type": int, "default": 256, "metavar": "N",
                                 "help": "Size of each virtqueue in descriptors (default: 256)"}),
        ("--virtio-dashboard", {"action": "store_true", "default": False,
                                "help": "Display the FizzVirtIO ASCII dashboard"}),
    ]

    def is_enabled(self, args: Any) -> bool:
        return any([
            getattr(args, "virtio", False),
            getattr(args, "virtio_dashboard", False),
        ])

    def has_early_exit(self, args: Any) -> bool:
        return False

    def run_early_exit(self, args: Any, config: Any) -> int:
        return 0

    def create(self, config: Any, args: Any, event_bus: Any = None) -> tuple:
        from enterprise_fizzbuzz.infrastructure.fizzvirtio import (
            create_fizzvirtio_subsystem,
        )

        bus, middleware = create_fizzvirtio_subsystem(
            num_devices=getattr(args, "virtio_devices", 1),
            queue_size=getattr(args, "virtio_queue_size", 256),
        )

        return bus, middleware

    def render(self, middleware: Any, args: Any) -> Optional[str]:
        if not getattr(args, "virtio_dashboard", False):
            return None
        if middleware is None:
            return "\n  FizzVirtIO not enabled. Use --virtio to enable.\n"

        from enterprise_fizzbuzz.infrastructure.fizzvirtio import VirtIODashboard

        bus = middleware.bus if hasattr(middleware, "bus") else None
        if bus is not None:
            return VirtIODashboard.render(bus)
        return None
