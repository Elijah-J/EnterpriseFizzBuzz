"""Cross-Compiler events."""

from enterprise_fizzbuzz.domain.events._registry import EventType

EventType.register("COMPILER_IR_GENERATED")
EventType.register("COMPILER_CODE_EMITTED")
EventType.register("COMPILER_ROUND_TRIP_VERIFIED")
EventType.register("COMPILER_ROUND_TRIP_FAILED")
EventType.register("COMPILER_DASHBOARD_RENDERED")
