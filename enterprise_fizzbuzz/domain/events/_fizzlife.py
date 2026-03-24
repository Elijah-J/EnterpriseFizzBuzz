"""FizzLife events."""

from enterprise_fizzbuzz.domain.events._registry import EventType

EventType.register("FIZZLIFE_SIMULATION_STARTED")
EventType.register("FIZZLIFE_GENERATION_ADVANCED")
EventType.register("FIZZLIFE_SPECIES_DETECTED")
EventType.register("FIZZLIFE_SPECIES_EXTINCT")
EventType.register("FIZZLIFE_MASS_FLOW_COMPUTED")
EventType.register("FIZZLIFE_EQUILIBRIUM_REACHED")
EventType.register("FIZZLIFE_PATTERN_CLASSIFIED")
EventType.register("FIZZLIFE_EVOLUTION_STARTED")
EventType.register("FIZZLIFE_EVOLUTION_GENERATION")
EventType.register("FIZZLIFE_DASHBOARD_RENDERED")
