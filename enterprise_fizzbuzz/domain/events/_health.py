"""Health Check Probe events."""

from enterprise_fizzbuzz.domain.events._registry import EventType

EventType.register("HEALTH_CHECK_STARTED")
EventType.register("HEALTH_CHECK_COMPLETED")
EventType.register("HEALTH_LIVENESS_PASSED")
EventType.register("HEALTH_LIVENESS_FAILED")
EventType.register("HEALTH_READINESS_PASSED")
EventType.register("HEALTH_READINESS_FAILED")
EventType.register("HEALTH_STARTUP_MILESTONE")
EventType.register("HEALTH_SELF_HEAL_ATTEMPTED")
