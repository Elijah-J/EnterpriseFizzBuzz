"""Feature descriptor for the FizzCheck formal model checker."""

from __future__ import annotations

from typing import Any, Optional

from enterprise_fizzbuzz.infrastructure.features._registry import FeatureDescriptor


class ModelCheckerFeature(FeatureDescriptor):
    name = "model_checker"
    description = "TLA+-style temporal logic model checking for verification of all stateful subsystems"
    middleware_priority = 142
    cli_flags = [
        ("--model-check", {"action": "store_true", "default": False,
                           "help": "Enable FizzCheck: TLA+-style temporal logic model checking of all stateful subsystems"}),
        ("--model-check-property", {"type": str, "default": None, "metavar": "NAME",
                                    "help": "Verify a specific named property only (e.g., 'MESI: reachability of valid state')"}),
        ("--model-check-dashboard", {"action": "store_true", "default": False,
                                     "help": "Display the FizzCheck ASCII dashboard with verification results, counterexamples, and reduction stats"}),
    ]

    def is_enabled(self, args: Any) -> bool:
        return any([
            getattr(args, "model_check", False),
            getattr(args, "model_check_property", None) is not None,
            getattr(args, "model_check_dashboard", False),
        ])

    def create(self, config: Any, args: Any, event_bus: Any = None) -> tuple:
        from enterprise_fizzbuzz.infrastructure.model_checker import (
            ModelCheckerMiddleware,
        )

        mc_middleware = ModelCheckerMiddleware(
            max_states=config.model_check_max_states,
        )

        return mc_middleware, mc_middleware

    def get_banner(self, config: Any, args: Any) -> Optional[str]:
        return (
            "  +---------------------------------------------------------+\n"
            "  | FIZZCHECK FORMAL MODEL CHECKING ENABLED                 |\n"
            "  | TLA+-style temporal logic verification active           |\n"
            "  | Models: MESI cache | Circuit breaker | Middleware       |\n"
            '  | "Every state machine deserves formal verification."     |\n'
            "  | Correctness is not optional. It is proven.              |\n"
            "  +---------------------------------------------------------+"
        )

    def render(self, middleware: Any, args: Any) -> Optional[str]:
        if middleware is None:
            if getattr(args, "model_check_dashboard", False):
                return "  FizzCheck not enabled. Use --model-check to enable."
            return None

        from enterprise_fizzbuzz.infrastructure.model_checker import (
            ModelCheckerDashboard,
        )

        parts = []

        if getattr(args, "model_check_dashboard", False):
            if getattr(middleware, "results", None) is None:
                middleware._results = middleware._run_verification()
                middleware._checked = True
            parts.append(ModelCheckerDashboard.render(
                results=middleware.results,
                width=80,
            ))

        return "\n".join(parts) if parts else None
