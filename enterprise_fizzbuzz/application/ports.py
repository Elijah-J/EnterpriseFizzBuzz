"""
Enterprise FizzBuzz Platform - Repository & Unit of Work Ports

Defines the abstract contracts (ports) for the Repository Pattern and
Unit of Work Pattern, because storing FizzBuzz results in a Python dict
wasn't enterprise enough until it had a formal hexagonal-architecture
port definition with abstract base classes and context manager protocols.

These ports live in the application layer per Ports & Adapters convention,
ensuring that the domain remains blissfully ignorant of how its precious
FizzBuzz results are persisted — whether that's in-memory, SQLite, the
filesystem, or carrier pigeon.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from enterprise_fizzbuzz.domain.models import EvaluationResult, FizzBuzzResult


class StrategyPort(ABC):
    """Abstract port for FizzBuzz evaluation strategies.

    The Anti-Corruption Layer's primary abstraction — a clean interface
    that hides the grotesque implementation details of whichever
    evaluation engine lurks beneath. Whether it's a simple modulo
    check, a Chain of Responsibility with seventeen links, or a
    neural network that took longer to train than it would have taken
    to just write ``n % 3``, this port presents a uniform facade.

    Every strategy adapter must implement this port, because without
    a common interface, the domain model would be contaminated by
    engine-specific concerns, and that would violate the sacred
    principles of hexagonal architecture.
    """

    @abstractmethod
    def classify(self, number: int) -> EvaluationResult:
        """Classify a number according to this strategy.

        Returns a frozen EvaluationResult containing the canonical
        classification and the strategy name for traceability.
        """
        ...

    @abstractmethod
    def get_strategy_name(self) -> str:
        """Return a human-readable name for this strategy.

        Used in logging, dashboards, disagreement reports, and
        passive-aggressive commit messages about why the ML strategy
        is slower than a for-loop.
        """
        ...


class AbstractRepository(ABC):
    """Abstract contract for FizzBuzz result persistence.

    Implementations must provide a transactional buffer that accumulates
    results via add(), makes them queryable via get()/list(), and only
    durably persists them upon commit(). Rollback discards all pending
    changes, because even FizzBuzz results deserve ACID guarantees
    (well, ACI at least — durability is negotiable when your backing
    store is a Python dictionary).
    """

    @abstractmethod
    def add(self, result: FizzBuzzResult) -> None:
        """Stage a FizzBuzz result for persistence.

        The result is buffered but NOT committed until commit() is called.
        Think of this as writing your grocery list — you haven't bought
        anything yet.
        """
        ...

    @abstractmethod
    def get(self, result_id: str) -> FizzBuzzResult:
        """Retrieve a single FizzBuzz result by its unique identifier.

        Raises ResultNotFoundError if the result doesn't exist, because
        returning None would be too easy and not enterprise enough.
        """
        ...

    @abstractmethod
    def list(self) -> list[FizzBuzzResult]:
        """Return all committed FizzBuzz results.

        Returns a list because generators are too lazy for enterprise
        software — we need all results in memory simultaneously so we
        can properly stress-test the garbage collector.
        """
        ...

    @abstractmethod
    def commit(self) -> None:
        """Durably persist all staged results.

        After this call, the results are considered committed and will
        survive... until the process exits, at which point the in-memory
        backend loses everything anyway. But at least we committed.
        """
        ...

    @abstractmethod
    def rollback(self) -> None:
        """Discard all staged-but-uncommitted results.

        This is the persistence equivalent of pretending the last few
        minutes never happened. All pending results are discarded, and
        the repository returns to its last committed state, ready to
        accept new results with a clean conscience.
        """
        ...


class AbstractUnitOfWork(ABC):
    """Abstract contract for transactional boundaries around repository operations.

    The Unit of Work groups multiple repository operations into a single
    atomic transaction. It's a context manager because Python's 'with'
    statement is the closest thing we have to a two-phase commit protocol.

    Usage::

        with uow:
            uow.repository.add(result1)
            uow.repository.add(result2)
            uow.repository.commit()
        # If an exception occurs, rollback is automatic.
        # If you forget to commit, rollback is also automatic.
        # The UoW assumes the worst about your code, and frankly,
        # it's usually right.
    """

    @property
    @abstractmethod
    def repository(self) -> AbstractRepository:
        """Access the repository managed by this Unit of Work.

        Returns the repository instance that participates in the current
        transaction. All operations through this repository are scoped
        to the UoW's transaction boundary.
        """
        ...

    @abstractmethod
    def __enter__(self) -> AbstractUnitOfWork:
        """Begin the transactional scope.

        Sets up any required transaction state. For the in-memory backend,
        this takes a snapshot. For SQLite, this begins a transaction.
        For the filesystem... well, it crosses its fingers.
        """
        ...

    @abstractmethod
    def __exit__(self, exc_type: type | None, exc_val: BaseException | None, exc_tb: object) -> None:
        """End the transactional scope.

        If an exception occurred, rollback is performed automatically.
        If no exception occurred but commit() was never called, rollback
        is ALSO performed automatically, because the UoW does not trust
        you to remember.
        """
        ...
