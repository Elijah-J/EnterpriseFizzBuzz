"""Repository Pattern and Unit of Work events."""

from enterprise_fizzbuzz.domain.events._registry import EventType

EventType.register("REPOSITORY_RESULT_ADDED")
EventType.register("REPOSITORY_COMMITTED")
EventType.register("REPOSITORY_ROLLED_BACK")
EventType.register("ROLLBACK_FILE_DELETED")
