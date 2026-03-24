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

        self._es_system = es_system

        return es_system, es_middleware

    def render(self, middleware: Any, args: Any) -> Optional[str]:
        es_system = getattr(self, "_es_system", None)
        if es_system is None:
            return None

        parts = [es_system.render_summary()]

        if getattr(args, "replay", False):
            replay_result = es_system.replay_events()
            parts.append(f"  Replayed {replay_result['replayed_events']} events.")
            parts.append(f"  Statistics after replay: {replay_result['statistics']}")
            parts.append("")

        temporal_seq = getattr(args, "temporal_query", None)
        if temporal_seq is not None:
            temporal_state = es_system.temporal_engine.query_at_sequence(temporal_seq)
            temporal_lines = [
                "  +===========================================================+",
                "  |             TEMPORAL QUERY RESULT                         |",
                "  +===========================================================+",
                f"  |  As-of sequence    : {temporal_seq:<37}|",
                f"  |  Events processed  : {temporal_state['events_processed']:<37}|",
                f"  |  Evaluations       : {temporal_state['total_evaluations']:<37}|",
                "  +===========================================================+",
            ]
            parts.append("\n".join(temporal_lines))

        return "\n".join(parts)
