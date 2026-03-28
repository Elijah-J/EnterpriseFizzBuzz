"""FizzGenomics Genome Sequence Analyzer Properties"""

from __future__ import annotations

from typing import Any


class FizzGenomicsConfigMixin:
    """Configuration properties for the FizzGenomics subsystem."""

    # ----------------------------------------------------------------
    # FizzGenomics Genome Sequence Analyzer Properties
    # ----------------------------------------------------------------

    @property
    def fizzgenomics_enabled(self) -> bool:
        """Whether the FizzGenomics genome sequence analyzer is enabled."""
        self._ensure_loaded()
        return self._raw_config.get("fizzgenomics", {}).get("enabled", False)

    @property
    def fizzgenomics_min_orf_length(self) -> int:
        """Minimum ORF length in nucleotides for detection."""
        self._ensure_loaded()
        return int(self._raw_config.get("fizzgenomics", {}).get("min_orf_length", 30))

    @property
    def fizzgenomics_enable_blast(self) -> bool:
        """Whether BLAST-style sequence search is enabled."""
        self._ensure_loaded()
        return self._raw_config.get("fizzgenomics", {}).get("enable_blast", False)

    @property
    def fizzgenomics_blast_kmer_size(self) -> int:
        """K-mer size for BLAST seed indexing."""
        self._ensure_loaded()
        return int(self._raw_config.get("fizzgenomics", {}).get("blast_kmer_size", 7))
