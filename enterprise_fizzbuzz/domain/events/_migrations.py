"""Database Migration Framework events."""

from enterprise_fizzbuzz.domain.events._registry import EventType

EventType.register("MIGRATION_STARTED")
EventType.register("MIGRATION_APPLIED")
EventType.register("MIGRATION_ROLLED_BACK")
EventType.register("MIGRATION_FAILED")
EventType.register("MIGRATION_SEED_STARTED")
EventType.register("MIGRATION_SEED_COMPLETED")
EventType.register("MIGRATION_SCHEMA_CHANGED")
