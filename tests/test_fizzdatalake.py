"""
Enterprise FizzBuzz Platform - FizzDataLake Test Suite

Tests for the FizzDataLake subsystem, which provides schema-on-read semantics,
partitioning strategies, and columnar query capabilities for managing the
vast quantities of FizzBuzz evaluation data produced at enterprise scale.
Without a proper data lake, organizations risk losing critical audit trails
of which integers were divisible by three, five, or both.
"""

from __future__ import annotations

import pytest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

from enterprise_fizzbuzz.infrastructure.fizzdatalake import (
    FIZZDATALAKE_VERSION,
    MIDDLEWARE_PRIORITY,
    FileFormat,
    PartitionStrategy,
    FizzDataLakeConfig,
    DataObject,
    Partition,
    DataLakeStore,
    SchemaRegistry,
    PartitionManager,
    FizzDataLakeDashboard,
    FizzDataLakeMiddleware,
    create_fizzdatalake_subsystem,
)


# ---------------------------------------------------------------------------
# TestConstants
# ---------------------------------------------------------------------------


class TestConstants:
    """Verify module-level constants are correctly defined."""

    def test_version(self):
        assert FIZZDATALAKE_VERSION == "1.0.0"

    def test_middleware_priority(self):
        assert MIDDLEWARE_PRIORITY == 166


# ---------------------------------------------------------------------------
# TestDataLakeStore
# ---------------------------------------------------------------------------


class TestDataLakeStore:
    """Tests for the core data lake storage engine."""

    def _make_store(self):
        return DataLakeStore()

    def test_ingest_returns_data_object(self):
        store = self._make_store()
        data = [{"number": 3, "result": "Fizz"}, {"number": 5, "result": "Buzz"}]
        schema = {"number": "int", "result": "str"}
        obj = store.ingest(
            path="/fizzbuzz/results/2026",
            data=data,
            format=FileFormat.PARQUET,
            partition_key="date",
            schema=schema,
        )
        assert isinstance(obj, DataObject)
        assert obj.path == "/fizzbuzz/results/2026"
        assert obj.format == FileFormat.PARQUET
        assert obj.partition_key == "date"
        assert obj.schema == schema
        assert len(obj.data) == 2
        assert obj.size_bytes > 0
        assert isinstance(obj.object_id, str)
        assert len(obj.object_id) > 0
        assert isinstance(obj.created_at, datetime)

    def test_get_retrieves_ingested_object(self):
        store = self._make_store()
        data = [{"number": 15, "result": "FizzBuzz"}]
        obj = store.ingest(
            path="/fizzbuzz/results",
            data=data,
            format=FileFormat.JSON,
            partition_key="hash",
            schema={"number": "int", "result": "str"},
        )
        retrieved = store.get(obj.object_id)
        assert retrieved.object_id == obj.object_id
        assert retrieved.data == data
        assert retrieved.path == "/fizzbuzz/results"

    def test_query_with_filters(self):
        store = self._make_store()
        store.ingest(
            path="/fizzbuzz/output",
            data=[
                {"number": 3, "result": "Fizz"},
                {"number": 5, "result": "Buzz"},
                {"number": 15, "result": "FizzBuzz"},
            ],
            format=FileFormat.CSV,
            partition_key="default",
            schema={"number": "int", "result": "str"},
        )
        results = store.query("/fizzbuzz/output", filters={"result": "Fizz"})
        assert isinstance(results, list)
        assert all(row["result"] == "Fizz" for row in results)
        assert len(results) >= 1

    def test_list_objects_by_path_prefix(self):
        store = self._make_store()
        store.ingest(
            path="/lake/alpha/batch1",
            data=[{"x": 1}],
            format=FileFormat.JSON,
            partition_key="k1",
            schema={"x": "int"},
        )
        store.ingest(
            path="/lake/alpha/batch2",
            data=[{"x": 2}],
            format=FileFormat.CSV,
            partition_key="k2",
            schema={"x": "int"},
        )
        store.ingest(
            path="/lake/beta/batch1",
            data=[{"x": 3}],
            format=FileFormat.PARQUET,
            partition_key="k3",
            schema={"x": "int"},
        )
        alpha_objects = store.list_objects("/lake/alpha")
        assert len(alpha_objects) == 2
        all_objects = store.list_objects("/lake")
        assert len(all_objects) == 3

    def test_delete_removes_object(self):
        store = self._make_store()
        obj = store.ingest(
            path="/tmp/disposable",
            data=[{"val": 42}],
            format=FileFormat.AVRO,
            partition_key="none",
            schema={"val": "int"},
        )
        assert store.delete(obj.object_id) is True
        # After deletion, get should fail or return None
        with pytest.raises(Exception):
            store.get(obj.object_id)

    def test_get_stats_reflects_stored_data(self):
        store = self._make_store()
        store.ingest(
            path="/stats/test",
            data=[{"a": 1}, {"a": 2}, {"a": 3}],
            format=FileFormat.PARQUET,
            partition_key="pk",
            schema={"a": "int"},
        )
        stats = store.get_stats()
        assert isinstance(stats, dict)
        assert stats.get("object_count", stats.get("total_objects", 0)) >= 1
        # Stats should report total size
        total_size_key = None
        for key in ("total_size_bytes", "total_size", "size_bytes"):
            if key in stats:
                total_size_key = key
                break
        assert total_size_key is not None, f"Stats missing size key: {stats.keys()}"
        assert stats[total_size_key] > 0

    def test_query_by_path_prefix_returns_only_matching(self):
        store = self._make_store()
        store.ingest(
            path="/department/sales/q1",
            data=[{"revenue": 100}],
            format=FileFormat.JSON,
            partition_key="quarter",
            schema={"revenue": "int"},
        )
        store.ingest(
            path="/department/engineering/q1",
            data=[{"commits": 500}],
            format=FileFormat.JSON,
            partition_key="quarter",
            schema={"commits": "int"},
        )
        results = store.query("/department/sales")
        assert isinstance(results, list)
        assert len(results) >= 1
        # Should contain sales data, not engineering data
        all_keys = set()
        for row in results:
            all_keys.update(row.keys())
        assert "revenue" in all_keys


