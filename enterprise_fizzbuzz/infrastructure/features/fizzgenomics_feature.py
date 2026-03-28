"""Feature descriptor for the FizzGenomics genome sequence analyzer."""

from __future__ import annotations

from typing import Any, Optional

from enterprise_fizzbuzz.infrastructure.features._registry import FeatureDescriptor


class FizzGenomicsFeature(FeatureDescriptor):
    name = "fizzgenomics"
    description = "Genome sequence analyzer with Smith-Waterman alignment, BLAST search, codon translation, and phylogenetics"
    middleware_priority = 275
    cli_flags = [
        ("--fizzgenomics", {"action": "store_true", "default": False,
                            "help": "Enable FizzGenomics: encode FizzBuzz sequences as DNA and analyze for ORFs, GC content, and genomic structure"}),
        ("--fizzgenomics-blast", {"action": "store_true", "default": False,
                                  "help": "Enable BLAST-style sequence search for homology detection in the FizzBuzz genome"}),
        ("--fizzgenomics-min-orf", {"type": int, "metavar": "LEN", "default": None,
                                    "help": "Minimum ORF length in nucleotides for detection (default: 30)"}),
    ]

    def is_enabled(self, args: Any) -> bool:
        return getattr(args, "fizzgenomics", False)

    def create(self, config: Any, args: Any, event_bus: Any = None) -> tuple:
        from enterprise_fizzbuzz.infrastructure.fizzgenomics import GenomicsMiddleware

        middleware = GenomicsMiddleware(
            min_orf_length=getattr(args, "fizzgenomics_min_orf", None) or config.fizzgenomics_min_orf_length,
            enable_blast=getattr(args, "fizzgenomics_blast", False) or config.fizzgenomics_enable_blast,
        )

        return None, middleware

    def get_banner(self, config: Any, args: Any) -> Optional[str]:
        if getattr(args, "no_banner", False):
            return None
        return (
            "  +---------------------------------------------------------+\n"
            "  | FIZZGENOMICS: GENOME SEQUENCE ANALYZER                   |\n"
            "  |   Smith-Waterman alignment, BLAST homology search        |\n"
            "  |   Codon translation and ORF detection                    |\n"
            "  |   UPGMA phylogenetic tree construction                   |\n"
            "  +---------------------------------------------------------+"
        )
