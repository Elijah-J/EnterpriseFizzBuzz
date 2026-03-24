"""
Enterprise FizzBuzz Platform - Regex Engine Exceptions
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from ._base import FizzBuzzError


class RegexEngineError(FizzBuzzError):
    """Base exception for the FizzRegex regular expression engine.

    All errors originating from the Thompson NFA construction, Rabin-Scott
    DFA compilation, Hopcroft minimization, or DFA matching phases inherit
    from this class. The regex engine is a critical classification validation
    component, and failures here indicate that pattern matching integrity
    may be compromised.
    """

    def __init__(
        self,
        message: str,
        *,
        error_code: str = "EFP-RX00",
        context: Optional[dict[str, Any]] = None,
    ) -> None:
        super().__init__(message, error_code=error_code, context=context)


class RegexPatternSyntaxError(RegexEngineError):
    """Raised when the regex parser encounters invalid pattern syntax.

    The recursive-descent parser found a token sequence that does not
    conform to the regex grammar. Common causes include unmatched
    parentheses, trailing backslashes, and missing bracket closures.
    """

    def __init__(self, pattern: str, position: int, detail: str) -> None:
        super().__init__(
            f"Syntax error in pattern {pattern!r} at position {position}: {detail}",
            error_code="EFP-RX01",
            context={"pattern": pattern, "position": position},
        )
        self.pattern = pattern
        self.position = position


class RegexCompilationError(RegexEngineError):
    """Raised when the NFA-to-DFA compilation pipeline fails.

    This may occur during Thompson's construction (unknown AST node),
    Rabin-Scott subset construction (state explosion beyond limits),
    or Hopcroft minimization (partition refinement anomaly).
    """

    def __init__(self, detail: str) -> None:
        super().__init__(
            f"Regex compilation failed: {detail}",
            error_code="EFP-RX02",
            context={"detail": detail},
        )

