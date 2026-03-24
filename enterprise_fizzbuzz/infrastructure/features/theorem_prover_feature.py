"""Feature descriptor for the FizzProve automated theorem prover."""

from __future__ import annotations

from typing import Any, Optional

from enterprise_fizzbuzz.infrastructure.features._registry import FeatureDescriptor


class TheoremProverFeature(FeatureDescriptor):
    name = "theorem_prover"
    description = "Automated theorem prover via Robinson's resolution for FizzBuzz correctness proofs"
    middleware_priority = 134
    cli_flags = [
        ("--prove-theorem", {"type": str,
                             "choices": ["completeness", "exclusivity", "periodicity", "primality"],
                             "default": None, "metavar": "THEOREM",
                             "help": "Prove a specific FizzBuzz theorem via Robinson's resolution "
                                     "(completeness | exclusivity | periodicity | primality)"}),
        ("--prove-all", {"action": "store_true", "default": False,
                         "help": "Prove all theorems in the FizzBuzz theorem library using automated resolution refutation"}),
        ("--prover-dashboard", {"action": "store_true", "default": False,
                                "help": "Display the FizzProve ASCII dashboard with theorem inventory, proof statistics, and resolution detail"}),
    ]

    def is_enabled(self, args: Any) -> bool:
        return any([
            getattr(args, "prove_theorem", None) is not None,
            getattr(args, "prove_all", False),
            getattr(args, "prover_dashboard", False),
        ])

    def has_early_exit(self, args: Any) -> bool:
        return any([
            getattr(args, "prove_theorem", None) is not None,
            getattr(args, "prove_all", False),
        ])

    def run_early_exit(self, args: Any, config: Any) -> int:
        from enterprise_fizzbuzz.infrastructure.theorem_prover import (
            FizzBuzzTheorems,
            ProverDashboard,
            TheoremStatus,
            prove_all_theorems,
            prove_theorem,
        )

        theorem_map = {
            "completeness": FizzBuzzTheorems.completeness,
            "exclusivity": FizzBuzzTheorems.exclusivity,
            "periodicity": FizzBuzzTheorems.periodicity,
            "primality": FizzBuzzTheorems.primality_exclusion,
        }

        if args.prove_theorem:
            theorem_fn = theorem_map[args.prove_theorem]
            theorem_spec = theorem_fn()
            print(
                "  +---------------------------------------------------------+\n"
                f"  | FIZZPROVE: {theorem_spec[2].upper():<44}|\n"
                "  | Constructing resolution refutation proof...             |\n"
                "  +---------------------------------------------------------+"
            )
            print()

            result = prove_theorem(
                theorem_spec,
                max_clauses=config.theorem_prover_max_clauses,
                max_steps=config.theorem_prover_max_steps,
            )

            status_icon = "\u2713 QED" if result.status == TheoremStatus.PROVED else "\u2717 UNPROVED"
            print(f"  [{status_icon}] {result.name}: {result.description}")
            print(f"  Clauses: {result.proof_tree.clause_count} | "
                  f"Resolutions: {result.proof_tree.resolution_count} | "
                  f"Time: {result.elapsed_ms:.2f}ms")
            print()

            print(ProverDashboard.render_proof(
                result.proof_tree,
                width=config.theorem_prover_dashboard_width,
            ))

            if args.prover_dashboard:
                print()
                print(ProverDashboard.render(
                    [result],
                    width=config.theorem_prover_dashboard_width,
                ))

            return 0

        # Prove all theorems
        print(
            "  +---------------------------------------------------------+\n"
            "  | FIZZPROVE -- AUTOMATED THEOREM PROVER                   |\n"
            "  | Proving all FizzBuzz theorems via Robinson's resolution  |\n"
            "  | refutation with set-of-support strategy.                |\n"
            "  | Because correctness must be earned, not assumed.         |\n"
            "  +---------------------------------------------------------+"
        )
        print()
        print(f"  Max clauses: {config.theorem_prover_max_clauses}")
        print(f"  Max steps:   {config.theorem_prover_max_steps}")
        print()

        results = prove_all_theorems(
            max_clauses=config.theorem_prover_max_clauses,
            max_steps=config.theorem_prover_max_steps,
        )

        for result in results:
            status_icon = "\u2713 QED" if result.status == TheoremStatus.PROVED else "\u2717 UNPROVED"
            print(f"  [{status_icon}] {result.name}: {result.description}")
            print(f"      Clauses: {result.proof_tree.clause_count} | "
                  f"Resolutions: {result.proof_tree.resolution_count} | "
                  f"Time: {result.elapsed_ms:.2f}ms")
        print()

        proved = sum(1 for r in results if r.status == TheoremStatus.PROVED)
        print(f"  Summary: {proved}/{len(results)} theorems proved.")
        print()

        if args.prover_dashboard:
            print(ProverDashboard.render(
                results,
                width=config.theorem_prover_dashboard_width,
            ))

        return 0

    def create(self, config: Any, args: Any, event_bus: Any = None) -> tuple:
        return None, None

    def render(self, middleware: Any, args: Any) -> Optional[str]:
        return None
