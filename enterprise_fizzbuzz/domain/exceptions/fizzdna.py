"""
Enterprise FizzBuzz Platform - FizzDNA Storage Encoder Exceptions

DNA-based data storage achieves information densities of 215 petabytes per
gram of nucleotide. Given that FizzBuzz evaluations produce approximately
4 bytes of output per integer, the Enterprise FizzBuzz Platform requires
a biologically faithful encoding pipeline to persist evaluation results
in synthetic oligonucleotide sequences.

These exceptions handle the inevitable failure modes that arise when
translating modulo arithmetic into adenine, thymine, guanine, and cytosine.
"""

from __future__ import annotations

from typing import Any, Optional

from ._base import FizzBuzzError


class FizzDNAError(FizzBuzzError):
    """Base exception for all FizzDNA subsystem errors.

    The DNA storage encoder has encountered a condition that prevents
    faithful transcription of FizzBuzz evaluation results into nucleotide
    sequences. In molecular biology, such errors are corrected by DNA
    polymerase proofreading. In software, we raise exceptions.
    """

    def __init__(
        self,
        message: str,
        *,
        error_code: str = "EFP-DNA00",
        context: Optional[dict[str, Any]] = None,
    ) -> None:
        super().__init__(message, error_code=error_code, context=context)


class DNAEncodingError(FizzDNAError):
    """Raised when a FizzBuzz result cannot be encoded into a DNA sequence.

    The two-bit-per-base encoding scheme maps every pair of bits in the
    binary representation to one of four nucleotides. If the input data
    contains values outside the expected range, the encoding is undefined
    and the resulting oligonucleotide would be biologically meaningless.
    """

    def __init__(self, data: str, reason: str) -> None:
        super().__init__(
            f"Failed to encode data '{data}' into DNA: {reason}. "
            f"The nucleotide sequence cannot represent this input.",
            error_code="EFP-DNA01",
            context={"data": data, "reason": reason},
        )


class DNADecodingError(FizzDNAError):
    """Raised when a DNA sequence cannot be decoded back into FizzBuzz output.

    The reverse transcription from nucleotide bases to binary data has failed.
    This may indicate sequence corruption during storage, an invalid base
    character in the input, or a checksum mismatch in the error-correcting code.
    """

    def __init__(self, sequence: str, reason: str) -> None:
        super().__init__(
            f"Failed to decode DNA sequence '{sequence[:20]}...': {reason}. "
            f"The original FizzBuzz result cannot be recovered.",
            error_code="EFP-DNA02",
            context={"sequence_prefix": sequence[:20], "reason": reason},
        )


class GCContentImbalanceError(FizzDNAError):
    """Raised when a synthesized oligonucleotide has unacceptable GC content.

    Practical DNA synthesis requires GC content between 40% and 60% to ensure
    thermal stability and avoid secondary structure formation. A sequence
    dominated by A/T bases will have a low melting temperature, while excessive
    G/C content creates hairpin loops that impede PCR amplification.
    """

    def __init__(self, gc_ratio: float, min_ratio: float, max_ratio: float) -> None:
        super().__init__(
            f"GC content {gc_ratio:.1%} is outside acceptable range "
            f"[{min_ratio:.1%}, {max_ratio:.1%}]. The oligonucleotide would be "
            f"thermodynamically unstable for synthesis.",
            error_code="EFP-DNA03",
            context={"gc_ratio": gc_ratio, "min_ratio": min_ratio, "max_ratio": max_ratio},
        )


class ECCChecksumError(FizzDNAError):
    """Raised when the error-correcting code detects uncorrectable corruption.

    The Reed-Solomon error-correcting code appended to each DNA data block
    can detect and correct a limited number of substitution errors. When
    the number of corrupted bases exceeds the correction capacity, the
    data is irrecoverable and the FizzBuzz evaluation must be re-executed.
    """

    def __init__(self, block_id: int, errors_found: int, max_correctable: int) -> None:
        super().__init__(
            f"Block {block_id} has {errors_found} base errors, exceeding the "
            f"Reed-Solomon correction capacity of {max_correctable}. "
            f"The data is irrecoverably corrupted.",
            error_code="EFP-DNA04",
            context={"block_id": block_id, "errors_found": errors_found,
                      "max_correctable": max_correctable},
        )


class HomopolymerRunError(FizzDNAError):
    """Raised when a sequence contains an excessively long homopolymer run.

    Runs of identical bases (e.g., AAAAAAA) cause sequencing errors in
    nanopore and Illumina platforms. The maximum tolerable homopolymer
    length depends on the sequencing technology, but runs exceeding 6
    bases are universally problematic.
    """

    def __init__(self, base: str, run_length: int, max_length: int) -> None:
        super().__init__(
            f"Homopolymer run of {run_length} '{base}' bases exceeds maximum "
            f"of {max_length}. Sequencing accuracy would be severely degraded.",
            error_code="EFP-DNA05",
            context={"base": base, "run_length": run_length, "max_length": max_length},
        )


class DNAStorageCapacityError(FizzDNAError):
    """Raised when the data payload exceeds the available oligo pool capacity.

    Each oligonucleotide has a maximum practical length of approximately
    300 bases. Longer sequences suffer from exponentially increasing
    synthesis error rates. The total storage capacity is therefore bounded
    by the number of oligos in the pool multiplied by the payload per oligo.
    """

    def __init__(self, data_bytes: int, capacity_bytes: int) -> None:
        super().__init__(
            f"Data payload of {data_bytes} bytes exceeds DNA pool capacity "
            f"of {capacity_bytes} bytes. Additional oligonucleotides are required.",
            error_code="EFP-DNA06",
            context={"data_bytes": data_bytes, "capacity_bytes": capacity_bytes},
        )


class DNAMiddlewareError(FizzDNAError):
    """Raised when the DNA storage middleware fails during pipeline processing."""

    def __init__(self, number: int, reason: str) -> None:
        super().__init__(
            f"DNA storage middleware failed for number {number}: {reason}.",
            error_code="EFP-DNA07",
            context={"number": number, "reason": reason},
        )
