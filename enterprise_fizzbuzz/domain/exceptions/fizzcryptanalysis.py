"""
Enterprise FizzBuzz Platform - FizzCryptanalysis Exceptions (EFP-CRY00 through EFP-CRY07)
"""

from __future__ import annotations

from typing import Any, Optional

from ._base import FizzBuzzError


class FizzCryptanalysisError(FizzBuzzError):
    """Base exception for the FizzCryptanalysis cipher breaking subsystem.

    Cryptanalysis involves statistical and algebraic attacks against
    classical and modern cipher systems. Frequency analysis, the Kasiski
    examination, index of coincidence computation, known-plaintext attacks,
    and differential cryptanalysis each require specific preconditions
    regarding ciphertext length, alphabet distribution, and cipher structure.
    """

    def __init__(
        self,
        message: str,
        *,
        error_code: str = "EFP-CRY00",
        context: dict | None = None,
    ) -> None:
        super().__init__(message, error_code=error_code, context=context)


class FrequencyAnalysisError(FizzCryptanalysisError):
    """Raised when frequency analysis cannot distinguish the cipher alphabet.

    Monoalphabetic substitution ciphers require sufficient ciphertext
    length for letter frequency distributions to converge to their
    expected values. Short ciphertexts produce flat frequency profiles
    that are indistinguishable from polyalphabetic encryption.
    """

    def __init__(self, ciphertext_length: int, min_required: int) -> None:
        super().__init__(
            f"Frequency analysis requires at least {min_required} characters; "
            f"ciphertext contains only {ciphertext_length}",
            error_code="EFP-CRY01",
            context={
                "ciphertext_length": ciphertext_length,
                "min_required": min_required,
            },
        )


class KasiskiError(FizzCryptanalysisError):
    """Raised when the Kasiski examination finds no repeated trigrams.

    The Kasiski examination identifies repeated sequences in a
    polyalphabetic ciphertext and uses the GCD of their spacings to
    estimate the key length. If no repeated trigrams are found, the
    ciphertext may be too short or encrypted with a one-time pad.
    """

    def __init__(self, ciphertext_length: int) -> None:
        super().__init__(
            f"Kasiski examination found no repeated trigrams in "
            f"{ciphertext_length}-character ciphertext",
            error_code="EFP-CRY02",
            context={"ciphertext_length": ciphertext_length},
        )


class IndexOfCoincidenceError(FizzCryptanalysisError):
    """Raised when the index of coincidence is outside interpretable range.

    The index of coincidence for English text is approximately 0.0667,
    while a random uniform distribution yields approximately 0.0385.
    Values significantly outside this range suggest a non-alphabetic
    cipher or data corruption.
    """

    def __init__(self, ioc_value: float, expected_range: tuple) -> None:
        super().__init__(
            f"Index of coincidence {ioc_value:.6f} outside expected range "
            f"[{expected_range[0]:.4f}, {expected_range[1]:.4f}]",
            error_code="EFP-CRY03",
            context={"ioc_value": ioc_value, "expected_range": expected_range},
        )


class KnownPlaintextError(FizzCryptanalysisError):
    """Raised when known-plaintext attack fails to recover the key.

    A known-plaintext attack requires that the plaintext-ciphertext
    pair provides sufficient constraints to uniquely determine the
    key. If the known segment is too short or the cipher has a
    large key space, the attack may be inconclusive.
    """

    def __init__(self, plaintext_length: int, key_space: int) -> None:
        super().__init__(
            f"Known-plaintext attack inconclusive: {plaintext_length} known "
            f"characters insufficient to reduce key space of {key_space}",
            error_code="EFP-CRY04",
            context={
                "plaintext_length": plaintext_length,
                "key_space": key_space,
            },
        )


class DifferentialCryptanalysisError(FizzCryptanalysisError):
    """Raised when differential cryptanalysis cannot find a valid differential trail.

    Differential cryptanalysis requires input pairs with specific
    XOR differences that propagate predictably through the cipher's
    round function. If no high-probability differential trail exists,
    the attack requires more chosen-plaintext pairs than are available.
    """

    def __init__(self, num_rounds: int, best_probability: float) -> None:
        super().__init__(
            f"Differential cryptanalysis failed for {num_rounds}-round cipher: "
            f"best trail probability {best_probability:.2e} is too low",
            error_code="EFP-CRY05",
            context={
                "num_rounds": num_rounds,
                "best_probability": best_probability,
            },
        )


class CipherIdentificationError(FizzCryptanalysisError):
    """Raised when automatic cipher identification is ambiguous."""

    def __init__(self, candidates: list) -> None:
        super().__init__(
            f"Cipher identification ambiguous: {len(candidates)} candidates "
            f"({', '.join(str(c) for c in candidates[:5])})",
            error_code="EFP-CRY06",
            context={"candidates": candidates},
        )


class CryptanalysisMiddlewareError(FizzCryptanalysisError):
    """Raised when the FizzCryptanalysis middleware encounters a fault."""

    def __init__(self, reason: str) -> None:
        super().__init__(
            f"FizzCryptanalysis middleware error: {reason}",
            error_code="EFP-CRY07",
            context={"reason": reason},
        )
