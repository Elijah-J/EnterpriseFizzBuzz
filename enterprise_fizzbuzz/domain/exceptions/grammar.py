"""
Enterprise FizzBuzz Platform - FizzGrammar -- Formal Grammar & Parser Generator Exceptions
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from ._base import FizzBuzzError


class GrammarError(FizzBuzzError):
    """Base exception for all Formal Grammar & Parser Generator errors.

    Raised when the FizzGrammar subsystem encounters a condition that
    prevents it from analyzing, classifying, or generating parsers for
    a formal grammar specification. The grammar may be syntactically
    malformed, semantically ambiguous, or structurally incompatible
    with the target parser class. In any case, the platform cannot
    proceed with grammar-driven parsing until the issue is resolved.
    """

    def __init__(self, message: str, **kwargs: Any) -> None:
        super().__init__(
            message,
            error_code=kwargs.pop("error_code", "EFP-GR00"),
            context=kwargs.pop("context", {}),
        )


class GrammarSyntaxError(GrammarError):
    """Raised when a BNF/EBNF grammar specification is malformed.

    The grammar parser encountered a token sequence that does not
    conform to the meta-grammar of BNF/EBNF notation. This is the
    meta-level equivalent of a syntax error: the grammar that defines
    grammars has been violated. The irony is not lost on the platform.
    """

    def __init__(self, line: int, column: int, detail: str) -> None:
        self.line = line
        self.column = column
        self.detail = detail
        super().__init__(
            f"Grammar syntax error at line {line}, column {column}: {detail}. "
            f"The grammar specification itself has a grammar error.",
            error_code="EFP-GR01",
            context={"line": line, "column": column, "detail": detail},
        )


class GrammarConflictError(GrammarError):
    """Raised when a grammar has LL(1) conflicts that prevent deterministic parsing.

    Two or more production alternatives for the same non-terminal have
    overlapping FIRST sets, meaning the parser cannot decide which
    alternative to pursue based on a single lookahead token. The grammar
    is not LL(1). This is not necessarily a defect in the grammar --
    many useful grammars are not LL(1) -- but it means the generated
    parser must use backtracking rather than predictive parsing, which
    offends the sensibilities of anyone who has read the Dragon Book.
    """

    def __init__(self, non_terminal: str, conflicts: list[str]) -> None:
        self.non_terminal = non_terminal
        self.conflicts = conflicts
        super().__init__(
            f"LL(1) conflict for non-terminal '{non_terminal}': "
            f"overlapping FIRST sets in alternatives: {', '.join(conflicts)}. "
            f"The grammar requires more than one token of lookahead.",
            error_code="EFP-GR02",
            context={"non_terminal": non_terminal, "conflicts": conflicts},
        )


class GrammarParseError(GrammarError):
    """Raised when a generated parser encounters a syntax error in its input.

    The generated recursive-descent parser found a token that does not
    match any expected alternative at the current parse position. The
    input string is not in the language defined by the grammar. This is
    the intended purpose of parsing: to distinguish strings that belong
    to the language from strings that do not. The parser has done its job.
    The input has failed its audition.
    """

    def __init__(
        self, line: int, column: int, found: str, expected: list[str]
    ) -> None:
        self.line = line
        self.column = column
        self.found = found
        self.expected = expected
        super().__init__(
            f"Parse error at line {line}, column {column}: "
            f"found '{found}', expected one of: {', '.join(expected)}. "
            f"The input does not belong to this language.",
            error_code="EFP-GR03",
            context={
                "line": line,
                "column": column,
                "found": found,
                "expected": expected,
            },
        )

