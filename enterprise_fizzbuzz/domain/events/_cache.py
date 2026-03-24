"""Cache events."""

from enterprise_fizzbuzz.domain.events._registry import EventType

EventType.register("CACHE_HIT")
EventType.register("CACHE_MISS")
EventType.register("CACHE_EVICTION")
EventType.register("CACHE_INVALIDATION")
EventType.register("CACHE_WARMING")
EventType.register("CACHE_COHERENCE_TRANSITION")
EventType.register("CACHE_EULOGY_COMPOSED")
