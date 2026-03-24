"""Event Sourcing / CQRS events."""

from enterprise_fizzbuzz.domain.events._registry import EventType

EventType.register("ES_NUMBER_RECEIVED")
EventType.register("ES_DIVISIBILITY_CHECKED")
EventType.register("ES_RULE_MATCHED")
EventType.register("ES_LABEL_ASSIGNED")
EventType.register("ES_EVALUATION_COMPLETED")
EventType.register("ES_SNAPSHOT_TAKEN")
EventType.register("ES_COMMAND_DISPATCHED")
EventType.register("ES_COMMAND_HANDLED")
EventType.register("ES_QUERY_DISPATCHED")
EventType.register("ES_PROJECTION_UPDATED")
EventType.register("ES_EVENT_REPLAYED")
EventType.register("ES_TEMPORAL_QUERY_EXECUTED")