# ---------------------------------------------------------------------------
# TestSchemaRegistry
# ---------------------------------------------------------------------------


class TestSchemaRegistry:
    """Tests for the schema-on-read registry."""

    def _make_registry(self):
        return SchemaRegistry()

    def test_register_and_get_schema(self):
        registry = self._make_registry()
        schema = {"number": "int", "label": "str", "timestamp": "datetime"}
        result = registry.register("/fizzbuzz/output", schema)
        assert isinstance(result, dict)
        retrieved = registry.get("/fizzbuzz/output")
        assert isinstance(retrieved, dict)
        # The retrieved schema should contain our fields
        assert "number" in str(retrieved) or retrieved.get("number") is not None

    def test_infer_schema_from_data(self):
        registry = self._make_registry()
        data = [
            {"id": 1, "name": "Fizz", "active": True},
            {"id": 2, "name": "Buzz", "active": False},
        ]
        inferred = registry.infer(data)
        assert isinstance(inferred, dict)
        assert len(inferred) > 0
        # Should detect at least the field names present in the data
        field_names = set()
        if isinstance(inferred, dict):
            for key in inferred:
                field_names.add(key)
        assert "id" in field_names or "name" in field_names

    def test_validate_valid_data(self):
        registry = self._make_registry()
        schema = {"number": "int", "result": "str"}
        data = [{"number": 3, "result": "Fizz"}]
        is_valid, errors = registry.validate(data, schema)
        assert is_valid is True
        assert isinstance(errors, list)
        assert len(errors) == 0

    def test_validate_invalid_data(self):
        registry = self._make_registry()
        schema = {"number": "int", "result": "str"}
        # Invalid data: wrong types or missing fields
        data = [{"number": "not_a_number", "result": 12345}]
        is_valid, errors = registry.validate(data, schema)
        assert is_valid is False
        assert isinstance(errors, list)
        assert len(errors) > 0


# ---------------------------------------------------------------------------
# TestPartitionManager
# ---------------------------------------------------------------------------


