"""A/B Testing Framework events."""

from enterprise_fizzbuzz.domain.events._registry import EventType

EventType.register("AB_TEST_EXPERIMENT_CREATED")
EventType.register("AB_TEST_EXPERIMENT_STARTED")
EventType.register("AB_TEST_EXPERIMENT_STOPPED")
EventType.register("AB_TEST_VARIANT_ASSIGNED")
EventType.register("AB_TEST_METRIC_RECORDED")
EventType.register("AB_TEST_SIGNIFICANCE_REACHED")
EventType.register("AB_TEST_RAMP_ADVANCED")
EventType.register("AB_TEST_AUTO_ROLLBACK")
EventType.register("AB_TEST_REPORT_GENERATED")
EventType.register("AB_TEST_VERDICT_REACHED")
