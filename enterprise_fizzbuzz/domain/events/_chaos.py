"""Chaos Engineering events."""

from enterprise_fizzbuzz.domain.events._registry import EventType

EventType.register("CHAOS_MONKEY_ACTIVATED")
EventType.register("CHAOS_FAULT_INJECTED")
EventType.register("CHAOS_RESULT_CORRUPTED")
EventType.register("CHAOS_LATENCY_INJECTED")
EventType.register("CHAOS_EXCEPTION_INJECTED")
EventType.register("CHAOS_GAMEDAY_STARTED")
EventType.register("CHAOS_GAMEDAY_ENDED")
