"""Tests for the FizzArrow Apache Arrow-Style Columnar Memory Format subsystem.

Validates all components of the FizzArrow engine including schema construction,
record batch creation, column projection, predicate-based row filtering,
vectorized aggregation, null bitmap handling, type enforcement, dashboard
rendering, and middleware integration.
"""

import uuid
from collections import OrderedDict
from unittest.mock import MagicMock

import pytest

from enterprise_fizzbuzz.infrastructure.fizzarrow import (
    FIZZARROW_VERSION,
    MIDDLEWARE_PRIORITY,
    DEFAULT_DASHBOARD_WIDTH,
    SUPPORTED_AGGREGATIONS,
    NUMERIC_TYPES,
    DataType,
    Column,
    RecordBatch,
    Schema,
    ArrowTable,
    FizzArrowDashboard,
    FizzArrowMiddleware,
    create_fizzarrow_subsystem,
)
from enterprise_fizzbuzz.domain.exceptions import (
    FizzArrowError,
    FizzArrowSchemaError,
    FizzArrowBatchError,
    FizzArrowBatchNotFoundError,
    FizzArrowColumnNotFoundError,
    FizzArrowAggregationError,
    FizzArrowUnsupportedOperationError,
    FizzArrowNullBitmapError,
    FizzArrowRowCountMismatchError,
    FizzArrowDuplicateColumnError,
)
from enterprise_fizzbuzz.domain.models import ProcessingContext


# ============================================================
# Fixtures
# ============================================================


@pytest.fixture
def table():
    """Fresh ArrowTable instance."""
    return ArrowTable()


@pytest.fixture
def simple_schema():
    """Schema with three columns: id (INT64), name (STRING), score (FLOAT64)."""
    return Schema(fields=[
        ("id", DataType.INT64),
        ("name", DataType.STRING),
        ("score", DataType.FLOAT64),
    ])


@pytest.fixture
def simple_data():
    """Sample data matching simple_schema."""
    return {
        "id": [1, 2, 3, 4, 5],
        "name": ["Fizz", "Buzz", "FizzBuzz", "4", "Buzz"],
        "score": [10.0, 20.0, 30.0, 40.0, 50.0],
    }


@pytest.fixture
def populated_table(table, simple_schema, simple_data):
    """Table with one batch already created."""
    batch = table.create_batch(simple_schema, simple_data)
    return table, batch


# ============================================================
# Constants
# ============================================================


class TestConstants:
    """Verify module-level constants are correctly defined."""

    def test_version(self):
        assert FIZZARROW_VERSION == "1.0.0"

    def test_middleware_priority(self):
        assert MIDDLEWARE_PRIORITY == 233

    def test_dashboard_width(self):
        assert DEFAULT_DASHBOARD_WIDTH == 72

    def test_supported_aggregations(self):
        assert "sum" in SUPPORTED_AGGREGATIONS
        assert "min" in SUPPORTED_AGGREGATIONS
        assert "max" in SUPPORTED_AGGREGATIONS
        assert "count" in SUPPORTED_AGGREGATIONS
        assert "avg" in SUPPORTED_AGGREGATIONS


# ============================================================
# DataType Enum
# ============================================================


class TestDataType:
    """Verify the DataType enum covers all required types."""

    def test_int32(self):
        assert DataType.INT32.value == "int32"

    def test_int64(self):
        assert DataType.INT64.value == "int64"

    def test_float64(self):
        assert DataType.FLOAT64.value == "float64"

    def test_string(self):
        assert DataType.STRING.value == "string"

    def test_bool(self):
        assert DataType.BOOL.value == "bool"

    def test_binary(self):
        assert DataType.BINARY.value == "binary"


# ============================================================
# Column
# ============================================================


class TestColumn:
    """Verify Column dataclass behavior."""

    def test_auto_bitmap(self):
        col = Column(name="x", dtype=DataType.INT32, values=[1, 2, 3])
        assert col.null_bitmap == [True, True, True]
        assert col.length == 3
        assert col.null_count == 0

    def test_null_values_tracked(self):
        col = Column(
            name="x", dtype=DataType.INT32,
            values=[1, None, 3],
            null_bitmap=[True, False, True],
        )
        assert col.null_count == 1

    def test_bitmap_length_mismatch_raises(self):
        with pytest.raises(FizzArrowNullBitmapError):
            Column(name="x", dtype=DataType.INT32, values=[1, 2], null_bitmap=[True])


# ============================================================
# Schema
# ============================================================


