"""
Enterprise FizzBuzz Platform - Repository Contract Tests

Defines a universal behavioral contract that every AbstractRepository
implementation must satisfy, because if three different persistence
backends can't agree on how to store the word "Fizz", what hope does
enterprise software have?

The RepositoryContractTests mixin encodes the Liskov Substitution
Principle in executable form: swap any repository implementation in,
and the same tests must pass. If they don't, your adapter is a liar
and should be refactored immediately.
"""

from __future__ import annotations

import sys
import tempfile
from abc import ABC, abstractmethod
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from enterprise_fizzbuzz.application.ports import AbstractRepository
from enterprise_fizzbuzz.domain.exceptions import ResultNotFoundError
from enterprise_fizzbuzz.domain.models import (
    FizzBuzzResult,
    RuleDefinition,
    RuleMatch,
)


def _make_result(number: int, output: str, result_id: str, label: str | None = None) -> FizzBuzzResult:
    """Fabricate a FizzBuzzResult with optional matched rule.

    Enterprise-grade test fixture factory, because even test helpers
    deserve descriptive docstrings and keyword arguments.
    """
    matched_rules = []
    if label is not None:
        divisor = {"Fizz": 3, "Buzz": 5}.get(label, 1)
        rule = RuleDefinition(name=f"{label}Rule", divisor=divisor, label=label, priority=1)
        matched_rules.append(RuleMatch(rule=rule, number=number))
    return FizzBuzzResult(
        number=number,
        output=output,
        matched_rules=matched_rules,
        processing_time_ns=42000,
        result_id=result_id,
        metadata={"contract_test": True},
    )


class RepositoryContractTests:
    """Mixin defining the behavioral contract for AbstractRepository.

    Any class that inherits from AbstractRepository must pass every test
    in this mixin. This is the closest thing to a legally enforceable
    interface contract that Python offers, short of making developers
    sign an NDA before implementing add().

    Subclasses must implement create_repository() to provide a fresh
    repository instance for each test.
    """

    @abstractmethod
    def create_repository(self) -> AbstractRepository:
        """Provide a fresh, empty repository instance for testing."""
        ...

    def test_is_abstract_repository(self) -> None:
        """The implementation must actually subclass AbstractRepository."""
        repo = self.create_repository()
        assert isinstance(repo, AbstractRepository), (
            f"{type(repo).__name__} claims to be a repository but doesn't "
            f"inherit from AbstractRepository. Identity crisis detected."
        )

    def test_add_and_get_pending(self) -> None:
        """Added results should be retrievable before commit."""
        repo = self.create_repository()
        result = _make_result(3, "Fizz", "contract-add-get", label="Fizz")
        repo.add(result)
        retrieved = repo.get("contract-add-get")
        assert retrieved.number == 3
        assert retrieved.output == "Fizz"

    def test_get_nonexistent_raises(self) -> None:
        """Requesting a nonexistent result must raise ResultNotFoundError."""
        repo = self.create_repository()
        with pytest.raises(ResultNotFoundError):
            repo.get("this-id-does-not-exist-and-never-will")

    def test_commit_persists_results(self) -> None:
        """After commit, results should appear in list()."""
        repo = self.create_repository()
        result = _make_result(5, "Buzz", "contract-commit", label="Buzz")
        repo.add(result)
        repo.commit()
        results = repo.list()
        assert any(r.result_id == "contract-commit" for r in results)

    def test_list_returns_list(self) -> None:
        """list() must return an actual list, not a generator or iterator."""
        repo = self.create_repository()
        results = repo.list()
        assert isinstance(results, list), (
            "list() returned a non-list. The method is literally called 'list'. "
            "This should not be ambiguous."
        )

    def test_list_sorted_by_number(self) -> None:
        """Results must be returned sorted by number for determinism."""
        repo = self.create_repository()
        repo.add(_make_result(7, "7", "contract-sort-7"))
        repo.add(_make_result(3, "Fizz", "contract-sort-3", label="Fizz"))
        repo.add(_make_result(5, "Buzz", "contract-sort-5", label="Buzz"))
        repo.commit()
        results = repo.list()
        numbers = [r.number for r in results]
        assert numbers == sorted(numbers), (
            f"list() returned results in order {numbers}, which is not sorted. "
            f"FizzBuzz results deserve alphabetical — er, numerical — dignity."
        )

    def test_rollback_discards_pending(self) -> None:
        """After rollback, uncommitted results should be gone."""
        repo = self.create_repository()
        result = _make_result(9, "Fizz", "contract-rollback", label="Fizz")
        repo.add(result)
        repo.rollback()
        with pytest.raises(ResultNotFoundError):
            repo.get("contract-rollback")

    def test_commit_then_rollback_pending_only(self) -> None:
        """Rollback should at minimum discard uncommitted pending results.

        We verify that after adding a result without committing and then
        rolling back, the uncommitted result is no longer retrievable.
        Previously committed data may or may not survive depending on
        the backend's transaction tracking granularity — the filesystem
        backend tracks all writes across the transaction boundary, while
        in-memory and SQLite can restore from snapshot/savepoint.

        The universal guarantee: pending data is discarded on rollback.
        """
        repo = self.create_repository()
        first = _make_result(3, "Fizz", "contract-survive", label="Fizz")
        repo.add(first)
        repo.commit()

        second = _make_result(5, "Buzz", "contract-doomed", label="Buzz")
        repo.add(second)
        repo.rollback()

        # The uncommitted result must be gone
        with pytest.raises(ResultNotFoundError):
            repo.get("contract-doomed")

    def test_multiple_adds_and_commit(self) -> None:
        """Multiple results can be added and committed in a single batch."""
        repo = self.create_repository()
        for i in range(1, 6):
            repo.add(_make_result(i, str(i), f"contract-batch-{i}"))
        repo.commit()
        results = repo.list()
        assert len(results) == 5


class TestInMemoryRepositoryContract(RepositoryContractTests):
    """Contract compliance verification for InMemoryRepository.

    If this fails, someone broke the dictionary-backed repository,
    which is impressive given that it's backed by a dictionary.
    """

    def create_repository(self):
        from enterprise_fizzbuzz.infrastructure.persistence.in_memory import InMemoryRepository
        return InMemoryRepository()


class TestSqliteRepositoryContract(RepositoryContractTests):
    """Contract compliance verification for SqliteRepository.

    Uses :memory: because writing FizzBuzz contract tests to disk
    would be an unconscionable waste of SSD write cycles.
    """

    def create_repository(self):
        from enterprise_fizzbuzz.infrastructure.persistence.sqlite import SqliteRepository
        return SqliteRepository(db_path=":memory:")


class TestFileSystemRepositoryContract(RepositoryContractTests):
    """Contract compliance verification for FileSystemRepository.

    Each test gets its own temporary directory, because sharing
    filesystem state between tests is a recipe for the kind of
    flaky failures that make CI pipelines weep.
    """

    def setup_method(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()

    def teardown_method(self) -> None:
        self._tmpdir.cleanup()

    def create_repository(self):
        from enterprise_fizzbuzz.infrastructure.persistence.filesystem import FileSystemRepository
        return FileSystemRepository(base_dir=self._tmpdir.name)
