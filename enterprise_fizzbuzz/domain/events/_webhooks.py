"""Webhook Notification System events."""

from enterprise_fizzbuzz.domain.events._registry import EventType

EventType.register("WEBHOOK_DISPATCHED")
EventType.register("WEBHOOK_DELIVERY_SUCCESS")
EventType.register("WEBHOOK_DELIVERY_FAILED")
EventType.register("WEBHOOK_RETRY_SCHEDULED")
EventType.register("WEBHOOK_DEAD_LETTERED")
EventType.register("WEBHOOK_SIGNATURE_GENERATED")
