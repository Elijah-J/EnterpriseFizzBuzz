"""Query Optimizer events."""

from enterprise_fizzbuzz.domain.events._registry import EventType

EventType.register("OPTIMIZER_PLAN_GENERATED")
EventType.register("OPTIMIZER_PLAN_SELECTED")
EventType.register("OPTIMIZER_PLAN_CACHED")
EventType.register("OPTIMIZER_CACHE_HIT")
EventType.register("OPTIMIZER_EXPLAIN_RENDERED")
