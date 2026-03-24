"""
Enterprise FizzBuzz Platform - Z Spec Exceptions
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from ._base import FizzBuzzError


class ZSpecError(FizzBuzzError):
    """Base exception for all Z notation formal specification errors.

    Raised when the Z specification engine encounters a condition that
    prevents the construction, evaluation, or verification of a formal
    specification. In a system where correctness is defined by mathematical
    specification, failure of the specification engine itself represents
    a foundational crisis.
    """

    def __init__(
        self,
        message: str,
        *,
        error_code: str = "EFP-ZS00",
        context: Optional[dict[str, Any]] = None,
    ) -> None:
        super().__init__(message, error_code=error_code, context=context)


class ZSpecTypeError(ZSpecError):
    """Raised when a Z schema calculus operation encounters a type mismatch.

    Schema conjunction requires that shared variable names have compatible
    types. When two schemas declare the same variable with different types,
    their conjunction is undefined — the schemas describe incompatible
    state spaces that cannot be meaningfully combined.
    """

    def __init__(self, variable: str, type_a: str, type_b: str) -> None:
        super().__init__(
            f"Type mismatch for variable '{variable}' in schema conjunction: "
            f"{type_a} vs {type_b}",
            error_code="EFP-ZS01",
            context={"variable": variable, "type_a": type_a, "type_b": type_b},
        )
        self.variable = variable
        self.type_a = type_a
        self.type_b = type_b


class ZSpecRefinementError(ZSpecError):
    """Raised when a refinement check detects a specification violation.

    A refinement violation means the implementation does not correctly
    implement the abstract specification. The retrieve relation fails
    to preserve the invariant, or an operation fails to satisfy the
    specification's postcondition. This is the formal equivalent of
    "the code is wrong".
    """

    def __init__(self, spec_name: str, impl_name: str, violations: int) -> None:
        super().__init__(
            f"Refinement check failed: '{impl_name}' does not refine '{spec_name}' "
            f"({violations} violation(s) detected)",
            error_code="EFP-ZS02",
            context={
                "spec_name": spec_name,
                "impl_name": impl_name,
                "violations": violations,
            },
        )
        self.spec_name = spec_name
        self.impl_name = impl_name
        self.violation_count = violations

