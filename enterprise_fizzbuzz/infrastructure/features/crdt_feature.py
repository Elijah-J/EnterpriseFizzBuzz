"""Feature descriptor for FizzCRDT conflict-free replicated data types."""

from __future__ import annotations

from typing import Any, Optional

from enterprise_fizzbuzz.infrastructure.features._registry import FeatureDescriptor


class CRDTFeature(FeatureDescriptor):
    name = "crdt"
    description = "Conflict-free replicated data types with join-semilattice merge and strong eventual consistency"
    middleware_priority = 870
    cli_flags = [
        ("--crdt", {"action": "store_true",
                    "help": "Enable FizzCRDT: replicate classification state across simulated replicas using CvRDTs with join-semilattice merge"}),
        ("--crdt-dashboard", {"action": "store_true",
                              "help": "Display the FizzCRDT ASCII dashboard with per-CRDT state, vector clocks, convergence stats, and merge history"}),
    ]

    def is_enabled(self, args: Any) -> bool:
        return any([
            getattr(args, "crdt", False),
            getattr(args, "crdt_dashboard", False),
        ])

    def create(self, config: Any, args: Any, event_bus: Any = None) -> tuple:
        from enterprise_fizzbuzz.infrastructure.crdt import (
            CRDTMergeEngine,
            CRDTMiddleware,
        )

        engine = CRDTMergeEngine()
        middleware = CRDTMiddleware(
            engine=engine,
            replica_count=config.crdt_replica_count,
        )

        return engine, middleware

    def render(self, middleware: Any, args: Any) -> Optional[str]:
        if not getattr(args, "crdt_dashboard", False):
            return None
        if middleware is None:
            return None
        from enterprise_fizzbuzz.infrastructure.crdt import CRDTDashboard
        return CRDTDashboard.render(
            engine=middleware._engine,
            width=60,
        )
