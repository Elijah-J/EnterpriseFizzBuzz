"""
Enterprise FizzBuzz Platform - FizzLog Datalog Query Engine Errors
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from ._base import FizzBuzzError


class DatalogError(FizzBuzzError):
    """Base exception for all Datalog query engine errors.

    The Datalog subsystem operates on logical facts and Horn clauses.
    When the engine encounters a condition that violates the semantic
    requirements of Datalog evaluation — non-ground assertions,
    unstratifiable programs, failed unification, or syntactically
    invalid queries — it raises a subclass of this exception to
    communicate the precise nature of the logical failure.
    """

    def __init__(self, message: str, **kwargs: Any) -> None:
        super().__init__(message, error_code=kwargs.pop("error_code", "EFP-DG00"), **kwargs)


class DatalogStratificationError(DatalogError):
    """Raised when a Datalog program contains a negative cycle.

    Stratified negation requires that the predicate dependency graph
    have no cycles involving negated edges. A negative cycle means
    that a predicate depends negatively on itself (directly or
    transitively), making the program's semantics undefined under
    the stratified semantics. The program must be restructured to
    break the negative cycle before evaluation can proceed.
    """

    def __init__(self, predicate: str, cycle_path: list[str]) -> None:
        self.predicate = predicate
        self.cycle_path = cycle_path
        cycle_str = " -> ".join(cycle_path)
        super().__init__(
            f"Negative cycle detected involving predicate '{predicate}': {cycle_str}. "
            f"Stratified negation requires acyclic negative dependencies.",
            error_code="EFP-DG01",
            context={"predicate": predicate, "cycle_path": cycle_path},
        )


class DatalogUnificationError(DatalogError):
    """Raised when unification fails in an unexpected manner.

    Unification between a pattern and a fact should either succeed
    (producing a substitution) or fail (returning None). This
    exception is raised when the unification engine encounters an
    internal inconsistency, such as a variable bound to two different
    values in the same substitution — a condition that should be
    impossible in a correctly implemented engine but is checked
    defensively because enterprise software trusts nothing.
    """

    def __init__(self, pattern: str, fact: str, reason: str) -> None:
        super().__init__(
            f"Unification failed between '{pattern}' and '{fact}': {reason}",
            error_code="EFP-DG02",
            context={"pattern": pattern, "fact": fact, "reason": reason},
        )


class DatalogQuerySyntaxError(DatalogError):
    """Raised when a Datalog query string cannot be parsed.

    The query parser expects the format predicate(arg1, arg2, ...)
    where arguments are variables (uppercase), string constants
    (lowercase), or integer literals. Deviations from this syntax
    result in a parse error at the indicated position.
    """

    def __init__(self, query: str, position: int, expected: str) -> None:
        super().__init__(
            f"Syntax error in query '{query}' at position {position}: expected {expected}",
            error_code="EFP-DG03",
            context={"query": query, "position": position, "expected": expected},
        )

