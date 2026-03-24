"""Anti-Corruption Layer events."""

from enterprise_fizzbuzz.domain.events._registry import EventType

EventType.register("CLASSIFICATION_AMBIGUITY")
EventType.register("STRATEGY_DISAGREEMENT")
