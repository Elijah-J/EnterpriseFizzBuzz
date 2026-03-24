"""Message Queue and Event Bus events."""

from enterprise_fizzbuzz.domain.events._registry import EventType

EventType.register("MQ_MESSAGE_PUBLISHED")
EventType.register("MQ_MESSAGE_CONSUMED")
EventType.register("MQ_MESSAGE_ACKNOWLEDGED")
EventType.register("MQ_TOPIC_CREATED")
EventType.register("MQ_PARTITION_ASSIGNED")
EventType.register("MQ_CONSUMER_GROUP_JOINED")
EventType.register("MQ_CONSUMER_GROUP_LEFT")
EventType.register("MQ_REBALANCE_STARTED")
EventType.register("MQ_REBALANCE_COMPLETED")
EventType.register("MQ_OFFSET_COMMITTED")
EventType.register("MQ_SCHEMA_VALIDATED")
EventType.register("MQ_SCHEMA_VALIDATION_FAILED")
EventType.register("MQ_DUPLICATE_DETECTED")
EventType.register("MQ_DASHBOARD_RENDERED")
