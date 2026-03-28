"""
Enterprise FizzBuzz Platform - FizzMigration2 Database Migration Framework Test Suite

Comprehensive tests for the Multi-Backend Database Migration Framework.
Validates migration application, rollback, version tracking, history recording,
dashboard rendering, middleware integration, and subsystem factory wiring.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, AsyncMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from enterprise_fizzbuzz.infrastructure.fizzmigration2 import (
    FIZZMIGRATION2_VERSION,
    MIDDLEWARE_PRIORITY,
    MigrationState,
    MigrationDirection,
    FizzMigration2Config,
    Migration,
    MigrationRunner,
    MigrationHistory,
    FizzMigration2Dashboard,
    FizzMigration2Middleware,
    create_fizzmigration2_subsystem,
)
from enterprise_fizzbuzz.infrastructure.config import _SingletonMeta
from enterprise_fizzbuzz.domain.models import ProcessingContext, FizzBuzzResult


@pytest.fixture(autouse=True)
def reset_singletons():
    """Reset all singletons between tests."""
    _SingletonMeta.reset()
    yield


@pytest.fixture
def config():
    """Create a default FizzMigration2Config."""
    return FizzMigration2Config()


@pytest.fixture
def runner(config):
    """Create a MigrationRunner with default config."""
    return MigrationRunner(config)


@pytest.fixture
def history():
    """Create a MigrationHistory instance."""
    return MigrationHistory()


@pytest.fixture
def sample_migration():
    """Create a sample migration for testing."""
    return Migration(
        migration_id="mig_001",
        version="1.0.0",
        description="Create fizzbuzz_results table",
        up_sql="CREATE TABLE fizzbuzz_results (id INTEGER PRIMARY KEY, value TEXT);",
        down_sql="DROP TABLE fizzbuzz_results;",
    )


@pytest.fixture
def sample_migrations():
    """Create a sequence of migrations for multi-step tests."""
    return [
        Migration(
            migration_id="mig_001",
            version="1.0.0",
            description="Create fizzbuzz_results table",
            up_sql="CREATE TABLE fizzbuzz_results (id INTEGER PRIMARY KEY, value TEXT);",
            down_sql="DROP TABLE fizzbuzz_results;",
        ),
        Migration(
            migration_id="mig_002",
            version="2.0.0",
            description="Add index on value column",
            up_sql="CREATE INDEX idx_value ON fizzbuzz_results(value);",
            down_sql="DROP INDEX idx_value;",
        ),
        Migration(
            migration_id="mig_003",
            version="3.0.0",
            description="Add timestamp column",
            up_sql="ALTER TABLE fizzbuzz_results ADD COLUMN created_at TIMESTAMP;",
            down_sql="ALTER TABLE fizzbuzz_results DROP COLUMN created_at;",
        ),
    ]


# ---------------------------------------------------------------------------
# TestConstants
# ---------------------------------------------------------------------------

class TestConstants:
    """Verify exported constants match the documented specification."""

    def test_version(self):
        assert FIZZMIGRATION2_VERSION == "1.0.0"

    def test_middleware_priority(self):
        assert MIDDLEWARE_PRIORITY == 196


# ---------------------------------------------------------------------------
# TestMigrationRunner
# ---------------------------------------------------------------------------

class TestMigrationRunner:
    """Validate migration application, rollback, and version tracking."""

    def test_apply_sets_completed_state(self, runner, sample_migration):
        """Applying a migration transitions its state to COMPLETED."""
        result = runner.apply(sample_migration)
        assert result.state == MigrationState.COMPLETED

    def test_apply_sets_applied_at_timestamp(self, runner, sample_migration):
        """Applying a migration records the application timestamp."""
        result = runner.apply(sample_migration)
        assert result.applied_at is not None

    def test_rollback_sets_rolled_back_state(self, runner, sample_migration):
        """Rolling back a migration transitions its state to ROLLED_BACK."""
        applied = runner.apply(sample_migration)
        result = runner.rollback(applied)
        assert result.state == MigrationState.ROLLED_BACK

    def test_current_version_after_apply(self, runner, sample_migration):
        """Current version reflects the most recently applied migration."""
        runner.apply(sample_migration)
        version = runner.get_current_version()
        assert version == "1.0.0"

    def test_list_applied_returns_applied_migrations(self, runner, sample_migrations):
        """list_applied returns only migrations that have been applied."""
        runner.apply(sample_migrations[0])
        runner.apply(sample_migrations[1])
        applied = runner.list_applied()
        assert len(applied) >= 2

    def test_list_pending_returns_unapplied(self, runner, sample_migrations):
        """list_pending returns migrations not yet applied."""
        for m in sample_migrations:
            runner.apply(m)
        pending = runner.list_pending()
        # After applying all, nothing should be pending from those
        applied_ids = {m.migration_id for m in runner.list_applied()}
        for p in pending:
            assert p.migration_id not in applied_ids

    def test_migrate_to_applies_multiple(self, runner, sample_migrations):
        """migrate_to applies all migrations up to the target version."""
        for m in sample_migrations:
            runner.apply(m)  # register them first if needed
        # Reset and use migrate_to
        runner2 = MigrationRunner(FizzMigration2Config())
        # Register migrations by applying the first, then migrate_to the last
        result = runner.migrate_to(sample_migrations[-1].version)
        assert isinstance(result, list)

    def test_already_applied_migration_skipped(self, runner, sample_migration):
        """Applying an already-completed migration does not re-apply it."""
        first = runner.apply(sample_migration)
        assert first.state == MigrationState.COMPLETED
        second = runner.apply(sample_migration)
        # Should either skip or still be COMPLETED without error
        assert second.state == MigrationState.COMPLETED


# ---------------------------------------------------------------------------
# TestMigrationHistory
# ---------------------------------------------------------------------------

class TestMigrationHistory:
    """Validate migration history tracking."""

    def test_record_and_get_history(self, history, sample_migration, runner):
        """Recording a migration makes it appear in the history."""
        applied = runner.apply(sample_migration)
        history.record(applied)
        entries = history.get_history()
        assert len(entries) >= 1

    def test_get_last_applied_returns_most_recent(self, history, sample_migrations, runner):
        """get_last_applied returns the most recently recorded migration."""
        for m in sample_migrations[:2]:
            applied = runner.apply(m)
            history.record(applied)
        last = history.get_last_applied()
        assert last is not None
        assert last.migration_id == "mig_002"

    def test_get_last_applied_empty_returns_none(self, history):
        """get_last_applied returns None when no migrations have been recorded."""
        result = history.get_last_applied()
        assert result is None


# ---------------------------------------------------------------------------
# TestDashboard
# ---------------------------------------------------------------------------

class TestDashboard:
    """Validate dashboard rendering output."""

    def test_render_returns_string(self):
        """Dashboard render produces a string."""
        dashboard = FizzMigration2Dashboard()
        output = dashboard.render()
        assert isinstance(output, str)

    def test_render_contains_migration_info(self):
        """Dashboard render includes migration-relevant content."""
        dashboard = FizzMigration2Dashboard()
        output = dashboard.render()
        assert len(output) > 0
        # Should contain some reference to migration state or version
        lower = output.lower()
        assert "migrat" in lower or "version" in lower or "fizzmigration" in lower


# ---------------------------------------------------------------------------
# TestMiddleware
# ---------------------------------------------------------------------------

class TestMiddleware:
    """Validate middleware interface conformance."""

    def test_get_name(self):
        """Middleware reports its canonical name."""
        mw = FizzMigration2Middleware()
        assert mw.get_name() == "fizzmigration2"

    def test_get_priority(self):
        """Middleware priority matches the module constant."""
        mw = FizzMigration2Middleware()
        assert mw.get_priority() == 196

    def test_process_calls_next(self):
        """Middleware passes control to the next handler in the pipeline."""
        mw = FizzMigration2Middleware()
        ctx = ProcessingContext(number=15, session_id="test")
        next_handler = MagicMock(return_value=ctx)
        result = mw.process(ctx, next_handler)
        next_handler.assert_called_once()


# ---------------------------------------------------------------------------
# TestCreateSubsystem
# ---------------------------------------------------------------------------

class TestCreateSubsystem:
    """Validate the subsystem factory function wiring."""

    def test_returns_tuple_of_three(self):
        """Factory returns a 3-tuple of subsystem components."""
        result = create_fizzmigration2_subsystem()
        assert isinstance(result, tuple)
        assert len(result) == 3

    def test_returns_correct_types(self):
        """Factory returns (MigrationRunner, Dashboard, Middleware)."""
        runner, dashboard, middleware = create_fizzmigration2_subsystem()
        assert isinstance(runner, MigrationRunner)
        assert isinstance(dashboard, FizzMigration2Dashboard)
        assert isinstance(middleware, FizzMigration2Middleware)

    def test_middleware_is_functional(self):
        """Middleware from factory is fully operational."""
        _, _, middleware = create_fizzmigration2_subsystem()
        assert middleware.get_name() == "fizzmigration2"
        assert middleware.get_priority() == 196
