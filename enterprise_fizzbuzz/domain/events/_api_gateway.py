"""API Gateway events."""

from enterprise_fizzbuzz.domain.events._registry import EventType

EventType.register("GATEWAY_REQUEST_RECEIVED")
EventType.register("GATEWAY_REQUEST_ROUTED")
EventType.register("GATEWAY_REQUEST_TRANSFORMED")
EventType.register("GATEWAY_RESPONSE_TRANSFORMED")
EventType.register("GATEWAY_VERSION_RESOLVED")
EventType.register("GATEWAY_DEPRECATION_WARNING")
EventType.register("GATEWAY_API_KEY_VALIDATED")
EventType.register("GATEWAY_API_KEY_REJECTED")
EventType.register("GATEWAY_QUOTA_EXCEEDED")
EventType.register("GATEWAY_REQUEST_REPLAYED")
EventType.register("GATEWAY_DASHBOARD_RENDERED")
