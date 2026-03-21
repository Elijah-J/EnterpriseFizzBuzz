"""
Enterprise FizzBuzz Platform - Database Migration Framework Tests

Comprehensive tests for the migration framework that manages
in-memory data structures destined for garbage collection.
Because even ephemeral dicts deserve test coverage.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from exceptions import (
    MigrationAlreadyAppliedError,
    MigrationDependencyError,
    MigrationError,
    MigrationNotFoundError,
    MigrationRollbackError,
    SchemaError,
    SeedDataError,
)
from migrations import (
    M001InitialSchema,
    M002AddIsPrime,
    M003AddConfidence,
    M004AddBlockchainHash,
    M005SplitFizzBuzzTables,
    Migration,
    MigrationDashboard,
    MigrationRecord,
    MigrationRegistry,
    MigrationRunner,
    MigrationState,
    SchemaManager,
    SchemaVisualizer,
    SeedDataGenerator,
)


# ============================================================
# Fixtures
# ============================================================


@pytest.fixture(autouse=True)
def reset_registry():
    """Reset the MigrationRegistry singleton between tests."""
    MigrationRegistry.reset()
    yield
    MigrationRegistry.reset()


@pytest.fixture
def schema():
    """Create a fresh SchemaManager."""
    return SchemaManager(log_fake_sql=True)


@pytest.fixture
def registry():
    """Create and populate a fresh MigrationRegistry."""
    reg = MigrationRegistry.get_instance()
    reg.register(M001InitialSchema)
    reg.register(M002AddIsPrime)
    reg.register(M003AddConfidence)
    reg.register(M004AddBlockchainHash)
    reg.register(M005SplitFizzBuzzTables)
    return reg


@pytest.fixture
def runner(schema, registry):
    """Create a MigrationRunner with the standard registry."""
    return MigrationRunner(schema, registry)


# ============================================================
# SchemaManager Tests
# ============================================================


class TestSchemaManager:
    def test_create_table(self, schema):
        schema.create_table("test", {"id": "int", "name": "str"})
        assert schema.table_exists("test")
        assert schema.list_tables() == ["test"]

    def test_create_duplicate_table_raises(self, schema):
        schema.create_table("test", {"id": "int"})
        with pytest.raises(SchemaError):
            schema.create_table("test", {"id": "int"})

    def test_drop_table(self, schema):
        schema.create_table("test", {"id": "int"})
        schema.drop_table("test")
        assert not schema.table_exists("test")

    def test_drop_nonexistent_table_raises(self, schema):
        with pytest.raises(SchemaError):
            schema.drop_table("nonexistent")

    def test_add_column(self, schema):
        schema.create_table("test", {"id": "int"})
        schema.insert("test", {"id": 1})
        schema.add_column("test", "name", "str", default="unknown")
        table_schema = schema.get_table_schema("test")
        assert "name" in table_schema
        rows = schema.get_data("test")
        assert rows[0]["name"] == "unknown"

    def test_add_column_to_nonexistent_table_raises(self, schema):
        with pytest.raises(SchemaError):
            schema.add_column("ghost", "col", "str")

    def test_add_duplicate_column_raises(self, schema):
        schema.create_table("test", {"id": "int"})
        with pytest.raises(SchemaError):
            schema.add_column("test", "id", "int")

    def test_drop_column(self, schema):
        schema.create_table("test", {"id": "int", "name": "str"})
        schema.insert("test", {"id": 1, "name": "alice"})
        schema.drop_column("test", "name")
        table_schema = schema.get_table_schema("test")
        assert "name" not in table_schema
        rows = schema.get_data("test")
        assert "name" not in rows[0]

    def test_drop_nonexistent_column_raises(self, schema):
        schema.create_table("test", {"id": "int"})
        with pytest.raises(SchemaError):
            schema.drop_column("test", "ghost")

    def test_rename_column(self, schema):
        schema.create_table("test", {"id": "int", "old_name": "str"})
        schema.insert("test", {"id": 1, "old_name": "alice"})
        schema.rename_column("test", "old_name", "new_name")
        table_schema = schema.get_table_schema("test")
        assert "new_name" in table_schema
        assert "old_name" not in table_schema
        rows = schema.get_data("test")
        assert rows[0]["new_name"] == "alice"

    def test_rename_to_existing_column_raises(self, schema):
        schema.create_table("test", {"id": "int", "name": "str"})
        with pytest.raises(SchemaError):
            schema.rename_column("test", "id", "name")

    def test_insert_and_get_data(self, schema):
        schema.create_table("test", {"id": "int", "val": "str"})
        schema.insert("test", {"id": 1, "val": "hello"})
        schema.insert("test", {"id": 2, "val": "world"})
        data = schema.get_data("test")
        assert len(data) == 2
        assert data[0]["val"] == "hello"
        assert data[1]["val"] == "world"

    def test_insert_into_nonexistent_table_raises(self, schema):
        with pytest.raises(SchemaError):
            schema.insert("ghost", {"id": 1})

    def test_row_count(self, schema):
        schema.create_table("test", {"id": "int"})
        assert schema.row_count("test") == 0
        schema.insert("test", {"id": 1})
        schema.insert("test", {"id": 2})
        assert schema.row_count("test") == 2

    def test_row_count_nonexistent_returns_zero(self, schema):
        assert schema.row_count("ghost") == 0

    def test_sql_log(self, schema):
        schema.create_table("test", {"id": "int"})
        schema.insert("test", {"id": 1})
        assert len(schema.sql_log) >= 2
        assert "CREATE TABLE" in schema.sql_log[0]
        assert "INSERT INTO" in schema.sql_log[1]

    def test_sql_log_disabled(self):
        schema = SchemaManager(log_fake_sql=False)
        schema.create_table("test", {"id": "int"})
        assert len(schema.sql_log) == 0

    def test_get_table_schema(self, schema):
        schema.create_table("test", {"id": "int", "name": "str"})
        ts = schema.get_table_schema("test")
        assert ts == {"id": "int", "name": "str"}


# ============================================================
# MigrationRegistry Tests
# ============================================================


class TestMigrationRegistry:
    def test_register_and_get(self, registry):
        cls = registry.get("m001_initial_schema")
        assert cls is M001InitialSchema

    def test_get_nonexistent_raises(self, registry):
        with pytest.raises(MigrationNotFoundError):
            registry.get("m999_does_not_exist")

    def test_get_all_sorted(self, registry):
        all_migrations = registry.get_all()
        ids = [m.migration_id for m in all_migrations]
        assert ids == sorted(ids)

    def test_get_ids(self, registry):
        ids = registry.get_ids()
        assert "m001_initial_schema" in ids
        assert "m005_split_fizz_buzz_tables" in ids

    def test_singleton(self):
        reg1 = MigrationRegistry.get_instance()
        reg2 = MigrationRegistry.get_instance()
        assert reg1 is reg2

    def test_reset(self):
        reg1 = MigrationRegistry.get_instance()
        MigrationRegistry.reset()
        reg2 = MigrationRegistry.get_instance()
        assert reg1 is not reg2


# ============================================================
# MigrationRunner Tests
# ============================================================


class TestMigrationRunner:
    def test_apply_single(self, runner):
        record = runner.apply("m001_initial_schema")
        assert record.state == MigrationState.APPLIED
        assert record.applied_at is not None
        assert record.duration_ms >= 0
        assert runner.schema.table_exists("fizzbuzz_results")

    def test_apply_all(self, runner):
        records = runner.apply_all()
        assert len(records) == 5
        for r in records:
            assert r.state == MigrationState.APPLIED

    def test_apply_already_applied_raises(self, runner):
        runner.apply("m001_initial_schema")
        with pytest.raises(MigrationAlreadyAppliedError):
            runner.apply("m001_initial_schema")

    def test_apply_with_missing_dependency_raises(self, runner):
        with pytest.raises(MigrationDependencyError):
            runner.apply("m002_add_is_prime")

    def test_get_pending(self, runner):
        pending = runner.get_pending()
        assert len(pending) == 5
        runner.apply("m001_initial_schema")
        pending = runner.get_pending()
        assert len(pending) == 4
        assert "m001_initial_schema" not in pending

    def test_get_status(self, runner):
        runner.apply("m001_initial_schema")
        status = runner.get_status()
        assert len(status) == 5
        applied = [s for s in status if s.state == MigrationState.APPLIED]
        assert len(applied) == 1

    def test_rollback(self, runner):
        runner.apply("m001_initial_schema")
        assert runner.schema.table_exists("fizzbuzz_results")
        rolled = runner.rollback(1)
        assert len(rolled) == 1
        assert rolled[0].state == MigrationState.ROLLED_BACK
        assert not runner.schema.table_exists("fizzbuzz_results")

    def test_rollback_multiple(self, runner):
        runner.apply_all()
        rolled = runner.rollback(3)
        assert len(rolled) == 3

    def test_rollback_more_than_applied(self, runner):
        runner.apply("m001_initial_schema")
        rolled = runner.rollback(100)
        assert len(rolled) == 1

    def test_rollback_nothing(self, runner):
        rolled = runner.rollback(1)
        assert len(rolled) == 0

    def test_checksum(self, runner):
        record = runner.apply("m001_initial_schema")
        assert len(record.checksum) == 16


# ============================================================
# Pre-built Migration Tests
# ============================================================


class TestPrebuiltMigrations:
    def test_m001_creates_table(self, runner):
        runner.apply("m001_initial_schema")
        assert runner.schema.table_exists("fizzbuzz_results")
        schema = runner.schema.get_table_schema("fizzbuzz_results")
        assert "number" in schema
        assert "output" in schema
        assert "is_fizz" in schema
        assert "is_buzz" in schema

    def test_m002_adds_is_prime(self, runner):
        runner.apply("m001_initial_schema")
        # Insert some data first
        runner.schema.insert("fizzbuzz_results", {
            "number": 7, "output": "7", "is_fizz": False,
            "is_buzz": False, "is_fizzbuzz": False, "is_plain": True,
            "rules_matched": 0,
        })
        runner.apply("m002_add_is_prime")
        schema = runner.schema.get_table_schema("fizzbuzz_results")
        assert "is_prime" in schema
        rows = runner.schema.get_data("fizzbuzz_results")
        assert rows[0]["is_prime"] is True  # 7 is prime

    def test_m003_adds_confidence(self, runner):
        runner.apply("m001_initial_schema")
        runner.apply("m003_add_confidence")
        schema = runner.schema.get_table_schema("fizzbuzz_results")
        assert "ml_confidence" in schema

    def test_m004_adds_blockchain_hash(self, runner):
        runner.apply("m001_initial_schema")
        runner.schema.insert("fizzbuzz_results", {
            "number": 3, "output": "Fizz", "is_fizz": True,
            "is_buzz": False, "is_fizzbuzz": False, "is_plain": False,
            "rules_matched": 1,
        })
        runner.apply("m004_add_blockchain_hash")
        schema = runner.schema.get_table_schema("fizzbuzz_results")
        assert "blockchain_hash" in schema
        rows = runner.schema.get_data("fizzbuzz_results")
        assert len(rows[0]["blockchain_hash"]) > 0

    def test_m005_splits_tables(self, runner):
        runner.apply("m001_initial_schema")
        # Insert Fizz and Buzz results
        runner.schema.insert("fizzbuzz_results", {
            "number": 3, "output": "Fizz", "is_fizz": True,
            "is_buzz": False, "is_fizzbuzz": False, "is_plain": False,
            "rules_matched": 1,
        })
        runner.schema.insert("fizzbuzz_results", {
            "number": 5, "output": "Buzz", "is_fizz": False,
            "is_buzz": True, "is_fizzbuzz": False, "is_plain": False,
            "rules_matched": 1,
        })
        runner.schema.insert("fizzbuzz_results", {
            "number": 15, "output": "FizzBuzz", "is_fizz": True,
            "is_buzz": True, "is_fizzbuzz": True, "is_plain": False,
            "rules_matched": 2,
        })
        runner.apply("m005_split_fizz_buzz_tables")
        assert runner.schema.table_exists("fizz_results")
        assert runner.schema.table_exists("buzz_results")
        # 15 is both fizz and buzz, so 2 fizz rows, 2 buzz rows
        fizz_data = runner.schema.get_data("fizz_results")
        buzz_data = runner.schema.get_data("buzz_results")
        assert len(fizz_data) == 2  # 3 and 15
        assert len(buzz_data) == 2  # 5 and 15

    def test_m005_rollback_drops_tables(self, runner):
        runner.apply("m001_initial_schema")
        runner.apply("m005_split_fizz_buzz_tables")
        runner.rollback(1)  # Rolls back m005
        assert not runner.schema.table_exists("fizz_results")
        assert not runner.schema.table_exists("buzz_results")

    def test_all_migrations_apply_and_rollback(self, runner):
        """Apply all migrations, then roll them all back."""
        runner.apply_all()
        assert runner.schema.table_exists("fizzbuzz_results")
        assert runner.schema.table_exists("fizz_results")
        assert runner.schema.table_exists("buzz_results")

        # Roll back all 5
        runner.rollback(5)
        assert not runner.schema.table_exists("fizzbuzz_results")
        assert not runner.schema.table_exists("fizz_results")
        assert not runner.schema.table_exists("buzz_results")


# ============================================================
# SeedDataGenerator Tests
# ============================================================


class TestSeedDataGenerator:
    def test_generate_seed_data(self, runner):
        runner.apply("m001_initial_schema")
        seeder = SeedDataGenerator(runner.schema)
        count = seeder.generate(1, 15)
        assert count == 15
        data = runner.schema.get_data("fizzbuzz_results")
        assert len(data) == 15

        # Verify correctness — FizzBuzz evaluating itself
        outputs = {row["number"]: row["output"] for row in data}
        assert outputs[1] == "1"
        assert outputs[3] == "Fizz"
        assert outputs[5] == "Buzz"
        assert outputs[15] == "FizzBuzz"

    def test_generate_without_table_raises(self, schema):
        seeder = SeedDataGenerator(schema)
        with pytest.raises(SeedDataError):
            seeder.generate(1, 10)

    def test_seed_with_extra_columns(self, runner):
        """Verify seed data populates optional columns when they exist."""
        runner.apply("m001_initial_schema")
        runner.apply("m002_add_is_prime")
        runner.apply("m003_add_confidence")
        runner.apply("m004_add_blockchain_hash")

        seeder = SeedDataGenerator(runner.schema)
        seeder.generate(1, 10)

        data = runner.schema.get_data("fizzbuzz_results")
        # Check a prime number
        row_7 = [r for r in data if r["number"] == 7][0]
        assert row_7["is_prime"] is True
        assert row_7["ml_confidence"] == 1.0
        assert len(row_7["blockchain_hash"]) > 0


# ============================================================
# SchemaVisualizer Tests
# ============================================================


class TestSchemaVisualizer:
    def test_render_empty_schema(self, schema):
        output = SchemaVisualizer.render(schema)
        assert "empty" in output.lower()

    def test_render_with_tables(self, runner):
        runner.apply("m001_initial_schema")
        output = SchemaVisualizer.render(runner.schema)
        assert "fizzbuzz_results" in output
        assert "ER DIAGRAM" in output
        assert "number" in output
        assert "RAM" in output

    def test_render_multiple_tables(self, runner):
        runner.apply_all()
        output = SchemaVisualizer.render(runner.schema)
        assert "fizzbuzz_results" in output
        assert "fizz_results" in output
        assert "buzz_results" in output


# ============================================================
# MigrationDashboard Tests
# ============================================================


class TestMigrationDashboard:
    def test_render_empty(self, schema):
        reg = MigrationRegistry.get_instance()
        runner = MigrationRunner(schema, reg)
        output = MigrationDashboard.render(runner)
        assert "DASHBOARD" in output

    def test_render_with_applied(self, runner):
        runner.apply("m001_initial_schema")
        output = MigrationDashboard.render(runner)
        assert "m001_initial_schema" in output
        assert "[+]" in output  # Applied symbol
        assert "Applied: 1" in output

    def test_render_shows_pending(self, runner):
        output = MigrationDashboard.render(runner)
        assert "Pending: 5" in output
        assert "[ ]" in output  # Pending symbol

    def test_render_after_rollback(self, runner):
        runner.apply("m001_initial_schema")
        runner.rollback(1)
        output = MigrationDashboard.render(runner)
        assert "[-]" in output  # Rolled back symbol


# ============================================================
# MigrationRecord Tests
# ============================================================


class TestMigrationRecord:
    def test_default_state(self):
        record = MigrationRecord(
            migration_id="test_001",
            name="Test Migration",
        )
        assert record.state == MigrationState.PENDING
        assert record.applied_at is None
        assert record.duration_ms == 0.0

    def test_state_values(self):
        """Verify all MigrationState enum values exist."""
        assert MigrationState.PENDING
        assert MigrationState.APPLYING
        assert MigrationState.APPLIED
        assert MigrationState.ROLLING_BACK
        assert MigrationState.ROLLED_BACK
        assert MigrationState.FAILED


# ============================================================
# Migration ABC Tests
# ============================================================


class TestMigrationABC:
    def test_checksum_is_deterministic(self):
        m = M001InitialSchema()
        c1 = m.get_checksum()
        c2 = m.get_checksum()
        assert c1 == c2
        assert len(c1) == 16

    def test_different_migrations_different_checksums(self):
        m1 = M001InitialSchema()
        m2 = M002AddIsPrime()
        assert m1.get_checksum() != m2.get_checksum()
