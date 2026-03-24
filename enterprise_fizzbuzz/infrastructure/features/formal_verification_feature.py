"""Feature descriptor for the Formal Verification & Proof System subsystem."""

from __future__ import annotations

from typing import Any, Optional

from enterprise_fizzbuzz.infrastructure.features._registry import FeatureDescriptor


class FormalVerificationFeature(FeatureDescriptor):
    name = "formal_verification"
    description = "Prove totality, determinism, completeness, and correctness via structural induction"
    middleware_priority = 0
    cli_flags = [
        ("--verify", {"action": "store_true", "default": False,
                      "help": "Run the Formal Verification engine: prove totality, determinism, completeness, and correctness of FizzBuzz evaluation via structural induction"}),
        ("--verify-property", {"type": str,
                               "choices": ["totality", "determinism", "completeness", "correctness"],
                               "default": None, "metavar": "PROPERTY",
                               "help": "Verify a single property (totality | determinism | completeness | correctness)"}),
        ("--proof-tree", {"action": "store_true", "default": False,
                          "help": "Display the Gentzen-style natural deduction proof tree for the induction proof"}),
        ("--verify-dashboard", {"action": "store_true", "default": False,
                                "help": "Display the Formal Verification ASCII dashboard with QED status and proof obligations"}),
    ]

    def is_enabled(self, args: Any) -> bool:
        return any([
            getattr(args, "verify", False),
            bool(getattr(args, "verify_property", None)),
            getattr(args, "proof_tree", False),
            getattr(args, "verify_dashboard", False),
        ])

    def has_early_exit(self, args: Any) -> bool:
        return self.is_enabled(args)

    def run_early_exit(self, args: Any, config: Any) -> int:
        from enterprise_fizzbuzz.infrastructure.formal_verification import (
            PropertyVerifier,
            VerificationDashboard,
        )

        verifier = PropertyVerifier(
            rules=config.rules,
            proof_depth=config.formal_verification_proof_depth,
            timeout_ms=config.formal_verification_timeout_ms,
        )

        if args.verify_property:
            prop_map = {
                "totality": ("verify_totality", "TOTALITY"),
                "determinism": ("verify_determinism", "DETERMINISM"),
                "completeness": ("verify_completeness", "COMPLETENESS"),
                "correctness": ("verify_correctness", "CORRECTNESS"),
            }
            method_name, prop_name = prop_map[args.verify_property]
            print(
                "  +---------------------------------------------------------+\n"
                f"  | FORMAL VERIFICATION: {prop_name:<36}|\n"
                "  | Verifying property against StandardRuleEngine oracle... |\n"
                "  +---------------------------------------------------------+"
            )
            print()

            obligation = getattr(verifier, method_name)()
            status_icon = "\u2713 QED" if obligation.is_discharged else "\u2717 FAIL"
            print(f"  [{status_icon}] {prop_name}: {obligation.description}")
            print(f"  Time: {obligation.elapsed_ms:.2f}ms")
            if obligation.counterexample is not None:
                print(f"  Counterexample: {obligation.counterexample}")
            print()

            if obligation.proof_tree is not None and args.proof_tree:
                from enterprise_fizzbuzz.infrastructure.formal_verification import VerificationReport
                mini_report = VerificationReport(
                    obligations=[obligation],
                    total_elapsed_ms=obligation.elapsed_ms,
                    proof_depth=config.formal_verification_proof_depth,
                    rules=config.rules,
                )
                print(VerificationDashboard.render_proof_tree(
                    mini_report, width=config.formal_verification_dashboard_width
                ))

            return 0

        # Full verification
        print(
            "  +---------------------------------------------------------+\n"
            "  | ENTERPRISE FIZZBUZZ FORMAL VERIFICATION ENGINE          |\n"
            "  | Constructing proofs of totality, determinism,           |\n"
            "  | completeness, and correctness via structural induction. |\n"
            "  | Because trust is earned, not assumed.                   |\n"
            "  +---------------------------------------------------------+"
        )
        print()
        print(f"  Proof depth: {config.formal_verification_proof_depth}")
        print(f"  Rules: {len(config.rules)}")
        print()

        report = verifier.verify_all()
        print(report.summary())
        print()

        if args.proof_tree:
            print(VerificationDashboard.render_proof_tree(
                report, width=config.formal_verification_dashboard_width
            ))

        if args.verify_dashboard:
            print(VerificationDashboard.render(
                report, width=config.formal_verification_dashboard_width
            ))

        return 0

    def create(self, config: Any, args: Any, event_bus: Any = None) -> tuple:
        return None, None

    def render(self, middleware: Any, args: Any) -> Optional[str]:
        return None
