"""
Enterprise FizzBuzz Platform - ELF Binary Format Exceptions (EFP-ELF0 through EFP-ELF2)
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from ._base import FizzBuzzError


class ELFFormatError(FizzBuzzError):
    """Base exception for all ELF binary format errors.

    Covers generation, parsing, and structural validation failures
    in the ELF subsystem. All ELF-related exceptions inherit from
    this class to enable targeted error handling in the middleware
    pipeline.
    """

    def __init__(
        self,
        message: str,
        *,
        error_code: str = "EFP-ELF0",
        context: Optional[dict[str, Any]] = None,
    ) -> None:
        super().__init__(message, error_code=error_code, context=context)


class ELFParseError(ELFFormatError):
    """Raised when an ELF binary cannot be parsed from raw bytes.

    Parse errors indicate that the input data does not conform to
    the ELF specification — the magic bytes are wrong, a header
    field is out of range, or the binary is truncated. In a production
    environment, this could indicate data corruption during
    transmission or storage of the FizzBuzz evaluation artifact.
    """

    def __init__(self, message: str) -> None:
        super().__init__(
            message,
            error_code="EFP-ELF1",
            context={},
        )


class ELFGenerationError(ELFFormatError):
    """Raised when the ELF generator fails to produce a valid binary.

    Generation errors occur when the builder encounters an internal
    inconsistency — for example, a symbol referencing a non-existent
    section, or a segment covering zero bytes. These errors indicate
    a defect in the generation pipeline rather than in the input data.
    """

    def __init__(self, message: str, *, detail: str = "") -> None:
        super().__init__(
            message,
            error_code="EFP-ELF2",
            context={"detail": detail},
        )

