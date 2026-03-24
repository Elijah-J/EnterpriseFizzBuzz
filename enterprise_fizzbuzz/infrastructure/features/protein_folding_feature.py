"""Feature descriptor for the FizzFold protein folding simulator."""

from __future__ import annotations

from typing import Any, Optional

from enterprise_fizzbuzz.infrastructure.features._registry import FeatureDescriptor


class ProteinFoldingFeature(FeatureDescriptor):
    name = "protein_folding"
    description = "Monte Carlo simulated annealing protein folder for FizzBuzz amino acid sequences"
    middleware_priority = 172
    cli_flags = [
        ("--fold", {"action": "store_true", "default": False,
                    "help": "Enable FizzFold: interpret FizzBuzz output as amino acid sequences and fold them using Monte Carlo simulated annealing"}),
        ("--fold-pdb", {"type": str, "metavar": "FILE", "default": None,
                        "help": "Write the folded protein structure to a PDB-format file"}),
        ("--fold-steps", {"type": int, "metavar": "N", "default": None,
                          "help": "Number of Monte Carlo steps for the simulated annealing schedule (default: 10000)"}),
        ("--fold-dashboard", {"action": "store_true", "default": False,
                              "help": "Display the FizzFold ASCII dashboard with energy curve, contact map, and folding statistics"}),
    ]

    def is_enabled(self, args: Any) -> bool:
        return any([
            getattr(args, "fold", False),
            getattr(args, "fold_pdb", None) is not None,
            getattr(args, "fold_dashboard", False),
        ])

    def create(self, config: Any, args: Any, event_bus: Any = None) -> tuple:
        from enterprise_fizzbuzz.infrastructure.protein_folding import FoldingMiddleware

        fold_steps = getattr(args, "fold_steps", None) or 10000
        middleware = FoldingMiddleware(
            max_steps=fold_steps,
            pdb_output_path=getattr(args, "fold_pdb", None),
            enable_dashboard=getattr(args, "fold_dashboard", False),
        )

        return None, middleware

    def get_banner(self, config: Any, args: Any) -> Optional[str]:
        if getattr(args, "no_banner", False):
            return None
        fold_steps = getattr(args, "fold_steps", None) or 10000
        return (
            "  +---------------------------------------------------------+\n"
            "  | FIZZFOLD: PROTEIN FOLDING SIMULATOR                     |\n"
            f"  |   MC Steps: {fold_steps:<10d}  Cooling: geometric (0.995) |\n"
            "  |   Energy: LJ + H-bond + hydrophobic + bond restraints   |\n"
            "  |   FIZZBUZZ = Phe-Ile-Glx-Glx-Asx-Sec-Glx-Glx          |\n"
            "  +---------------------------------------------------------+"
        )

    def render(self, middleware: Any, args: Any) -> Optional[str]:
        if middleware is None:
            return None
        if not getattr(args, "fold_dashboard", False):
            return None
        from enterprise_fizzbuzz.infrastructure.protein_folding import FoldingDashboard

        last_folder = middleware.last_folder
        last_conf = middleware.last_conformation
        if last_folder is not None and last_conf is not None:
            return FoldingDashboard.render(
                folder=last_folder,
                conformation=last_conf,
            )
        return "\n  FizzFold: no sequences were folded during this run.\n"
