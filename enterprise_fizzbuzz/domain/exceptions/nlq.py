"""
Enterprise FizzBuzz Platform - Natural Language Query Interface Exceptions
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from ._base import FizzBuzzError


class NLQError(FizzBuzzError):
    """Base exception for all Natural Language Query Interface errors.

    When the enterprise-grade, regex-powered, artisanally hand-crafted
    natural language processing pipeline fails to comprehend your
    perfectly reasonable question about divisibility, this is the
    exception hierarchy that catches the pieces.
    """

    def __init__(
        self,
        message: str,
        *,
        error_code: str = "EFP-NLQ0",
        context: Optional[dict[str, Any]] = None,
    ) -> None:
        super().__init__(message, error_code=error_code, context=context)


class NLQTokenizationError(NLQError):
    """Raised when the tokenizer fails to decompose a query into tokens.

    The regex-based lexer has encountered a string so incomprehensible
    that even our carefully curated pattern list — which handles numbers,
    keywords, and the occasional existential question about modulo
    arithmetic — has thrown up its hands in defeat.
    """

    def __init__(self, query: str, reason: str) -> None:
        super().__init__(
            f"Tokenization failed for query {query!r}: {reason}. "
            f"The regex engine has seen things it cannot unsee.",
            error_code="EFP-NLQ1",
            context={"query": query, "reason": reason},
        )


class NLQIntentClassificationError(NLQError):
    """Raised when the intent classifier cannot determine what the user wants.

    The rule-based decision tree — a sophisticated cascade of if/elif
    statements disguised as enterprise architecture — has examined your
    query from every angle and concluded that it has no idea what you're
    asking. Perhaps try phrasing your FizzBuzz question more corporately.
    """

    def __init__(self, query: str, tokens: Optional[list[str]] = None) -> None:
        super().__init__(
            f"Cannot classify intent for query {query!r}. "
            f"Tokens: {tokens or []}. The decision tree is stumped.",
            error_code="EFP-NLQ2",
            context={"query": query, "tokens": tokens or []},
        )


class NLQEntityExtractionError(NLQError):
    """Raised when the entity extractor fails to find actionable entities.

    Your query was understood at an intent level — we know you want
    something — but the entity extractor could not find any numbers,
    ranges, or classifications to operate on. It's like ordering at
    a restaurant but forgetting to specify what food you want.
    """

    def __init__(self, query: str, intent: str) -> None:
        super().__init__(
            f"Entity extraction failed for query {query!r} with intent '{intent}'. "
            f"No numbers, ranges, or classifications could be extracted. "
            f"The query is syntactically ambitious but semantically vacant.",
            error_code="EFP-NLQ3",
            context={"query": query, "intent": intent},
        )


class NLQExecutionError(NLQError):
    """Raised when query execution fails after successful parsing.

    The query was tokenized, the intent was classified, the entities
    were extracted — everything was going so well — and then the
    execution engine encountered an error. This is the NLQ equivalent
    of a plane that taxis, takes off, and then remembers it has no wings.
    """

    def __init__(self, query: str, intent: str, reason: str) -> None:
        super().__init__(
            f"Execution failed for query {query!r} (intent: {intent}): {reason}. "
            f"The parsing was flawless. The execution was not.",
            error_code="EFP-NLQ4",
            context={"query": query, "intent": intent, "reason": reason},
        )


class NLQUnsupportedQueryError(NLQError):
    """Raised when a query is syntactically valid but semantically unsupported.

    We understood what you said. We even agree it's a reasonable thing
    to ask. We just don't support it yet because the Enterprise FizzBuzz
    NLQ roadmap prioritizes other features, including expanded query
    coverage and additional semantic analysis capabilities.
    """

    def __init__(self, query: str, reason: str) -> None:
        super().__init__(
            f"Unsupported query {query!r}: {reason}. "
            f"This feature is on the NLQ roadmap, tentatively scheduled "
            f"for the heat death of the universe.",
            error_code="EFP-NLQ5",
            context={"query": query, "reason": reason},
        )

