"""
Enterprise FizzBuzz Platform - Homomorphic Encryption Exceptions (EFP-HE00 through EFP-HE09)
"""

from __future__ import annotations

from typing import Any, Optional

from ._base import FizzBuzzError


class HomomorphicEncryptionError(FizzBuzzError):
    """Base exception for all FizzHomomorphic encryption subsystem errors.

    Homomorphic encryption enables FizzBuzz evaluation on encrypted
    integers without ever exposing the plaintext value. This is essential
    for regulatory environments where the number being evaluated is
    classified and the operator must not learn whether it is divisible
    by 3 or 5 until the ciphertext result is decrypted by an authorized
    key holder.
    """

    def __init__(
        self,
        message: str,
        *,
        error_code: str = "EFP-HE00",
        context: Optional[dict[str, Any]] = None,
    ) -> None:
        super().__init__(message, error_code=error_code, context=context)


class KeyGenerationError(HomomorphicEncryptionError):
    """Raised when homomorphic key generation fails.

    Key generation requires selecting polynomial modulus degree and
    coefficient modulus chain parameters that satisfy both security
    level requirements and computational depth constraints. Invalid
    parameter combinations produce keys that are either insecure or
    unable to support the required circuit depth.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(
            f"Homomorphic key generation failed: {reason}",
            error_code="EFP-HE01",
            context={"reason": reason},
        )


class EncryptionError(HomomorphicEncryptionError):
    """Raised when plaintext encryption fails.

    Encryption encodes a plaintext integer into a ring element and adds
    noise drawn from a discrete Gaussian distribution. If the plaintext
    exceeds the representable range or the noise sampling fails, the
    resulting ciphertext is invalid.
    """

    def __init__(self, plaintext_value: int, reason: str) -> None:
        super().__init__(
            f"Failed to encrypt plaintext value {plaintext_value}: {reason}",
            error_code="EFP-HE02",
            context={"plaintext_value": plaintext_value, "reason": reason},
        )


class DecryptionError(HomomorphicEncryptionError):
    """Raised when ciphertext decryption produces an incorrect result.

    Decryption removes the secret key component from the ciphertext and
    rounds the result to recover the plaintext. If the accumulated noise
    exceeds half the plaintext modulus, rounding fails and the decrypted
    value is incorrect.
    """

    def __init__(self, noise_budget_bits: int) -> None:
        super().__init__(
            f"Decryption failed: noise budget exhausted ({noise_budget_bits} bits remaining).",
            error_code="EFP-HE03",
            context={"noise_budget_bits": noise_budget_bits},
        )


class NoiseBudgetExhaustedError(HomomorphicEncryptionError):
    """Raised when the noise budget of a ciphertext is exhausted.

    Each homomorphic operation increases the noise in the ciphertext.
    When the noise budget reaches zero, further operations produce
    garbled results. The FizzBuzz evaluation circuit must complete
    within the available noise budget.
    """

    def __init__(self, operation: str, budget_before: int, budget_after: int) -> None:
        super().__init__(
            f"Noise budget exhausted during '{operation}': "
            f"{budget_before} bits before, {budget_after} bits after.",
            error_code="EFP-HE04",
            context={"operation": operation, "budget_before": budget_before},
        )


class HomomorphicOperationError(HomomorphicEncryptionError):
    """Raised when a homomorphic add or multiply operation fails.

    Homomorphic operations on ciphertexts must preserve structural
    compatibility (matching parameters, compatible noise levels).
    Attempting to operate on incompatible ciphertexts produces
    undefined results.
    """

    def __init__(self, operation: str, reason: str) -> None:
        super().__init__(
            f"Homomorphic {operation} failed: {reason}",
            error_code="EFP-HE05",
            context={"operation": operation, "reason": reason},
        )
