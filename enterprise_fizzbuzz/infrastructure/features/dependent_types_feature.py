"""Feature descriptor for the Dependent Type System and Curry-Howard Proof Engine."""

from __future__ import annotations

from typing import Any, Optional

from enterprise_fizzbuzz.infrastructure.features._registry import FeatureDescriptor


class DependentTypesFeature(FeatureDescriptor):
    name = "dependent_types"
    description = "Dependent type system with Curry-Howard proof engine, bidirectional type checking, and beta-normalization"
    middleware_priority = 59
    cli_flags = [
        ("--dependent-types", {"action": "store_true",
                               "help": "Enable the Dependent Type System & Curry-Howard Proof Engine (every evaluation becomes a theorem)"}),
        ("--prove", {"type": int, "metavar": "N", "default": None,
                     "help": "Construct a fully witnessed proof for a specific number (e.g. --prove 15)"}),
        ("--type-check", {"action": "store_true",
                          "help": "Run bidirectional type checking on all proof terms after evaluation"}),
        ("--types-dashboard", {"action": "store_true",
                               "help": "Display the Dependent Type System & Curry-Howard Proof Engine ASCII dashboard"}),
    ]

    def is_enabled(self, args: Any) -> bool:
        return any([
            getattr(args, "dependent_types", False),
            getattr(args, "prove", None) is not None,
            getattr(args, "type_check", False),
            getattr(args, "types_dashboard", False),
        ])

    def has_early_exit(self, args: Any) -> bool:
        return getattr(args, "prove", None) is not None

    def run_early_exit(self, args: Any, config: Any) -> int:
        from enterprise_fizzbuzz.infrastructure.dependent_types import (
            ProofEngine,
            TypeDashboard,
        )

        engine = ProofEngine(
            max_beta_reductions=config.dependent_types_max_beta_reductions,
            max_unification_depth=config.dependent_types_max_unification_depth,
            enable_cache=config.dependent_types_enable_proof_cache,
            cache_size=config.dependent_types_proof_cache_size,
            enable_type_inference=config.dependent_types_enable_type_inference,
            strict_mode=config.dependent_types_strict_mode,
        )

        proof = engine.prove(args.prove)
        print(TypeDashboard.render_single_proof(
            proof,
            width=config.dependent_types_dashboard_width,
        ))
        if getattr(args, "types_dashboard", False):
            print(TypeDashboard.render(
                engine,
                proofs=[proof],
                width=config.dependent_types_dashboard_width,
                show_curry_howard=config.dependent_types_dashboard_show_curry_howard,
                show_proof_tree=config.dependent_types_dashboard_show_proof_tree,
                show_complexity_index=config.dependent_types_dashboard_show_complexity_index,
            ))
        return 0

    def create(self, config: Any, args: Any, event_bus: Any = None) -> tuple:
        from enterprise_fizzbuzz.infrastructure.dependent_types import ProofEngine

        engine = ProofEngine(
            max_beta_reductions=config.dependent_types_max_beta_reductions,
            max_unification_depth=config.dependent_types_max_unification_depth,
            enable_cache=config.dependent_types_enable_proof_cache,
            cache_size=config.dependent_types_proof_cache_size,
            enable_type_inference=config.dependent_types_enable_type_inference,
            strict_mode=config.dependent_types_strict_mode,
        )

        return engine, None

    def render(self, middleware: Any, args: Any) -> Optional[str]:
        if not getattr(args, "types_dashboard", False):
            return None
        if middleware is None:
            return None
        from enterprise_fizzbuzz.infrastructure.dependent_types import TypeDashboard
        return TypeDashboard.render(
            middleware,
            proofs=None,
            width=60,
            show_curry_howard=True,
            show_proof_tree=True,
            show_complexity_index=True,
        )
