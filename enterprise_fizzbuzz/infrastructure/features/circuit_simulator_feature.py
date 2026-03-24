"""Feature descriptor for the FizzGate digital logic circuit simulator."""

from __future__ import annotations

from typing import Any, Optional

from enterprise_fizzbuzz.infrastructure.features._registry import FeatureDescriptor


class CircuitSimulatorFeature(FeatureDescriptor):
    name = "circuit_simulator"
    description = "Gate-level digital logic simulation for FizzBuzz divisibility checking with waveform output"
    middleware_priority = 143
    cli_flags = [
        ("--fizzgate", {"action": "store_true", "default": False,
                        "help": "Enable FizzGate: gate-level digital logic simulation for FizzBuzz divisibility checking"}),
        ("--fizzgate-waveform", {"action": "store_true", "default": False,
                                 "help": "Display ASCII waveform timing diagrams of circuit signal transitions"}),
        ("--fizzgate-dashboard", {"action": "store_true", "default": False,
                                  "help": "Display the FizzGate ASCII dashboard with circuit topology, gate counts, and critical path analysis"}),
    ]

    def is_enabled(self, args: Any) -> bool:
        return any([
            getattr(args, "fizzgate", False),
            getattr(args, "fizzgate_waveform", False),
            getattr(args, "fizzgate_dashboard", False),
        ])

    def create(self, config: Any, args: Any, event_bus: Any = None) -> tuple:
        from enterprise_fizzbuzz.infrastructure.circuit_simulator import (
            CircuitMiddleware,
        )

        circuit_middleware = CircuitMiddleware(
            event_bus=event_bus,
            enable_waveform=getattr(args, "fizzgate_waveform", False) or config.circuit_enable_waveform,
            enable_dashboard=getattr(args, "fizzgate_dashboard", False) or config.circuit_enable_dashboard,
        )

        return circuit_middleware, circuit_middleware

    def get_banner(self, config: Any, args: Any) -> Optional[str]:
        return (
            "  +---------------------------------------------------------+\n"
            "  | FIZZGATE: DIGITAL LOGIC CIRCUIT SIMULATOR               |\n"
            "  |   Gate-level divisibility verification enabled           |\n"
            "  |   Modulo-3 and Modulo-5 circuits active                 |\n"
            "  +---------------------------------------------------------+"
        )

    def render(self, middleware: Any, args: Any) -> Optional[str]:
        if middleware is None:
            if getattr(args, "fizzgate_dashboard", False):
                return "  FizzGate not enabled. Use --fizzgate to enable."
            if getattr(args, "fizzgate_waveform", False):
                return "  FizzGate not enabled. Use --fizzgate to enable."
            return None

        from enterprise_fizzbuzz.infrastructure.circuit_simulator import (
            CircuitDashboard,
        )

        parts = []

        if getattr(args, "fizzgate_dashboard", False):
            classifier = getattr(middleware, "classifier", None)
            if classifier is not None:
                parts.append(CircuitDashboard.render(
                    classifier=classifier,
                    simulation_results=middleware.results,
                    width=80,
                ))
            else:
                parts.append("  FizzGate circuit has not been exercised yet.")

        if getattr(args, "fizzgate_waveform", False):
            results = getattr(middleware, "results", None)
            if results:
                last_result = results[-1]
                waveform = last_result.get("waveform")
                if waveform is not None:
                    parts.append("  FizzGate Signal Waveform (last evaluation):")
                    parts.append(waveform.render_ascii(width=80))
            else:
                parts.append("  FizzGate has no simulation results to display.")

        return "\n".join(parts) if parts else None
