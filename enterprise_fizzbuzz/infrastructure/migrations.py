"""
Enterprise FizzBuzz Platform - Database Migration Framework

Implements a full-featured database migration framework for in-memory
data structures (dicts of lists of dicts) that are guaranteed to be
destroyed when the process exits. This is the enterprise equivalent
of building a sand castle at high tide — meticulous, technically
impressive, and ultimately doomed.

Features:
- Schema management for ephemeral in-memory "tables"
- Forward and reverse migrations with dependency tracking
- Seed data generation using the FizzBuzz engine itself (the ouroboros!)
- ASCII ER diagram visualization
- Migration status dashboard
- Fake SQL logging for maximum enterprise cosplay
- Avro/Protobuf-inspired schema versioning with compatibility enforcement
- Paxos-based consensus approval for schema changes
- Migration planning with field-level diff analysis

All data managed by this framework exists exclusively in RAM and will
vanish without a trace the moment you press Ctrl+C. This is by design.

When the shape of an EvaluationResult changes (e.g., adding a ``cache_hit``
field in v3), every downstream consumer — dashboards, compliance auditors,
blockchain observers, the ML engine — must be consulted. Schema changes
undergo the same rigorous governance as a constitutional amendment: proposal,
compatibility analysis, majority consensus, and ratification.
"""

from __future__ import annotations

import hashlib
import json
import logging
import math
import threading
import time
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum, auto
from typing import Any, Callable, Dict, List, Optional, Tuple

from enterprise_fizzbuzz.domain.exceptions import (
    MigrationAlreadyAppliedError,
    MigrationConflictError,
    MigrationDependencyError,
    MigrationError,
    MigrationNotFoundError,
    MigrationRollbackError,
    SchemaCompatibilityError,
    SchemaConsensusError,
    SchemaError,
    SchemaEvolutionError,
    SchemaRegistrationError,
    SeedDataError,
)
from enterprise_fizzbuzz.domain.interfaces import IMiddleware
from enterprise_fizzbuzz.domain.models import ProcessingContext

logger = logging.getLogger(__name__)


# ============================================================
# Enumerations
# ============================================================


class MigrationState(Enum):
    """Lifecycle states for a database migration.

    Every migration traverses this lifecycle with the solemnity of
    a database schema change in production, despite the fact that
    the "database" is a Python dict that will be garbage collected
    in approximately 0.1 seconds.

    PENDING:     The migration has been registered but not yet applied.
    APPLYING:    The migration is currently being applied (a fleeting state).
    APPLIED:     The migration has been successfully applied to the schema.
    ROLLING_BACK: The migration is being rolled back (buyer's remorse).
    ROLLED_BACK: The migration has been successfully rolled back.
    FAILED:      The migration encountered an error during application.
    """

    PENDING = auto()
    APPLYING = auto()
    APPLIED = auto()
    ROLLING_BACK = auto()
    ROLLED_BACK = auto()
    FAILED = auto()


# ============================================================
# Data Classes
# ============================================================


@dataclass
class MigrationRecord:
    """Tracks the application status of a single migration.

    Maintains a comprehensive audit trail of when a migration was
    applied, how long it took, and whether it succeeded — all for
    schema changes to dicts that exist only in memory.

    Attributes:
        migration_id: Unique identifier for the migration.
        name: Human-readable name of the migration.
        state: Current lifecycle state.
        applied_at: Timestamp when the migration was applied (UTC).
        rolled_back_at: Timestamp when the migration was rolled back, if applicable.
        duration_ms: Time taken to apply the migration in milliseconds.
        checksum: SHA-256 hash of the migration class name for integrity verification.
        error_message: Error message if the migration failed.
    """

    migration_id: str
    name: str
    state: MigrationState = MigrationState.PENDING
    applied_at: Optional[datetime] = None
    rolled_back_at: Optional[datetime] = None
    duration_ms: float = 0.0
    checksum: str = ""
    error_message: Optional[str] = None


# ============================================================
# Migration ABC
# ============================================================


class Migration(ABC):
    """Abstract base class for all database migrations.

    Every migration must implement up() and down() methods, providing
    both forward and reverse transformations for the in-memory schema.
    This ensures full reversibility of all schema changes, even though
    the schema itself will cease to exist when the process terminates.

    Subclasses should set:
        migration_id: Unique identifier (e.g., "m001_initial_schema")
        dependencies: List of migration IDs that must be applied first.
        description: Human-readable description of the migration.
    """

    migration_id: str = ""
    dependencies: list[str] = []
    description: str = ""

    @abstractmethod
    def up(self, schema: SchemaManager) -> None:
        """Apply the forward migration to the schema.

        This method should create tables, add columns, or modify data
        in the SchemaManager. It will be called exactly once per
        migration application (barring rollbacks and re-applications,
        which is the database equivalent of relationship drama).
        """
        ...

    @abstractmethod
    def down(self, schema: SchemaManager) -> None:
        """Reverse the migration (rollback).

        This method should undo everything that up() did, restoring
        the schema to its previous state. In theory, applying up()
        followed by down() should be a no-op. In practice, this is
        about as reliable as "I'll just undo that git force push."
        """
        ...

    def get_checksum(self) -> str:
        """Compute a SHA-256 checksum for migration integrity verification."""
        content = f"{self.migration_id}:{self.__class__.__name__}:{self.description}"
        return hashlib.sha256(content.encode()).hexdigest()[:16]


# ============================================================
# Schema Manager
# ============================================================


