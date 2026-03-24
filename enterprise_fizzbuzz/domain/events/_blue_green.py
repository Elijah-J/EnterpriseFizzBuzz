"""Blue/Green Deployment Simulation events."""

from enterprise_fizzbuzz.domain.events._registry import EventType

EventType.register("DEPLOYMENT_STARTED")
EventType.register("DEPLOYMENT_SLOT_PROVISIONED")
EventType.register("DEPLOYMENT_SHADOW_TRAFFIC_STARTED")
EventType.register("DEPLOYMENT_SHADOW_TRAFFIC_COMPLETED")
EventType.register("DEPLOYMENT_SMOKE_TEST_STARTED")
EventType.register("DEPLOYMENT_SMOKE_TEST_PASSED")
EventType.register("DEPLOYMENT_SMOKE_TEST_FAILED")
EventType.register("DEPLOYMENT_BAKE_PERIOD_STARTED")
EventType.register("DEPLOYMENT_BAKE_PERIOD_COMPLETED")
EventType.register("DEPLOYMENT_CUTOVER_INITIATED")
EventType.register("DEPLOYMENT_CUTOVER_COMPLETED")
EventType.register("DEPLOYMENT_ROLLBACK_INITIATED")
EventType.register("DEPLOYMENT_ROLLBACK_COMPLETED")
EventType.register("DEPLOYMENT_DASHBOARD_RENDERED")
