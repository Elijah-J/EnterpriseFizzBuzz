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

All data managed by this framework exists exclusively in RAM and will
vanish without a trace the moment you press Ctrl+C. This is by design.
"""

from __future__ import annotations

import hashlib
import logging
import math
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum, auto
from typing import Any, Optional

from enterprise_fizzbuzz.domain.exceptions import (
    MigrationAlreadyAppliedError,
    MigrationConflictError,
    MigrationDependencyError,
    MigrationError,
    MigrationNotFoundError,
    MigrationRollbackError,
    SchemaError,
    SeedDataError,
)

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
    would be over-engineering, and we would never do that.
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
