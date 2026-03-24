"""
Enterprise FizzBuzz Platform - Database Migration Framework Exceptions
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from ._base import CacheError, FizzBuzzError


class MigrationError(FizzBuzzError):
    """Base exception for all Database Migration Framework errors.

    When your migration framework for ephemeral in-memory data structures
    encounters a problem, it raises profound questions about the nature
    of persistence. These dicts were never going to survive a process
    restart, but that's no reason not to manage their schema with the
    same rigor as a production PostgreSQL database.
    """

    def __init__(self, message: str, **kwargs: Any) -> None:
        super().__init__(
            message,
            error_code=kwargs.pop("error_code", "EFP-MG00"),
            context=kwargs.pop("context", {}),
        )


class MigrationNotFoundError(MigrationError):
    """Raised when a referenced migration does not exist in the registry.

    You asked for a migration that the registry has never heard of.
    Perhaps it was never registered, perhaps it was lost in a tragic
    rebasing incident, or perhaps it only existed in a parallel universe
    where FizzBuzz databases are a real thing.
    """

    def __init__(self, migration_id: str) -> None:
        super().__init__(
            f"Migration '{migration_id}' not found in the registry. "
            f"It may have been lost to the void, or perhaps it was never "
            f"meant to exist in the first place.",
            error_code="EFP-MG01",
            context={"migration_id": migration_id},
        )
        self.migration_id = migration_id


class MigrationAlreadyAppliedError(MigrationError):
    """Raised when attempting to apply a migration that has already been applied.

    This migration has already been applied to the in-memory schema.
    Applying it again would be like folding the same origami crane twice —
    technically possible, but the result would be an abomination that
    violates the fundamental principles of database schema management.
    """

    def __init__(self, migration_id: str) -> None:
        super().__init__(
            f"Migration '{migration_id}' has already been applied. "
            f"Applying it again would create a temporal paradox in the "
            f"schema version timeline. Re-application denied.",
            error_code="EFP-MG02",
            context={"migration_id": migration_id},
        )
        self.migration_id = migration_id


class MigrationRollbackError(MigrationError):
    """Raised when a migration rollback fails.

    The migration's down() method encountered an error while trying
    to undo its changes. This is the database equivalent of trying to
    un-bake a cake. The schema is now in an indeterminate state,
    which for an in-memory dict is both tragic and completely irrelevant.
    """

    def __init__(self, migration_id: str, reason: str) -> None:
        super().__init__(
            f"Rollback of migration '{migration_id}' failed: {reason}. "
            f"The schema is now in a superposition of applied and not-applied. "
            f"Schrodinger would be proud.",
            error_code="EFP-MG03",
            context={"migration_id": migration_id, "reason": reason},
        )
        self.migration_id = migration_id


class MigrationDependencyError(MigrationError):
    """Raised when a migration's dependencies are not satisfied.

    This migration requires other migrations to be applied first,
    but they haven't been. You can't add a column to a table that
    doesn't exist yet, even when both the column and the table are
    just keys in a Python dict that will be garbage collected in
    approximately 0.3 seconds.
    """

    def __init__(self, migration_id: str, missing_deps: list[str]) -> None:
        deps_str = ", ".join(missing_deps)
        super().__init__(
            f"Migration '{migration_id}' has unsatisfied dependencies: [{deps_str}]. "
            f"Please apply the prerequisite migrations first, in a display of "
            f"ceremonial ordering that would make any DBA weep with pride.",
            error_code="EFP-MG04",
            context={"migration_id": migration_id, "missing_deps": missing_deps},
        )
        self.migration_id = migration_id
        self.missing_deps = missing_deps


class MigrationConflictError(MigrationError):
    """Raised when two migrations conflict with each other.

    Two migrations are attempting to modify the same part of the
    schema in incompatible ways. This is the migration equivalent
    of a git merge conflict, except the stakes are even lower because
    the entire database exists only in RAM and will be destroyed
    when you press Ctrl+C.
    """

    def __init__(self, migration_a: str, migration_b: str, reason: str) -> None:
        super().__init__(
            f"Migrations '{migration_a}' and '{migration_b}' are in conflict: "
            f"{reason}. Please resolve this conflict by choosing a side, "
            f"like a database King Solomon.",
            error_code="EFP-MG05",
            context={"migration_a": migration_a, "migration_b": migration_b, "reason": reason},
        )


class SchemaError(MigrationError):
    """Raised when a schema operation fails.

    The schema manager encountered an error while trying to modify
    the in-memory schema. Perhaps you tried to create a table that
    already exists, drop one that doesn't, or add a column to the
    void. These are all violations of the schema contract
    that governs our dict-of-lists-of-dicts architecture.
    """

    def __init__(self, operation: str, reason: str) -> None:
        super().__init__(
            f"Schema operation '{operation}' failed: {reason}. "
            f"The in-memory schema has not been modified. "
            f"Your dicts remain untouched.",
            error_code="EFP-MG06",
            context={"operation": operation, "reason": reason},
        )


class SeedDataError(MigrationError):
    """Raised when the seed data generator encounters an error.

    The seed data generator, which runs FizzBuzz to populate a
    FizzBuzz database (yes, you read that correctly), has encountered
    a problem. This is the ouroboros of enterprise software: the snake
    eating its own tail, the FizzBuzz evaluating itself into existence.
    If this error occurs, the circle of life has been broken.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(
            f"Seed data generation failed: {reason}. "
            f"The ouroboros of FizzBuzz self-population has been interrupted. "
            f"The snake has choked on its own tail.",
            error_code="EFP-MG07",
            context={"reason": reason},
        )


class CacheEulogyCompositionError(CacheError):
    """Raised when the eulogy generator fails to compose a eulogy.

    Every evicted cache entry deserves a dignified farewell, and the
    eulogy generator has failed to produce output. The entry will be
    evicted without a proper log record, which may complicate
    post-mortem analysis of cache performance.
    """

    def __init__(self, key: str, reason: str) -> None:
        super().__init__(
            f"Failed to compose eulogy for cache entry '{key}': {reason}. "
            f"The entry will be evicted in silence, which is worse than "
            f"any exception.",
            error_code="EFP-CA07",
            context={"key": key, "reason": reason},
        )

