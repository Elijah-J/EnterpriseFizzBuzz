"""Digital Twin events."""

from enterprise_fizzbuzz.domain.events._registry import EventType

EventType.register("TWIN_MODEL_BUILT")
EventType.register("TWIN_SIMULATION_COMPLETED")
EventType.register("TWIN_DRIFT_DETECTED")
EventType.register("TWIN_DASHBOARD_RENDERED")
