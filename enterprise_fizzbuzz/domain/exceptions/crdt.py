"""
Enterprise FizzBuzz Platform - FizzCRDT — Conflict-Free Replicated Data Types
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from ._base import FizzBuzzError


class CRDTError(FizzBuzzError):
    """Base exception for all CRDT subsystem failures.

    Raised when the Conflict-Free Replicated Data Type engine encounters
    a condition that prevents it from fulfilling its sacred duty of
    ensuring Strong Eventual Consistency across the FizzBuzz cluster.
    The join-semilattice axioms (commutative, associative, idempotent)
    are inviolable; any violation is a cardinal sin against distributed
    systems theory.
    """

    def __init__(self, message: str) -> None:
        FizzBuzzError.__init__(
            self,
            f"CRDT subsystem error: {message}",
            error_code="EFP-CRDT00",
            context={},
        )


class CRDTMergeConflictError(CRDTError):
    """Raised when a CRDT merge operation encounters an irreconcilable state.

    This should, by the mathematical properties of CRDTs, be impossible.
    If you see this error, either the implementation is wrong, the laws
    of mathematics have changed, or someone has been manually editing
    CRDT state — all equally catastrophic scenarios.
    """

    def __init__(self, crdt_type: str, detail: str) -> None:
        self.crdt_type = crdt_type
        self.detail = detail
        FizzBuzzError.__init__(
            self,
            f"CRDT merge conflict in {crdt_type}: {detail}. "
            f"This violates the join-semilattice axioms and should be "
            f"mathematically impossible. Please check your axioms.",
            error_code="EFP-CRDT01",
            context={"crdt_type": crdt_type, "detail": detail},
        )


class CRDTCausalityViolationError(CRDTError):
    """Raised when a causal ordering constraint is violated.

    The vector clock detected an event that claims to have happened
    before another event, but the timestamps disagree. This is the
    distributed systems equivalent of a time travel paradox, and
    the CRDT engine refuses to participate in temporal contradictions.
    """

    def __init__(self, clock_a: str, clock_b: str) -> None:
        self.clock_a = clock_a
        self.clock_b = clock_b
        FizzBuzzError.__init__(
            self,
            f"Causality violation detected between vector clocks "
            f"{clock_a} and {clock_b}. The causal ordering of FizzBuzz "
            f"evaluations has been compromised. Lamport would be disappointed.",
            error_code="EFP-CRDT02",
            context={"clock_a": clock_a, "clock_b": clock_b},
        )


class CRDTReplicaDivergenceError(CRDTError):
    """Raised when replicas have diverged beyond recovery.

    Two replicas hold CRDT states that cannot be merged because one or
    both have been corrupted, or contain CRDTs of incompatible types
    under the same name. In a correctly operating system, anti-entropy
    rounds should always converge. Divergence indicates a fundamental
    breach of the replication protocol.
    """

    def __init__(self, replica_a: str, replica_b: str, crdt_name: str) -> None:
        self.replica_a = replica_a
        self.replica_b = replica_b
        self.crdt_name = crdt_name
        FizzBuzzError.__init__(
            self,
            f"Replicas '{replica_a}' and '{replica_b}' have irreconcilably "
            f"diverged on CRDT '{crdt_name}'. Anti-entropy has failed. "
            f"Strong Eventual Consistency can no longer be guaranteed.",
            error_code="EFP-CRDT03",
            context={
                "replica_a": replica_a,
                "replica_b": replica_b,
                "crdt_name": crdt_name,
            },
        )

