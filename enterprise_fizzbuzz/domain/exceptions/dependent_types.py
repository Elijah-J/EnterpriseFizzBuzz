"""
Enterprise FizzBuzz Platform - Dependent Type System & Curry-Howard Proof Engine Exceptions
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from ._base import FizzBuzzError


class DependentTypeError(FizzBuzzError):
    """Base exception for all dependent type system errors.

    When your type theory is so dependent that it can't even check whether
    15 is divisible by 3 without constructing a proof term, and that proof
    term fails to type-check, you've reached the Curry-Howard correspondence's
    final form: crashing at the type level to avoid crashing at the value level.
    The fact that a single modulo operation would have sufficed is, as always,
    outside the scope of the type system's guarantees.
    """

    def __init__(
        self,
        message: str,
        *,
        error_code: str = "EFP-DP00",
        context: Optional[dict[str, Any]] = None,
    ) -> None:
        super().__init__(message, error_code=error_code, context=context)


class WitnessConstructionError(DependentTypeError):
    """Raised when a divisibility witness cannot be constructed.

    A witness is a constructive proof that n is divisible by d — i.e.,
    there exists a quotient q such that n = d * q. If no such q exists
    (because n is not, in fact, divisible by d), the witness construction
    fails, and the type system refuses to let you lie about arithmetic.

    The standard approach of checking n % d == 0 provides correctness
    but not formal verifiability. The witness-based approach provides
    a constructive proof that is machine-checkable.
    """

    def __init__(self, n: int, d: int) -> None:
        super().__init__(
            f"Cannot construct divisibility witness: {n} is not divisible by {d}. "
            f"No quotient q exists such that {n} = {d} * q. "
            f"The Curry-Howard correspondence weeps.",
            error_code="EFP-DP01",
            context={"n": n, "d": d, "remainder": n % d if d != 0 else None},
        )
        self.n = n
        self.d = d


class ProofObligationError(DependentTypeError):
    """Raised when a proof obligation cannot be discharged.

    The proof engine was asked to prove a proposition for which no
    evidence could be found. In a total language, this would be a
    compile-time error. In Python, it is a runtime exception, which
    is arguably worse but definitely more exciting.
    """

    def __init__(self, n: int, classification: str, reason: str) -> None:
        super().__init__(
            f"Proof obligation for {n} as '{classification}' could not be discharged: "
            f"{reason}. The type-theoretic gods are displeased.",
            error_code="EFP-DP02",
            context={
                "n": n,
                "classification": classification,
                "reason": reason,
            },
        )
        self.n = n
        self.classification = classification


class TypeCheckError(DependentTypeError):
    """Raised when bidirectional type checking fails.

    The proof term was well-formed syntactically but ill-typed semantically.
    In Agda, this would be a yellow highlighting. In Coq, a red squiggly.
    In the Enterprise FizzBuzz type system, this manifests as an exception
    with a detailed error message and a six-character error code for
    precise diagnostic identification.
    """

    def __init__(self, term: str, expected_type: str, actual_type: str) -> None:
        super().__init__(
            f"Type check failed: term '{term}' has type '{actual_type}' "
            f"but was expected to have type '{expected_type}'. "
            f"The bidirectional type checker is not impressed.",
            error_code="EFP-DP03",
            context={
                "term": term,
                "expected_type": expected_type,
                "actual_type": actual_type,
            },
        )
        self.term = term
        self.expected_type = expected_type
        self.actual_type = actual_type


class UnificationError(DependentTypeError):
    """Raised when first-order unification of type expressions fails.

    Two types were expected to unify but turned out to be incompatible.
    This is the type-theoretic equivalent of discovering that Fizz and
    Buzz are, in fact, different words — a revelation that should surprise
    no one, yet here we are with a dedicated exception class for it.
    """

    def __init__(self, type_a: str, type_b: str, reason: str) -> None:
        super().__init__(
            f"Unification failed: cannot unify '{type_a}' with '{type_b}': {reason}. "
            f"The occurs check sends its regards.",
            error_code="EFP-DP04",
            context={
                "type_a": type_a,
                "type_b": type_b,
                "reason": reason,
            },
        )
        self.type_a = type_a
        self.type_b = type_b

