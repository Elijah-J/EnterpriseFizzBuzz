"""Natural Language Query Interface events."""

from enterprise_fizzbuzz.domain.events._registry import EventType

EventType.register("NLQ_QUERY_RECEIVED")
EventType.register("NLQ_TOKENIZATION_COMPLETED")
EventType.register("NLQ_INTENT_CLASSIFIED")
EventType.register("NLQ_ENTITIES_EXTRACTED")
EventType.register("NLQ_QUERY_EXECUTED")
EventType.register("NLQ_SESSION_STARTED")