class TestSchema:
    """Verify Schema validation and accessors."""

    def test_field_names(self, simple_schema):
        assert simple_schema.field_names == ["id", "name", "score"]

    def test_get_type(self, simple_schema):
        assert simple_schema.get_type("id") == DataType.INT64
        assert simple_schema.get_type("score") == DataType.FLOAT64

    def test_get_type_missing(self, simple_schema):
        with pytest.raises(FizzArrowColumnNotFoundError):
            simple_schema.get_type("nonexistent")

    def test_duplicate_field_names(self):
        with pytest.raises(FizzArrowDuplicateColumnError):
            Schema(fields=[("x", DataType.INT32), ("x", DataType.INT64)])


# ============================================================
# ArrowTable - Batch Creation
# ============================================================


class TestArrowTableCreateBatch:
    """Verify record batch creation with schema enforcement."""

    def test_create_batch(self, table, simple_schema, simple_data):
        batch = table.create_batch(simple_schema, simple_data)
        assert batch.num_rows == 5
        assert batch.num_columns == 3
        assert "id" in batch.columns
        assert "name" in batch.columns
        assert "score" in batch.columns

    def test_batch_has_uuid(self, table, simple_schema, simple_data):
        batch = table.create_batch(simple_schema, simple_data)
        uuid.UUID(batch.batch_id)  # Should not raise

    def test_empty_schema_raises(self, table):
        schema = Schema(fields=[])
        with pytest.raises(FizzArrowSchemaError):
            table.create_batch(schema, {})

    def test_missing_column_data_raises(self, table, simple_schema):
        with pytest.raises(FizzArrowBatchError):
            table.create_batch(simple_schema, {"id": [1], "name": ["a"]})

    def test_extra_column_data_raises(self, table, simple_schema, simple_data):
        simple_data["extra"] = [1, 2, 3, 4, 5]
        with pytest.raises(FizzArrowBatchError):
            table.create_batch(simple_schema, simple_data)

    def test_unequal_column_lengths_raises(self, table):
        schema = Schema(fields=[("a", DataType.INT32), ("b", DataType.INT32)])
        with pytest.raises(FizzArrowRowCountMismatchError):
            table.create_batch(schema, {"a": [1, 2, 3], "b": [1, 2]})


# ============================================================
# ArrowTable - Retrieval
# ============================================================


class TestArrowTableRetrieval:
    """Verify batch retrieval and listing."""

    def test_get_batch(self, populated_table):
        table, batch = populated_table
        retrieved = table.get_batch(batch.batch_id)
        assert retrieved.batch_id == batch.batch_id

    def test_get_batch_not_found(self, table):
        with pytest.raises(FizzArrowBatchNotFoundError):
            table.get_batch("nonexistent-id")

    def test_list_batches(self, populated_table):
        table, batch = populated_table
        batches = table.list_batches()
        assert len(batches) == 1
        assert batches[0].batch_id == batch.batch_id


# ============================================================
# ArrowTable - Select (Projection)
# ============================================================


class TestArrowTableSelect:
    """Verify column projection."""

    def test_select_single_column(self, populated_table):
        table, batch = populated_table
        projected = table.select(batch.batch_id, ["name"])
        assert projected.num_columns == 1
        assert "name" in projected.columns
        assert projected.num_rows == 5

    def test_select_multiple_columns(self, populated_table):
        table, batch = populated_table
        projected = table.select(batch.batch_id, ["id", "score"])
        assert projected.num_columns == 2
        assert projected.columns["id"].values == [1, 2, 3, 4, 5]

    def test_select_missing_column_raises(self, populated_table):
        table, batch = populated_table
        with pytest.raises(FizzArrowColumnNotFoundError):
            table.select(batch.batch_id, ["nonexistent"])


# ============================================================
# ArrowTable - Filter
# ============================================================


class TestArrowTableFilter:
    """Verify predicate-based row filtering."""

    def test_filter_numeric(self, populated_table):
        table, batch = populated_table
        filtered = table.filter(batch.batch_id, "score", lambda v: v > 25.0)
        assert filtered.num_rows == 3
        assert filtered.columns["score"].values == [30.0, 40.0, 50.0]

    def test_filter_string(self, populated_table):
        table, batch = populated_table
        filtered = table.filter(batch.batch_id, "name", lambda v: v == "Buzz")
        assert filtered.num_rows == 2
        assert filtered.columns["id"].values == [2, 5]

    def test_filter_all_excluded(self, populated_table):
        table, batch = populated_table
        filtered = table.filter(batch.batch_id, "score", lambda v: v > 100.0)
        assert filtered.num_rows == 0

    def test_filter_missing_column_raises(self, populated_table):
        table, batch = populated_table
        with pytest.raises(FizzArrowColumnNotFoundError):
            table.filter(batch.batch_id, "nonexistent", lambda v: True)


# ============================================================
# ArrowTable - Aggregate
# ============================================================


