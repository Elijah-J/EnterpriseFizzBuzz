"""
Enterprise FizzBuzz Platform - Formal Verification & Proof System Exceptions
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from ._base import FizzBuzzError


class FormalVerificationError(FizzBuzzError):
    """Base exception for the Formal Verification & Proof System.

    When your FizzBuzz platform requires Gentzen-style natural deduction
    proofs to verify that modulo arithmetic still works, you have achieved
    a level of engineering rigor that would make Bertrand Russell weep
    with either pride or despair. These exceptions cover everything from
    failed proof obligations to unsound Hoare triples to the devastating
    discovery that n % 3 might not always equal what you think it does.
    (Spoiler: it does. But we check anyway.)
    """

    def __init__(self, message: str, **kwargs: Any) -> None:
        super().__init__(
            message,
            error_code=kwargs.pop("error_code", "EFP-FV00"),
            context=kwargs.pop("context", {}),
        )


class ProofObligationFailedError(FormalVerificationError):
    """Raised when a proof obligation cannot be discharged.

    The verification engine attempted to prove a property of the
    FizzBuzz evaluation function and failed. This means either the
    property does not hold (unlikely for modulo arithmetic), the
    prover is buggy (always possible), or mathematics itself has
    a regression. We recommend filing a ticket with Euclid.
    """

    def __init__(self, property_name: str, counterexample: Optional[Any] = None) -> None:
        ce_msg = f" Counterexample: {counterexample}" if counterexample is not None else ""
        super().__init__(
            f"Proof obligation for property '{property_name}' could not be "
            f"discharged.{ce_msg} The theorem remains unproven, which is "
            f"the formal methods equivalent of a P0 incident.",
            error_code="EFP-FV01",
            context={"property_name": property_name, "counterexample": counterexample},
        )
        self.property_name = property_name
        self.counterexample = counterexample


class HoareTripleViolationError(FormalVerificationError):
    """Raised when a Hoare triple {P} S {Q} fails verification.

    The precondition held, the statement executed, but the postcondition
    was violated. In the context of FizzBuzz, this means that given a
    positive integer, the evaluate() function produced a result that is
    not in the set of valid outputs. This is the formal verification
    equivalent of discovering that 15 % 3 is suddenly 7.
    """

    def __init__(self, number: int, expected_outputs: str, actual_output: str) -> None:
        super().__init__(
            f"Hoare triple violation at n={number}: expected output in "
            f"{{{expected_outputs}}}, got '{actual_output}'. "
            f"The specification and implementation have irreconcilable differences.",
            error_code="EFP-FV02",
            context={
                "number": number,
                "expected_outputs": expected_outputs,
                "actual_output": actual_output,
            },
        )
        self.number = number


class InductionBaseFailedError(FormalVerificationError):
    """Raised when the base case of an induction proof fails.

    The very first step of the proof — verifying P(1) — has failed.
    If you cannot even prove that your FizzBuzz function works for
    the number 1, the inductive step is moot and the universal
    quantifier remains tragically uninstantiated.
    """

    def __init__(self, base_value: int, reason: str) -> None:
        super().__init__(
            f"Induction base case P({base_value}) failed: {reason}. "
            f"The proof collapses at its foundation, like a house of "
            f"cards built on unverified modulo arithmetic.",
            error_code="EFP-FV03",
            context={"base_value": base_value, "reason": reason},
        )
        self.base_value = base_value


class InductionStepFailedError(FormalVerificationError):
    """Raised when the inductive step of a proof fails.

    We assumed P(n) and tried to prove P(n+1), but the proof
    did not go through. The inductive hypothesis was insufficient,
    the case analysis was incomplete, or the FizzBuzz function has
    a subtle bug that only manifests under the scrutiny of formal
    methods. (Just kidding. It's modulo arithmetic. It works.)
    """

    def __init__(self, step_case: str, reason: str) -> None:
        super().__init__(
            f"Induction step failed for case '{step_case}': {reason}. "
            f"The proof cannot proceed beyond the base case, leaving an "
            f"infinite number of integers formally unverified.",
            error_code="EFP-FV04",
            context={"step_case": step_case, "reason": reason},
        )
        self.step_case = step_case


class PropertyVerificationTimeoutError(FormalVerificationError):
    """Raised when property verification exceeds the allotted time.

    If verifying that n % 3 == 0 implies the output contains "Fizz"
    takes longer than the configured timeout, something has gone
    profoundly wrong. Perhaps the integers have become uncountably
    infinite, or perhaps someone passed float('inf') as the range end.
    Either way, the verification engine has given up.
    """

    def __init__(self, property_name: str, timeout_ms: float) -> None:
        super().__init__(
            f"Property verification for '{property_name}' timed out after "
            f"{timeout_ms:.0f}ms. The proof search space is too large, or "
            f"the theorem is unprovable, or the CPU is philosophically opposed "
            f"to formal methods.",
            error_code="EFP-FV05",
            context={"property_name": property_name, "timeout_ms": timeout_ms},
        )

