"""
Enterprise FizzBuzz Platform - Repository Pattern + Unit of Work Tests

Comprehensive tests for all three persistence backends and their
respective Unit of Work implementations.

Because untested persistence code is just a bug that hasn't been
discovered yet, and FizzBuzz results that vanish into the void
without a trace are a compliance violation of the highest order.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from enterprise_fizzbuzz.domain.exceptions import (
    RepositoryError,
    ResultNotFoundError,
    RollbackError,
    UnitOfWorkError,
)
from enterprise_fizzbuzz.domain.models import (
    EventType,
    FizzBuzzResult,
    RuleDefinition,
    RuleMatch,
)
from enterprise_fizzbuzz.infrastructure.persistence.in_memory import (
    InMemoryRepository,
    InMemoryUnitOfWork,
)
from enterprise_fizzbuzz.infrastructure.persistence.sqlite import (
    SqliteRepository,
    SqliteUnitOfWork,
)
from enterprise_fizzbuzz.infrastructure.persistence.filesystem import (
    FileSystemRepository,
    FileSystemUnitOfWork,
)


# ============================================================
# Fixtures
# ============================================================


@pytest.fixture
def fizz_result() -> FizzBuzzResult:
    """A FizzBuzz result for the number 3 (Fizz)."""
    rule = RuleDefinition(name="FizzRule", divisor=3, label="Fizz", priority=1)
    return FizzBuzzResult(
        number=3,
        output="Fizz",
        matched_rules=[RuleMatch(rule=rule, number=3)],
        processing_time_ns=42000,
        result_id="fizz-0003",
        metadata={"strategy": "standard"},
    )


@pytest.fixture
def buzz_result() -> FizzBuzzResult:
    """A FizzBuzz result for the number 5 (Buzz)."""
    rule = RuleDefinition(name="BuzzRule", divisor=5, label="Buzz", priority=2)
    return FizzBuzzResult(
        number=5,
        output="Buzz",
        matched_rules=[RuleMatch(rule=rule, number=5)],
        processing_time_ns=37000,
        result_id="buzz-0005",
        metadata={"strategy": "standard"},
    )


@pytest.fixture
def plain_result() -> FizzBuzzResult:
    """A FizzBuzz result for the number 7 (plain number)."""
    return FizzBuzzResult(
        number=7,
        output="7",
        matched_rules=[],
        processing_time_ns=1000,
        result_id="plain-0007",
    )


# ============================================================
# Exception Tests
# ============================================================


class TestRepositoryExceptions:
    def test_repository_error_has_code(self):
        err = RepositoryError("test failure", backend="in_memory")
        assert "EFP-RP00" in str(err)
        assert "in_memory" in str(err)

    def test_result_not_found_error(self):
        err = ResultNotFoundError("some-id", backend="sqlite")
        assert err.result_id == "some-id"
        assert "EFP-RP01" == err.error_code

    def test_unit_of_work_error(self):
        err = UnitOfWorkError("transaction violated", backend="filesystem")
        assert "EFP-RP02" == err.error_code

    def test_rollback_error(self):
        err = RollbackError("disk full", backend="filesystem")
        assert "EFP-RP03" == err.error_code


# ============================================================
# EventType Tests
# ============================================================


class TestRepositoryEventTypes:
    def test_repository_event_types_exist(self):
        assert EventType.REPOSITORY_RESULT_ADDED is not None
        assert EventType.REPOSITORY_COMMITTED is not None
        assert EventType.REPOSITORY_ROLLED_BACK is not None
        assert EventType.ROLLBACK_FILE_DELETED is not None


# ============================================================
# InMemoryRepository Tests
# ============================================================


class TestInMemoryRepository:
    def test_add_and_get(self, fizz_result):
        repo = InMemoryRepository()
        repo.add(fizz_result)
        retrieved = repo.get(fizz_result.result_id)
        assert retrieved.number == 3
        assert retrieved.output == "Fizz"

    def test_get_not_found_raises(self):
        repo = InMemoryRepository()
        with pytest.raises(ResultNotFoundError):
            repo.get("nonexistent-id")

    def test_commit_moves_pending_to_committed(self, fizz_result):
        repo = InMemoryRepository()
        repo.add(fizz_result)
        assert repo.list() == []  # not committed yet
        repo.commit()
        results = repo.list()
        assert len(results) == 1
        assert results[0].output == "Fizz"

    def test_rollback_discards_pending(self, fizz_result):
        repo = InMemoryRepository()
        repo.add(fizz_result)
        repo.rollback()
        assert repo.list() == []
        with pytest.raises(ResultNotFoundError):
            repo.get(fizz_result.result_id)

    def test_rollback_restores_snapshot(self, fizz_result, buzz_result):
        repo = InMemoryRepository()
        repo.add(fizz_result)
        repo.commit()
        repo.take_snapshot()
        repo.add(buzz_result)
        repo.commit()
        # Now rollback should restore to snapshot state (only fizz)
        repo.rollback()
        results = repo.list()
        assert len(results) == 1
        assert results[0].output == "Fizz"

    def test_list_returns_sorted_by_number(self, fizz_result, buzz_result, plain_result):
        repo = InMemoryRepository()
        repo.add(buzz_result)
        repo.add(plain_result)
        repo.add(fizz_result)
        repo.commit()
        results = repo.list()
        assert [r.number for r in results] == [3, 5, 7]


class TestInMemoryUnitOfWork:
    def test_commit_persists_results(self, fizz_result, buzz_result):
        uow = InMemoryUnitOfWork()
        with uow:
            uow.repository.add(fizz_result)
            uow.repository.add(buzz_result)
            uow.commit()
        # After context exit, results should still be in the repo
        assert len(uow.repository.list()) == 2

    def test_auto_rollback_on_exception(self, fizz_result):
        uow = InMemoryUnitOfWork()
        with pytest.raises(ValueError):
            with uow:
                uow.repository.add(fizz_result)
                raise ValueError("Oops")
        # Result should not be persisted
        assert len(uow.repository.list()) == 0

    def test_auto_rollback_without_commit(self, fizz_result):
        uow = InMemoryUnitOfWork()
        with uow:
            uow.repository.add(fizz_result)
            # Deliberately not calling commit()
        assert len(uow.repository.list()) == 0

    def test_repository_property(self):
        uow = InMemoryUnitOfWork()
        assert isinstance(uow.repository, InMemoryRepository)


# ============================================================
# SqliteRepository Tests
# ============================================================


class TestSqliteRepository:
    def test_add_and_get(self, tmp_path, fizz_result):
        db_path = str(tmp_path / "test.db")
        repo = SqliteRepository(db_path=db_path)
        repo.add(fizz_result)
        repo.commit()
        retrieved = repo.get(fizz_result.result_id)
        assert retrieved.number == 3
        assert retrieved.output == "Fizz"
        assert len(retrieved.matched_rules) == 1
        assert retrieved.matched_rules[0].rule.label == "Fizz"
        repo.close()

    def test_get_not_found_raises(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        repo = SqliteRepository(db_path=db_path)
        with pytest.raises(ResultNotFoundError):
            repo.get("nonexistent-id")
        repo.close()

    def test_list_returns_sorted(self, tmp_path, fizz_result, buzz_result, plain_result):
        db_path = str(tmp_path / "test.db")
        repo = SqliteRepository(db_path=db_path)
        repo.add(buzz_result)
        repo.add(plain_result)
        repo.add(fizz_result)
        repo.commit()
        results = repo.list()
        assert [r.number for r in results] == [3, 5, 7]
        repo.close()

    def test_rollback_discards_uncommitted(self, tmp_path, fizz_result, buzz_result):
        db_path = str(tmp_path / "test.db")
        repo = SqliteRepository(db_path=db_path)
        repo.add(fizz_result)
        repo.commit()
        repo.add(buzz_result)
        repo.rollback()
        results = repo.list()
        assert len(results) == 1
        assert results[0].output == "Fizz"
        repo.close()

    def test_in_memory_sqlite(self, fizz_result):
        repo = SqliteRepository(db_path=":memory:")
        repo.add(fizz_result)
        repo.commit()
        assert len(repo.list()) == 1
        repo.close()

    def test_metadata_round_trip(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        repo = SqliteRepository(db_path=db_path)
        result = FizzBuzzResult(
            number=42,
            output="42",
            result_id="meta-test",
            metadata={"strategy": "ml", "confidence": 0.99},
        )
        repo.add(result)
        repo.commit()
        retrieved = repo.get("meta-test")
        assert retrieved.metadata["strategy"] == "ml"
        assert retrieved.metadata["confidence"] == 0.99
        repo.close()


class TestSqliteUnitOfWork:
    def test_commit_persists_results(self, tmp_path, fizz_result):
        db_path = str(tmp_path / "test.db")
        uow = SqliteUnitOfWork(db_path=db_path)
        with uow:
            uow.repository.add(fizz_result)
            uow.commit()
        # Verify with a fresh connection
        repo = SqliteRepository(db_path=db_path)
        assert len(repo.list()) == 1
        repo.close()

    def test_auto_rollback_on_exception(self, tmp_path, fizz_result):
        db_path = str(tmp_path / "test.db")
        uow = SqliteUnitOfWork(db_path=db_path)
        with pytest.raises(ValueError):
            with uow:
                uow.repository.add(fizz_result)
                raise ValueError("Oops")
        # Verify nothing persisted
        repo = SqliteRepository(db_path=db_path)
        assert len(repo.list()) == 0
        repo.close()

    def test_auto_rollback_without_commit(self, tmp_path, fizz_result):
        db_path = str(tmp_path / "test.db")
        uow = SqliteUnitOfWork(db_path=db_path)
        with uow:
            uow.repository.add(fizz_result)
        # Verify nothing persisted
        repo = SqliteRepository(db_path=db_path)
        assert len(repo.list()) == 0
        repo.close()


# ============================================================
# FileSystemRepository Tests
# ============================================================


class TestFileSystemRepository:
    def test_add_and_commit(self, tmp_path, fizz_result):
        repo = FileSystemRepository(base_dir=str(tmp_path))
        repo.add(fizz_result)
        repo.commit()
        # Verify file exists on disk
        expected_file = tmp_path / f"{fizz_result.result_id}.json"
        assert expected_file.exists()
        # Verify content
        data = json.loads(expected_file.read_text())
        assert data["number"] == 3
        assert data["output"] == "Fizz"

    def test_get_from_disk(self, tmp_path, fizz_result):
        repo = FileSystemRepository(base_dir=str(tmp_path))
        repo.add(fizz_result)
        repo.commit()
        # Create fresh repo to force disk read
        repo2 = FileSystemRepository(base_dir=str(tmp_path))
        retrieved = repo2.get(fizz_result.result_id)
        assert retrieved.number == 3
        assert retrieved.output == "Fizz"
        assert len(retrieved.matched_rules) == 1

    def test_get_not_found_raises(self, tmp_path):
        repo = FileSystemRepository(base_dir=str(tmp_path))
        with pytest.raises(ResultNotFoundError):
            repo.get("nonexistent-id")

    def test_list_returns_sorted(self, tmp_path, fizz_result, buzz_result, plain_result):
        repo = FileSystemRepository(base_dir=str(tmp_path))
        repo.add(buzz_result)
        repo.add(plain_result)
        repo.add(fizz_result)
        repo.commit()
        results = repo.list()
        assert [r.number for r in results] == [3, 5, 7]

    def test_rollback_deletes_written_files(self, tmp_path, fizz_result, buzz_result):
        repo = FileSystemRepository(base_dir=str(tmp_path))
        repo.add(fizz_result)
        repo.commit()
        # Now add another and rollback
        repo.add(buzz_result)
        repo.commit()
        repo.rollback()
        # buzz file should be deleted
        buzz_file = tmp_path / f"{buzz_result.result_id}.json"
        assert not buzz_file.exists()

    def test_pending_results_not_on_disk_until_commit(self, tmp_path, fizz_result):
        repo = FileSystemRepository(base_dir=str(tmp_path))
        repo.add(fizz_result)
        # File should NOT exist yet
        expected_file = tmp_path / f"{fizz_result.result_id}.json"
        assert not expected_file.exists()
        repo.commit()
        assert expected_file.exists()


class TestFileSystemUnitOfWork:
    def test_commit_writes_files(self, tmp_path, fizz_result, buzz_result):
        uow = FileSystemUnitOfWork(base_dir=str(tmp_path))
        with uow:
            uow.repository.add(fizz_result)
            uow.repository.add(buzz_result)
            uow.commit()
        # Both files should exist
        assert (tmp_path / f"{fizz_result.result_id}.json").exists()
        assert (tmp_path / f"{buzz_result.result_id}.json").exists()

    def test_auto_rollback_on_exception(self, tmp_path, fizz_result):
        uow = FileSystemUnitOfWork(base_dir=str(tmp_path))
        with pytest.raises(ValueError):
            with uow:
                uow.repository.add(fizz_result)
                uow.repository.commit()  # Write to disk
                raise ValueError("Oops")
        # File should have been cleaned up by rollback
        assert not (tmp_path / f"{fizz_result.result_id}.json").exists()

    def test_auto_rollback_without_commit(self, tmp_path, fizz_result):
        uow = FileSystemUnitOfWork(base_dir=str(tmp_path))
        with uow:
            uow.repository.add(fizz_result)
            # Deliberately not calling commit
        # File should not exist (pending was discarded, no files written)
        assert not (tmp_path / f"{fizz_result.result_id}.json").exists()

    def test_repository_property(self, tmp_path):
        uow = FileSystemUnitOfWork(base_dir=str(tmp_path))
        assert isinstance(uow.repository, FileSystemRepository)


# ============================================================
# Abstract Port Contract Tests
# ============================================================


class TestPortContracts:
    """Verify that all implementations satisfy the abstract port contracts."""

    def test_in_memory_is_abstract_repository(self):
        from enterprise_fizzbuzz.application.ports import AbstractRepository
        assert issubclass(InMemoryRepository, AbstractRepository)

    def test_sqlite_is_abstract_repository(self):
        from enterprise_fizzbuzz.application.ports import AbstractRepository
        assert issubclass(SqliteRepository, AbstractRepository)

    def test_filesystem_is_abstract_repository(self):
        from enterprise_fizzbuzz.application.ports import AbstractRepository
        assert issubclass(FileSystemRepository, AbstractRepository)

    def test_in_memory_uow_is_abstract_unit_of_work(self):
        from enterprise_fizzbuzz.application.ports import AbstractUnitOfWork
        assert issubclass(InMemoryUnitOfWork, AbstractUnitOfWork)

    def test_sqlite_uow_is_abstract_unit_of_work(self):
        from enterprise_fizzbuzz.application.ports import AbstractUnitOfWork
        assert issubclass(SqliteUnitOfWork, AbstractUnitOfWork)

    def test_filesystem_uow_is_abstract_unit_of_work(self):
        from enterprise_fizzbuzz.application.ports import AbstractUnitOfWork
        assert issubclass(FileSystemUnitOfWork, AbstractUnitOfWork)