class SchemaManager:
    """Manages in-memory "tables" (dicts of lists of dicts).

    Provides a full DDL/DML interface for managing the Enterprise
    FizzBuzz Platform's in-memory database. Tables are represented
    as lists of dicts, with a separate schema registry tracking
    column definitions.

    This is functionally equivalent to a production database, except:
    - There is no disk I/O (or any I/O at all)
    - There is no ACID compliance (or any compliance at all)
    - The entire database will be destroyed when you close the terminal
    - There is no way to back it up, replicate it, or shard it

    Other than that, it's enterprise-grade.
    """

    def __init__(self, log_fake_sql: bool = True) -> None:
        self._tables: dict[str, list[dict[str, Any]]] = {}
        self._schemas: dict[str, dict[str, str]] = {}  # table -> {col: type}
        self._log_fake_sql = log_fake_sql
        self._sql_log: list[str] = []

    def _log_sql(self, sql: str) -> None:
        """Log a fake SQL statement for enterprise cosplay purposes."""
        if self._log_fake_sql:
            self._sql_log.append(sql)
            logger.debug("[FAKE SQL] %s", sql)

    @property
    def sql_log(self) -> list[str]:
        """Return the log of fake SQL statements executed against this schema."""
        return list(self._sql_log)

    def create_table(self, table_name: str, columns: dict[str, str]) -> None:
        """Create a new in-memory table with the specified columns.

        Args:
            table_name: Name of the table to create.
            columns: Dict mapping column names to type strings
                     (e.g., {"id": "int", "name": "str"}).

        Raises:
            SchemaError: If the table already exists.
        """
        if table_name in self._tables:
            raise SchemaError(
                "CREATE TABLE",
                f"Table '{table_name}' already exists. DROP it first, or "
                f"accept that your schema has commitment issues.",
            )

        self._tables[table_name] = []
        self._schemas[table_name] = dict(columns)

        col_defs = ", ".join(f"{col} {typ}" for col, typ in columns.items())
        self._log_sql(f"CREATE TABLE {table_name} ({col_defs});")

        logger.info(
            "Created in-memory table '%s' with columns: %s (will vanish on exit)",
            table_name,
            list(columns.keys()),
        )

    def drop_table(self, table_name: str) -> None:
        """Drop an in-memory table, destroying all its data forever.

        "Forever" here means "until the process exits, at which point
        all tables would have been destroyed anyway."

        Raises:
            SchemaError: If the table does not exist.
        """
        if table_name not in self._tables:
            raise SchemaError(
                "DROP TABLE",
                f"Table '{table_name}' does not exist. You cannot drop "
                f"what was never created. This is both a technical error "
                f"and a philosophical observation.",
            )

        row_count = len(self._tables[table_name])
        del self._tables[table_name]
        del self._schemas[table_name]

        self._log_sql(f"DROP TABLE {table_name}; -- {row_count} rows lost to the void")

        logger.info(
            "Dropped table '%s' (%d rows ceremonially destroyed)", table_name, row_count
        )

    def add_column(
        self, table_name: str, column_name: str, column_type: str, default: Any = None
    ) -> None:
        """Add a column to an existing table, backfilling with a default value.

        Args:
            table_name: The table to modify.
            column_name: The new column name.
            column_type: Type string for the column.
            default: Default value for existing rows.

        Raises:
            SchemaError: If the table doesn't exist or column already exists.
        """
        if table_name not in self._tables:
            raise SchemaError(
                "ALTER TABLE ADD COLUMN",
                f"Table '{table_name}' does not exist.",
            )
        if column_name in self._schemas[table_name]:
            raise SchemaError(
                "ALTER TABLE ADD COLUMN",
                f"Column '{column_name}' already exists in table '{table_name}'.",
            )

        self._schemas[table_name][column_name] = column_type

        # Backfill existing rows
        for row in self._tables[table_name]:
            row[column_name] = default

        self._log_sql(
            f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type} "
            f"DEFAULT {default!r};"
        )

        logger.info(
            "Added column '%s' (%s) to table '%s', backfilled %d rows",
            column_name,
            column_type,
            table_name,
            len(self._tables[table_name]),
        )

    def drop_column(self, table_name: str, column_name: str) -> None:
        """Remove a column from an existing table.

        Raises:
            SchemaError: If the table or column doesn't exist.
        """
        if table_name not in self._tables:
            raise SchemaError("ALTER TABLE DROP COLUMN", f"Table '{table_name}' does not exist.")
        if column_name not in self._schemas[table_name]:
            raise SchemaError(
                "ALTER TABLE DROP COLUMN",
                f"Column '{column_name}' does not exist in table '{table_name}'.",
            )

        del self._schemas[table_name][column_name]
        for row in self._tables[table_name]:
            row.pop(column_name, None)

        self._log_sql(f"ALTER TABLE {table_name} DROP COLUMN {column_name};")

    def rename_column(self, table_name: str, old_name: str, new_name: str) -> None:
        """Rename a column in an existing table.

        Raises:
            SchemaError: If the table doesn't exist, old column doesn't exist,
                        or new column already exists.
        """
        if table_name not in self._tables:
            raise SchemaError("ALTER TABLE RENAME COLUMN", f"Table '{table_name}' does not exist.")
        if old_name not in self._schemas[table_name]:
            raise SchemaError(
                "ALTER TABLE RENAME COLUMN",
                f"Column '{old_name}' does not exist in table '{table_name}'.",
            )
        if new_name in self._schemas[table_name]:
            raise SchemaError(
                "ALTER TABLE RENAME COLUMN",
                f"Column '{new_name}' already exists in table '{table_name}'.",
            )

        col_type = self._schemas[table_name].pop(old_name)
        self._schemas[table_name][new_name] = col_type

        for row in self._tables[table_name]:
            if old_name in row:
                row[new_name] = row.pop(old_name)

        self._log_sql(
            f"ALTER TABLE {table_name} RENAME COLUMN {old_name} TO {new_name};"
        )

    def insert(self, table_name: str, row: dict[str, Any]) -> None:
        """Insert a row into a table.

        Raises:
            SchemaError: If the table doesn't exist.
        """
        if table_name not in self._tables:
            raise SchemaError("INSERT", f"Table '{table_name}' does not exist.")

        # Fill missing columns with None
        full_row = {col: row.get(col) for col in self._schemas[table_name]}
        # Also include any extra keys from the row
        full_row.update(row)
        self._tables[table_name].append(full_row)

        cols = ", ".join(full_row.keys())
        vals = ", ".join(repr(v) for v in full_row.values())
        self._log_sql(f"INSERT INTO {table_name} ({cols}) VALUES ({vals});")

    def get_data(self, table_name: str) -> list[dict[str, Any]]:
        """Retrieve all rows from a table.

        Raises:
            SchemaError: If the table doesn't exist.
        """
        if table_name not in self._tables:
            raise SchemaError("SELECT *", f"Table '{table_name}' does not exist.")
        return list(self._tables[table_name])

    def get_table_schema(self, table_name: str) -> dict[str, str]:
        """Get the schema definition for a table.

        Raises:
            SchemaError: If the table doesn't exist.
        """
        if table_name not in self._tables:
            raise SchemaError("DESCRIBE", f"Table '{table_name}' does not exist.")
        return dict(self._schemas[table_name])

    def table_exists(self, table_name: str) -> bool:
        """Check whether a table exists in the schema."""
        return table_name in self._tables

    def list_tables(self) -> list[str]:
        """List all tables in the schema."""
        return list(self._tables.keys())

    def row_count(self, table_name: str) -> int:
        """Return the number of rows in a table."""
        if table_name not in self._tables:
            return 0
        return len(self._tables[table_name])


# ============================================================
# Migration Registry (Singleton)
# ============================================================


