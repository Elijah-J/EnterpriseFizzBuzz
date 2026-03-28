"""
Enterprise FizzBuzz Platform - FizzGenomics Exceptions (EFP-GEN00 through EFP-GEN09)
"""

from __future__ import annotations

from typing import Any, Optional

from ._base import FizzBuzzError


class FizzGenomicsError(FizzBuzzError):
    """Base exception for all FizzGenomics genome sequence analysis errors.

    The FizzGenomics engine performs DNA/RNA sequence alignment, codon
    translation, and phylogenetic analysis to discover the biological
    ancestry of FizzBuzz divisibility patterns. Errors at this layer
    indicate that the genomic context of a classification cannot be
    reliably determined.
    """

    def __init__(
        self,
        message: str,
        *,
        error_code: str = "EFP-GEN00",
        context: dict | None = None,
    ) -> None:
        super().__init__(message, error_code=error_code, context=context)


class InvalidSequenceError(FizzGenomicsError):
    """Raised when a nucleotide sequence contains invalid characters.

    Valid DNA sequences contain only A, T, C, G (and N for unknown).
    Valid RNA sequences contain only A, U, C, G. Any other character
    would corrupt the alignment matrix and produce biologically
    meaningless FizzBuzz classifications.
    """

    def __init__(self, sequence_id: str, invalid_char: str, position: int) -> None:
        super().__init__(
            f"Invalid nucleotide '{invalid_char}' at position {position} "
            f"in sequence '{sequence_id}'",
            error_code="EFP-GEN01",
            context={
                "sequence_id": sequence_id,
                "invalid_char": invalid_char,
                "position": position,
            },
        )


class AlignmentError(FizzGenomicsError):
    """Raised when the Smith-Waterman alignment algorithm fails.

    The Smith-Waterman local alignment requires non-negative scoring
    matrix values and valid gap penalties. A failed alignment means the
    evolutionary distance between FizzBuzz sequences cannot be
    quantified, preventing phylogenetic classification.
    """

    def __init__(self, seq_a: str, seq_b: str, reason: str) -> None:
        super().__init__(
            f"Alignment failed between '{seq_a}' and '{seq_b}': {reason}",
            error_code="EFP-GEN02",
            context={"seq_a": seq_a, "seq_b": seq_b, "reason": reason},
        )


class CodonTranslationError(FizzGenomicsError):
    """Raised when codon-to-amino-acid translation encounters an error.

    Each triplet of nucleotides maps to a specific amino acid via the
    standard genetic code. An incomplete codon (sequence length not
    divisible by 3) or an unrecognized codon halts the translation
    machinery.
    """

    def __init__(self, codon: str, reason: str) -> None:
        super().__init__(
            f"Codon translation error for '{codon}': {reason}",
            error_code="EFP-GEN03",
            context={"codon": codon, "reason": reason},
        )


class ORFDetectionError(FizzGenomicsError):
    """Raised when open reading frame detection fails.

    ORF detection searches for start codons (ATG) followed by an
    in-frame stop codon. If the sequence is too short or corrupted,
    no valid reading frames can be identified, preventing the
    translation of FizzBuzz patterns into protein sequences.
    """

    def __init__(self, sequence_id: str, reason: str) -> None:
        super().__init__(
            f"ORF detection failed for sequence '{sequence_id}': {reason}",
            error_code="EFP-GEN04",
            context={"sequence_id": sequence_id, "reason": reason},
        )


class PhylogeneticTreeError(FizzGenomicsError):
    """Raised when phylogenetic tree construction fails.

    The UPGMA algorithm requires a valid distance matrix with at least
    two taxa. A degenerate or inconsistent distance matrix prevents
    hierarchical clustering and the resulting evolutionary tree
    cannot be built.
    """

    def __init__(self, num_taxa: int, reason: str) -> None:
        super().__init__(
            f"Phylogenetic tree construction failed with {num_taxa} taxa: {reason}",
            error_code="EFP-GEN05",
            context={"num_taxa": num_taxa, "reason": reason},
        )


class BLASTSearchError(FizzGenomicsError):
    """Raised when a BLAST-style sequence search encounters an error.

    The BLAST algorithm requires a valid query sequence and a non-empty
    database. An empty result set or index corruption prevents homology
    detection between FizzBuzz sequences.
    """

    def __init__(self, query_id: str, reason: str) -> None:
        super().__init__(
            f"BLAST search failed for query '{query_id}': {reason}",
            error_code="EFP-GEN06",
            context={"query_id": query_id, "reason": reason},
        )


class GenomicsMiddlewareError(FizzGenomicsError):
    """Raised when the FizzGenomics middleware pipeline encounters a fault."""

    def __init__(self, reason: str) -> None:
        super().__init__(
            f"FizzGenomics middleware error: {reason}",
            error_code="EFP-GEN07",
            context={"reason": reason},
        )
