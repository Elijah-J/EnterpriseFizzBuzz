"""
Enterprise FizzBuzz Platform - SQLite Repository & Unit of Work

Implements the Repository Pattern using a real SQLite database with
actual SQL queries, because the FizzBuzz results have finally graduated
from dictionaries to relational storage. They grow up so fast.

The SQLite backend stores FizzBuzz results in a proper table with
columns for result_id, number, output, matched_rules (as a JSON
string), processing_time_ns, and metadata (also JSON). Because
if you're going to persist the output of n % 3, you might as well
normalize it into a relational schema.

Features:
  - Real SQL CREATE TABLE, INSERT, SELECT statements
  - JSON serialization for matched_rules and metadata
  - Transaction support via sqlite3's built-in commit/rollback
  - On-disk persistence that survives process restarts (finally,
    your FizzBuzz results are durable!)
"""

from __future__ import annotations

import json
import logging
import sqlite3
from pathlib import Path
from typing import Any, Optional

from enterprise_fizzbuzz.application.ports import AbstractRepository, AbstractUnitOfWork
from enterprise_fizzbuzz.domain.exceptions import (
    RepositoryError,
    ResultNotFoundError,
    RollbackError,
)
from enterprise_fizzbuzz.domain.models import (
    FizzBuzzResult,
    RuleDefinition,
    RuleMatch,
)

logger = logging.getLogger(__name__)

_BACKEND = "sqlite"

_CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS fizzbuzz_results (
    result_id          TEXT PRIMARY KEY,
    number             INTEGER NOT NULL,
    output             TEXT NOT NULL,
    matched_rules_json TEXT NOT NULL DEFAULT '[]',
    processing_time_ns INTEGER NOT NULL DEFAULT 0,
    metadata_json      TEXT NOT NULL DEFAULT '{}'
);
"""


def _serialize_matched_rules(rules: list[RuleMatch]) -> str:
    """Serialize matched rules to a JSON string for storage.

    Each RuleMatch is flattened to its essential fields because
    SQLite doesn't support nested dataclass columns — yet.
    """
    serialized = []
    for rm in rules:
        serialized.append({
            "rule_name": rm.rule.name,
            "rule_divisor": rm.rule.divisor,
            "rule_label": rm.rule.label,
            "rule_priority": rm.rule.priority,
            "number": rm.number,
            "timestamp": rm.timestamp.isoformat(),
        })
    return json.dumps(serialized)


def _deserialize_matched_rules(json_str: str) -> list[RuleMatch]:
    """Reconstruct matched rules from their JSON representation."""
    from datetime import datetime, timezone

    raw = json.loads(json_str)
    rules = []
    for entry in raw:
        rule_def = RuleDefinition(
            name=entry["rule_name"],
            divisor=entry["rule_divisor"],
            label=entry["rule_label"],
            priority=entry.get("rule_priority", 0),
        )
        ts = datetime.fromisoformat(entry["timestamp"])
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        rules.append(RuleMatch(rule=rule_def, number=entry["number"], timestamp=ts))
    return rules


def _row_to_result(row: sqlite3.Row | tuple) -> FizzBuzzResult:
    """Convert a database row to a FizzBuzzResult."""
    if isinstance(row, sqlite3.Row):
        result_id = row["result_id"]
        number = row["number"]
        output = row["output"]
        matched_json = row["matched_rules_json"]
        processing_ns = row["processing_time_ns"]
        meta_json = row["metadata_json"]
    else:
        result_id, number, output, matched_json, processing_ns, meta_json = row

    return FizzBuzzResult(
        result_id=result_id,
        number=number,
        output=output,
        matched_rules=_deserialize_matched_rules(matched_json),
        processing_time_ns=processing_ns,
        metadata=json.loads(meta_json),
    )


class SqliteRepository(AbstractRepository):
    """Repository backed by a SQLite database.

    Your FizzBuzz results now live in a B-tree on disk, indexed by
    a UUID primary key, queryable via SQL, and protected by WAL-mode
    journaling. This is the storage upgrade that FizzBuzz always
    deserved but never asked for.

    The repository operates within the transaction boundary of its
    owning connection. Commit and rollback delegate to the connection's
    transaction management.
    """

    def __init__(self, db_path: str = ":memory:") -> None:
        self._db_path = db_path
        self._conn: Optional[sqlite3.Connection] = None

    def _ensure_connection(self) -> sqlite3.Connection:
        """Lazily open the database connection and create the schema."""
        if self._conn is None:
            self._conn = sqlite3.connect(self._db_path)
            self._conn.row_factory = sqlite3.Row
            self._conn.execute("PRAGMA journal_mode=WAL;")
            self._conn.execute(_CREATE_TABLE_SQL)
            self._conn.commit()
            logger.info(
                "SQLite repository initialized at '%s'", self._db_path
            )
        return self._conn

    def add(self, result: FizzBuzzResult) -> None:
        """Insert a FizzBuzz result into the database within the current transaction."""
        conn = self._ensure_connection()
        try:
            conn.execute(
                """
                INSERT INTO fizzbuzz_results
                    (result_id, number, output, matched_rules_json,
                     processing_time_ns, metadata_json)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    result.result_id,
                    result.number,
                    result.output,
                    _serialize_matched_rules(result.matched_rules),
                    result.processing_time_ns,
                    json.dumps(result.metadata),
                ),
            )
            logger.debug(
                "Inserted result %s into SQLite (number=%d)",
                result.result_id[:8],
                result.number,
            )
        except sqlite3.IntegrityError as e:
            raise RepositoryError(
                f"Duplicate result_id '{result.result_id}': {e}",
                backend=_BACKEND,
            ) from e

    def get(self, result_id: str) -> FizzBuzzResult:
        """Retrieve a single result by its primary key."""
        conn = self._ensure_connection()
        row = conn.execute(
            "SELECT * FROM fizzbuzz_results WHERE result_id = ?",
            (result_id,),
        ).fetchone()
        if row is None:
            raise ResultNotFoundError(result_id, backend=_BACKEND)
        return _row_to_result(row)

    def list(self) -> list[FizzBuzzResult]:
        """Return all committed results ordered by number."""
        conn = self._ensure_connection()
        rows = conn.execute(
            "SELECT * FROM fizzbuzz_results ORDER BY number"
        ).fetchall()
        return [_row_to_result(r) for r in rows]

    def commit(self) -> None:
        """Commit the current SQLite transaction."""
        conn = self._ensure_connection()
        conn.commit()
        logger.info("SQLite transaction committed")

    def rollback(self) -> None:
        """Roll back the current SQLite transaction."""
        conn = self._ensure_connection()
        conn.rollback()
        logger.info("SQLite transaction rolled back")

    def close(self) -> None:
        """Close the database connection."""
        if self._conn is not None:
            self._conn.close()
            self._conn = None


class SqliteUnitOfWork(AbstractUnitOfWork):
    """Unit of Work wrapping a SqliteRepository.

    Manages the SQLite transaction lifecycle. On __enter__, a new
    transaction begins (SQLite's default autocommit is off when you
    use execute() without committing). On __exit__, if commit() was
    not called or an exception occurred, the transaction is rolled back.

    This is the first time in the history of this project that
    FizzBuzz results can survive a process restart. Celebrate
    accordingly.
    """

    def __init__(self, db_path: str = ":memory:") -> None:
        self._repo = SqliteRepository(db_path=db_path)
        self._committed = False

    @property
    def repository(self) -> SqliteRepository:
        return self._repo

    def __enter__(self) -> SqliteUnitOfWork:
        self._committed = False
        # Ensure connection is open (schema created)
        self._repo._ensure_connection()
        logger.debug("SqliteUnitOfWork: transaction started")
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
                "SqliteUnitOfWork: auto-rollback (exc=%s, committed=%s)",
                exc_type,
                self._committed,
            )
        self._repo.close()

    def commit(self) -> None:
        """Commit the current transaction."""
        self._repo.commit()
        self._committed = True
