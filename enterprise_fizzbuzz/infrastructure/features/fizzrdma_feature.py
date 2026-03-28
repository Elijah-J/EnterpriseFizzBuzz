"""Feature descriptor for the FizzRDMA Remote DMA Engine."""

from __future__ import annotations

from typing import Any, Optional

from enterprise_fizzbuzz.infrastructure.features._registry import FeatureDescriptor


class FizzrdmaFeature(FeatureDescriptor):
    name = "fizzrdma"
    description = "Remote DMA engine with send/recv/read/write verbs, completion queues, memory regions, protection domains, and queue pairs for zero-copy FizzBuzz result transfer"
    middleware_priority = 252
    cli_flags = [
        ("--rdma", {"action": "store_true", "default": False,
                    "help": "Enable the FizzRDMA remote DMA engine"}),
        ("--rdma-dashboard", {"action": "store_true", "default": False,
                              "help": "Display the FizzRDMA ASCII dashboard"}),
    ]

    def is_enabled(self, args: Any) -> bool:
        return any([
            getattr(args, "rdma", False),
            getattr(args, "rdma_dashboard", False),
        ])

    def has_early_exit(self, args: Any) -> bool:
        return False

    def run_early_exit(self, args: Any, config: Any) -> int:
        return 0

    def create(self, config: Any, args: Any, event_bus: Any = None) -> tuple:
        from enterprise_fizzbuzz.infrastructure.fizzrdma import create_fizzrdma_subsystem

        ctx, middleware = create_fizzrdma_subsystem()
        return ctx, middleware

    def render(self, middleware: Any, args: Any) -> Optional[str]:
        if not getattr(args, "rdma_dashboard", False):
            return None
        if middleware is None:
            return "\n  FizzRDMA not enabled. Use --rdma to enable.\n"

        from enterprise_fizzbuzz.infrastructure.fizzrdma import RDMADashboard

        ctx = middleware.ctx if hasattr(middleware, "ctx") else None
        if ctx is not None:
            return RDMADashboard.render(ctx)
        return None
