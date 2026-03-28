"""Feature descriptor for the FizzOptane persistent memory manager."""

from __future__ import annotations

from typing import Any, Optional

from enterprise_fizzbuzz.infrastructure.features._registry import FeatureDescriptor


class FizzOptaneFeature(FeatureDescriptor):
    name = "fizzoptane"
    description = "Persistent memory manager with DAX mapping, CLWB/SFENCE barriers, and crash-consistent writes"
    middleware_priority = 265
    cli_flags = [
        ("--optane", {"action": "store_true", "default": False,
                      "help": "Enable FizzOptane: persist FizzBuzz results in emulated Intel Optane-style persistent memory"}),
        ("--optane-dashboard", {"action": "store_true", "default": False,
                                "help": "Display the FizzOptane ASCII dashboard with pool layout and barrier statistics"}),
    ]

    def is_enabled(self, args: Any) -> bool:
        return any([
            getattr(args, "optane", False),
            getattr(args, "optane_dashboard", False),
        ])

    def create(self, config: Any, args: Any, event_bus: Any = None) -> tuple:
        from enterprise_fizzbuzz.infrastructure.fizzoptane import (
            OptaneMiddleware,
            PMEMAllocator,
            PersistentFizzBuzzStore,
            PersistentRegion,
        )

        region = PersistentRegion(size=config.fizzoptane_pool_size)
        allocator = PMEMAllocator(region=region)
        store = PersistentFizzBuzzStore(allocator=allocator)
        middleware = OptaneMiddleware(
            store=store,
            enable_dashboard=getattr(args, "optane_dashboard", False),
        )
        return store, middleware

    def get_banner(self, config: Any, args: Any) -> Optional[str]:
        if getattr(args, "no_banner", False):
            return None
        pool_kb = config.fizzoptane_pool_size // 1024
        return (
            "  +---------------------------------------------------------+\n"
            "  | FIZZOPTANE: PERSISTENT MEMORY MANAGER                    |\n"
            f"  |   Pool: {pool_kb} KB  Record size: {config.fizzoptane_record_size} bytes              |\n"
            "  |   DAX mapping + CLWB/SFENCE persistence barriers         |\n"
            "  |   Crash-consistent undo-log transactions                  |\n"
            "  +---------------------------------------------------------+"
        )

    def render(self, middleware: Any, args: Any) -> Optional[str]:
        if middleware is None:
            return None
        if not getattr(args, "optane_dashboard", False):
            return None
        from enterprise_fizzbuzz.infrastructure.fizzoptane import OptaneDashboard
        from enterprise_fizzbuzz.infrastructure.config import ConfigurationManager
        config = ConfigurationManager()
        return OptaneDashboard.render(
            middleware.store,
            width=config.fizzoptane_dashboard_width,
        )