class TestArrowTableAggregate:
    """Verify vectorized aggregation operations."""

    def test_sum(self, populated_table):
        table, batch = populated_table
        result = table.aggregate(batch.batch_id, "score", op="sum")
        assert result == 150.0

    def test_min(self, populated_table):
        table, batch = populated_table
        result = table.aggregate(batch.batch_id, "score", op="min")
        assert result == 10.0

    def test_max(self, populated_table):
        table, batch = populated_table
        result = table.aggregate(batch.batch_id, "score", op="max")
        assert result == 50.0

    def test_count(self, populated_table):
        table, batch = populated_table
        result = table.aggregate(batch.batch_id, "score", op="count")
        assert result == 5

    def test_avg(self, populated_table):
        table, batch = populated_table
        result = table.aggregate(batch.batch_id, "score", op="avg")
        assert result == 30.0

    def test_count_on_string_column(self, populated_table):
        table, batch = populated_table
        result = table.aggregate(batch.batch_id, "name", op="count")
        assert result == 5

    def test_sum_on_string_raises(self, populated_table):
        table, batch = populated_table
        with pytest.raises(FizzArrowAggregationError):
            table.aggregate(batch.batch_id, "name", op="sum")

    def test_unsupported_operation_raises(self, populated_table):
        table, batch = populated_table
        with pytest.raises(FizzArrowUnsupportedOperationError):
            table.aggregate(batch.batch_id, "score", op="median")

    def test_aggregate_missing_column_raises(self, populated_table):
        table, batch = populated_table
        with pytest.raises(FizzArrowColumnNotFoundError):
            table.aggregate(batch.batch_id, "nonexistent", op="sum")

    def test_aggregate_with_nulls(self, table):
        schema = Schema(fields=[("val", DataType.FLOAT64)])
        data = {"val": [10.0, None, 30.0]}
        batch = table.create_batch(schema, data)
        result = table.aggregate(batch.batch_id, "val", op="sum")
        assert result == 40.0
        count = table.aggregate(batch.batch_id, "val", op="count")
        assert count == 2


# ============================================================
# Dashboard
# ============================================================


class TestFizzArrowDashboard:
    """Verify ASCII dashboard rendering."""

    def test_render_overview(self, populated_table):
        table, batch = populated_table
        dashboard = FizzArrowDashboard(width=72)
        output = dashboard.render_overview(table)
        assert "FizzArrow Columnar Memory Format" in output
        assert FIZZARROW_VERSION in output
        assert "Total Batches" in output

    def test_render_batch(self, populated_table):
        table, batch = populated_table
        dashboard = FizzArrowDashboard(width=72)
        output = dashboard.render_batch(batch)
        assert batch.batch_id in output
        assert "Rows" in output


# ============================================================
# Middleware
# ============================================================


class TestFizzArrowMiddleware:
    """Verify middleware integration with the FizzBuzz pipeline."""

    def test_get_name(self):
        table, middleware = create_fizzarrow_subsystem()
        assert middleware.get_name() == "fizzarrow"

    def test_get_priority(self):
        table, middleware = create_fizzarrow_subsystem()
        assert middleware.get_priority() == 233

    def test_process_annotates_context(self):
        table, middleware = create_fizzarrow_subsystem()
        context = ProcessingContext(number=42, session_id="test-session")
        called = False

        def next_handler(ctx):
            nonlocal called
            called = True
            return ctx

        result = middleware.process(context, next_handler)
        assert called
        assert result.metadata["fizzarrow_enabled"] is True
        assert result.metadata["fizzarrow_version"] == FIZZARROW_VERSION


# ============================================================
# Factory
# ============================================================


class TestFactory:
    """Verify subsystem factory function."""

    def test_create_returns_tuple(self):
        table, middleware = create_fizzarrow_subsystem()
        assert isinstance(table, ArrowTable)
        assert isinstance(middleware, FizzArrowMiddleware)

    def test_custom_dashboard_width(self):
        table, middleware = create_fizzarrow_subsystem(dashboard_width=100)
        assert middleware._dashboard._width == 100


# ============================================================
# Stats
# ============================================================


class TestStats:
    """Verify engine statistics tracking."""

    def test_stats_after_operations(self, table, simple_schema, simple_data):
        batch = table.create_batch(simple_schema, simple_data)
        table.select(batch.batch_id, ["id"])
        table.filter(batch.batch_id, "score", lambda v: v > 20)
        table.aggregate(batch.batch_id, "score", op="sum")
        stats = table.get_stats()
        assert stats["batches_created"] >= 1
        assert stats["projections"] >= 1
        assert stats["filters"] >= 1
        assert stats["aggregations"] >= 1
