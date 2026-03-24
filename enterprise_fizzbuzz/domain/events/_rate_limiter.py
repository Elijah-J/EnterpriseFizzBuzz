"""Rate Limiting and API Quota Management events."""

from enterprise_fizzbuzz.domain.events._registry import EventType

EventType.register("RATE_LIMIT_CHECK_STARTED")
EventType.register("RATE_LIMIT_CHECK_PASSED")
EventType.register("RATE_LIMIT_CHECK_FAILED")
EventType.register("RATE_LIMIT_QUOTA_CONSUMED")
EventType.register("RATE_LIMIT_QUOTA_REPLENISHED")
EventType.register("RATE_LIMIT_BURST_CREDIT_USED")
EventType.register("RATE_LIMIT_BURST_CREDIT_EARNED")
EventType.register("RATE_LIMIT_RESERVATION_CREATED")
EventType.register("RATE_LIMIT_RESERVATION_EXPIRED")
EventType.register("RATE_LIMIT_DASHBOARD_RENDERED")
