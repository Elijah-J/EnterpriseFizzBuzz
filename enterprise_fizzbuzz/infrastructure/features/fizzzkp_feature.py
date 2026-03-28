"""Feature descriptor for the FizzZKP zero-knowledge proof system."""

from __future__ import annotations

from typing import Any, Optional

from enterprise_fizzbuzz.infrastructure.features._registry import FeatureDescriptor


class FizzZKPFeature(FeatureDescriptor):
    name = "fizzzkp"
    description = "Zero-knowledge proof system with Schnorr proofs, Pedersen commitments, and Fiat-Shamir transform"
    middleware_priority = 261
    cli_flags = [
        ("--fizzzkp", {"action": "store_true", "default": False,
                       "help": "Enable FizzZKP: attach zero-knowledge proofs to FizzBuzz evaluations"}),
        ("--fizzzkp-audit-trail", {"action": "store_true", "default": True,
                                   "help": "Maintain full proof transcript audit trail (default: enabled)"}),
    ]

    def is_enabled(self, args: Any) -> bool:
        return getattr(args, "fizzzkp", False)

    def create(self, config: Any, args: Any, event_bus: Any = None) -> tuple:
        from enterprise_fizzbuzz.infrastructure.fizzzkp import (
            ZKPFizzBuzzEngine,
            FizzZKPMiddleware,
        )

        engine = ZKPFizzBuzzEngine()
        middleware = FizzZKPMiddleware(engine=engine)
        return engine, middleware

    def get_banner(self, config: Any, args: Any) -> Optional[str]:
        if getattr(args, "no_banner", False):
            return None
        return (
            "  +---------------------------------------------------------+\n"
            "  | FIZZZKP: ZERO-KNOWLEDGE PROOF SYSTEM                    |\n"
            "  |   Protocol: Schnorr sigma protocol                       |\n"
            "  |   Commitments: Pedersen (hiding + binding)                |\n"
            "  |   Non-interactive: Fiat-Shamir heuristic                  |\n"
            "  +---------------------------------------------------------+"
        )

    def render(self, middleware: Any, args: Any) -> Optional[str]:
        return None
