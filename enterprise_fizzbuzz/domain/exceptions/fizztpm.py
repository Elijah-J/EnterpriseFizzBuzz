"""
Enterprise FizzBuzz Platform - FizzTPM Exceptions (EFP-TPM0 through EFP-TPM7)

Exception hierarchy for the Trusted Platform Module 2.0 simulator. These
exceptions cover PCR bank errors, seal/unseal failures, attestation
violations, NVRAM storage faults, and random number generation issues
that may arise during TPM-secured FizzBuzz classification.
"""

from __future__ import annotations

from typing import Any

from ._base import FizzBuzzError


class TPMError(FizzBuzzError):
    """Base exception for all FizzTPM errors.

    The FizzTPM subsystem implements a TPM 2.0 simulator for hardware-rooted
    trust in FizzBuzz classification integrity. When the virtual TPM
    encounters PCR validation failures, seal/unseal mismatches, or
    attestation errors, this exception hierarchy provides diagnostics.
    """

    def __init__(self, message: str, **kwargs: Any) -> None:
        super().__init__(
            message,
            error_code=kwargs.pop("error_code", "EFP-TPM0"),
            context=kwargs.pop("context", {}),
        )


class TPMPCRError(TPMError):
    """Raised when a PCR index is out of range."""

    def __init__(self, pcr_index: int, max_pcrs: int) -> None:
        super().__init__(
            f"PCR index {pcr_index} out of range (0..{max_pcrs - 1})",
            error_code="EFP-TPM1",
            context={"pcr_index": pcr_index, "max_pcrs": max_pcrs},
        )
        self.pcr_index = pcr_index
        self.max_pcrs = max_pcrs


class TPMSealError(TPMError):
    """Raised when data sealing fails due to invalid PCR state."""

    def __init__(self, reason: str) -> None:
        super().__init__(
            f"TPM seal operation failed: {reason}",
            error_code="EFP-TPM2",
            context={"reason": reason},
        )
        self.reason = reason


class TPMUnsealError(TPMError):
    """Raised when data unsealing fails because PCR state has changed."""

    def __init__(self, pcr_index: int) -> None:
        super().__init__(
            f"TPM unseal failed: PCR[{pcr_index}] does not match sealed state",
            error_code="EFP-TPM3",
            context={"pcr_index": pcr_index},
        )
        self.pcr_index = pcr_index


class TPMAttestationError(TPMError):
    """Raised when a TPM quote or attestation verification fails."""

    def __init__(self, reason: str) -> None:
        super().__init__(
            f"TPM attestation failed: {reason}",
            error_code="EFP-TPM4",
            context={"reason": reason},
        )
        self.reason = reason


class TPMNVRAMError(TPMError):
    """Raised when an NVRAM read or write operation fails."""

    def __init__(self, nv_index: int, reason: str) -> None:
        super().__init__(
            f"NVRAM operation failed at index 0x{nv_index:08X}: {reason}",
            error_code="EFP-TPM5",
            context={"nv_index": nv_index, "reason": reason},
        )
        self.nv_index = nv_index
        self.reason = reason


class TPMAuthorizationError(TPMError):
    """Raised when TPM authorization policy check fails."""

    def __init__(self, handle: int) -> None:
        super().__init__(
            f"TPM authorization failed for handle 0x{handle:08X}",
            error_code="EFP-TPM6",
            context={"handle": handle},
        )
        self.handle = handle


class TPMRandomError(TPMError):
    """Raised when the TPM random number generator fails."""

    def __init__(self, requested_bytes: int) -> None:
        super().__init__(
            f"TPM RNG failed to generate {requested_bytes} bytes",
            error_code="EFP-TPM7",
            context={"requested_bytes": requested_bytes},
        )
        self.requested_bytes = requested_bytes
