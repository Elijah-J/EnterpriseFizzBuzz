"""
Enterprise FizzBuzz Platform - In-Memory Repository & Unit of Work

Implements the Repository Pattern and Unit of Work Pattern using a
Python dictionary as the backing store. This is, objectively, the
most over-engineered way to append items to a list ever conceived.

The InMemoryRepository maintains a committed store and a pending
buffer. On commit(), pending items are merged into the committed
store. On rollback(), the pending buffer is discarded and the
committed store is restored from a snapshot taken at transaction start.

The fact that we implemented transactional semantics for an in-memory
dictionary that will be garbage-collected when the process exits is
a testament to our unwavering commitment to enterprise architecture.
"""

from __future__ import annotations

import copy
import logging
from typing import Optional

from enterprise_fizzbuzz.application.ports import AbstractRepository, AbstractUnitOfWork
from enterprise_fizzbuzz.domain.exceptions import (
    RepositoryError,
    ResultNotFoundError,
    RollbackError,
    UnitOfWorkError,
)
from enterprise_fizzbuzz.domain.models import Event, EventType, FizzBuzzResult

logger = logging.getLogger(__name__)

_BACKEND = "in_memory"


class InMemoryRepository(AbstractRepository):
    """Repository backed by a Python dictionary.

    Because Martin Fowler's Patterns of Enterprise Application
    Architecture never said the repository had to be backed by
    anything more sophisticated than a dict. The pattern is the
    point, not the persistence.

    Attributes:
        _committed: The durably committed results (durably = in RAM).
        _pending: Results staged for the next commit.
        _snapshot: A deep copy of _committed, taken at transaction start,
                   for rollback support. Because even dicts deserve ACID.
    """

    def __init__(self) -> None:
        self._committed: dict[str, FizzBuzzResult] = {}
        self._pending: dict[str, FizzBuzzResult] = {}
        self._snapshot: Optional[dict[str, FizzBuzzResult]] = None

    def add(self, result: FizzBuzzResult) -> None:
        """Stage a FizzBuzz result in the pending buffer."""
        self._pending[result.result_id] = result
        logger.debug(
            "Staged result %s (number=%d, output=%s) in pending buffer",
            result.result_id[:8],
            result.number,
            result.output,
        )

    def get(self, result_id: str) -> FizzBuzzResult:
        """Retrieve a result from committed or pending stores."""
        if result_id in self._pending:
            return self._pending[result_id]
        if result_id in self._committed:
            return self._committed[result_id]
        raise ResultNotFoundError(result_id, backend=_BACKEND)

    def list(self) -> list[FizzBuzzResult]:
        """Return all committed results, sorted by number for determinism."""
        return sorted(self._committed.values(), key=lambda r: r.number)

    def commit(self) -> None:
        """Merge pending results into the committed store."""
        count = len(self._pending)
        self._committed.update(self._pending)
        self._pending.clear()
        logger.info(
            "Committed %d result(s) to in-memory repository (total: %d)",
            count,
            len(self._committed),
        )

    def rollback(self) -> None:
        """Discard pending results and restore from snapshot."""
        pending_count = len(self._pending)
        self._pending.clear()
        if self._snapshot is not None:
            self._committed = copy.deepcopy(self._snapshot)
            logger.info(
                "Rolled back %d pending result(s) and restored snapshot (%d committed)",
                pending_count,
                len(self._committed),
            )
        else:
            logger.info(
                "Rolled back %d pending result(s) (no snapshot to restore)",
                pending_count,
            )

    def take_snapshot(self) -> None:
        """Take a deep copy of the committed store for rollback support."""
        self._snapshot = copy.deepcopy(self._committed)
        logger.debug(
            "Snapshot taken: %d committed result(s)", len(self._committed)
        )

    def clear_snapshot(self) -> None:
        """Discard the rollback snapshot to free memory."""
        self._snapshot = None


class InMemoryUnitOfWork(AbstractUnitOfWork):
    """Unit of Work wrapping an InMemoryRepository.

    Provides transactional boundaries for in-memory FizzBuzz result
    persistence. On __enter__, a snapshot is taken. On __exit__, if
    no explicit commit was performed or if an exception occurred, an
    automatic rollback is triggered — because the UoW trusts nobody,
    least of all the developer who thought "I'll commit later."
    """

    def __init__(self, repo: Optional[InMemoryRepository] = None) -> None:
        self._repo = repo or InMemoryRepository()
        self._committed = False

    @property
    def repository(self) -> InMemoryRepository:
        return self._repo

    def __enter__(self) -> InMemoryUnitOfWork:
        self._committed = False
        self._repo.take_snapshot()
        logger.debug("InMemoryUnitOfWork: transaction started")
        return self

    def __exit__(
        self,
        exc_type: type | None,
        exc_val: BaseException | None,
        exc_tb: object,
    ) -> None:
        if exc_type is not None or not self._committed:
            self._repo.rollback()
            logger.debug(
                "InMemoryUnitOfWork: auto-rollback (exc=%s, committed=%s)",
                exc_type,
                self._committed,
            )
        self._repo.clear_snapshot()

    def commit(self) -> None:
        """Commit the current transaction via the repository."""
        self._repo.commit()
        self._committed = True
