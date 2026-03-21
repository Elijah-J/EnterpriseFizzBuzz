"""
Enterprise FizzBuzz Platform - Filesystem Repository & Unit of Work

Implements the Repository Pattern using the filesystem as a backing store,
where every single FizzBuzz result gets its own JSON file. Because your
file system's inode table was just sitting there, underutilized, waiting
for someone to write "Fizz" to a file named after a UUID.

Each result is persisted as an individual JSON file in a configurable
directory. The filename is the result_id with a .json extension. This
means evaluating FizzBuzz for the range [1, 1000] will create 1000
individual files, which is exactly the kind of I/O pattern that makes
storage engineers question their career choices.

Rollback support is provided by tracking which files were written during
the current transaction and deleting them on rollback. It's crude, it's
effective, and it's exactly what happens when you use the filesystem as
a database.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from enterprise_fizzbuzz.application.ports import AbstractRepository, AbstractUnitOfWork
from enterprise_fizzbuzz.domain.exceptions import (
    RepositoryError,
    ResultNotFoundError,
    RollbackError,
)
from enterprise_fizzbuzz.domain.models import (
    Event,
    EventType,
    FizzBuzzResult,
    RuleDefinition,
    RuleMatch,
)

logger = logging.getLogger(__name__)

_BACKEND = "filesystem"


def _result_to_dict(result: FizzBuzzResult) -> dict[str, Any]:
    """Serialize a FizzBuzzResult to a JSON-compatible dictionary."""
    matched = []
    for rm in result.matched_rules:
        matched.append({
            "rule_name": rm.rule.name,
            "rule_divisor": rm.rule.divisor,
            "rule_label": rm.rule.label,
            "rule_priority": rm.rule.priority,
            "number": rm.number,
            "timestamp": rm.timestamp.isoformat(),
        })
    return {
        "result_id": result.result_id,
        "number": result.number,
        "output": result.output,
        "matched_rules": matched,
        "processing_time_ns": result.processing_time_ns,
        "metadata": result.metadata,
    }


def _dict_to_result(data: dict[str, Any]) -> FizzBuzzResult:
    """Deserialize a FizzBuzzResult from a JSON dictionary."""
    matched_rules = []
    for entry in data.get("matched_rules", []):
        rule_def = RuleDefinition(
            name=entry["rule_name"],
            divisor=entry["rule_divisor"],
            label=entry["rule_label"],
            priority=entry.get("rule_priority", 0),
        )
        ts = datetime.fromisoformat(entry["timestamp"])
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        matched_rules.append(
            RuleMatch(rule=rule_def, number=entry["number"], timestamp=ts)
        )
    return FizzBuzzResult(
        result_id=data["result_id"],
        number=data["number"],
        output=data["output"],
        matched_rules=matched_rules,
        processing_time_ns=data.get("processing_time_ns", 0),
        metadata=data.get("metadata", {}),
    )


class FileSystemRepository(AbstractRepository):
    """Repository that persists each FizzBuzz result as an individual JSON file.

    The directory structure is flat — all results live in a single directory
    as {result_id}.json files. No subdirectories, no partitioning, no
    sharding. Just raw, unoptimized filesystem I/O, the way nature intended.

    Pending results are tracked in-memory and only written to disk on commit().
    On rollback(), any files written during the current transaction are deleted,
    which is the filesystem equivalent of "git reset --hard" but for JSON files
    containing the word "Fizz".
    """

    def __init__(self, base_dir: str) -> None:
        self._base_dir = Path(base_dir)
        self._pending: dict[str, FizzBuzzResult] = {}
        self._written_files: list[Path] = []

    def _ensure_dir(self) -> None:
        """Create the base directory if it doesn't exist."""
        self._base_dir.mkdir(parents=True, exist_ok=True)

    def _file_path(self, result_id: str) -> Path:
        """Compute the filesystem path for a given result_id."""
        return self._base_dir / f"{result_id}.json"

    def add(self, result: FizzBuzzResult) -> None:
        """Stage a result for filesystem persistence."""
        self._pending[result.result_id] = result
        logger.debug(
            "Staged result %s for filesystem write (number=%d)",
            result.result_id[:8],
            result.number,
        )

    def get(self, result_id: str) -> FizzBuzzResult:
        """Retrieve a result from pending buffer or from disk."""
        # Check pending first
        if result_id in self._pending:
            return self._pending[result_id]

        # Check disk
        path = self._file_path(result_id)
        if path.exists():
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return _dict_to_result(data)

        raise ResultNotFoundError(result_id, backend=_BACKEND)

    def list(self) -> list[FizzBuzzResult]:
        """Read all committed JSON files from the base directory."""
        self._ensure_dir()
        results = []
        for path in sorted(self._base_dir.glob("*.json")):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                results.append(_dict_to_result(data))
            except (json.JSONDecodeError, KeyError) as e:
                logger.warning("Skipping corrupt file %s: %s", path, e)
        return sorted(results, key=lambda r: r.number)

    def commit(self) -> None:
        """Write all pending results to disk as individual JSON files."""
        self._ensure_dir()
        count = 0
        for result_id, result in self._pending.items():
            path = self._file_path(result_id)
            with open(path, "w", encoding="utf-8") as f:
                json.dump(_result_to_dict(result), f, indent=2)
            self._written_files.append(path)
            count += 1
        self._pending.clear()
        logger.info(
            "Committed %d result file(s) to '%s' (total files: %d)",
            count,
            self._base_dir,
            len(list(self._base_dir.glob("*.json"))),
        )

    def rollback(self) -> None:
        """Discard pending results and delete any files written in this transaction."""
        self._pending.clear()
        deleted = 0
        for path in self._written_files:
            if path.exists():
                path.unlink()
                deleted += 1
                logger.debug("Rollback: deleted '%s'", path)
        self._written_files.clear()
        logger.info(
            "Rolled back: discarded pending, deleted %d written file(s)",
            deleted,
        )


class FileSystemUnitOfWork(AbstractUnitOfWork):
    """Unit of Work wrapping a FileSystemRepository.

    On __enter__, the transaction begins by clearing the written-files
    tracker. On __exit__, if commit() was not called or an exception
    occurred, all files written during the transaction are deleted.

    This is technically a form of compensating transaction — the most
    sophisticated pattern available when your "database" is a directory
    full of JSON files.
    """

    def __init__(self, base_dir: str) -> None:
        self._repo = FileSystemRepository(base_dir=base_dir)
        self._committed = False

    @property
    def repository(self) -> FileSystemRepository:
        return self._repo

    def __enter__(self) -> FileSystemUnitOfWork:
        self._committed = False
        self._repo._written_files.clear()
        logger.debug("FileSystemUnitOfWork: transaction started")
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
                "FileSystemUnitOfWork: auto-rollback (exc=%s, committed=%s)",
                exc_type,
                self._committed,
            )

    def commit(self) -> None:
        """Commit the current transaction by writing files to disk."""
        self._repo.commit()
        self._committed = True
