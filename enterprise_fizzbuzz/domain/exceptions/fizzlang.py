"""
Enterprise FizzBuzz Platform - FizzLang DSL Exceptions (EFP-FL10 through EFP-FL14)
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from ._base import FizzBuzzError


class FizzLangError(FizzBuzzError):
    """Base exception for all FizzLang domain-specific language errors.

    FizzLang is a purpose-built, Turing-INCOMPLETE programming language
    designed exclusively for expressing FizzBuzz rules. It cannot loop,
    recurse, or define functions — because those features would make it
    useful for something other than FizzBuzz, and we can't have that.

    All FizzLang exceptions include career advice, because if the DSL
    you built for modulo arithmetic is throwing errors, it may be time
    to reconsider your life choices.
    """

    def __init__(
        self,
        message: str,
        *,
        error_code: str = "EFP-FL10",
        context: Optional[dict[str, Any]] = None,
        career_advice: str = "Consider a career in COBOL maintenance.",
    ) -> None:
        full_message = f"{message} Career advice: {career_advice}"
        super().__init__(full_message, error_code=error_code, context=context)
        self.career_advice = career_advice


class FizzLangLexerError(FizzLangError):
    """Raised when the FizzLang lexer encounters an unrecognizable character.

    The hand-written character scanner has encountered a symbol that exists
    in no known programming language, natural language, or alien script.
    The lexer's vocabulary is intentionally limited — it knows keywords,
    operators, strings, and integers. Everything else is a personal affront
    to the tokenizer.
    """

    def __init__(self, char: str, line: int, col: int) -> None:
        super().__init__(
            f"Unexpected character {char!r} at line {line}, column {col}. "
            f"FizzLang does not recognize this glyph.",
            error_code="EFP-FL11",
            context={"char": char, "line": line, "col": col},
            career_advice="Consider a career in COBOL maintenance — they don't have Unicode problems.",
        )
        self.char = char
        self.line = line
        self.col = col


class FizzLangParseError(FizzLangError):
    """Raised when the recursive-descent parser encounters a syntax error.

    The parser expected one thing and got another, which is the fundamental
    tragedy of all parsing. FizzLang's grammar is deliberately minimal —
    no loops, no functions, no recursion — yet somehow the user still
    managed to confuse it. This is, frankly, impressive.
    """

    def __init__(self, expected: str, got: str, line: int) -> None:
        super().__init__(
            f"Parse error at line {line}: expected {expected}, got {got!r}. "
            f"FizzLang syntax is simpler than a shopping list, yet here we are.",
            error_code="EFP-FL12",
            context={"expected": expected, "got": got, "line": line},
            career_advice="Consider a career in artisanal YAML authoring — fewer semicolons.",
        )
        self.expected = expected
        self.got = got
        self.line = line


class FizzLangTypeError(FizzLangError):
    """Raised when the FizzLang type checker detects a semantic violation.

    The type checker enforces rules that the parser cannot: unique rule
    names, valid emit types, proper operator usage, and the existential
    requirement that at least one rule must exist. If the type checker
    rejects your program, it means the program is syntactically valid
    but logically inconsistent, indicating a semantic violation.
    """

    def __init__(self, reason: str, node_type: Optional[str] = None) -> None:
        super().__init__(
            f"Type error: {reason}. "
            f"The FizzLang type system is stricter than your code review process.",
            error_code="EFP-FL13",
            context={"reason": reason, "node_type": node_type or "unknown"},
            career_advice="Consider a career in dynamically typed languages — fewer rules, more chaos.",
        )
        self.reason = reason
        self.node_type = node_type


class FizzLangRuntimeError(FizzLangError):
    """Raised when the FizzLang tree-walking interpreter encounters a runtime error.

    Despite FizzLang being Turing-incomplete and incapable of infinite
    loops, the interpreter has still managed to fail at runtime. This
    requires a special kind of program — one that passes lexing, parsing,
    and type checking, yet still finds a way to misbehave. The interpreter
    is both impressed and disappointed.
    """

    def __init__(self, reason: str, number: Optional[int] = None) -> None:
        super().__init__(
            f"Runtime error: {reason}. "
            f"Even a Turing-incomplete language can fail at runtime, apparently.",
            error_code="EFP-FL14",
            context={"reason": reason, "number": number},
            career_advice="Consider a career in manual arithmetic — no runtime errors, just carpal tunnel.",
        )
        self.reason = reason
        self.number = number

