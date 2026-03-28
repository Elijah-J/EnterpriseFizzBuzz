"""Feature descriptor for the FizzDNA DNA storage encoder."""

from __future__ import annotations

from typing import Any, Optional

from enterprise_fizzbuzz.infrastructure.features._registry import FeatureDescriptor


class FizzDNAFeature(FeatureDescriptor):
    name = "fizzdna"
    description = "DNA storage encoder with Reed-Solomon ECC, GC-content balancing, and oligo segmentation"
    middleware_priority = 262
    cli_flags = [
        ("--dna-storage", {"action": "store_true", "default": False,
                           "help": "Enable FizzDNA: encode FizzBuzz results into synthetic DNA oligonucleotide sequences"}),
        ("--dna-dashboard", {"action": "store_true", "default": False,
                             "help": "Display the FizzDNA ASCII dashboard with oligo pool statistics and helix visualization"}),
    ]

    def is_enabled(self, args: Any) -> bool:
        return any([
            getattr(args, "dna_storage", False),
            getattr(args, "dna_dashboard", False),
        ])

    def create(self, config: Any, args: Any, event_bus: Any = None) -> tuple:
        from enterprise_fizzbuzz.infrastructure.fizzdna import (
            DNAEncoder,
            DNAStorageMiddleware,
            FizzBuzzDNAStorage,
        )

        encoder = DNAEncoder(
            gc_min=config.fizzdna_gc_min,
            gc_max=config.fizzdna_gc_max,
            max_homopolymer=config.fizzdna_max_homopolymer,
            ecc_symbols=config.fizzdna_ecc_symbols,
            oligo_length=config.fizzdna_oligo_length,
        )
        storage = FizzBuzzDNAStorage(encoder=encoder)
        middleware = DNAStorageMiddleware(
            storage=storage,
            enable_dashboard=getattr(args, "dna_dashboard", False),
        )
        return storage, middleware

    def get_banner(self, config: Any, args: Any) -> Optional[str]:
        if getattr(args, "no_banner", False):
            return None
        return (
            "  +---------------------------------------------------------+\n"
            "  | FIZZDNA: DNA STORAGE ENCODER                            |\n"
            "  |   Encoding: 2 bits/base (A=00 T=01 G=10 C=11)          |\n"
            f"  |   GC range: [{config.fizzdna_gc_min:.0%}, {config.fizzdna_gc_max:.0%}]  ECC: RS({config.fizzdna_ecc_symbols})           |\n"
            "  |   Oligo pool persistence: in-silico synthesis ready      |\n"
            "  +---------------------------------------------------------+"
        )

    def render(self, middleware: Any, args: Any) -> Optional[str]:
        if middleware is None:
            return None
        if not getattr(args, "dna_dashboard", False):
            return None
        from enterprise_fizzbuzz.infrastructure.fizzdna import DNADashboard
        from enterprise_fizzbuzz.infrastructure.config import ConfigurationManager
        config = ConfigurationManager()
        return DNADashboard.render(
            middleware.storage,
            width=config.fizzdna_dashboard_width,
        )
