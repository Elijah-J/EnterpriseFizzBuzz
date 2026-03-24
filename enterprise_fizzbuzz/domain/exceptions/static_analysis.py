"""
Enterprise FizzBuzz Platform - Static Analysis / Linter Errors
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from ._base import FizzBuzzError


class LintError(FizzBuzzError):
    """Base exception for all FizzLint static analysis errors."""

    def __init__(self, message: str, **kwargs: Any) -> None:
        super().__init__(message, error_code="EFP-LINT0", **kwargs)


class LintConfigurationError(LintError):
    """Raised when the linter is misconfigured.

    This can occur when invalid rule IDs are passed to the disabled
    rules list, or when lint rule parameters are out of range.
    """

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.error_code = "EFP-LINT1"


class LintEngineError(LintError):
    """Raised when a lint rule fails during execution.

    This indicates an internal error in the lint rule implementation,
    not a violation in the user's rule definitions. Lint rules are
    expected to be side-effect-free and must not raise exceptions
    during normal operation.
    """

    def __init__(self, rule_id: str, message: str) -> None:
        self.failing_rule_id = rule_id
        super().__init__(message)
        self.error_code = "EFP-LINT2"

