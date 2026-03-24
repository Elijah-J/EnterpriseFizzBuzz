"""
Enterprise FizzBuzz Platform - FizzSQL Relational Query Engine Exceptions
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from ._base import FizzBuzzError


class FizzSQLError(FizzBuzzError):
    """Base exception for all FizzSQL query engine errors.

    When the FizzSQL engine encounters a query it cannot parse,
    plan, optimize, or execute, this exception (or one of its
    children) is raised. The query has been logged for audit
    purposes. The DBA has been paged. (The DBA is Bob
    McFizzington. He is unavailable.)
    """

    def __init__(
        self,
        message: str,
        *,
        error_code: str = "EFP-SQL0",
        context: Optional[dict[str, Any]] = None,
    ) -> None:
        super().__init__(message, error_code=error_code, context=context)


class FizzSQLSyntaxError(FizzSQLError):
    """Raised when the FizzSQL lexer or parser encounters invalid syntax.

    The recursive descent parser has descended into a state of
    recursive despair. Your SQL query contains a token that
    violates the grammar of the FizzBuzz Query Language.
    Common causes include: missing FROM clause, unmatched
    parentheses, or attempting to use HAVING without GROUP BY
    (an act of hubris). The parser's state machine has entered
    an absorbing state from which no recovery is possible.
    """

    def __init__(self, query: str, position: int, detail: str) -> None:
        marker = " " * position + "^"
        super().__init__(
            f"FizzSQL syntax error at position {position}: {detail}\n"
            f"  {query}\n"
            f"  {marker}\n"
            f"The parser's recursive descent has become a recursive crash.",
            error_code="EFP-SQL1",
            context={"query": query, "position": position, "detail": detail},
        )
        self.query = query
        self.position = position
        self.detail = detail


class FizzSQLTableNotFoundError(FizzSQLError):
    """Raised when a query references a virtual table that does not exist.

    The FizzSQL engine provides exactly 5 virtual tables:
    evaluations, cache_entries, blockchain_blocks, sla_metrics,
    and events. You managed to reference a table that doesn't
    exist in this carefully curated catalog of in-memory views
    over FizzBuzz platform internals. The information_schema
    weeps for your lost query.
    """

    def __init__(self, table_name: str, available: list[str]) -> None:
        available_str = ", ".join(available)
        super().__init__(
            f"Table '{table_name}' does not exist. Available tables: "
            f"[{available_str}]. The FizzSQL catalog contains exactly "
            f"5 virtual tables, and somehow you referenced one that "
            f"isn't among them. This is the relational equivalent "
            f"of looking for a book in a library with 5 books and "
            f"asking for a 6th.",
            error_code="EFP-SQL2",
            context={"table_name": table_name, "available": available},
        )
        self.table_name = table_name
        self.available = available


class FizzSQLExecutionError(FizzSQLError):
    """Raised when a query fails during the Volcano model execution phase.

    The physical operator pipeline has encountered a runtime error
    while pulling tuples through the open()/next()/close() iterator
    protocol. This is the database equivalent of a segfault, except
    in Python we get a stack trace and a strongly worded exception
    message. The query execution plan looked promising on paper, but
    reality — as always — had other plans.
    """

    def __init__(self, query: str, detail: str) -> None:
        super().__init__(
            f"FizzSQL execution error: {detail}\n"
            f"  Query: {query}\n"
            f"The Volcano model has erupted. Lava (exceptions) everywhere.",
            error_code="EFP-SQL3",
            context={"query": query, "detail": detail},
        )
        self.query = query
        self.detail = detail

