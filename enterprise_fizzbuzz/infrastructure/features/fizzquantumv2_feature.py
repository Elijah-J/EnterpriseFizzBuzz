"""Feature descriptor for the FizzQuantumV2 quantum error correction engine."""

from __future__ import annotations

from typing import Any, Optional

from enterprise_fizzbuzz.infrastructure.features._registry import FeatureDescriptor


class FizzQuantumV2Feature(FeatureDescriptor):
    name = "fizzquantumv2"
    description = "Quantum error correction with surface codes, syndrome measurement, and fault-tolerant gates"
    middleware_priority = 257
    cli_flags = [
        ("--fizzquantumv2", {"action": "store_true", "default": False,
                             "help": "Enable FizzQuantumV2: quantum error-corrected FizzBuzz evaluation"}),
        ("--fizzquantumv2-distance", {"type": int, "default": 3, "metavar": "D",
                                      "help": "Surface code distance (odd, >= 3; default: 3)"}),
        ("--fizzquantumv2-error-rate", {"type": float, "default": 0.001, "metavar": "R",
                                        "help": "Physical qubit error rate (default: 0.001)"}),
    ]

    def is_enabled(self, args: Any) -> bool:
        return getattr(args, "fizzquantumv2", False)

    def create(self, config: Any, args: Any, event_bus: Any = None) -> tuple:
        from enterprise_fizzbuzz.infrastructure.fizzquantumv2 import (
            QuantumErrorCorrectionEngine,
            FizzQuantumV2Middleware,
        )

        engine = QuantumErrorCorrectionEngine(
            distance=getattr(args, "fizzquantumv2_distance", config.fizzquantumv2_distance),
            error_rate=getattr(args, "fizzquantumv2_error_rate", config.fizzquantumv2_error_rate),
        )
        middleware = FizzQuantumV2Middleware(engine=engine)
        return engine, middleware

    def get_banner(self, config: Any, args: Any) -> Optional[str]:
        if getattr(args, "no_banner", False):
            return None
        d = getattr(args, "fizzquantumv2_distance", 3)
        return (
            "  +---------------------------------------------------------+\n"
            "  | FIZZQUANTUMV2: QUANTUM ERROR CORRECTION                 |\n"
            f"  |   Surface code distance: {d}  Correction capacity: {(d-1)//2}     |\n"
            "  |   Decoder: Minimum-weight perfect matching (greedy)      |\n"
            "  |   Fault-tolerant transversal CNOT enabled                |\n"
            "  +---------------------------------------------------------+"
        )

    def render(self, middleware: Any, args: Any) -> Optional[str]:
        return None
