"""Feature descriptor for the FizzQuantumChem quantum chemistry engine."""

from __future__ import annotations

from typing import Any, Optional

from enterprise_fizzbuzz.infrastructure.features._registry import FeatureDescriptor


class FizzQuantumChemFeature(FeatureDescriptor):
    name = "fizzquantumchem"
    description = "Quantum chemistry with Hartree-Fock SCF, STO-3G basis sets, molecular orbital theory, and energy minimization"
    middleware_priority = 285
    cli_flags = [
        ("--fizzquantumchem", {"action": "store_true", "default": False,
                               "help": "Enable FizzQuantumChem: ab initio electronic structure of FizzBuzz molecules"}),
        ("--fizzquantumchem-max-scf", {"type": int, "metavar": "N", "default": None,
                                        "help": "Maximum SCF iterations (default: 100)"}),
        ("--fizzquantumchem-threshold", {"type": float, "metavar": "E", "default": None,
                                          "help": "SCF convergence threshold in Hartree (default: 1e-6)"}),
    ]

    def is_enabled(self, args: Any) -> bool:
        return getattr(args, "fizzquantumchem", False)

    def create(self, config: Any, args: Any, event_bus: Any = None) -> tuple:
        from enterprise_fizzbuzz.infrastructure.fizzquantumchem import (
            QuantumChemEngine,
            QuantumChemMiddleware,
        )

        max_scf = getattr(args, "fizzquantumchem_max_scf", None) or config.fizzquantumchem_max_scf_iterations
        threshold = getattr(args, "fizzquantumchem_threshold", None) or config.fizzquantumchem_convergence_threshold

        middleware = QuantumChemMiddleware(
            max_scf_iterations=max_scf,
            convergence_threshold=threshold,
        )

        return middleware.engine, middleware

    def get_banner(self, config: Any, args: Any) -> Optional[str]:
        if getattr(args, "no_banner", False):
            return None
        return (
            "  +---------------------------------------------------------+\n"
            "  | FIZZQUANTUMCHEM: QUANTUM CHEMISTRY ENGINE                |\n"
            "  |   Hartree-Fock self-consistent field method              |\n"
            "  |   STO-3G Gaussian basis set expansion                    |\n"
            "  |   HOMO-LUMO gap and orbital energy analysis              |\n"
            "  +---------------------------------------------------------+"
        )
