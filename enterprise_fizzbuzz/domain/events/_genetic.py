"""Genetic Algorithm events."""

from enterprise_fizzbuzz.domain.events._registry import EventType

EventType.register("GENETIC_EVOLUTION_STARTED")
EventType.register("GENETIC_GENERATION_COMPLETED")
EventType.register("GENETIC_MUTATION_APPLIED")
EventType.register("GENETIC_CROSSOVER_PERFORMED")
EventType.register("GENETIC_MASS_EXTINCTION")
EventType.register("GENETIC_CONVERGENCE_DETECTED")
EventType.register("GENETIC_HALL_OF_FAME_UPDATED")
EventType.register("GENETIC_EVOLUTION_COMPLETED")
