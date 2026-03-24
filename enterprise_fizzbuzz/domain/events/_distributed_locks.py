"""Distributed Lock Manager events."""

from enterprise_fizzbuzz.domain.events._registry import EventType

EventType.register("LOCK_ACQUIRED")
EventType.register("LOCK_RELEASED")
EventType.register("LOCK_UPGRADE_REQUESTED")
EventType.register("LOCK_UPGRADE_COMPLETED")
EventType.register("LOCK_ACQUISITION_TIMEOUT")
EventType.register("LOCK_DEADLOCK_DETECTED")
EventType.register("LOCK_TRANSACTION_ABORTED")
EventType.register("LOCK_LEASE_EXPIRED")
EventType.register("LOCK_LEASE_RENEWED")
EventType.register("LOCK_CONTENTION_DETECTED")
EventType.register("LOCK_DASHBOARD_RENDERED")