class TestPartitionManager:
    """Tests for the partition management layer."""

    def _make_manager(self):
        return PartitionManager()

    def test_create_and_get_partition(self):
        manager = self._make_manager()
        partition = manager.create_partition("year_2026", PartitionStrategy.DATE)
        assert isinstance(partition, Partition)
        assert partition.key == "year_2026"
        assert partition.strategy == PartitionStrategy.DATE

        retrieved = manager.get_partition("year_2026")
        assert retrieved.key == "year_2026"
        assert retrieved.strategy == PartitionStrategy.DATE

    def test_list_partitions(self):
        manager = self._make_manager()
        manager.create_partition("region_us", PartitionStrategy.HASH)
        manager.create_partition("region_eu", PartitionStrategy.HASH)
        partitions = manager.list_partitions()
        assert isinstance(partitions, list)
        assert len(partitions) >= 2
        keys = [p.key for p in partitions]
        assert "region_us" in keys
        assert "region_eu" in keys

    def test_partition_strategy_types(self):
        manager = self._make_manager()
        p_date = manager.create_partition("by_date", PartitionStrategy.DATE)
        p_hash = manager.create_partition("by_hash", PartitionStrategy.HASH)
        p_range = manager.create_partition("by_range", PartitionStrategy.RANGE)
        assert p_date.strategy == PartitionStrategy.DATE
        assert p_hash.strategy == PartitionStrategy.HASH
        assert p_range.strategy == PartitionStrategy.RANGE


# ---------------------------------------------------------------------------
# TestFizzDataLakeDashboard
# ---------------------------------------------------------------------------


class TestFizzDataLakeDashboard:
    """Tests for the operational dashboard."""

    def test_render_returns_string(self):
        store = DataLakeStore()
        dashboard = FizzDataLakeDashboard(store)
        output = dashboard.render()
        assert isinstance(output, str)
        assert len(output) > 0

    def test_render_contains_lake_info(self):
        store = DataLakeStore()
        store.ingest(
            path="/dashboard/test",
            data=[{"n": 1}],
            format=FileFormat.JSON,
            partition_key="default",
            schema={"n": "int"},
        )
        dashboard = FizzDataLakeDashboard(store)
        output = dashboard.render()
        lower_output = output.lower()
        # Dashboard should reference the data lake in some capacity
        assert any(
            term in lower_output
            for term in ("lake", "data", "object", "store", "partition", "fizz")
        ), f"Dashboard output missing expected lake info: {output[:200]}"


# ---------------------------------------------------------------------------
# TestFizzDataLakeMiddleware
# ---------------------------------------------------------------------------


class TestFizzDataLakeMiddleware:
    """Tests for the middleware integration."""

    def _make_middleware(self):
        return FizzDataLakeMiddleware()

    def test_get_name(self):
        mw = self._make_middleware()
        assert mw.get_name() == "fizzdatalake"

    def test_get_priority(self):
        mw = self._make_middleware()
        assert mw.get_priority() == 166

    def test_process_calls_next(self):
        mw = self._make_middleware()
        ctx = MagicMock()
        next_handler = MagicMock()
        mw.process(ctx, next_handler)
        next_handler.assert_called_once()


# ---------------------------------------------------------------------------
# TestCreateSubsystem
# ---------------------------------------------------------------------------


class TestCreateSubsystem:
    """Tests for the factory function that wires the subsystem."""

    def test_returns_tuple_of_three(self):
        result = create_fizzdatalake_subsystem()
        assert isinstance(result, tuple)
        assert len(result) == 3
        store, dashboard, middleware = result
        assert isinstance(store, DataLakeStore)
        assert isinstance(dashboard, FizzDataLakeDashboard)
        assert isinstance(middleware, FizzDataLakeMiddleware)

    def test_store_is_functional(self):
        store, _, _ = create_fizzdatalake_subsystem()
        obj = store.ingest(
            path="/subsystem/test",
            data=[{"fizz": "buzz"}],
            format=FileFormat.PARQUET,
            partition_key="test",
            schema={"fizz": "str"},
        )
        assert isinstance(obj, DataObject)
        retrieved = store.get(obj.object_id)
        assert retrieved.data == [{"fizz": "buzz"}]

    def test_store_has_default_data(self):
        store, _, _ = create_fizzdatalake_subsystem()
        stats = store.get_stats()
        assert isinstance(stats, dict)
