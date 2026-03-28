"""Feature descriptor for the FizzHomomorphic encryption engine."""

from __future__ import annotations

from typing import Any, Optional

from enterprise_fizzbuzz.infrastructure.features._registry import FeatureDescriptor


class FizzHomomorphicFeature(FeatureDescriptor):
    name = "fizzhomomorphic"
    description = "Homomorphic encryption engine with BFV scheme for privacy-preserving FizzBuzz evaluation"
    middleware_priority = 260
    cli_flags = [
        ("--fizzhomomorphic", {"action": "store_true", "default": False,
                               "help": "Enable FizzHomomorphic: evaluate FizzBuzz on encrypted integers"}),
        ("--fizzhomomorphic-poly-degree", {"type": int, "default": 64, "metavar": "N",
                                           "help": "Polynomial modulus degree (power of 2; default: 64)"}),
        ("--fizzhomomorphic-plain-mod", {"type": int, "default": 257, "metavar": "T",
                                         "help": "Plaintext modulus (default: 257)"}),
    ]

    def is_enabled(self, args: Any) -> bool:
        return getattr(args, "fizzhomomorphic", False)

    def create(self, config: Any, args: Any, event_bus: Any = None) -> tuple:
        from enterprise_fizzbuzz.infrastructure.fizzhomomorphic import (
            HomomorphicFizzBuzzEngine,
            FizzHomomorphicMiddleware,
        )

        engine = HomomorphicFizzBuzzEngine(
            poly_degree=getattr(args, "fizzhomomorphic_poly_degree", config.fizzhomomorphic_poly_degree),
            plain_modulus=getattr(args, "fizzhomomorphic_plain_mod", config.fizzhomomorphic_plain_modulus),
        )
        middleware = FizzHomomorphicMiddleware(engine=engine)
        return engine, middleware

    def get_banner(self, config: Any, args: Any) -> Optional[str]:
        if getattr(args, "no_banner", False):
            return None
        return (
            "  +---------------------------------------------------------+\n"
            "  | FIZZHOMOMORPHIC: HOMOMORPHIC ENCRYPTION ENGINE           |\n"
            "  |   Scheme: BFV (Brakerski/Fan-Vercauteren)                |\n"
            "  |   Ring: Z_q[x]/(x^n + 1)  Noise budget tracking         |\n"
            "  |   Operations: Encrypt, Add, Multiply, Decrypt            |\n"
            "  +---------------------------------------------------------+"
        )

    def render(self, middleware: Any, args: Any) -> Optional[str]:
        return None
