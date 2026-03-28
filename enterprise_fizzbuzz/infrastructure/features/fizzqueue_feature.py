"""Feature descriptor for the FizzQueue AMQP-compatible message broker."""
from __future__ import annotations
from typing import Any, Optional
from enterprise_fizzbuzz.infrastructure.features._registry import FeatureDescriptor

class FizzQueueFeature(FeatureDescriptor):
    name = "fizzqueue"
    description = "AMQP-compatible message broker with exchanges, queues, bindings, and dead-letter routing"
    middleware_priority = 134
    cli_flags = [
        ("--fizzqueue", {"action": "store_true", "default": False, "help": "Enable FizzQueue message broker"}),
        ("--fizzqueue-publish", {"type": str, "default": None, "help": "Publish message (exchange:routing_key:body)"}),
        ("--fizzqueue-consume", {"type": str, "default": None, "help": "Consume from queue"}),
        ("--fizzqueue-list-exchanges", {"action": "store_true", "default": False, "help": "List exchanges"}),
        ("--fizzqueue-list-queues", {"action": "store_true", "default": False, "help": "List queues"}),
        ("--fizzqueue-list-bindings", {"action": "store_true", "default": False, "help": "List bindings"}),
        ("--fizzqueue-stats", {"action": "store_true", "default": False, "help": "Display broker statistics"}),
        ("--fizzqueue-purge", {"type": str, "default": None, "help": "Purge a queue"}),
        ("--fizzqueue-dlq", {"action": "store_true", "default": False, "help": "Show dead-letter queue contents"}),
    ]

    def is_enabled(self, args: Any) -> bool:
        return any([getattr(args, "fizzqueue", False), getattr(args, "fizzqueue_list_queues", False),
                    getattr(args, "fizzqueue_stats", False), getattr(args, "fizzqueue_publish", None)])

    def create(self, config: Any, args: Any, event_bus: Any = None) -> tuple:
        from enterprise_fizzbuzz.infrastructure.fizzqueue import FizzQueueMiddleware, create_fizzqueue_subsystem
        broker, dashboard, mw = create_fizzqueue_subsystem(
            max_queues=config.fizzqueue_max_queues, prefetch=config.fizzqueue_prefetch,
            dashboard_width=config.fizzqueue_dashboard_width,
        )
        return broker, mw

    def render(self, middleware: Any, args: Any) -> Optional[str]:
        if middleware is None: return None
        parts = []
        if getattr(args, "fizzqueue_list_exchanges", False): parts.append(middleware.render_exchanges())
        if getattr(args, "fizzqueue_list_queues", False): parts.append(middleware.render_queues())
        if getattr(args, "fizzqueue_stats", False): parts.append(middleware.render_stats())
        if getattr(args, "fizzqueue", False) and not parts: parts.append(middleware.render_dashboard())
        return "\n".join(parts) if parts else None
