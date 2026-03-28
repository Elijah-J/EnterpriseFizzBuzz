"""
Enterprise FizzBuzz Platform - FizzSGX Exceptions (EFP-SGX0 through EFP-SGX7)

Exception hierarchy for the Intel SGX enclave simulator. These exceptions
cover enclave creation failures, ECALL/OCALL bridge errors, sealed storage
violations, remote attestation failures, memory encryption faults, and
enclave measurement mismatches that may arise during secure FizzBuzz
computation within trusted execution environments.
"""

from __future__ import annotations

from typing import Any

from ._base import FizzBuzzError


class SGXError(FizzBuzzError):
    """Base exception for all FizzSGX errors.

    The FizzSGX subsystem simulates Intel SGX enclaves for secure
    FizzBuzz classification within isolated trusted execution environments,
    providing confidentiality and integrity guarantees through hardware-
    assisted memory encryption and attestation.
    """

    def __init__(self, message: str, **kwargs: Any) -> None:
        super().__init__(
            message,
            error_code=kwargs.pop("error_code", "EFP-SGX0"),
            context=kwargs.pop("context", {}),
        )


class SGXEnclaveCreationError(SGXError):
    """Raised when enclave creation fails."""

    def __init__(self, enclave_id: str, reason: str) -> None:
        super().__init__(
            f"SGX enclave '{enclave_id}' creation failed: {reason}",
            error_code="EFP-SGX1",
            context={"enclave_id": enclave_id, "reason": reason},
        )
        self.enclave_id = enclave_id
        self.reason = reason


class SGXECallError(SGXError):
    """Raised when an ECALL into the enclave fails."""

    def __init__(self, function_id: int, reason: str) -> None:
        super().__init__(
            f"SGX ECALL to function {function_id} failed: {reason}",
            error_code="EFP-SGX2",
            context={"function_id": function_id, "reason": reason},
        )
        self.function_id = function_id
        self.reason = reason


class SGXOCallError(SGXError):
    """Raised when an OCALL from the enclave fails."""

    def __init__(self, function_id: int, reason: str) -> None:
        super().__init__(
            f"SGX OCALL from function {function_id} failed: {reason}",
            error_code="EFP-SGX3",
            context={"function_id": function_id, "reason": reason},
        )
        self.function_id = function_id
        self.reason = reason


class SGXSealError(SGXError):
    """Raised when data sealing within the enclave fails."""

    def __init__(self, reason: str) -> None:
        super().__init__(
            f"SGX data sealing failed: {reason}",
            error_code="EFP-SGX4",
            context={"reason": reason},
        )
        self.reason = reason


class SGXAttestationError(SGXError):
    """Raised when remote attestation verification fails."""

    def __init__(self, enclave_id: str, reason: str) -> None:
        super().__init__(
            f"SGX attestation failed for enclave '{enclave_id}': {reason}",
            error_code="EFP-SGX5",
            context={"enclave_id": enclave_id, "reason": reason},
        )
        self.enclave_id = enclave_id
        self.reason = reason


class SGXMemoryError(SGXError):
    """Raised when enclave memory allocation or access fails."""

    def __init__(self, address: int, size: int, reason: str) -> None:
        super().__init__(
            f"SGX memory error at 0x{address:016X} size {size}: {reason}",
            error_code="EFP-SGX6",
            context={"address": address, "size": size, "reason": reason},
        )
        self.address = address
        self.size = size
        self.reason = reason


class SGXMeasurementError(SGXError):
    """Raised when enclave measurement (MRENCLAVE/MRSIGNER) does not match."""

    def __init__(self, expected: str, actual: str) -> None:
        super().__init__(
            f"SGX measurement mismatch: expected {expected[:16]}..., got {actual[:16]}...",
            error_code="EFP-SGX7",
            context={"expected": expected, "actual": actual},
        )
        self.expected = expected
        self.actual = actual
