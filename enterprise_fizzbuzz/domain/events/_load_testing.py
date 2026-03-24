"""Load Testing Framework events."""

from enterprise_fizzbuzz.domain.events._registry import EventType

EventType.register("LOAD_TEST_STARTED")
EventType.register("LOAD_TEST_COMPLETED")
EventType.register("LOAD_TEST_VU_SPAWNED")
EventType.register("LOAD_TEST_VU_COMPLETED")
EventType.register("LOAD_TEST_REQUEST_COMPLETED")
EventType.register("LOAD_TEST_BOTTLENECK_IDENTIFIED")
