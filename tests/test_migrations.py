"""
Enterprise FizzBuzz Platform - Database Migration Framework Tests

Comprehensive tests for the migration framework that manages
in-memory data structures destined for garbage collection, plus
the FizzSchema consensus-based schema evolution subsystem.

Validates schema field types, versioned schema definitions, SHA-256
fingerprinting, compatibility checking (BACKWARD/FORWARD/FULL/NONE),
schema registry, migration planning, Paxos consensus approval,
dashboard rendering, and middleware integration.

Because even ephemeral dicts deserve test coverage.
"""

from __future__ import annotations

import hashlib
import json
import sys
import threading
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from exceptions import (
    MigrationAlreadyAppliedError,
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
from migrations import (
    CompatibilityChecker,
    CompatibilityMode,
    CompatibilityResult,
    ConsensusApprover,
    ConsensusNode,
    ConsensusNodeState,
    ConsensusRound,
    FieldMigration,
    M001InitialSchema,
    M002AddIsPrime,
    M003AddConfidence,
    M004AddBlockchainHash,
    M005SplitFizzBuzzTables,
    Migration,
    MigrationDashboard,
    MigrationPlan,
    MigrationPlanner,
    MigrationRecord,
    MigrationRegistry,
    MigrationRunner,
    MigrationState,
    PaxosPhase,
    Schema,
    SchemaDashboard,
    SchemaField,
    SchemaFieldType,
    SchemaManager,
    SchemaMiddleware,
    SchemaRegistry,
    SchemaVisualizer,
    SeedDataGenerator,
    bootstrap_registry,
    build_evaluation_result_lineage,
)
from enterprise_fizzbuzz.infrastructure.config import _SingletonMeta


# ============================================================
# Fixtures
# ============================================================


@pytest.fixture(autouse=True)
def reset_registry():
    """Reset the MigrationRegistry singleton and other singletons between tests."""
    MigrationRegistry.reset()
    _SingletonMeta.reset()
    yield
    MigrationRegistry.reset()
    _SingletonMeta.reset()


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


# ============================================================
# SchemaFieldType Tests
# ============================================================


class TestSchemaFieldType:
    """Tests for the SchemaFieldType enum."""

    def test_all_types_defined(self):
        assert len(SchemaFieldType) == 6

    def test_int64_value(self):
        assert SchemaFieldType.INT64.value == "int64"

    def test_float64_value(self):
        assert SchemaFieldType.FLOAT64.value == "float64"

    def test_string_value(self):
        assert SchemaFieldType.STRING.value == "string"

    def test_bool_value(self):
        assert SchemaFieldType.BOOL.value == "bool"

    def test_enum_value(self):
        assert SchemaFieldType.ENUM.value == "enum"

    def test_array_value(self):
        assert SchemaFieldType.ARRAY.value == "array"


# ============================================================
# SchemaField Tests
# ============================================================


class TestSchemaField:
    """Tests for the SchemaField dataclass."""

    def test_basic_field(self):
        f = SchemaField("number", SchemaFieldType.INT64, tag=1)
        assert f.name == "number"
        assert f.field_type == SchemaFieldType.INT64
        assert f.tag == 1
        assert f.default is None
        assert f.deprecated is False

    def test_field_with_default(self):
        f = SchemaField("strategy", SchemaFieldType.STRING, tag=3, default="standard")
        assert f.has_default() is True
        assert f.default == "standard"

    def test_field_without_default(self):
        f = SchemaField("number", SchemaFieldType.INT64, tag=1)
        assert f.has_default() is False

    def test_deprecated_field(self):
        f = SchemaField("old_field", SchemaFieldType.STRING, tag=99, deprecated=True)
        assert f.deprecated is True

    def test_to_dict(self):
        f = SchemaField("result", SchemaFieldType.STRING, tag=2, default="", doc="The result")
        d = f.to_dict()
        assert d["name"] == "result"
        assert d["type"] == "string"
        assert d["tag"] == 2
        assert d["default"] == ""
        assert d["deprecated"] is False
        assert d["doc"] == "The result"


# ============================================================
# Schema Tests
# ============================================================


class TestSchema:
    """Tests for the Schema dataclass and fingerprinting."""

    def _make_schema(self, version: int = 1) -> Schema:
        return Schema(
            name="TestSchema",
            version=version,
            fields=[
                SchemaField("number", SchemaFieldType.INT64, tag=1),
                SchemaField("result", SchemaFieldType.STRING, tag=2),
            ],
        )

    def test_basic_schema(self):
        s = self._make_schema()
        assert s.name == "TestSchema"
        assert s.version == 1
        assert len(s.fields) == 2

    def test_fingerprint_is_sha256(self):
        s = self._make_schema()
        assert len(s.fingerprint) == 64  # hex digest length
        # Verify it's a valid hex string
        int(s.fingerprint, 16)

    def test_fingerprint_deterministic(self):
        s1 = self._make_schema()
        s2 = self._make_schema()
        assert s1.fingerprint == s2.fingerprint

    def test_fingerprint_changes_with_fields(self):
        s1 = self._make_schema()
        s2 = Schema(
            name="TestSchema",
            version=1,
            fields=[
                SchemaField("number", SchemaFieldType.INT64, tag=1),
                SchemaField("result", SchemaFieldType.STRING, tag=2),
                SchemaField("extra", SchemaFieldType.BOOL, tag=3),
            ],
        )
        assert s1.fingerprint != s2.fingerprint

    def test_fingerprint_order_independent(self):
        """Fields declared in different order produce the same fingerprint."""
        s1 = Schema(
            name="Test", version=1,
            fields=[
                SchemaField("a", SchemaFieldType.INT64, tag=1),
                SchemaField("b", SchemaFieldType.STRING, tag=2),
            ],
        )
        s2 = Schema(
            name="Test", version=1,
            fields=[
                SchemaField("b", SchemaFieldType.STRING, tag=2),
                SchemaField("a", SchemaFieldType.INT64, tag=1),
            ],
        )
        assert s1.fingerprint == s2.fingerprint

    def test_fingerprint_manual_computation(self):
        """Verify fingerprint matches manual SHA-256 of sorted tuples."""
        s = self._make_schema()
        canonical = sorted([("number", 1, "int64"), ("result", 2, "string")])
        raw = json.dumps(canonical, sort_keys=True).encode("utf-8")
        expected = hashlib.sha256(raw).hexdigest()
        assert s.fingerprint == expected

    def test_field_names(self):
        s = self._make_schema()
        assert s.field_names == {"number", "result"}

    def test_field_by_name(self):
        s = self._make_schema()
        assert "number" in s.field_by_name
        assert s.field_by_name["number"].tag == 1

    def test_field_by_tag(self):
        s = self._make_schema()
        assert 1 in s.field_by_tag
        assert s.field_by_tag[1].name == "number"

    def test_to_dict(self):
        s = self._make_schema()
        d = s.to_dict()
        assert d["name"] == "TestSchema"
        assert d["version"] == 1
        assert d["field_count"] == 2
        assert "fingerprint" in d
        assert len(d["fields"]) == 2


# ============================================================
# CompatibilityMode Tests
# ============================================================


class TestCompatibilityMode:
    """Tests for the CompatibilityMode enum."""

    def test_all_modes(self):
        assert len(CompatibilityMode) == 4

    def test_mode_values(self):
        assert CompatibilityMode.BACKWARD.value == "BACKWARD"
        assert CompatibilityMode.FORWARD.value == "FORWARD"
        assert CompatibilityMode.FULL.value == "FULL"
        assert CompatibilityMode.NONE.value == "NONE"


# ============================================================
# CompatibilityChecker Tests
# ============================================================


class TestCompatibilityChecker:
    """Tests for the CompatibilityChecker."""

    def setup_method(self):
        self.checker = CompatibilityChecker()
        self.v1 = Schema("Test", 1, [
            SchemaField("number", SchemaFieldType.INT64, tag=1),
            SchemaField("result", SchemaFieldType.STRING, tag=2),
        ])

    def test_identical_schemas_compatible(self):
        result = self.checker.check(self.v1, self.v1, CompatibilityMode.FULL)
        assert result.compatible is True
        assert len(result.violations) == 0

    def test_none_mode_always_compatible(self):
        v2 = Schema("Test", 2, [])  # Completely different
        result = self.checker.check(self.v1, v2, CompatibilityMode.NONE)
        assert result.compatible is True

    def test_backward_new_field_with_default(self):
        v2 = Schema("Test", 2, [
            SchemaField("number", SchemaFieldType.INT64, tag=1),
            SchemaField("result", SchemaFieldType.STRING, tag=2),
            SchemaField("strategy", SchemaFieldType.STRING, tag=3, default="standard"),
        ])
        result = self.checker.check(self.v1, v2, CompatibilityMode.BACKWARD)
        assert result.compatible is True

    def test_backward_new_field_without_default_fails(self):
        v2 = Schema("Test", 2, [
            SchemaField("number", SchemaFieldType.INT64, tag=1),
            SchemaField("result", SchemaFieldType.STRING, tag=2),
            SchemaField("strategy", SchemaFieldType.STRING, tag=3),  # No default
        ])
        result = self.checker.check(self.v1, v2, CompatibilityMode.BACKWARD)
        assert result.compatible is False
        assert any("BACKWARD violation" in v for v in result.violations)

    def test_backward_remove_optional_field(self):
        """Removing a field that had a default is BACKWARD-compatible."""
        v1 = Schema("Test", 1, [
            SchemaField("number", SchemaFieldType.INT64, tag=1),
            SchemaField("optional", SchemaFieldType.STRING, tag=2, default=""),
        ])
        v2 = Schema("Test", 2, [
            SchemaField("number", SchemaFieldType.INT64, tag=1),
        ])
        result = self.checker.check(v1, v2, CompatibilityMode.BACKWARD)
        assert result.compatible is True

    def test_backward_remove_required_field_fails(self):
        v2 = Schema("Test", 2, [
            SchemaField("number", SchemaFieldType.INT64, tag=1),
        ])
        result = self.checker.check(self.v1, v2, CompatibilityMode.BACKWARD)
        assert result.compatible is False

    def test_forward_remove_with_default(self):
        v1 = Schema("Test", 1, [
            SchemaField("number", SchemaFieldType.INT64, tag=1),
            SchemaField("extra", SchemaFieldType.STRING, tag=2, default="x"),
        ])
        v2 = Schema("Test", 2, [
            SchemaField("number", SchemaFieldType.INT64, tag=1),
        ])
        result = self.checker.check(v1, v2, CompatibilityMode.FORWARD)
        assert result.compatible is True

    def test_forward_remove_without_default_fails(self):
        v2 = Schema("Test", 2, [
            SchemaField("number", SchemaFieldType.INT64, tag=1),
        ])
        result = self.checker.check(self.v1, v2, CompatibilityMode.FORWARD)
        assert result.compatible is False
        assert any("FORWARD violation" in v for v in result.violations)

    def test_full_mode_checks_both(self):
        """FULL mode requires both BACKWARD and FORWARD compatibility."""
        v2 = Schema("Test", 2, [
            SchemaField("number", SchemaFieldType.INT64, tag=1),
            SchemaField("result", SchemaFieldType.STRING, tag=2),
            SchemaField("new_field", SchemaFieldType.STRING, tag=3),  # No default
        ])
        result = self.checker.check(self.v1, v2, CompatibilityMode.FULL)
        assert result.compatible is False

    def test_safe_type_promotion_int_to_float(self):
        v2 = Schema("Test", 2, [
            SchemaField("number", SchemaFieldType.FLOAT64, tag=1),  # INT64->FLOAT64
            SchemaField("result", SchemaFieldType.STRING, tag=2),
        ])
        result = self.checker.check(self.v1, v2, CompatibilityMode.BACKWARD)
        assert result.compatible is True
        assert any("type promotion" in w for w in result.warnings)

    def test_safe_type_promotion_int_to_string(self):
        v2 = Schema("Test", 2, [
            SchemaField("number", SchemaFieldType.STRING, tag=1),  # INT64->STRING
            SchemaField("result", SchemaFieldType.STRING, tag=2),
        ])
        result = self.checker.check(self.v1, v2, CompatibilityMode.BACKWARD)
        assert result.compatible is True

    def test_unsafe_type_change_fails(self):
        v2 = Schema("Test", 2, [
            SchemaField("number", SchemaFieldType.BOOL, tag=1),  # INT64->BOOL: not safe
            SchemaField("result", SchemaFieldType.STRING, tag=2),
        ])
        result = self.checker.check(self.v1, v2, CompatibilityMode.BACKWARD)
        assert result.compatible is False
        assert any("incompatible type change" in v for v in result.violations)

    def test_tag_reassignment_fails(self):
        v2 = Schema("Test", 2, [
            SchemaField("number", SchemaFieldType.INT64, tag=99),  # Changed tag
            SchemaField("result", SchemaFieldType.STRING, tag=2),
        ])
        result = self.checker.check(self.v1, v2, CompatibilityMode.BACKWARD)
        assert result.compatible is False
        assert any("tag number changed" in v for v in result.violations)

    def test_deprecation_warning(self):
        v2 = Schema("Test", 2, [
            SchemaField("number", SchemaFieldType.INT64, tag=1, deprecated=True),
            SchemaField("result", SchemaFieldType.STRING, tag=2),
        ])
        result = self.checker.check(self.v1, v2, CompatibilityMode.BACKWARD)
        assert result.compatible is True
        assert any("deprecated" in w for w in result.warnings)

    def test_bool_to_string_promotion(self):
        v1 = Schema("Test", 1, [SchemaField("flag", SchemaFieldType.BOOL, tag=1)])
        v2 = Schema("Test", 2, [SchemaField("flag", SchemaFieldType.STRING, tag=1)])
        result = self.checker.check(v1, v2, CompatibilityMode.BACKWARD)
        assert result.compatible is True

    def test_bool_to_int_promotion(self):
        v1 = Schema("Test", 1, [SchemaField("flag", SchemaFieldType.BOOL, tag=1)])
        v2 = Schema("Test", 2, [SchemaField("flag", SchemaFieldType.INT64, tag=1)])
        result = self.checker.check(v1, v2, CompatibilityMode.BACKWARD)
        assert result.compatible is True


# ============================================================
# SchemaRegistry Tests
# ============================================================


class TestSchemaRegistry:
    """Tests for the SchemaRegistry."""

    def setup_method(self):
        self.registry = SchemaRegistry(default_mode=CompatibilityMode.BACKWARD)
        self.v1 = Schema("Test", 1, [
            SchemaField("number", SchemaFieldType.INT64, tag=1),
            SchemaField("result", SchemaFieldType.STRING, tag=2),
        ])

    def test_register_first_version(self):
        result = self.registry.register(self.v1)
        assert result.compatible is True

    def test_get_by_name_and_version(self):
        self.registry.register(self.v1)
        s = self.registry.get("Test", 1)
        assert s is not None
        assert s.version == 1

    def test_get_latest_version(self):
        self.registry.register(self.v1)
        v2 = Schema("Test", 2, [
            SchemaField("number", SchemaFieldType.INT64, tag=1),
            SchemaField("result", SchemaFieldType.STRING, tag=2),
            SchemaField("strategy", SchemaFieldType.STRING, tag=3, default="standard"),
        ])
        self.registry.register(v2)
        s = self.registry.get("Test")
        assert s is not None
        assert s.version == 2

    def test_get_nonexistent_returns_none(self):
        assert self.registry.get("Nonexistent") is None

    def test_get_by_fingerprint(self):
        self.registry.register(self.v1)
        s = self.registry.get_by_fingerprint(self.v1.fingerprint)
        assert s is not None
        assert s.name == "Test"

    def test_get_versions(self):
        self.registry.register(self.v1)
        v2 = Schema("Test", 2, [
            SchemaField("number", SchemaFieldType.INT64, tag=1),
            SchemaField("result", SchemaFieldType.STRING, tag=2),
            SchemaField("extra", SchemaFieldType.STRING, tag=3, default="x"),
        ])
        self.registry.register(v2)
        assert self.registry.get_versions("Test") == [1, 2]

    def test_incompatible_registration_fails(self):
        self.registry.register(self.v1)
        v2 = Schema("Test", 2, [
            SchemaField("number", SchemaFieldType.INT64, tag=1),
            SchemaField("result", SchemaFieldType.STRING, tag=2),
            SchemaField("bad_field", SchemaFieldType.STRING, tag=3),  # No default
        ])
        with pytest.raises(SchemaRegistrationError):
            self.registry.register(v2)

    def test_force_registration_bypasses_check(self):
        self.registry.register(self.v1)
        v2 = Schema("Test", 2, [
            SchemaField("number", SchemaFieldType.INT64, tag=1),
            SchemaField("result", SchemaFieldType.STRING, tag=2),
            SchemaField("bad_field", SchemaFieldType.STRING, tag=3),  # No default
        ])
        result = self.registry.register(v2, force=True)
        assert result.compatible is False
        # But it was registered anyway
        assert self.registry.get("Test", 2) is not None

    def test_idempotent_registration(self):
        self.registry.register(self.v1)
        result = self.registry.register(self.v1)
        assert result.compatible is True

    def test_version_conflict_different_fingerprint(self):
        self.registry.register(self.v1)
        different_v1 = Schema("Test", 1, [
            SchemaField("different", SchemaFieldType.BOOL, tag=99),
        ])
        with pytest.raises(SchemaRegistrationError):
            self.registry.register(different_v1)

    def test_schema_names(self):
        self.registry.register(self.v1)
        other = Schema("Other", 1, [SchemaField("x", SchemaFieldType.INT64, tag=1)])
        self.registry.register(other)
        assert sorted(self.registry.schema_names) == ["Other", "Test"]

    def test_compatibility_mode_per_schema(self):
        self.registry.set_compatibility_mode("Test", CompatibilityMode.NONE)
        assert self.registry.get_compatibility_mode("Test") == CompatibilityMode.NONE

    def test_compatibility_mode_default(self):
        assert self.registry.get_compatibility_mode("Unknown") == CompatibilityMode.BACKWARD

    def test_history_recorded(self):
        self.registry.register(self.v1)
        v2 = Schema("Test", 2, [
            SchemaField("number", SchemaFieldType.INT64, tag=1),
            SchemaField("result", SchemaFieldType.STRING, tag=2),
            SchemaField("extra", SchemaFieldType.STRING, tag=3, default="x"),
        ])
        self.registry.register(v2)
        history = self.registry.history
        assert len(history) == 1
        assert history[0]["from_version"] == 1
        assert history[0]["to_version"] == 2
        assert history[0]["compatible"] is True

    def test_get_all_schemas(self):
        self.registry.register(self.v1)
        v2 = Schema("Test", 2, [
            SchemaField("number", SchemaFieldType.INT64, tag=1),
            SchemaField("result", SchemaFieldType.STRING, tag=2),
            SchemaField("extra", SchemaFieldType.STRING, tag=3, default="x"),
        ])
        self.registry.register(v2)
        all_schemas = self.registry.get_all_schemas()
        assert len(all_schemas) == 2
        assert all_schemas[0].version == 1
        assert all_schemas[1].version == 2


# ============================================================
# SchemaMigrationPlanner Tests
# ============================================================


class TestSchemaMigrationPlanner:
    """Tests for the MigrationPlanner (schema field-level planning)."""

    def setup_method(self):
        self.planner = MigrationPlanner()
        self.v1 = Schema("Test", 1, [
            SchemaField("number", SchemaFieldType.INT64, tag=1),
            SchemaField("result", SchemaFieldType.STRING, tag=2),
        ])

    def test_plan_field_addition(self):
        v2 = Schema("Test", 2, [
            SchemaField("number", SchemaFieldType.INT64, tag=1),
            SchemaField("result", SchemaFieldType.STRING, tag=2),
            SchemaField("strategy", SchemaFieldType.STRING, tag=3, default="standard"),
        ])
        plan = self.planner.plan(self.v1, v2)
        assert plan.schema_name == "Test"
        assert plan.from_version == 1
        assert plan.to_version == 2
        assert len(plan.actions) == 1
        assert plan.actions[0].action == "ADD"
        assert plan.actions[0].field_name == "strategy"

    def test_plan_field_removal(self):
        v2 = Schema("Test", 2, [
            SchemaField("number", SchemaFieldType.INT64, tag=1),
        ])
        plan = self.planner.plan(self.v1, v2)
        assert any(a.action == "REMOVE" for a in plan.actions)
        assert plan.has_breaking_changes is True

    def test_plan_type_promotion(self):
        v2 = Schema("Test", 2, [
            SchemaField("number", SchemaFieldType.FLOAT64, tag=1),
            SchemaField("result", SchemaFieldType.STRING, tag=2),
        ])
        plan = self.planner.plan(self.v1, v2)
        assert any(a.action == "PROMOTE" for a in plan.actions)

    def test_plan_deprecation(self):
        v2 = Schema("Test", 2, [
            SchemaField("number", SchemaFieldType.INT64, tag=1, deprecated=True),
            SchemaField("result", SchemaFieldType.STRING, tag=2),
        ])
        plan = self.planner.plan(self.v1, v2)
        assert any(a.action == "DEPRECATE" for a in plan.actions)

    def test_plan_no_changes(self):
        plan = self.planner.plan(self.v1, self.v1)
        assert len(plan.actions) == 0
        assert plan.has_breaking_changes is False

    def test_plan_summary(self):
        v2 = Schema("Test", 2, [
            SchemaField("number", SchemaFieldType.INT64, tag=1),
            SchemaField("result", SchemaFieldType.STRING, tag=2),
            SchemaField("strategy", SchemaFieldType.STRING, tag=3, default="standard"),
            SchemaField("latency", SchemaFieldType.INT64, tag=4, default=0),
        ])
        plan = self.planner.plan(self.v1, v2)
        assert "2 add(s)" in plan.summary

    def test_plan_default_value_captured(self):
        v2 = Schema("Test", 2, [
            SchemaField("number", SchemaFieldType.INT64, tag=1),
            SchemaField("result", SchemaFieldType.STRING, tag=2),
            SchemaField("cached", SchemaFieldType.BOOL, tag=3, default=False),
        ])
        plan = self.planner.plan(self.v1, v2)
        add_action = [a for a in plan.actions if a.action == "ADD"][0]
        assert add_action.default_value is False


# ============================================================
# ConsensusApprover Tests
# ============================================================


class TestConsensusApprover:
    """Tests for the Paxos-based ConsensusApprover."""

    def setup_method(self):
        self.approver = ConsensusApprover(num_nodes=5, quorum=3)
        self.v1 = Schema("Test", 1, [
            SchemaField("number", SchemaFieldType.INT64, tag=1),
            SchemaField("result", SchemaFieldType.STRING, tag=2),
        ])
        self.v2 = Schema("Test", 2, [
            SchemaField("number", SchemaFieldType.INT64, tag=1),
            SchemaField("result", SchemaFieldType.STRING, tag=2),
            SchemaField("strategy", SchemaFieldType.STRING, tag=3, default="standard"),
        ])

    def test_approve_compatible_change(self):
        r = self.approver.approve(self.v1, self.v2, CompatibilityMode.BACKWARD)
        assert r.approved is True
        assert r.approvals >= 3

    def test_approve_first_version(self):
        r = self.approver.approve(None, self.v1, CompatibilityMode.BACKWARD)
        assert r.approved is True

    def test_reject_incompatible_change(self):
        bad_v2 = Schema("Test", 2, [
            SchemaField("number", SchemaFieldType.INT64, tag=1),
            SchemaField("result", SchemaFieldType.STRING, tag=2),
            SchemaField("bad", SchemaFieldType.STRING, tag=3),  # No default
        ])
        with pytest.raises(SchemaConsensusError):
            self.approver.approve(self.v1, bad_v2, CompatibilityMode.BACKWARD)

    def test_approve_with_node_failure(self):
        """Should succeed with 1 failed node (4 healthy >= quorum 3)."""
        self.approver.inject_failure(0)
        r = self.approver.approve(self.v1, self.v2, CompatibilityMode.BACKWARD)
        assert r.approved is True
        assert r.failures == 1

    def test_approve_with_two_node_failures(self):
        """Should succeed with 2 failed nodes (3 healthy == quorum 3)."""
        self.approver.inject_failure(0)
        self.approver.inject_failure(1)
        r = self.approver.approve(self.v1, self.v2, CompatibilityMode.BACKWARD)
        assert r.approved is True
        assert r.failures == 2

    def test_reject_with_three_node_failures(self):
        """Should fail with 3 failed nodes (2 healthy < quorum 3)."""
        self.approver.inject_failure(0)
        self.approver.inject_failure(1)
        self.approver.inject_failure(2)
        with pytest.raises(SchemaConsensusError):
            self.approver.approve(self.v1, self.v2, CompatibilityMode.BACKWARD)

    def test_recover_node(self):
        self.approver.inject_failure(0)
        self.approver.recover_node(0)
        r = self.approver.approve(self.v1, self.v2, CompatibilityMode.BACKWARD)
        assert r.approved is True
        assert r.failures == 0

    def test_none_mode_auto_approves(self):
        bad_v2 = Schema("Test", 2, [
            SchemaField("completely_different", SchemaFieldType.BOOL, tag=99),
        ])
        r = self.approver.approve(self.v1, bad_v2, CompatibilityMode.NONE)
        assert r.approved is True

    def test_quorum_exceeds_nodes_raises(self):
        with pytest.raises(SchemaEvolutionError):
            ConsensusApprover(num_nodes=3, quorum=5)

    def test_rounds_history(self):
        self.approver.approve(None, self.v1, CompatibilityMode.BACKWARD)
        assert len(self.approver.rounds) == 1
        r = self.approver.rounds[0]
        assert r.schema_name == "Test"
        assert r.version == 1

    def test_phase_log_contains_all_phases(self):
        r = self.approver.approve(None, self.v1, CompatibilityMode.BACKWARD)
        phases = {entry["phase"] for entry in r.phase_log}
        assert PaxosPhase.PREPARE.name in phases
        assert PaxosPhase.PROMISE.name in phases
        assert PaxosPhase.ACCEPT.name in phases
        assert PaxosPhase.LEARN.name in phases

    def test_consensus_round_duration(self):
        r = self.approver.approve(None, self.v1, CompatibilityMode.BACKWARD)
        assert r.duration_ms >= 0

    def test_nodes_property(self):
        nodes = self.approver.nodes
        assert len(nodes) == 5
        assert all(isinstance(n, ConsensusNode) for n in nodes)


# ============================================================
# Built-in Lineage Tests
# ============================================================


class TestEvaluationResultLineage:
    """Tests for the built-in EvaluationResult schema lineage."""

    def test_lineage_has_three_versions(self):
        lineage = build_evaluation_result_lineage()
        assert len(lineage) == 3

    def test_lineage_versions(self):
        lineage = build_evaluation_result_lineage()
        assert [s.version for s in lineage] == [1, 2, 3]

    def test_v1_has_two_fields(self):
        lineage = build_evaluation_result_lineage()
        assert len(lineage[0].fields) == 2

    def test_v2_has_four_fields(self):
        lineage = build_evaluation_result_lineage()
        assert len(lineage[1].fields) == 4

    def test_v3_has_six_fields(self):
        lineage = build_evaluation_result_lineage()
        assert len(lineage[2].fields) == 6

    def test_lineage_backward_compatible(self):
        """The entire lineage should be BACKWARD-compatible."""
        lineage = build_evaluation_result_lineage()
        checker = CompatibilityChecker()
        for i in range(len(lineage) - 1):
            result = checker.check(lineage[i], lineage[i + 1], CompatibilityMode.BACKWARD)
            assert result.compatible is True, f"v{lineage[i].version}->v{lineage[i+1].version} incompatible"

    def test_bootstrap_registry(self):
        registry = bootstrap_registry()
        assert registry.get("EvaluationResult", 1) is not None
        assert registry.get("EvaluationResult", 2) is not None
        assert registry.get("EvaluationResult", 3) is not None

    def test_bootstrap_registry_custom_mode(self):
        registry = bootstrap_registry(mode=CompatibilityMode.FULL)
        assert registry.get_compatibility_mode("EvaluationResult") == CompatibilityMode.FULL


# ============================================================
# SchemaDashboard Tests
# ============================================================


class TestSchemaDashboard:
    """Tests for the SchemaDashboard ASCII renderer."""

    def test_render_empty_registry(self):
        registry = SchemaRegistry()
        output = SchemaDashboard.render(registry, width=60)
        assert "FizzSchema" in output
        assert "no schemas registered" in output

    def test_render_with_schemas(self):
        registry = bootstrap_registry()
        output = SchemaDashboard.render(registry, width=60)
        assert "EvaluationResult" in output
        assert "Schema Inventory" in output
        assert "Version Timeline" in output

    def test_render_with_approver(self):
        registry = bootstrap_registry()
        approver = ConsensusApprover()
        approver.approve(None, build_evaluation_result_lineage()[0], CompatibilityMode.BACKWARD)
        output = SchemaDashboard.render(registry, approver=approver, width=60)
        assert "Consensus Rounds" in output

    def test_render_contains_box_drawing(self):
        registry = bootstrap_registry()
        output = SchemaDashboard.render(registry, width=60)
        assert "+" in output
        assert "-" in output
        assert "|" in output

    def test_render_width_respected(self):
        registry = bootstrap_registry()
        output = SchemaDashboard.render(registry, width=50)
        for line in output.split("\n"):
            assert len(line) <= 50


# ============================================================
# SchemaMiddleware Tests
# ============================================================


class TestSchemaMiddleware:
    """Tests for the SchemaMiddleware."""

    def test_middleware_stamps_context(self):
        registry = bootstrap_registry()
        middleware = SchemaMiddleware(registry)

        context = MagicMock()
        context.metadata = {}

        def next_handler(ctx):
            return ctx

        result = middleware.process(context, next_handler)
        assert result.metadata["schema_name"] == "EvaluationResult"
        assert result.metadata["schema_version"] == 3
        assert "schema_fingerprint" in result.metadata

    def test_middleware_no_schema_found(self):
        registry = SchemaRegistry()
        middleware = SchemaMiddleware(registry, schema_name="NonExistent")

        context = MagicMock()
        context.metadata = {}

        def next_handler(ctx):
            return ctx

        result = middleware.process(context, next_handler)
        assert "schema_version" not in result.metadata

    def test_middleware_name(self):
        middleware = SchemaMiddleware(SchemaRegistry())
        assert middleware.get_name() == "SchemaMiddleware"

    def test_middleware_priority(self):
        middleware = SchemaMiddleware(SchemaRegistry())
        assert middleware.get_priority() == 950


# ============================================================
# Schema Exception Tests
# ============================================================


class TestSchemaExceptions:
    """Tests for the FizzSchema exception hierarchy."""

    def test_schema_evolution_error_base(self):
        e = SchemaEvolutionError("test error")
        assert "EFP-SE00" in str(e)

    def test_schema_compatibility_error(self):
        e = SchemaCompatibilityError("Test", 1, 2, ["violation1"])
        assert "EFP-SE01" in str(e)
        assert e.schema_name == "Test"
        assert e.violations == ["violation1"]

    def test_schema_registration_error(self):
        e = SchemaRegistrationError("Test", 1, "duplicate")
        assert "EFP-SE02" in str(e)
        assert e.reason == "duplicate"

    def test_schema_consensus_error(self):
        e = SchemaConsensusError("Test", 2, 3, "quorum not reached")
        assert "EFP-SE03" in str(e)
        assert e.approvals == 2
        assert e.required == 3

    def test_exceptions_inherit_from_fizzbuzz_error(self):
        from enterprise_fizzbuzz.domain.exceptions import FizzBuzzError
        assert issubclass(SchemaEvolutionError, FizzBuzzError)
        assert issubclass(SchemaCompatibilityError, SchemaEvolutionError)
        assert issubclass(SchemaRegistrationError, SchemaEvolutionError)
        assert issubclass(SchemaConsensusError, SchemaEvolutionError)


# ============================================================
# FieldMigration / MigrationPlan Tests
# ============================================================


class TestFieldMigration:
    """Tests for FieldMigration and MigrationPlan dataclasses."""

    def test_field_migration_creation(self):
        fm = FieldMigration(action="ADD", field_name="x", detail="Add x")
        assert fm.action == "ADD"
        assert fm.field_name == "x"
        assert fm.default_value is None

    def test_migration_plan_no_breaking_changes(self):
        plan = MigrationPlan("Test", 1, 2, [
            FieldMigration("ADD", "x", "Add x", default_value=0),
        ])
        assert plan.has_breaking_changes is False

    def test_migration_plan_with_breaking_changes(self):
        plan = MigrationPlan("Test", 1, 2, [
            FieldMigration("REMOVE", "x", "Remove x"),
        ])
        assert plan.has_breaking_changes is True


# ============================================================
# ConsensusNode Tests
# ============================================================


class TestConsensusNode:
    """Tests for the ConsensusNode dataclass."""

    def test_node_creation(self):
        node = ConsensusNode(node_id=0)
        assert node.state == ConsensusNodeState.IDLE
        assert node.promised_proposal is None

    def test_node_reset(self):
        node = ConsensusNode(node_id=0, state=ConsensusNodeState.ACCEPTED, promised_proposal=5)
        node.reset()
        assert node.state == ConsensusNodeState.IDLE
        assert node.promised_proposal is None

    def test_node_states(self):
        assert len(ConsensusNodeState) == 5


# ============================================================
# Thread Safety Test
# ============================================================


class TestSchemaRegistryThreadSafety:
    """Tests that the schema registry is thread-safe under concurrent access."""

    def test_concurrent_registrations(self):
        registry = SchemaRegistry(default_mode=CompatibilityMode.NONE)
        errors: list[Exception] = []

        def register_schema(version: int):
            try:
                s = Schema(f"Schema_{version}", 1, [
                    SchemaField(f"f_{version}", SchemaFieldType.INT64, tag=version + 1),
                ])
                registry.register(s)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=register_schema, args=(i,)) for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0
        assert len(registry.schema_names) == 10