class MigrationRegistry:
    """Singleton registry of all available migration classes.

    Maintains a global registry of migrations, ordered by their IDs,
    so the MigrationRunner can apply them in the correct sequence.
    Because even ephemeral in-memory schema changes deserve a
    well-ordered migration history.
    """

    _instance: Optional[MigrationRegistry] = None
    _migrations: dict[str, type[Migration]]

    def __init__(self) -> None:
        self._migrations = {}

    @classmethod
    def get_instance(cls) -> MigrationRegistry:
        """Get or create the singleton MigrationRegistry."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def reset(cls) -> None:
        """Reset the singleton instance. Used for testing."""
        cls._instance = None

    def register(self, migration_cls: type[Migration]) -> None:
        """Register a migration class in the registry.

        Args:
            migration_cls: The migration class to register.

        Raises:
            MigrationConflictError: If a migration with the same ID is already registered.
        """
        mid = migration_cls.migration_id
        if mid in self._migrations:
            existing = self._migrations[mid]
            if existing is not migration_cls:
                raise MigrationConflictError(
                    mid,
                    existing.__name__,
                    f"Migration ID '{mid}' is already registered by {existing.__name__}.",
                )
        self._migrations[mid] = migration_cls

    def get(self, migration_id: str) -> type[Migration]:
        """Retrieve a migration class by ID.

        Raises:
            MigrationNotFoundError: If the migration ID is not registered.
        """
        if migration_id not in self._migrations:
            raise MigrationNotFoundError(migration_id)
        return self._migrations[migration_id]

    def get_all(self) -> list[type[Migration]]:
        """Return all registered migrations, sorted by ID."""
        return [
            cls
            for _, cls in sorted(self._migrations.items(), key=lambda x: x[0])
        ]

    def get_ids(self) -> list[str]:
        """Return all registered migration IDs, sorted."""
        return sorted(self._migrations.keys())


# ============================================================
# Migration Runner
# ============================================================


class MigrationRunner:
    """Applies and rolls back migrations with dependency tracking.

    Orchestrates the full migration lifecycle: checking dependencies,
    applying migrations in order, tracking state, and handling rollbacks.
    All of this for data structures that will be garbage collected when
    the process exits. Enterprise-grade ephemeral schema management.
    """

    def __init__(
        self,
        schema: SchemaManager,
        registry: Optional[MigrationRegistry] = None,
    ) -> None:
        self._schema = schema
        self._registry = registry or MigrationRegistry.get_instance()
        self._records: dict[str, MigrationRecord] = {}
        self._applied_order: list[str] = []

    @property
    def schema(self) -> SchemaManager:
        """Access the underlying SchemaManager."""
        return self._schema

    def get_status(self) -> list[MigrationRecord]:
        """Return status records for all registered migrations."""
        records = []
        for mid in self._registry.get_ids():
            if mid in self._records:
                records.append(self._records[mid])
            else:
                migration_cls = self._registry.get(mid)
                records.append(
                    MigrationRecord(
                        migration_id=mid,
                        name=migration_cls.description or migration_cls.__name__,
                        state=MigrationState.PENDING,
                    )
                )
        return records

    def get_pending(self) -> list[str]:
        """Return IDs of migrations that have not yet been applied."""
        return [
            mid
            for mid in self._registry.get_ids()
            if mid not in self._records or self._records[mid].state != MigrationState.APPLIED
        ]

    def _check_dependencies(self, migration: Migration) -> None:
        """Verify that all dependencies for a migration have been applied.

        Raises:
            MigrationDependencyError: If any dependencies are not satisfied.
        """
        missing = []
        for dep_id in migration.dependencies:
            if dep_id not in self._records or self._records[dep_id].state != MigrationState.APPLIED:
                missing.append(dep_id)
        if missing:
            raise MigrationDependencyError(migration.migration_id, missing)

    def apply_all(self) -> list[MigrationRecord]:
        """Apply all pending migrations in order.

        Returns:
            List of MigrationRecords for applied migrations.
        """
        applied = []
        for mid in self._registry.get_ids():
            if mid in self._records and self._records[mid].state == MigrationState.APPLIED:
                continue
            record = self.apply(mid)
            applied.append(record)
        return applied

    def apply(self, migration_id: str) -> MigrationRecord:
        """Apply a single migration by ID.

        Args:
            migration_id: The ID of the migration to apply.

        Returns:
            The MigrationRecord for the applied migration.

        Raises:
            MigrationNotFoundError: If the migration doesn't exist.
            MigrationAlreadyAppliedError: If the migration is already applied.
            MigrationDependencyError: If dependencies aren't met.
            MigrationError: If the migration fails.
        """
        migration_cls = self._registry.get(migration_id)
        migration = migration_cls()

        # Check if already applied
        if migration_id in self._records and self._records[migration_id].state == MigrationState.APPLIED:
            raise MigrationAlreadyAppliedError(migration_id)

        # Check dependencies
        self._check_dependencies(migration)

        # Create record
        record = MigrationRecord(
            migration_id=migration_id,
            name=migration.description or migration.__class__.__name__,
            state=MigrationState.APPLYING,
            checksum=migration.get_checksum(),
        )

        start_time = time.perf_counter()

        try:
            migration.up(self._schema)
            elapsed_ms = (time.perf_counter() - start_time) * 1000

            record.state = MigrationState.APPLIED
            record.applied_at = datetime.now(timezone.utc)
            record.duration_ms = elapsed_ms

            self._records[migration_id] = record
            self._applied_order.append(migration_id)

            logger.info(
                "Migration '%s' applied successfully in %.2fms (data will vanish on exit)",
                migration_id,
                elapsed_ms,
            )

        except Exception as e:
            elapsed_ms = (time.perf_counter() - start_time) * 1000
            record.state = MigrationState.FAILED
            record.duration_ms = elapsed_ms
            record.error_message = str(e)
            self._records[migration_id] = record

            raise MigrationError(
                f"Migration '{migration_id}' failed: {e}",
                error_code="EFP-MG00",
                context={"migration_id": migration_id},
            ) from e

        return record

    def rollback(self, count: int = 1) -> list[MigrationRecord]:
        """Roll back the last N applied migrations.

        Args:
            count: Number of migrations to roll back (default: 1).

        Returns:
            List of MigrationRecords for rolled-back migrations.
        """
        rolled_back = []

        for _ in range(min(count, len(self._applied_order))):
            if not self._applied_order:
                break

            migration_id = self._applied_order[-1]
            migration_cls = self._registry.get(migration_id)
            migration = migration_cls()

            record = self._records[migration_id]
            record.state = MigrationState.ROLLING_BACK

            try:
                migration.down(self._schema)
                record.state = MigrationState.ROLLED_BACK
                record.rolled_back_at = datetime.now(timezone.utc)
                self._applied_order.pop()
                rolled_back.append(record)

                logger.info("Migration '%s' rolled back successfully", migration_id)

            except Exception as e:
                record.state = MigrationState.FAILED
                record.error_message = f"Rollback failed: {e}"
                raise MigrationRollbackError(migration_id, str(e)) from e

        return rolled_back


# ============================================================
# Seed Data Generator (The Ouroboros)
# ============================================================


class SeedDataGenerator:
    """Generates FizzBuzz seed data by running the FizzBuzz engine.

    This is the ouroboros of enterprise software: we run the FizzBuzz
    evaluation engine to generate seed data for the FizzBuzz database,
    which exists solely to store FizzBuzz results that were computed
    by the FizzBuzz engine that we're using to generate the seed data.

    The snake eats its own tail. The circle is complete. The enterprise
    architect sheds a single tear of pride.
    """

    def __init__(self, schema: SchemaManager) -> None:
        self._schema = schema

    def generate(self, start: int = 1, end: int = 50) -> int:
        """Generate FizzBuzz seed data and insert it into the schema.

        Uses the StandardRuleEngine to evaluate FizzBuzz for the given
        range, then inserts the results into the fizzbuzz_results table.
        Yes, we are running FizzBuzz to populate a FizzBuzz database.
        The irony is not lost on us — it is, in fact, the entire point.

        Args:
            start: Start of the FizzBuzz range.
            end: End of the FizzBuzz range.

        Returns:
            Number of rows inserted.

        Raises:
            SeedDataError: If seed data generation fails.
        """
        if not self._schema.table_exists("fizzbuzz_results"):
            raise SeedDataError(
                "Table 'fizzbuzz_results' does not exist. "
                "Apply the initial schema migration (m001) first. "
                "You can't seed a table that doesn't exist, even in "
                "an ephemeral in-memory database."
            )

        try:
            from enterprise_fizzbuzz.domain.models import RuleDefinition
            from enterprise_fizzbuzz.infrastructure.rules_engine import ConcreteRule, StandardRuleEngine

            # Create the standard rules
            fizz_rule = ConcreteRule(
                RuleDefinition(name="FizzRule", divisor=3, label="Fizz", priority=1)
            )
            buzz_rule = ConcreteRule(
                RuleDefinition(name="BuzzRule", divisor=5, label="Buzz", priority=2)
            )
            rules = [fizz_rule, buzz_rule]

            engine = StandardRuleEngine()
            inserted = 0

            for number in range(start, end + 1):
                result = engine.evaluate(number, rules)

                row: dict[str, Any] = {
                    "number": number,
                    "output": result.output,
                    "is_fizz": result.is_fizz,
                    "is_buzz": result.is_buzz,
                    "is_fizzbuzz": result.is_fizzbuzz,
                    "is_plain": result.is_plain_number,
                    "rules_matched": len(result.matched_rules),
                }

                # Add optional columns if they exist in the schema
                schema = self._schema.get_table_schema("fizzbuzz_results")
                if "is_prime" in schema:
                    row["is_prime"] = self._is_prime(number)
                if "ml_confidence" in schema:
                    row["ml_confidence"] = 1.0  # Perfect confidence from the source of truth
                if "blockchain_hash" in schema:
                    row["blockchain_hash"] = hashlib.sha256(
                        f"fizzbuzz:{number}:{result.output}".encode()
                    ).hexdigest()[:16]

                self._schema.insert("fizzbuzz_results", row)
                inserted += 1

            logger.info(
                "Seed data generated: %d FizzBuzz results inserted using FizzBuzz "
                "to populate the FizzBuzz database (the ouroboros is complete)",
                inserted,
            )

            return inserted

        except SeedDataError:
            raise
        except Exception as e:
            raise SeedDataError(
                f"The ouroboros has choked: {e}. "
                f"FizzBuzz could not FizzBuzz itself into the FizzBuzz database."
            ) from e

    @staticmethod
    def _is_prime(n: int) -> bool:
        """Trial division primality test, because enterprise."""
        if n < 2:
            return False
        if n < 4:
            return True
        if n % 2 == 0 or n % 3 == 0:
            return False
        i = 5
        while i * i <= n:
            if n % i == 0 or n % (i + 2) == 0:
                return False
            i += 6
        return True


# ============================================================
# Schema Visualizer
# ============================================================


class SchemaVisualizer:
    """Renders ASCII ER diagrams of the in-memory schema.

    Because no enterprise database is complete without a visual
    representation of its tables and relationships, even when those
    tables are Python dicts and the relationships are entirely
    imaginary.
    """

    @staticmethod
    def render(schema: SchemaManager) -> str:
        """Render an ASCII ER diagram of the current schema.

        Args:
            schema: The SchemaManager whose tables to visualize.

        Returns:
            A string containing the ASCII ER diagram.
        """
        tables = schema.list_tables()
        if not tables:
            return (
                "  +-------------------------------------------+\n"
                "  | SCHEMA: (empty)                           |\n"
                "  | No tables exist in the ephemeral database |\n"
                "  | (which is arguably the correct state)     |\n"
                "  +-------------------------------------------+\n"
            )

        lines = []
        lines.append("")
        lines.append("  +===================================================+")
        lines.append("  |     ENTERPRISE FIZZBUZZ ER DIAGRAM                |")
        lines.append("  |     (All relationships are imaginary)             |")
        lines.append("  +===================================================+")
        lines.append("")

        for table_name in tables:
            table_schema = schema.get_table_schema(table_name)
            row_count = schema.row_count(table_name)

            # Calculate box width
            header = f" {table_name} ({row_count} rows) "
            col_lines = [f"  {col} : {typ}" for col, typ in table_schema.items()]
            max_width = max(
                len(header),
                max((len(cl) for cl in col_lines), default=0),
                40,
            )
            max_width += 2  # padding

            lines.append(f"  +{'=' * max_width}+")
            lines.append(f"  |{header:^{max_width}}|")
            lines.append(f"  +{'-' * max_width}+")

            for cl in col_lines:
                lines.append(f"  | {cl:<{max_width - 1}}|")

            lines.append(f"  +{'=' * max_width}+")
            lines.append("")

        # Add the disclaimer
        lines.append("  NOTE: This schema exists entirely in RAM.")
        lines.append("  It will be destroyed when the process exits.")
        lines.append("  No actual databases were harmed in the making")
        lines.append("  of this ER diagram.")
        lines.append("")

        return "\n".join(lines)


# ============================================================
# Migration Dashboard
# ============================================================


class MigrationDashboard:
    """Renders an ASCII status dashboard for database migrations.

    Provides a comprehensive visual overview of all migration states,
    complete with timestamps, durations, and sarcastic commentary
    about the ephemeral nature of the entire endeavor.
    """

    _STATE_SYMBOLS = {
        MigrationState.PENDING: "[ ]",
        MigrationState.APPLYING: "[~]",
        MigrationState.APPLIED: "[+]",
        MigrationState.ROLLING_BACK: "[<]",
        MigrationState.ROLLED_BACK: "[-]",
        MigrationState.FAILED: "[!]",
    }

    @classmethod
    def render(cls, runner: MigrationRunner) -> str:
        """Render the migration status dashboard.

        Args:
            runner: The MigrationRunner whose status to display.

        Returns:
            A string containing the ASCII dashboard.
        """
        records = runner.get_status()

        lines = []
        lines.append("")
        lines.append("  +===========================================================+")
        lines.append("  |         DATABASE MIGRATION STATUS DASHBOARD               |")
        lines.append("  |       (for an in-memory database that won't persist)      |")
        lines.append("  +===========================================================+")
        lines.append("")

        if not records:
            lines.append("  No migrations registered. The schema is a blank canvas.")
            lines.append("  (Or a blank dict, which is less poetic but more accurate.)")
            lines.append("")
            return "\n".join(lines)

        # Summary counts
        applied = sum(1 for r in records if r.state == MigrationState.APPLIED)
        pending = sum(1 for r in records if r.state == MigrationState.PENDING)
        failed = sum(1 for r in records if r.state == MigrationState.FAILED)
        rolled_back = sum(1 for r in records if r.state == MigrationState.ROLLED_BACK)

        lines.append(f"  Applied: {applied}  |  Pending: {pending}  |  Failed: {failed}  |  Rolled Back: {rolled_back}")
        lines.append(f"  Total: {len(records)} migrations registered")
        lines.append("")
        lines.append(f"  {'Status':<8} {'ID':<30} {'Duration':>10}  {'Name'}")
        lines.append(f"  {'-' * 70}")

        for record in records:
            symbol = cls._STATE_SYMBOLS.get(record.state, "[?]")
            duration = f"{record.duration_ms:.1f}ms" if record.duration_ms > 0 else "-"
            name = record.name[:30] if record.name else ""
            lines.append(f"  {symbol:<8} {record.migration_id:<30} {duration:>10}  {name}")

        lines.append(f"  {'-' * 70}")

        # Tables summary
        tables = runner.schema.list_tables()
        if tables:
            lines.append("")
            lines.append(f"  Tables in schema: {', '.join(tables)}")
            total_rows = sum(runner.schema.row_count(t) for t in tables)
            lines.append(f"  Total rows across all tables: {total_rows}")
            lines.append(f"  Total data persistence: 0 bytes (it's all in RAM)")

        lines.append("")
        lines.append("  REMINDER: All of this will be destroyed when the process exits.")
        lines.append("")

        return "\n".join(lines)


# ============================================================
# Pre-built Migrations
# ============================================================


class M001InitialSchema(Migration):
    """m001: Create the initial fizzbuzz_results table.

    This is where it all begins. A table to store FizzBuzz results
    in memory, with columns for the number, output, and boolean
    flags for Fizz/Buzz/FizzBuzz/Plain classification. It's a
    normalized, well-structured table that will exist for approximately
    the duration of a single CLI invocation.
    """

    migration_id = "m001_initial_schema"
    dependencies: list[str] = []
    description = "Create initial fizzbuzz_results table"

    def up(self, schema: SchemaManager) -> None:
        schema.create_table(
            "fizzbuzz_results",
            {
                "number": "int",
                "output": "str",
                "is_fizz": "bool",
                "is_buzz": "bool",
                "is_fizzbuzz": "bool",
                "is_plain": "bool",
                "rules_matched": "int",
            },
        )

    def down(self, schema: SchemaManager) -> None:
        schema.drop_table("fizzbuzz_results")


class M002AddIsPrime(Migration):
    """m002: Add is_prime column with trial division backfill.

    Because every FizzBuzz database needs to know which numbers are
    prime. We use trial division for the backfill, because implementing
    a Miller-Rabin probabilistic primality test for numbers under 100
    would exceed the requirements for numbers under 100.
    """

    migration_id = "m002_add_is_prime"
    dependencies = ["m001_initial_schema"]
    description = "Add is_prime column with trial division backfill"

    def up(self, schema: SchemaManager) -> None:
        schema.add_column("fizzbuzz_results", "is_prime", "bool", default=False)

        # Backfill with trial division
        for row in schema.get_data("fizzbuzz_results"):
            row["is_prime"] = self._is_prime(row["number"])

    def down(self, schema: SchemaManager) -> None:
        schema.drop_column("fizzbuzz_results", "is_prime")

    @staticmethod
    def _is_prime(n: int) -> bool:
        """Trial division primality test."""
        if n < 2:
            return False
        if n < 4:
            return True
        if n % 2 == 0 or n % 3 == 0:
            return False
        i = 5
        while i * i <= n:
            if n % i == 0 or n % (i + 2) == 0:
                return False
            i += 6
        return True


class M003AddConfidence(Migration):
    """m003: Add ml_confidence float column.

    Every FizzBuzz result deserves a machine learning confidence score,
    even when the result was computed using simple modulo arithmetic.
    The default confidence of 1.0 reflects our absolute certainty that
    15 % 3 == 0, which is honestly more confidence than most ML models
    can muster for any prediction.
    """

    migration_id = "m003_add_confidence"
    dependencies = ["m001_initial_schema"]
    description = "Add ml_confidence float column"

    def up(self, schema: SchemaManager) -> None:
        schema.add_column(
            "fizzbuzz_results", "ml_confidence", "float", default=1.0
        )

    def down(self, schema: SchemaManager) -> None:
        schema.drop_column("fizzbuzz_results", "ml_confidence")


class M004AddBlockchainHash(Migration):
    """m004: Add blockchain_hash string column.

    For tamper-proof FizzBuzz compliance, every result needs a
    blockchain hash. We compute SHA-256 hashes of the number and
    output, because if you can't verify the cryptographic integrity
    of "Fizz" for the number 3, can you really trust anything?
    """

    migration_id = "m004_add_blockchain_hash"
    dependencies = ["m001_initial_schema"]
    description = "Add blockchain_hash column for immutable audit trail"

    def up(self, schema: SchemaManager) -> None:
        schema.add_column(
            "fizzbuzz_results", "blockchain_hash", "str", default=""
        )

        # Backfill with SHA-256 hashes
        for row in schema.get_data("fizzbuzz_results"):
            content = f"fizzbuzz:{row['number']}:{row['output']}"
            row["blockchain_hash"] = hashlib.sha256(content.encode()).hexdigest()[:16]

    def down(self, schema: SchemaManager) -> None:
        schema.drop_column("fizzbuzz_results", "blockchain_hash")


class M005SplitFizzBuzzTables(Migration):
    """m005: Normalize into fizz_results and buzz_results tables.

    Because a single fizzbuzz_results table is clearly a violation
    of third normal form. We must split Fizz and Buzz into their
    own dedicated tables, creating a fully normalized relational
    schema for our in-memory dict-based database. This is the
    enterprise way.
    """

    migration_id = "m005_split_fizz_buzz_tables"
    dependencies = ["m001_initial_schema"]
    description = "Normalize into fizz_results and buzz_results tables"

    def up(self, schema: SchemaManager) -> None:
        # Create the normalized tables
        schema.create_table(
            "fizz_results",
            {
                "number": "int",
                "output": "str",
                "rules_matched": "int",
            },
        )

        schema.create_table(
            "buzz_results",
            {
                "number": "int",
                "output": "str",
                "rules_matched": "int",
            },
        )

        # Populate from the main table
        if schema.table_exists("fizzbuzz_results"):
            for row in schema.get_data("fizzbuzz_results"):
                if row.get("is_fizz"):
                    schema.insert(
                        "fizz_results",
                        {
                            "number": row["number"],
                            "output": row["output"],
                            "rules_matched": row.get("rules_matched", 0),
                        },
                    )
                if row.get("is_buzz"):
                    schema.insert(
                        "buzz_results",
                        {
                            "number": row["number"],
                            "output": row["output"],
                            "rules_matched": row.get("rules_matched", 0),
                        },
                    )

    def down(self, schema: SchemaManager) -> None:
        if schema.table_exists("fizz_results"):
            schema.drop_table("fizz_results")
        if schema.table_exists("buzz_results"):
            schema.drop_table("buzz_results")


# ============================================================
# Auto-register all pre-built migrations
# ============================================================


def _register_builtin_migrations() -> None:
    """Register all built-in migrations with the global registry."""
    registry = MigrationRegistry.get_instance()
    for migration_cls in [
        M001InitialSchema,
        M002AddIsPrime,
        M003AddConfidence,
        M004AddBlockchainHash,
        M005SplitFizzBuzzTables,
    ]:
        registry.register(migration_cls)


# Register on module import
_register_builtin_migrations()


# ============================================================
# FizzSchema: Consensus-Based Schema Evolution
# ============================================================
#
# Avro/Protobuf-inspired schema versioning with compatibility
# enforcement, Paxos-based consensus approval, and migration
# planning. Data contracts are not suggestions — they are
# legally binding agreements between producers and consumers.
# ============================================================


# ============================================================
# Schema Evolution Enums
# ============================================================


class SchemaFieldType(Enum):
    """Supported field types in the FizzSchema type system.

    These types map to the intersection of Avro primitive types
    and Protobuf scalar types, providing a lingua franca for
    schema definitions across serialization frameworks. The fact
    that we are using them to describe whether a number is
    divisible by 3 is entirely beside the point.
    """

    INT64 = "int64"
    FLOAT64 = "float64"
    STRING = "string"
    BOOL = "bool"
    ENUM = "enum"
    ARRAY = "array"


class CompatibilityMode(Enum):
    """Schema compatibility enforcement modes.

    These modes mirror Apache Avro's compatibility guarantees and
    determine which schema changes are permitted without breaking
    existing consumers or producers.

    BACKWARD: New schema can read data written by old schema.
    FORWARD: Old schema can read data written by new schema.
    FULL: Both BACKWARD and FORWARD simultaneously.
    NONE: Anarchy. No compatibility checking. Not recommended
          for production FizzBuzz deployments.
    """

    BACKWARD = "BACKWARD"
    FORWARD = "FORWARD"
    FULL = "FULL"
    NONE = "NONE"


class PaxosPhase(Enum):
    """Phases of the Paxos consensus protocol for schema approval."""

    PREPARE = auto()
    PROMISE = auto()
    ACCEPT = auto()
    LEARN = auto()


class ConsensusNodeState(Enum):
    """State of a consensus node during schema approval voting."""

    IDLE = auto()
    PROMISED = auto()
    ACCEPTED = auto()
    REJECTED = auto()
    FAILED = auto()


# ============================================================
# Schema Evolution Data Models
# ============================================================


@dataclass
class SchemaField:
    """A single field within a versioned schema definition.

    Each field has a unique tag number (analogous to Protobuf field
    numbers) that provides stable wire-format identification across
    schema versions. Tags are immutable once assigned — reusing a
    tag for a different field is a war crime under the Data Contract
    Geneva Convention.
    """

    name: str
    field_type: SchemaFieldType
    tag: int
    default: Any = None
    deprecated: bool = False
    doc: str = ""

    def has_default(self) -> bool:
        """Whether this field has a default value defined."""
        return self.default is not None

    def to_dict(self) -> dict[str, Any]:
        """Serialize field metadata to dictionary."""
        return {
            "name": self.name,
            "type": self.field_type.value,
            "tag": self.tag,
            "default": self.default,
            "deprecated": self.deprecated,
            "doc": self.doc,
        }


@dataclass
class Schema:
    """A versioned schema definition with fingerprint-based identity.

    Schemas are immutable once registered. The fingerprint is computed
    from the sorted (name, tag, type) tuples of all fields, providing
    a content-addressable identity that is independent of field ordering
    in the source definition. Two schemas with identical fields will
    always produce the same fingerprint, regardless of declaration order.
    """

    name: str
    version: int
    fields: list[SchemaField]
    doc: str = ""
    _fingerprint: Optional[str] = field(default=None, repr=False)

    @property
    def fingerprint(self) -> str:
        """SHA-256 fingerprint of the schema's field structure.

        Computed lazily and cached. The fingerprint is derived from
        the sorted (name, tag, type) tuples, ensuring order-independent
        identity. This is the schema's true name — version numbers are
        for humans, fingerprints are for machines.
        """
        if self._fingerprint is None:
            canonical = sorted(
                (f.name, f.tag, f.field_type.value) for f in self.fields
            )
            raw = json.dumps(canonical, sort_keys=True).encode("utf-8")
            self._fingerprint = hashlib.sha256(raw).hexdigest()
        return self._fingerprint

    @property
    def field_names(self) -> set[str]:
        """Set of all field names in this schema."""
        return {f.name for f in self.fields}

    @property
    def field_by_name(self) -> dict[str, SchemaField]:
        """Lookup fields by name."""
        return {f.name: f for f in self.fields}

    @property
    def field_by_tag(self) -> dict[int, SchemaField]:
        """Lookup fields by tag number."""
        return {f.tag: f for f in self.fields}

    def to_dict(self) -> dict[str, Any]:
        """Serialize schema metadata to dictionary."""
        return {
            "name": self.name,
            "version": self.version,
            "fingerprint": self.fingerprint,
            "field_count": len(self.fields),
            "fields": [f.to_dict() for f in self.fields],
            "doc": self.doc,
        }


# ============================================================
# Compatibility Checking
# ============================================================


@dataclass
class CompatibilityResult:
    """Result of comparing two schemas for compatibility.

    Contains violations (hard failures), warnings (deprecations,
    type promotions), and an overall verdict. A schema change with
    any violations is rejected; warnings are informational and
    logged for the Schema Review Board's quarterly audit.
    """

    compatible: bool
    violations: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    mode: CompatibilityMode = CompatibilityMode.BACKWARD


class CompatibilityChecker:
    """Compares two schemas and produces a compatibility verdict.

    Implements the compatibility rules defined by Avro's Schema
    Resolution specification, adapted for the unique requirements
    of the FizzBuzz evaluation pipeline. The checker supports
    BACKWARD, FORWARD, FULL, and NONE compatibility modes, each
    with distinct constraints on field additions, removals, and
    type changes.
    """

    # Type promotions that are safe (widening conversions only)
    SAFE_PROMOTIONS: dict[SchemaFieldType, set[SchemaFieldType]] = {
        SchemaFieldType.INT64: {SchemaFieldType.FLOAT64, SchemaFieldType.STRING},
        SchemaFieldType.FLOAT64: {SchemaFieldType.STRING},
        SchemaFieldType.BOOL: {SchemaFieldType.STRING, SchemaFieldType.INT64},
    }

    def check(
        self,
        old_schema: Schema,
        new_schema: Schema,
        mode: CompatibilityMode,
    ) -> CompatibilityResult:
        """Check compatibility between old and new schema versions.

        Args:
            old_schema: The previously registered schema version.
            new_schema: The proposed new schema version.
            mode: The compatibility mode to enforce.

        Returns:
            CompatibilityResult with violations, warnings, and verdict.
        """
        if mode == CompatibilityMode.NONE:
            return CompatibilityResult(compatible=True, mode=mode)

        violations: list[str] = []
        warnings: list[str] = []

        old_fields = old_schema.field_by_name
        new_fields = new_schema.field_by_name

        added_fields = new_schema.field_names - old_schema.field_names
        removed_fields = old_schema.field_names - new_schema.field_names
        common_fields = old_schema.field_names & new_schema.field_names

        if mode in (CompatibilityMode.BACKWARD, CompatibilityMode.FULL):
            self._check_backward(
                added_fields, removed_fields, old_fields, new_fields,
                violations, warnings,
            )

        if mode in (CompatibilityMode.FORWARD, CompatibilityMode.FULL):
            self._check_forward(
                added_fields, removed_fields, old_fields, new_fields,
                violations, warnings,
            )

        # Check type changes for common fields
        for name in common_fields:
            old_f = old_fields[name]
            new_f = new_fields[name]

            if old_f.field_type != new_f.field_type:
                if new_f.field_type in self.SAFE_PROMOTIONS.get(old_f.field_type, set()):
                    warnings.append(
                        f"Field '{name}': type promotion {old_f.field_type.value} -> "
                        f"{new_f.field_type.value} (safe widening conversion)"
                    )
                else:
                    violations.append(
                        f"Field '{name}': incompatible type change "
                        f"{old_f.field_type.value} -> {new_f.field_type.value}"
                    )

            if old_f.tag != new_f.tag:
                violations.append(
                    f"Field '{name}': tag number changed from {old_f.tag} to {new_f.tag} "
                    f"(tag reassignment violates the Data Contract Geneva Convention)"
                )

            if new_f.deprecated and not old_f.deprecated:
                warnings.append(
                    f"Field '{name}': newly deprecated (consumers should migrate away)"
                )

        return CompatibilityResult(
            compatible=len(violations) == 0,
            violations=violations,
            warnings=warnings,
            mode=mode,
        )

    def _check_backward(
        self,
        added: set[str],
        removed: set[str],
        old_fields: dict[str, SchemaField],
        new_fields: dict[str, SchemaField],
        violations: list[str],
        warnings: list[str],
    ) -> None:
        """BACKWARD: new readers must handle old data."""
        # New fields must have defaults (old data won't have them)
        for name in added:
            f = new_fields[name]
            if not f.has_default():
                violations.append(
                    f"BACKWARD violation: new field '{name}' has no default value "
                    f"(old data will not contain this field)"
                )
            else:
                warnings.append(
                    f"New field '{name}' added with default={f.default!r}"
                )

        # Removed fields must have had defaults (they were optional)
        for name in removed:
            f = old_fields[name]
            if not f.has_default():
                violations.append(
                    f"BACKWARD violation: removed field '{name}' had no default value "
                    f"(it was required in the old schema)"
                )

    def _check_forward(
        self,
        added: set[str],
        removed: set[str],
        old_fields: dict[str, SchemaField],
        new_fields: dict[str, SchemaField],
        violations: list[str],
        warnings: list[str],
    ) -> None:
        """FORWARD: old readers must handle new data."""
        # Removed fields must have defaults in old schema
        # (old readers will look for them in new data and not find them)
        for name in removed:
            f = old_fields[name]
            if not f.has_default():
                violations.append(
                    f"FORWARD violation: removed field '{name}' has no default in old schema "
                    f"(old readers will fail when field is missing from new data)"
                )

        # New fields are ignored by old readers (acceptable for FORWARD)
        for name in added:
            warnings.append(
                f"New field '{name}' will be ignored by old readers (FORWARD-safe)"
            )


# ============================================================
# Schema Registry
# ============================================================


class SchemaRegistry:
    """Central registry for all versioned schemas in the platform.

    The registry enforces compatibility constraints on registration,
    maintains a version history for each schema name, and supports
    lookup by name+version or by fingerprint. It is the single
    source of truth for data contracts.

    Think of it as a corporate HR department, but for data structures.
    Every field must be properly onboarded, documented, and approved
    before it can participate in the organization.
    """

    def __init__(self, default_mode: CompatibilityMode = CompatibilityMode.BACKWARD) -> None:
        self._schemas: dict[str, dict[int, Schema]] = {}
        self._fingerprint_index: dict[str, Schema] = {}
        self._compatibility_mode: dict[str, CompatibilityMode] = {}
        self._default_mode = default_mode
        self._checker = CompatibilityChecker()
        self._history: list[dict[str, Any]] = []
        self._lock = threading.Lock()

    @property
    def schema_names(self) -> list[str]:
        """All registered schema names."""
        return list(self._schemas.keys())

    @property
    def history(self) -> list[dict[str, Any]]:
        """Compatibility check history for audit purposes."""
        return list(self._history)

    def set_compatibility_mode(self, schema_name: str, mode: CompatibilityMode) -> None:
        """Set the compatibility mode for a specific schema."""
        with self._lock:
            self._compatibility_mode[schema_name] = mode
            logger.info(
                "Compatibility mode for '%s' set to %s",
                schema_name, mode.value,
            )

    def get_compatibility_mode(self, schema_name: str) -> CompatibilityMode:
        """Get the compatibility mode for a schema (falls back to default)."""
        return self._compatibility_mode.get(schema_name, self._default_mode)

    def register(self, schema: Schema, *, force: bool = False) -> CompatibilityResult:
        """Register a new schema version in the registry.

        Enforces compatibility against the latest version of the
        same schema name. If compatibility check fails and force
        is not set, raises SchemaRegistrationError.

        Args:
            schema: The schema to register.
            force: Skip compatibility checking (use with extreme caution).

        Returns:
            CompatibilityResult from the check (or a clean result if first version).

        Raises:
            SchemaRegistrationError: If compatibility check fails.
        """
        with self._lock:
            return self._register_internal(schema, force=force)

    def _register_internal(self, schema: Schema, *, force: bool = False) -> CompatibilityResult:
        """Internal registration logic (must be called under lock)."""
        name = schema.name
        version = schema.version

        # Check for duplicate fingerprint with different name/version
        if schema.fingerprint in self._fingerprint_index:
            existing = self._fingerprint_index[schema.fingerprint]
            if existing.name != name or existing.version != version:
                raise SchemaRegistrationError(
                    name, version,
                    f"Fingerprint collision with '{existing.name}' v{existing.version} "
                    f"(identical field structure already registered)",
                )

        # Check for version conflict
        if name in self._schemas and version in self._schemas[name]:
            existing = self._schemas[name][version]
            if existing.fingerprint != schema.fingerprint:
                raise SchemaRegistrationError(
                    name, version,
                    f"Version {version} already registered with different fingerprint "
                    f"(existing: {existing.fingerprint[:16]}..., "
                    f"proposed: {schema.fingerprint[:16]}...)",
                )
            # Identical re-registration is idempotent
            return CompatibilityResult(compatible=True, mode=self.get_compatibility_mode(name))

        # Compatibility check against latest version
        result = CompatibilityResult(compatible=True, mode=self.get_compatibility_mode(name))
        if name in self._schemas and self._schemas[name]:
            latest_version = max(self._schemas[name].keys())
            latest = self._schemas[name][latest_version]
            mode = self.get_compatibility_mode(name)
            result = self._checker.check(latest, schema, mode)

            self._history.append({
                "schema_name": name,
                "from_version": latest_version,
                "to_version": version,
                "mode": mode.value,
                "compatible": result.compatible,
                "violations": result.violations,
                "warnings": result.warnings,
                "timestamp": time.time(),
            })

            if not result.compatible and not force:
                raise SchemaRegistrationError(
                    name, version,
                    f"Compatibility check failed ({mode.value}): "
                    f"{len(result.violations)} violation(s)",
                )

        # Register
        if name not in self._schemas:
            self._schemas[name] = {}
        self._schemas[name][version] = schema
        self._fingerprint_index[schema.fingerprint] = schema

        logger.info(
            "Registered schema '%s' v%d (fingerprint: %s)",
            name, version, schema.fingerprint[:16],
        )

        return result

    def get(self, name: str, version: Optional[int] = None) -> Optional[Schema]:
        """Look up a schema by name and optional version.

        If version is None, returns the latest version.
        """
        if name not in self._schemas:
            return None
        versions = self._schemas[name]
        if not versions:
            return None
        if version is not None:
            return versions.get(version)
        return versions[max(versions.keys())]

    def get_by_fingerprint(self, fingerprint: str) -> Optional[Schema]:
        """Look up a schema by its SHA-256 fingerprint."""
        return self._fingerprint_index.get(fingerprint)

    def get_versions(self, name: str) -> list[int]:
        """Get all registered version numbers for a schema name."""
        if name not in self._schemas:
            return []
        return sorted(self._schemas[name].keys())

    def get_all_schemas(self) -> list[Schema]:
        """Get all registered schemas, ordered by name and version."""
        result: list[Schema] = []
        for name in sorted(self._schemas.keys()):
            for version in sorted(self._schemas[name].keys()):
                result.append(self._schemas[name][version])
        return result


# ============================================================
# Schema Migration Planning
# ============================================================


@dataclass
class FieldMigration:
    """A single field-level migration action."""

    action: str  # "ADD", "REMOVE", "PROMOTE", "DEPRECATE"
    field_name: str
    detail: str
    default_value: Any = None


@dataclass
class MigrationPlan:
    """A complete migration plan from one schema version to another.

    Contains the ordered list of field-level actions required to
    transform data from the old schema to the new schema. The plan
    is deterministic: given the same old and new schemas, the same
    plan will always be produced.
    """

    schema_name: str
    from_version: int
    to_version: int
    actions: list[FieldMigration] = field(default_factory=list)

    @property
    def has_breaking_changes(self) -> bool:
        """Whether the migration contains potentially breaking changes."""
        return any(a.action == "REMOVE" for a in self.actions)

    @property
    def summary(self) -> str:
        """Human-readable summary of the migration plan."""
        counts: dict[str, int] = {}
        for a in self.actions:
            counts[a.action] = counts.get(a.action, 0) + 1
        parts = [f"{count} {action.lower()}(s)" for action, count in sorted(counts.items())]
        return f"{self.schema_name} v{self.from_version} -> v{self.to_version}: {', '.join(parts) or 'no changes'}"


class MigrationPlanner:
    """Produces migration plans between schema versions.

    The planner compares two schemas and generates a deterministic
    ordered list of field-level migration actions. These actions can
    be applied to transform data from the old schema format to the
    new format, handling field additions (with defaults), removals,
    type promotions, and deprecation transitions.
    """

    SAFE_PROMOTIONS = CompatibilityChecker.SAFE_PROMOTIONS

    def plan(self, old_schema: Schema, new_schema: Schema) -> MigrationPlan:
        """Generate a migration plan between two schema versions.

        Args:
            old_schema: The source schema version.
            new_schema: The target schema version.

        Returns:
            MigrationPlan with ordered field-level actions.
        """
        actions: list[FieldMigration] = []

        old_fields = old_schema.field_by_name
        new_fields = new_schema.field_by_name

        added = new_schema.field_names - old_schema.field_names
        removed = old_schema.field_names - new_schema.field_names
        common = old_schema.field_names & new_schema.field_names

        # Additions
        for name in sorted(added):
            f = new_fields[name]
            actions.append(FieldMigration(
                action="ADD",
                field_name=name,
                detail=f"Add field '{name}' ({f.field_type.value}, tag={f.tag})"
                       + (f", default={f.default!r}" if f.has_default() else ", NO DEFAULT"),
                default_value=f.default,
            ))

        # Removals
        for name in sorted(removed):
            f = old_fields[name]
            actions.append(FieldMigration(
                action="REMOVE",
                field_name=name,
                detail=f"Remove field '{name}' ({f.field_type.value}, tag={f.tag})",
            ))

        # Changes to common fields
        for name in sorted(common):
            old_f = old_fields[name]
            new_f = new_fields[name]

            # Type promotion
            if old_f.field_type != new_f.field_type:
                safe = new_f.field_type in self.SAFE_PROMOTIONS.get(old_f.field_type, set())
                actions.append(FieldMigration(
                    action="PROMOTE",
                    field_name=name,
                    detail=f"Type promotion '{name}': {old_f.field_type.value} -> "
                           f"{new_f.field_type.value} ({'safe' if safe else 'UNSAFE'})",
                ))

            # Deprecation
            if new_f.deprecated and not old_f.deprecated:
                actions.append(FieldMigration(
                    action="DEPRECATE",
                    field_name=name,
                    detail=f"Deprecate field '{name}' (consumers should migrate away)",
                ))

        return MigrationPlan(
            schema_name=new_schema.name,
            from_version=old_schema.version,
            to_version=new_schema.version,
            actions=actions,
        )


# ============================================================
# Paxos Consensus Approval
# ============================================================


@dataclass
class ConsensusNode:
    """A single node in the Paxos consensus cluster.

    Each node independently evaluates schema compatibility and
    casts its vote. Nodes can fail (simulated) to test fault
    tolerance of the consensus protocol. A failed node does not
    participate in voting but counts toward the total cluster size.
    """

    node_id: int
    state: ConsensusNodeState = ConsensusNodeState.IDLE
    promised_proposal: Optional[int] = None
    accepted_proposal: Optional[int] = None
    accepted_value: Optional[bool] = None
    failure_injected: bool = False

    def reset(self) -> None:
        """Reset node to idle state for the next round."""
        self.state = ConsensusNodeState.IDLE
        self.promised_proposal = None
        self.accepted_proposal = None
        self.accepted_value = None


@dataclass
class ConsensusRound:
    """Record of a single Paxos consensus round."""

    round_id: str
    schema_name: str
    version: int
    proposal_number: int
    phase_log: list[dict[str, Any]] = field(default_factory=list)
    approved: bool = False
    approvals: int = 0
    rejections: int = 0
    failures: int = 0
    duration_ms: float = 0.0


class ConsensusApprover:
    """Paxos-based consensus protocol for schema change approval.

    Implements a simplified Paxos consensus protocol with 5 nodes
    (configurable) and a quorum of 3 (configurable). Each node
    independently evaluates the proposed schema change against the
    active compatibility mode and casts its vote.

    The protocol proceeds through four phases:
    1. PREPARE: Proposer sends proposal number to all nodes.
    2. PROMISE: Nodes promise not to accept lower-numbered proposals.
    3. ACCEPT: Proposer sends the schema change for acceptance.
    4. LEARN: If quorum is reached, all nodes learn the decision.

    Fault injection is supported: individual nodes can be marked as
    failed, simulating network partitions or node crashes. The protocol
    tolerates up to (N - quorum) failures and still reaches consensus.
    """

    def __init__(
        self,
        num_nodes: int = 5,
        quorum: int = 3,
    ) -> None:
        if quorum > num_nodes:
            raise SchemaEvolutionError(
                f"Quorum ({quorum}) cannot exceed number of nodes ({num_nodes})"
            )
        self._num_nodes = num_nodes
        self._quorum = quorum
        self._nodes = [ConsensusNode(node_id=i) for i in range(num_nodes)]
        self._proposal_counter = 0
        self._checker = CompatibilityChecker()
        self._rounds: list[ConsensusRound] = []
        self._lock = threading.Lock()

    @property
    def nodes(self) -> list[ConsensusNode]:
        """Access the consensus nodes."""
        return list(self._nodes)

    @property
    def rounds(self) -> list[ConsensusRound]:
        """History of consensus rounds."""
        return list(self._rounds)

    def inject_failure(self, node_id: int) -> None:
        """Simulate a node failure (network partition, crash, etc.)."""
        if 0 <= node_id < self._num_nodes:
            self._nodes[node_id].failure_injected = True
            self._nodes[node_id].state = ConsensusNodeState.FAILED
            logger.warning("Node %d marked as failed", node_id)

    def recover_node(self, node_id: int) -> None:
        """Recover a previously failed node."""
        if 0 <= node_id < self._num_nodes:
            self._nodes[node_id].failure_injected = False
            self._nodes[node_id].state = ConsensusNodeState.IDLE
            logger.info("Node %d recovered", node_id)

    def approve(
        self,
        old_schema: Optional[Schema],
        new_schema: Schema,
        mode: CompatibilityMode,
    ) -> ConsensusRound:
        """Run the full Paxos consensus protocol for a schema change.

        Args:
            old_schema: The previous schema version (None if first version).
            new_schema: The proposed new schema version.
            mode: The compatibility mode to enforce.

        Returns:
            ConsensusRound with the full voting record.

        Raises:
            SchemaConsensusError: If quorum is not reached.
        """
        with self._lock:
            return self._run_consensus(old_schema, new_schema, mode)

    def _run_consensus(
        self,
        old_schema: Optional[Schema],
        new_schema: Schema,
        mode: CompatibilityMode,
    ) -> ConsensusRound:
        """Execute the Paxos protocol (must be called under lock)."""
        start_time = time.monotonic()
        self._proposal_counter += 1
        proposal_num = self._proposal_counter

        round_record = ConsensusRound(
            round_id=str(uuid.uuid4())[:8],
            schema_name=new_schema.name,
            version=new_schema.version,
            proposal_number=proposal_num,
        )

        # Reset non-failed nodes
        for node in self._nodes:
            if not node.failure_injected:
                node.reset()

        # Phase 1: PREPARE
        round_record.phase_log.append({
            "phase": PaxosPhase.PREPARE.name,
            "proposal": proposal_num,
            "message": f"Proposer sends PREPARE({proposal_num}) to all nodes",
        })

        # Phase 2: PROMISE
        promises = 0
        for node in self._nodes:
            if node.failure_injected:
                round_record.failures += 1
                round_record.phase_log.append({
                    "phase": PaxosPhase.PROMISE.name,
                    "node_id": node.node_id,
                    "result": "FAILED",
                    "message": f"Node {node.node_id} is unreachable (failure injected)",
                })
                continue

            if node.promised_proposal is None or proposal_num > node.promised_proposal:
                node.promised_proposal = proposal_num
                node.state = ConsensusNodeState.PROMISED
                promises += 1
                round_record.phase_log.append({
                    "phase": PaxosPhase.PROMISE.name,
                    "node_id": node.node_id,
                    "result": "PROMISED",
                    "message": f"Node {node.node_id} promises for proposal {proposal_num}",
                })
            else:
                round_record.phase_log.append({
                    "phase": PaxosPhase.PROMISE.name,
                    "node_id": node.node_id,
                    "result": "REJECTED",
                    "message": f"Node {node.node_id} already promised for higher proposal",
                })

        if promises < self._quorum:
            round_record.approved = False
            round_record.duration_ms = (time.monotonic() - start_time) * 1000
            self._rounds.append(round_record)
            raise SchemaConsensusError(
                new_schema.name, promises, self._quorum,
                "Failed to gather enough promises in PREPARE phase",
            )

        # Phase 3: ACCEPT — each node independently checks compatibility
        approvals = 0
        rejections = 0
        for node in self._nodes:
            if node.failure_injected or node.state != ConsensusNodeState.PROMISED:
                continue

            # Each node independently evaluates compatibility
            if old_schema is not None and mode != CompatibilityMode.NONE:
                result = self._checker.check(old_schema, new_schema, mode)
                vote = result.compatible
            else:
                vote = True  # First version or NONE mode — auto-approve

            node.accepted_proposal = proposal_num
            node.accepted_value = vote

            if vote:
                node.state = ConsensusNodeState.ACCEPTED
                approvals += 1
                round_record.phase_log.append({
                    "phase": PaxosPhase.ACCEPT.name,
                    "node_id": node.node_id,
                    "result": "ACCEPTED",
                    "message": f"Node {node.node_id} accepts schema change (compatible)",
                })
            else:
                node.state = ConsensusNodeState.REJECTED
                rejections += 1
                round_record.phase_log.append({
                    "phase": PaxosPhase.ACCEPT.name,
                    "node_id": node.node_id,
                    "result": "REJECTED",
                    "message": f"Node {node.node_id} rejects schema change (incompatible)",
                })

        round_record.approvals = approvals
        round_record.rejections = rejections

        # Phase 4: LEARN
        if approvals >= self._quorum:
            round_record.approved = True
            round_record.phase_log.append({
                "phase": PaxosPhase.LEARN.name,
                "result": "APPROVED",
                "message": f"Quorum reached ({approvals}/{self._quorum}): schema change approved",
            })
        else:
            round_record.approved = False
            round_record.phase_log.append({
                "phase": PaxosPhase.LEARN.name,
                "result": "REJECTED",
                "message": f"Quorum not reached ({approvals}/{self._quorum}): schema change rejected",
            })

        round_record.duration_ms = (time.monotonic() - start_time) * 1000
        self._rounds.append(round_record)

        if not round_record.approved:
            raise SchemaConsensusError(
                new_schema.name, approvals, self._quorum,
                f"Schema change rejected by consensus ({rejections} rejection(s), "
                f"{round_record.failures} failure(s))",
            )

        return round_record


# ============================================================
# Built-in EvaluationResult Schema Lineage
# ============================================================


def _build_evaluation_result_v1() -> Schema:
    """EvaluationResult v1: the original, pure schema."""
    return Schema(
        name="EvaluationResult",
        version=1,
        fields=[
            SchemaField("number", SchemaFieldType.INT64, tag=1),
            SchemaField("result", SchemaFieldType.STRING, tag=2),
        ],
        doc="Original EvaluationResult: number and its FizzBuzz classification",
    )


def _build_evaluation_result_v2() -> Schema:
    """EvaluationResult v2: added strategy and latency tracking."""
    return Schema(
        name="EvaluationResult",
        version=2,
        fields=[
            SchemaField("number", SchemaFieldType.INT64, tag=1),
            SchemaField("result", SchemaFieldType.STRING, tag=2),
            SchemaField("strategy", SchemaFieldType.STRING, tag=3, default="standard"),
            SchemaField("latency_ns", SchemaFieldType.INT64, tag=4, default=0),
        ],
        doc="EvaluationResult v2: strategy selection and nanosecond latency tracking",
    )


def _build_evaluation_result_v3() -> Schema:
    """EvaluationResult v3: added cache hit and confidence score."""
    return Schema(
        name="EvaluationResult",
        version=3,
        fields=[
            SchemaField("number", SchemaFieldType.INT64, tag=1),
            SchemaField("result", SchemaFieldType.STRING, tag=2),
            SchemaField("strategy", SchemaFieldType.STRING, tag=3, default="standard"),
            SchemaField("latency_ns", SchemaFieldType.INT64, tag=4, default=0),
            SchemaField("cache_hit", SchemaFieldType.BOOL, tag=5, default=False),
            SchemaField("confidence", SchemaFieldType.FLOAT64, tag=6, default=1.0),
        ],
        doc="EvaluationResult v3: cache observability and ML confidence scores",
    )


def build_evaluation_result_lineage() -> list[Schema]:
    """Return the complete EvaluationResult schema lineage (v1 -> v2 -> v3)."""
    return [
        _build_evaluation_result_v1(),
        _build_evaluation_result_v2(),
        _build_evaluation_result_v3(),
    ]


def bootstrap_registry(
    mode: CompatibilityMode = CompatibilityMode.BACKWARD,
) -> SchemaRegistry:
    """Create a registry pre-loaded with the EvaluationResult lineage.

    This is the standard bootstrap procedure for the FizzSchema subsystem.
    All three versions of EvaluationResult are registered in order,
    demonstrating backward-compatible schema evolution from the simplest
    (number, result) contract through to the full observability schema.
    """
    registry = SchemaRegistry(default_mode=mode)
    for schema in build_evaluation_result_lineage():
        registry.register(schema, force=True)
    return registry


# ============================================================
# Schema Dashboard
# ============================================================


class SchemaDashboard:
    """ASCII dashboard for the FizzSchema subsystem.

    Renders a comprehensive overview of schema inventory, version
    timelines, compatibility history, and consensus round summaries.
    The dashboard is designed for executive stakeholders who need
    real-time visibility into the schema governance pipeline.
    """

    @staticmethod
    def render(
        registry: SchemaRegistry,
        approver: Optional[ConsensusApprover] = None,
        planner: Optional[MigrationPlanner] = None,
        width: int = 60,
    ) -> str:
        """Render the FizzSchema ASCII dashboard.

        Args:
            registry: The schema registry to display.
            approver: Optional consensus approver for round history.
            planner: Optional migration planner (for migration summaries).
            width: Dashboard character width.

        Returns:
            Multi-line string with box-drawing characters.
        """
        lines: list[str] = []
        hr = "+" + "-" * (width - 2) + "+"

        def center(text: str) -> str:
            return "|" + text.center(width - 2) + "|"

        def left(text: str) -> str:
            truncated = text[: width - 4]
            return "| " + truncated.ljust(width - 4) + " |"

        # Title
        lines.append(hr)
        lines.append(center("FizzSchema - Schema Evolution Dashboard"))
        lines.append(hr)

        # Schema Inventory
        lines.append(center("Schema Inventory"))
        lines.append(hr)

        schemas = registry.get_all_schemas()
        if not schemas:
            lines.append(left("(no schemas registered)"))
        else:
            # Group by name
            by_name: dict[str, list[Schema]] = {}
            for s in schemas:
                by_name.setdefault(s.name, []).append(s)

            for name in sorted(by_name.keys()):
                versions = by_name[name]
                latest = versions[-1]
                lines.append(left(
                    f"{name}: {len(versions)} version(s), "
                    f"latest=v{latest.version}, "
                    f"{len(latest.fields)} field(s)"
                ))
                lines.append(left(
                    f"  fingerprint: {latest.fingerprint[:32]}..."
                ))
                mode = registry.get_compatibility_mode(name)
                lines.append(left(f"  compatibility: {mode.value}"))

        lines.append(hr)

        # Version Timeline
        lines.append(center("Version Timeline"))
        lines.append(hr)

        for s in schemas:
            field_names = ", ".join(f.name for f in s.fields)
            if len(field_names) > width - 20:
                field_names = field_names[: width - 23] + "..."
            lines.append(left(f"v{s.version} [{s.name}]: {field_names}"))

        if not schemas:
            lines.append(left("(no versions)"))

        lines.append(hr)

        # Compatibility History
        lines.append(center("Compatibility History"))
        lines.append(hr)

        history = registry.history
        if not history:
            lines.append(left("(no compatibility checks recorded)"))
        else:
            for entry in history[-10:]:  # Last 10 entries
                status = "PASS" if entry["compatible"] else "FAIL"
                lines.append(left(
                    f"{entry['schema_name']} v{entry['from_version']}->"
                    f"v{entry['to_version']} [{entry['mode']}]: {status}"
                ))
                if entry["violations"]:
                    for v in entry["violations"][:2]:
                        truncated = v[:width - 10]
                        lines.append(left(f"    ! {truncated}"))
                if entry["warnings"]:
                    for w in entry["warnings"][:2]:
                        truncated = w[:width - 10]
                        lines.append(left(f"    ~ {truncated}"))

        lines.append(hr)

        # Consensus Rounds
        if approver is not None:
            lines.append(center("Consensus Rounds"))
            lines.append(hr)

            rounds = approver.rounds
            if not rounds:
                lines.append(left("(no consensus rounds)"))
            else:
                for r in rounds[-5:]:  # Last 5 rounds
                    status = "APPROVED" if r.approved else "REJECTED"
                    lines.append(left(
                        f"Round {r.round_id}: {r.schema_name} v{r.version} "
                        f"[{status}] {r.approvals}A/{r.rejections}R/{r.failures}F "
                        f"({r.duration_ms:.1f}ms)"
                    ))

            lines.append(hr)

        # Footer
        lines.append(center(f"Registered: {len(schemas)} schema(s)"))
        lines.append(hr)

        return "\n".join(lines)


# ============================================================
# Schema Middleware
# ============================================================


class SchemaMiddleware(IMiddleware):
    """Attaches schema version metadata to the evaluation context.

    When installed in the middleware pipeline, this middleware stamps
    every ProcessingContext with the active EvaluationResult schema
    version and fingerprint, enabling downstream consumers to
    identify the exact data contract under which the result was
    produced. This is essential for schema-aware deserialization
    and audit trail compliance.
    """

    def __init__(self, registry: SchemaRegistry, schema_name: str = "EvaluationResult") -> None:
        self._registry = registry
        self._schema_name = schema_name

    def process(
        self,
        context: ProcessingContext,
        next_handler: Callable[[ProcessingContext], ProcessingContext],
    ) -> ProcessingContext:
        """Attach schema metadata to the processing context."""
        schema = self._registry.get(self._schema_name)
        if schema is not None:
            context.metadata["schema_name"] = schema.name
            context.metadata["schema_version"] = schema.version
            context.metadata["schema_fingerprint"] = schema.fingerprint
        return next_handler(context)

    def get_name(self) -> str:
        return "SchemaMiddleware"

    def get_priority(self) -> int:
        return 950  # High priority — stamp schema version early
