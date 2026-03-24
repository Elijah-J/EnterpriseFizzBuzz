"""Time-Travel Debugger events."""

from enterprise_fizzbuzz.domain.events._registry import EventType

EventType.register("TIME_TRAVEL_SNAPSHOT_CAPTURED")
EventType.register("TIME_TRAVEL_NAVIGATION")
EventType.register("TIME_TRAVEL_BREAKPOINT_HIT")
EventType.register("TIME_TRAVEL_ANOMALY_DETECTED")
EventType.register("TIME_TRAVEL_DASHBOARD_RENDERED")
