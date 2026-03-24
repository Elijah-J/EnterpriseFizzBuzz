"""Self-Modifying Code events."""

from enterprise_fizzbuzz.domain.events._registry import EventType

EventType.register("SELF_MODIFY_MUTATION_PROPOSED")
EventType.register("SELF_MODIFY_MUTATION_ACCEPTED")
EventType.register("SELF_MODIFY_MUTATION_REVERTED")
EventType.register("SELF_MODIFY_FITNESS_EVALUATED")
EventType.register("SELF_MODIFY_SAFETY_VIOLATION")
EventType.register("SELF_MODIFY_DASHBOARD_RENDERED")
