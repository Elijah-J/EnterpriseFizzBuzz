"""Feature Flag events."""

from enterprise_fizzbuzz.domain.events._registry import EventType

EventType.register("FLAG_EVALUATED")
EventType.register("FLAG_STATE_CHANGED")
EventType.register("FLAG_DEPENDENCY_RESOLVED")
EventType.register("FLAG_ROLLOUT_DECISION")
