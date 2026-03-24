"""Feature descriptor for the Event Sourcing / CQRS subsystem."""

from __future__ import annotations

from typing import Any, Optional

from enterprise_fizzbuzz.infrastructure.features._registry import FeatureDescriptor


class EventSourcingFeature(FeatureDescriptor):
    name = "event_sourcing"
    description = "Event Sourcing with CQRS for append-only FizzBuzz audit logging"
    middleware_priority = 90
    cli_flags = [
        ("--event-sourcing", {"action": "store_true",
                              "help": "Enable Event Sourcing with CQRS for append-only FizzBuzz audit logging"}),
        ("--replay", {"action": "store_true",
                      "help": "Replay all events from the event store to rebuild projections"}),
        ("--temporal-query", {"type": int, "metavar": "SEQ", "default": None,
                              "help": "Reconstruct FizzBuzz state at a specific event sequence number"}),
    ]

    def is_enabled(self, args: Any) -> bool:
        return getattr(args, "event_sourcing", False)

    def create(self, config: Any, args: Any, event_bus: Any = None) -> tuple:
        from enterprise_fizzbuzz.infrastructure.event_sourcing import EventSourcingSystem

        es_system = EventSourcingSystem(
            snapshot_interval=config.event_sourcing_snapshot_interval,
        )
        es_middleware = es_system.create_middleware()

        return es_system, es_middleware
