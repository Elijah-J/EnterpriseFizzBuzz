"""Feature descriptor for the Message Queue & Event Bus subsystem."""

from __future__ import annotations

from typing import Any, Optional

from enterprise_fizzbuzz.infrastructure.features._registry import FeatureDescriptor


class MessageQueueFeature(FeatureDescriptor):
    name = "message_queue"
    description = "Kafka-style message queue with topics, partitions, consumer groups, and exactly-once delivery"
    middleware_priority = 86
    cli_flags = [
        ("--mq", {"action": "store_true", "default": False,
                  "help": "Enable the Kafka-style Message Queue backed by Python lists"}),
        ("--mq-dashboard", {"action": "store_true", "default": False,
                            "help": "Display the message queue ASCII dashboard after execution"}),
        ("--mq-topics", {"action": "store_true", "default": False,
                         "help": "Display all message queue topics and exit"}),
        ("--mq-lag", {"action": "store_true", "default": False,
                      "help": "Display consumer lag report after execution"}),
    ]

    def is_enabled(self, args: Any) -> bool:
        return any([
            getattr(args, "mq", False),
            getattr(args, "mq_dashboard", False),
            getattr(args, "mq_topics", False),
            getattr(args, "mq_lag", False),
        ])

    def create(self, config: Any, args: Any, event_bus: Any = None) -> tuple:
        from enterprise_fizzbuzz.infrastructure.message_queue import create_message_queue_subsystem

        mq_broker, mq_producer, mq_middleware, mq_bridge = create_message_queue_subsystem(
            event_bus=event_bus,
            default_partitions=config.mq_default_partitions,
            partitioner_strategy=config.mq_partitioner_strategy,
            enable_schema_validation=config.mq_enable_schema_validation,
            enable_idempotency=config.mq_enable_idempotency,
            max_poll_records=config.mq_max_poll_records,
            topic_configs=config.mq_topics,
            consumer_group_configs=config.mq_consumer_groups,
        )

        # Subscribe the bridge to the event bus
        if event_bus is not None and mq_bridge is not None:
            event_bus.subscribe(mq_bridge)

        return mq_broker, mq_middleware

    def has_early_exit(self, args: Any) -> bool:
        return getattr(args, "mq_topics", False) and not getattr(args, "mq", False)

    def run_early_exit(self, args: Any, config: Any) -> int:
        print("\n  Message queue not enabled. Use --mq to enable.\n")
        return 0

    def render(self, middleware: Any, args: Any) -> Optional[str]:
        if middleware is None:
            return None

        from enterprise_fizzbuzz.infrastructure.message_queue import MQDashboard

        parts = []

        if getattr(args, "mq_dashboard", False):
            # The broker is stored as the service (first tuple element)
            # middleware is the MQMiddleware (second tuple element)
            if hasattr(middleware, "_broker"):
                parts.append(MQDashboard.render(middleware._broker, width=64))

        if getattr(args, "mq_lag", False):
            if hasattr(middleware, "_broker"):
                parts.append(MQDashboard.render_lag(middleware._broker, width=64))

        return "\n".join(parts) if parts else None
