"""
Enterprise FizzBuzz Platform - Zero-Knowledge Proof Exceptions (EFP-ZK00 through EFP-ZK09)
"""

from __future__ import annotations

from typing import Any, Optional

from ._base import FizzBuzzError


class ZeroKnowledgeProofError(FizzBuzzError):
    """Base exception for all FizzZKP zero-knowledge proof subsystem errors.

    Zero-knowledge proofs allow a prover to demonstrate that a number
    satisfies the FizzBuzz divisibility conditions without revealing
    the number itself. This is critical for privacy-preserving FizzBuzz
    evaluations where the input integer is sensitive and must not be
    disclosed to the verifier.
    """

    def __init__(
        self,
        message: str,
        *,
        error_code: str = "EFP-ZK00",
        context: Optional[dict[str, Any]] = None,
    ) -> None:
        super().__init__(message, error_code=error_code, context=context)


class ProofGenerationError(ZeroKnowledgeProofError):
    """Raised when proof generation fails.

    Proof generation requires computing commitments and responses that
    satisfy the verification equation without leaking the witness. If
    the witness is invalid or the random nonce generation fails, the
    proof cannot be constructed.
    """

    def __init__(self, protocol: str, reason: str) -> None:
        super().__init__(
            f"Failed to generate {protocol} proof: {reason}",
            error_code="EFP-ZK01",
            context={"protocol": protocol, "reason": reason},
        )


class ProofVerificationError(ZeroKnowledgeProofError):
    """Raised when proof verification fails.

    The verifier checks the proof against the public statement. A failed
    verification means either the proof is invalid (the prover does not
    know the witness) or the proof was tampered with in transit.
    """

    def __init__(self, protocol: str, reason: str) -> None:
        super().__init__(
            f"{protocol} proof verification failed: {reason}",
            error_code="EFP-ZK02",
            context={"protocol": protocol, "reason": reason},
        )


class CommitmentError(ZeroKnowledgeProofError):
    """Raised when a cryptographic commitment scheme fails.

    Commitments must be both hiding (reveal nothing about the committed
    value) and binding (the committer cannot change the value after
    committing). Invalid group parameters or randomness can violate
    these properties.
    """

    def __init__(self, scheme: str, reason: str) -> None:
        super().__init__(
            f"Commitment scheme '{scheme}' error: {reason}",
            error_code="EFP-ZK03",
            context={"scheme": scheme, "reason": reason},
        )


class TranscriptError(ZeroKnowledgeProofError):
    """Raised when the proof transcript is malformed or inconsistent.

    The transcript records all messages exchanged between prover and
    verifier. In the Fiat-Shamir heuristic, the transcript is hashed
    to produce non-interactive challenges. A malformed transcript
    produces incorrect challenges and invalidates the proof.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(
            f"Proof transcript error: {reason}",
            error_code="EFP-ZK04",
            context={"reason": reason},
        )


class FiatShamirError(ZeroKnowledgeProofError):
    """Raised when the Fiat-Shamir transform produces an invalid challenge.

    The Fiat-Shamir heuristic converts interactive proofs to non-interactive
    ones by deriving challenges from a hash of the transcript. If the hash
    function is misconfigured or the transcript binding is incomplete,
    the resulting challenge may be predictable, compromising soundness.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(
            f"Fiat-Shamir transform error: {reason}",
            error_code="EFP-ZK05",
            context={"reason": reason},
        )


class GroupParameterError(ZeroKnowledgeProofError):
    """Raised when the discrete logarithm group parameters are invalid.

    Schnorr proofs require a prime-order subgroup of Z_p*. If the group
    order is not prime or the generator does not have the claimed order,
    the proof system's soundness guarantee is void.
    """

    def __init__(self, parameter: str, reason: str) -> None:
        super().__init__(
            f"Invalid group parameter '{parameter}': {reason}",
            error_code="EFP-ZK06",
            context={"parameter": parameter, "reason": reason},
        )
