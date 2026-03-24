"""Feature descriptor for the quantum computing simulator."""

from __future__ import annotations

from typing import Any, Optional

from enterprise_fizzbuzz.infrastructure.features._registry import FeatureDescriptor


class QuantumFeature(FeatureDescriptor):
    name = "quantum"
    description = "Quantum computing simulator using Shor's algorithm for FizzBuzz divisibility checking"
    middleware_priority = 42
    cli_flags = [
        ("--quantum", {"action": "store_true", "default": False,
                       "help": "Enable the Quantum Computing Simulator: use Shor's algorithm for FizzBuzz divisibility checking"}),
        ("--quantum-circuit", {"action": "store_true", "default": False,
                               "help": "Display the ASCII quantum circuit diagram for the divisibility checking circuit"}),
        ("--quantum-dashboard", {"action": "store_true", "default": False,
                                 "help": "Display the Quantum Computing Simulator ASCII dashboard with negative advantage ratios"}),
    ]

    def is_enabled(self, args: Any) -> bool:
        return any([
            getattr(args, "quantum", False),
            getattr(args, "quantum_circuit", False),
            getattr(args, "quantum_dashboard", False),
        ])

    def create(self, config: Any, args: Any, event_bus: Any = None) -> tuple:
        from enterprise_fizzbuzz.infrastructure.quantum import (
            CircuitVisualizer,
            QuantumFizzBuzzEngine,
            QuantumMiddleware,
            build_qft_circuit,
        )

        quantum_rules = [
            {"name": r.name, "divisor": r.divisor, "label": r.label, "priority": r.priority}
            for r in config.rules
        ]

        engine = QuantumFizzBuzzEngine(
            rules=quantum_rules,
            num_qubits=config.quantum_num_qubits,
            max_attempts=config.quantum_max_measurement_attempts,
            decoherence_threshold=config.quantum_decoherence_threshold,
            max_period_attempts=config.quantum_shor_max_period_attempts,
            fallback_to_classical=config.quantum_fallback_to_classical,
        )

        middleware = QuantumMiddleware(
            engine=engine,
            event_bus=event_bus,
        )

        # Build a sample QFT circuit for visualization
        sample_circuit = build_qft_circuit(config.quantum_num_qubits)
        sample_circuit.measure_all()
        engine._sample_circuit = sample_circuit

        # Show circuit diagram if requested
        if getattr(args, "quantum_circuit", False):
            print()
            print("  Quantum Period-Finding Circuit (QFT):")
            print(CircuitVisualizer.render(sample_circuit, width=58))
            print()

        return engine, middleware

    def render(self, middleware: Any, args: Any) -> Optional[str]:
        if middleware is None:
            return None
        if not getattr(args, "quantum_dashboard", False):
            return None
        from enterprise_fizzbuzz.infrastructure.quantum import QuantumDashboard
        engine = middleware._engine if hasattr(middleware, "_engine") else None
        if engine is None:
            return None
        circuit = getattr(engine, "_sample_circuit", None)
        return QuantumDashboard.render(
            engine,
            circuit=circuit,
            width=60,
            show_circuit=True,
        )
