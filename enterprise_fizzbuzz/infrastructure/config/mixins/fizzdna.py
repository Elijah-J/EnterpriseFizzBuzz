"""FizzDNA DNA Storage Encoder properties."""

from __future__ import annotations

from typing import Any


class FizzdnaConfigMixin:
    """Configuration properties for the FizzDNA subsystem."""

    @property
    def fizzdna_gc_min(self) -> float:
        """Minimum acceptable GC content ratio for synthesized oligos."""
        self._ensure_loaded()
        return self._raw_config.get("fizzdna", {}).get("gc_min", 0.40)

    @property
    def fizzdna_gc_max(self) -> float:
        """Maximum acceptable GC content ratio for synthesized oligos."""
        self._ensure_loaded()
        return self._raw_config.get("fizzdna", {}).get("gc_max", 0.60)

    @property
    def fizzdna_max_homopolymer(self) -> int:
        """Maximum tolerable homopolymer run length."""
        self._ensure_loaded()
        return self._raw_config.get("fizzdna", {}).get("max_homopolymer", 4)

    @property
    def fizzdna_ecc_symbols(self) -> int:
        """Number of Reed-Solomon ECC parity symbols per block."""
        self._ensure_loaded()
        return self._raw_config.get("fizzdna", {}).get("ecc_symbols", 8)

    @property
    def fizzdna_oligo_length(self) -> int:
        """Maximum oligonucleotide length in bases."""
        self._ensure_loaded()
        return self._raw_config.get("fizzdna", {}).get("oligo_length", 200)

    @property
    def fizzdna_dashboard_width(self) -> int:
        """Width of the FizzDNA ASCII dashboard."""
        self._ensure_loaded()
        return self._raw_config.get("fizzdna", {}).get("dashboard_width", 60)
