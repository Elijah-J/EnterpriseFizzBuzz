"""
Enterprise FizzBuzz Platform - Repository Pattern + Unit of Work exceptions
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from ._base import FizzBuzzError


class RepositoryError(FizzBuzzError):
    """Base exception for all repository-layer failures.

    Raised when the persistence layer encounters an error so
    catastrophic that even the in-memory dict cannot cope.
    Because if storing a FizzBuzz result in a Python dictionary
    can fail, the universe has larger problems than your ORM.
    """

    def __init__(self, message: str, *, backend: str = "unknown") -> None:
        super().__init__(
            f"Repository error ({backend}): {message}",
            error_code="EFP-RP00",
            context={"backend": backend},
        )


class ResultNotFoundError(RepositoryError):
    """Raised when a FizzBuzz result cannot be located in the repository.

    You asked for a result. The repository searched its heart (and
    its backing store). It's not there. Maybe it was never persisted,
    maybe it was rolled back into oblivion, or maybe it simply chose
    not to be found. Respect its boundaries.
    """

    def __init__(self, result_id: str, *, backend: str = "unknown") -> None:
        super().__init__(
            f"Result '{result_id}' not found",
            backend=backend,
        )
        self.error_code = "EFP-RP01"
        self.result_id = result_id


class UnitOfWorkError(RepositoryError):
    """Raised when the Unit of Work transaction lifecycle is violated.

    The Unit of Work pattern demands discipline: enter, do work,
    commit or rollback, exit. Deviating from this lifecycle
    violates the transactional guarantees that the Unit of Work
    pattern is designed to enforce.
    """

    def __init__(self, message: str, *, backend: str = "unknown") -> None:
        super().__init__(
            f"Unit of Work violation: {message}",
            backend=backend,
        )
        self.error_code = "EFP-RP02"


class RollbackError(RepositoryError):
    """Raised when a rollback operation itself fails.

    The rollback was supposed to undo the damage. Instead, the
    rollback caused more damage. This is the persistence-layer
    equivalent of trying to put out a fire with gasoline. At
    this point, just restart the process and pretend nothing happened.
    """

    def __init__(self, message: str, *, backend: str = "unknown") -> None:
        super().__init__(
            f"Rollback failed: {message}",
            backend=backend,
        )
        self.error_code = "EFP-RP03"

