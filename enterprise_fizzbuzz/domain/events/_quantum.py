"""Quantum Computing Simulator events."""

from enterprise_fizzbuzz.domain.events._registry import EventType

EventType.register("QUANTUM_CIRCUIT_INITIALIZED")
EventType.register("QUANTUM_GATE_APPLIED")
EventType.register("QUANTUM_MEASUREMENT_PERFORMED")
EventType.register("QUANTUM_PERIOD_FOUND")
EventType.register("QUANTUM_CLASSICAL_FALLBACK")
EventType.register("QUANTUM_DASHBOARD_RENDERED")
