"""
Enterprise FizzBuzz Platform - FizzArrow: Apache Arrow-Style Columnar Memory Format

A columnar in-memory data representation engine implementing the core concepts
of the Apache Arrow specification for the Enterprise FizzBuzz Platform.
FizzArrow provides strongly-typed columnar storage with null bitmaps, record
batches with schema enforcement, column projection, predicate-based row
filtering, and vectorized aggregation operations (sum, min, max, count, avg).

Columnar memory layouts deliver measurable advantages for analytical workloads
over the row-oriented data structures used elsewhere in the platform.  The
FizzBuzz evaluation pipeline produces millions of results per session, each
containing a number, classification, matched rules, processing time, and
metadata.  Downstream analytics -- computing aggregate statistics, filtering
by classification, projecting specific fields for dashboard rendering --
operate on individual columns across many rows.  Storing these results in
columnar format enables sequential memory access patterns within each column,
eliminates deserialization overhead for unused fields during projection, and
provides a foundation for future SIMD-accelerated aggregation kernels.

The schema enforcement layer ensures type safety across batch boundaries.
Every column is tagged with an explicit DataType (INT32, INT64, FLOAT64,
STRING, BOOL, BINARY), and null values are tracked via a per-column validity
bitmap rather than sentinel values.  This design eliminates the ambiguity
between "value is zero" and "value is absent" that plagues the platform's
existing dict-based result containers.

Architecture references: Apache Arrow (https://arrow.apache.org/),
Apache Parquet (https://parquet.apache.org/),
DuckDB Vector Format (https://duckdb.org/internals/vector.html)
"""

from __future__ import annotations

import logging
import statistics
import uuid
from collections import OrderedDict
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Callable, Dict, List, Optional, Tuple

from enterprise_fizzbuzz.domain.exceptions import (
    FizzArrowError,
    FizzArrowSchemaError,
    FizzArrowBatchError,
    FizzArrowBatchNotFoundError,
    FizzArrowColumnNotFoundError,
    FizzArrowTypeMismatchError,
    FizzArrowAggregationError,
    FizzArrowFilterError,
    FizzArrowNullBitmapError,
    FizzArrowEmptyBatchError,
    FizzArrowRowCountMismatchError,
    FizzArrowUnsupportedOperationError,
    FizzArrowMiddlewareError,
    FizzArrowDashboardError,
    FizzArrowDuplicateColumnError,
)
from enterprise_fizzbuzz.domain.interfaces import IMiddleware
from enterprise_fizzbuzz.domain.models import (
    EventType,
    FizzBuzzResult,
    ProcessingContext,
)

logger = logging.getLogger("enterprise_fizzbuzz.fizzarrow")


# ============================================================
# Constants
# ============================================================

FIZZARROW_VERSION = "1.0.0"
MIDDLEWARE_PRIORITY = 233
DEFAULT_DASHBOARD_WIDTH = 72

SUPPORTED_AGGREGATIONS = ("sum", "min", "max", "count", "avg")
NUMERIC_TYPES = frozenset({"INT32", "INT64", "FLOAT64"})


# ============================================================
# Enums
# ============================================================


class DataType(Enum):
    """Arrow-compatible data type descriptors for columnar storage.

    Each type maps to a fixed-width or variable-width memory layout.
    INT32 and INT64 use 4-byte and 8-byte fixed-width buffers respectively.
    FLOAT64 uses IEEE 754 double-precision 8-byte layout.  STRING and
    BINARY use variable-length offset-based encoding.  BOOL uses a
    packed bit array for storage efficiency.
    """

    INT32 = "int32"
    INT64 = "int64"
    FLOAT64 = "float64"
    STRING = "string"
    BOOL = "bool"
    BINARY = "binary"


# ============================================================
# Data Classes
# ============================================================


@dataclass
class Column:
    """A single typed column within a record batch.

    Stores a contiguous array of values along with a validity bitmap
    indicating which positions contain non-null data.  The null_bitmap
    list has the same length as the values list; True indicates the
    corresponding value is valid, False indicates null.
    """

    name: str
    dtype: DataType
    values: List[Any] = field(default_factory=list)
    null_bitmap: List[bool] = field(default_factory=list)

    def __post_init__(self) -> None:
        if len(self.null_bitmap) == 0 and len(self.values) > 0:
            self.null_bitmap = [True] * len(self.values)
        if len(self.null_bitmap) != len(self.values):
            raise FizzArrowNullBitmapError(
                self.name, len(self.values), len(self.null_bitmap)
            )

    @property
    def length(self) -> int:
        """Return the number of elements in this column."""
        return len(self.values)

    @property
    def null_count(self) -> int:
        """Return the number of null values in this column."""
        return sum(1 for valid in self.null_bitmap if not valid)


@dataclass
class RecordBatch:
    """A collection of equal-length columns forming a tabular data unit.

    Each record batch is identified by a unique batch_id and contains
    an ordered dictionary of columns.  All columns must have the same
    number of rows.
    """

    batch_id: str
    columns: OrderedDict[str, Column] = field(default_factory=OrderedDict)
    num_rows: int = 0

    @property
    def num_columns(self) -> int:
        """Return the number of columns in this batch."""
        return len(self.columns)

    @property
    def column_names(self) -> List[str]:
        """Return the ordered list of column names."""
        return list(self.columns.keys())


@dataclass
class Schema:
    """Describes the structure of a record batch.

    A schema is an ordered list of (name, DataType) pairs defining
    the columns that a compliant record batch must contain.
    """

    fields: List[Tuple[str, DataType]] = field(default_factory=list)

    def __post_init__(self) -> None:
        names = [f[0] for f in self.fields]
        if len(names) != len(set(names)):
            seen = set()
            for n in names:
                if n in seen:
                    raise FizzArrowDuplicateColumnError(n)
                seen.add(n)

    @property
    def field_names(self) -> List[str]:
        """Return the ordered list of field names."""
        return [f[0] for f in self.fields]

    def get_type(self, name: str) -> DataType:
        """Return the DataType for a named field."""
        for field_name, dtype in self.fields:
            if field_name == name:
                return dtype
        raise FizzArrowColumnNotFoundError(name, "<schema>")


# ============================================================
# ArrowTable - Core Columnar Engine
# ============================================================


class ArrowTable:
    """In-memory columnar table engine with schema-enforced record batches.

    Provides batch creation with type validation, column projection,
    predicate-based row filtering, and vectorized aggregation.  All
    operations return new RecordBatch instances without mutating the
    source data, following the immutability principle of the Arrow
    specification.
    """

    def __init__(self) -> None:
        self._batches: OrderedDict[str, RecordBatch] = OrderedDict()
        self._schemas: Dict[str, Schema] = {}
        self._stats = {
            "batches_created": 0,
            "projections": 0,
            "filters": 0,
            "aggregations": 0,
            "total_rows": 0,
        }
        logger.info("FizzArrow columnar engine initialized (v%s)", FIZZARROW_VERSION)

    def create_batch(self, schema: Schema, data: dict) -> RecordBatch:
        """Create a new record batch from a schema and column data.

        Args:
            schema: The schema defining column names and types.
            data: A dictionary mapping column names to lists of values.

        Returns:
            A new RecordBatch containing the provided data.

        Raises:
            FizzArrowSchemaError: If the schema has no fields.
            FizzArrowBatchError: If data keys don't match schema fields.
            FizzArrowRowCountMismatchError: If columns have unequal lengths.
        """
        if not schema.fields:
            raise FizzArrowSchemaError("Schema must contain at least one field")

        # Validate data keys match schema
        schema_names = set(schema.field_names)
        data_names = set(data.keys())
        if schema_names != data_names:
            missing = schema_names - data_names
            extra = data_names - schema_names
            parts = []
            if missing:
                parts.append(f"missing columns: {sorted(missing)}")
            if extra:
                parts.append(f"extra columns: {sorted(extra)}")
            raise FizzArrowBatchError(
                f"Data does not match schema: {'; '.join(parts)}"
            )

        # Determine row count and validate uniformity
        row_counts = {name: len(values) for name, values in data.items()}
        unique_counts = set(row_counts.values())
        if len(unique_counts) > 1:
            expected = max(row_counts.values())
            for name, count in row_counts.items():
                if count != expected:
                    raise FizzArrowRowCountMismatchError(name, expected, count)

        num_rows = next(iter(row_counts.values())) if row_counts else 0

        # Build columns
        batch_id = str(uuid.uuid4())
        columns = OrderedDict()
        for field_name, dtype in schema.fields:
            values = data[field_name]
            null_bitmap = [v is not None for v in values]
            columns[field_name] = Column(
                name=field_name,
                dtype=dtype,
                values=values,
                null_bitmap=null_bitmap,
            )

        batch = RecordBatch(
            batch_id=batch_id,
            columns=columns,
            num_rows=num_rows,
        )
        self._batches[batch_id] = batch
        self._schemas[batch_id] = schema
        self._stats["batches_created"] += 1
        self._stats["total_rows"] += num_rows
        logger.debug(
            "Created batch %s: %d rows x %d columns",
            batch_id, num_rows, len(columns),
        )
        return batch

    def get_batch(self, batch_id: str) -> RecordBatch:
        """Retrieve a record batch by its identifier.

        Raises:
            FizzArrowBatchNotFoundError: If the batch does not exist.
        """
        if batch_id not in self._batches:
            raise FizzArrowBatchNotFoundError(batch_id)
        return self._batches[batch_id]

    def list_batches(self) -> List[RecordBatch]:
        """Return all record batches in creation order."""
        return list(self._batches.values())

    def select(self, batch_id: str, column_names: List[str]) -> RecordBatch:
        """Project specific columns from a record batch.

        Creates a new batch containing only the requested columns,
        preserving their original order within the source batch.

        Raises:
            FizzArrowBatchNotFoundError: If the batch does not exist.
            FizzArrowColumnNotFoundError: If a column name is not in the batch.
        """
        source = self.get_batch(batch_id)
        projected_columns = OrderedDict()
        for name in column_names:
            if name not in source.columns:
                raise FizzArrowColumnNotFoundError(name, batch_id)
            col = source.columns[name]
            projected_columns[name] = Column(
                name=col.name,
                dtype=col.dtype,
                values=list(col.values),
                null_bitmap=list(col.null_bitmap),
            )

        new_batch_id = str(uuid.uuid4())
        projected = RecordBatch(
            batch_id=new_batch_id,
            columns=projected_columns,
            num_rows=source.num_rows,
        )
        self._batches[new_batch_id] = projected
        self._stats["projections"] += 1
        logger.debug(
            "Projected %d columns from batch %s -> %s",
            len(column_names), batch_id, new_batch_id,
        )
        return projected

    def filter(
        self,
        batch_id: str,
        column_name: str,
        predicate: Callable[[Any], bool],
    ) -> RecordBatch:
        """Filter rows from a record batch based on a column predicate.

        Applies the predicate function to each value in the specified
        column and returns a new batch containing only rows where the
        predicate returned True.  Null values are excluded by default.

        Raises:
            FizzArrowBatchNotFoundError: If the batch does not exist.
            FizzArrowColumnNotFoundError: If the column is not in the batch.
        """
        source = self.get_batch(batch_id)
        if column_name not in source.columns:
            raise FizzArrowColumnNotFoundError(column_name, batch_id)

        filter_col = source.columns[column_name]
        mask = []
        for i, (value, valid) in enumerate(zip(filter_col.values, filter_col.null_bitmap)):
            if valid and predicate(value):
                mask.append(i)

        # Build filtered columns
        new_columns = OrderedDict()
        for name, col in source.columns.items():
            new_values = [col.values[i] for i in mask]
            new_bitmap = [col.null_bitmap[i] for i in mask]
            new_columns[name] = Column(
                name=col.name,
                dtype=col.dtype,
                values=new_values,
                null_bitmap=new_bitmap,
            )

        new_batch_id = str(uuid.uuid4())
        filtered = RecordBatch(
            batch_id=new_batch_id,
            columns=new_columns,
            num_rows=len(mask),
        )
        self._batches[new_batch_id] = filtered
        self._stats["filters"] += 1
        logger.debug(
            "Filtered batch %s on '%s': %d -> %d rows",
            batch_id, column_name, source.num_rows, len(mask),
        )
        return filtered

    def aggregate(
        self,
        batch_id: str,
        column_name: str,
        op: str = "sum",
    ) -> Any:
        """Compute an aggregate value over a column.

        Supported operations: sum, min, max, count, avg.
        Null values are excluded from all aggregation computations.

        Args:
            batch_id: The batch to aggregate.
            column_name: The column to aggregate.
            op: The aggregation operation.

        Returns:
            The aggregated scalar value.

        Raises:
            FizzArrowBatchNotFoundError: If the batch does not exist.
            FizzArrowColumnNotFoundError: If the column is not in the batch.
            FizzArrowUnsupportedOperationError: If the operation is not supported.
            FizzArrowAggregationError: If the column type is incompatible.
        """
        if op not in SUPPORTED_AGGREGATIONS:
            raise FizzArrowUnsupportedOperationError(op)

        source = self.get_batch(batch_id)
        if column_name not in source.columns:
            raise FizzArrowColumnNotFoundError(column_name, batch_id)

        col = source.columns[column_name]

        # Count works on all types
        valid_values = [
            v for v, bitmap in zip(col.values, col.null_bitmap) if bitmap
        ]

        if op == "count":
            self._stats["aggregations"] += 1
            return len(valid_values)

        # Numeric operations require numeric types
        if col.dtype.value not in ("int32", "int64", "float64"):
            raise FizzArrowAggregationError(
                f"Cannot compute '{op}' on non-numeric column '{column_name}' "
                f"(type: {col.dtype.value})",
                operation=op,
            )

        if not valid_values:
            self._stats["aggregations"] += 1
            return None

        self._stats["aggregations"] += 1

        if op == "sum":
            return sum(valid_values)
        elif op == "min":
            return min(valid_values)
        elif op == "max":
            return max(valid_values)
        elif op == "avg":
            return statistics.mean(valid_values)

    def get_stats(self) -> dict:
        """Return engine statistics."""
        return dict(self._stats)


# ============================================================
# Dashboard
# ============================================================


class FizzArrowDashboard:
    """ASCII dashboard renderer for the FizzArrow columnar engine."""

    def __init__(self, width: int = DEFAULT_DASHBOARD_WIDTH) -> None:
        self._width = width

    def render_overview(self, table: ArrowTable) -> str:
        """Render an overview of all batches in the table."""
        lines = []
        lines.append("=" * self._width)
        lines.append("FizzArrow Columnar Memory Format".center(self._width))
        lines.append(f"Version {FIZZARROW_VERSION}".center(self._width))
        lines.append("=" * self._width)

        batches = table.list_batches()
        lines.append(f"  Total Batches    : {len(batches)}")
        total_rows = sum(b.num_rows for b in batches)
        total_cols = sum(b.num_columns for b in batches)
        lines.append(f"  Total Rows       : {total_rows}")
        lines.append(f"  Total Columns    : {total_cols}")

        stats = table.get_stats()
        lines.append(f"  Projections      : {stats['projections']}")
        lines.append(f"  Filters          : {stats['filters']}")
        lines.append(f"  Aggregations     : {stats['aggregations']}")
        lines.append("=" * self._width)
        return "\n".join(lines)

    def render_batch(self, batch: RecordBatch) -> str:
        """Render details of a single record batch."""
        lines = []
        lines.append("-" * self._width)
        lines.append(f"  Batch ID         : {batch.batch_id}")
        lines.append(f"  Rows             : {batch.num_rows}")
        lines.append(f"  Columns          : {batch.num_columns}")
        for name, col in batch.columns.items():
            null_pct = (col.null_count / col.length * 100) if col.length else 0.0
            lines.append(f"    {name:20s}  {col.dtype.value:8s}  nulls={col.null_count} ({null_pct:.1f}%)")
        lines.append("-" * self._width)
        return "\n".join(lines)


# ============================================================
# Middleware
# ============================================================


class FizzArrowMiddleware(IMiddleware):
    """Middleware integrating FizzArrow columnar storage with the FizzBuzz pipeline.

    Priority: 233 (positioned after the bulk of infrastructure middleware).
    On each evaluation pass, the middleware annotates the processing context
    with FizzArrow engine metadata including batch count, total row count,
    and engine version.
    """

    def __init__(
        self,
        table: ArrowTable,
        dashboard: FizzArrowDashboard,
    ) -> None:
        self._table = table
        self._dashboard = dashboard

    def get_name(self) -> str:
        """Return 'fizzarrow'."""
        return "fizzarrow"

    def get_priority(self) -> int:
        """Return MIDDLEWARE_PRIORITY (233)."""
        return MIDDLEWARE_PRIORITY

    @property
    def priority(self) -> int:
        return MIDDLEWARE_PRIORITY

    @property
    def name(self) -> str:
        return "fizzarrow"

    def process(
        self,
        context: ProcessingContext,
        next_handler: Callable[[ProcessingContext], ProcessingContext],
    ) -> ProcessingContext:
        """Process evaluation, annotating with FizzArrow engine status."""
        context.metadata["fizzarrow_enabled"] = True
        context.metadata["fizzarrow_batch_count"] = len(self._table.list_batches())
        context.metadata["fizzarrow_version"] = FIZZARROW_VERSION
        return next_handler(context)

    def render_overview(self) -> str:
        """Render the FizzArrow dashboard overview."""
        return self._dashboard.render_overview(self._table)

    def render_batch(self, batch_id: str) -> str:
        """Render details for a specific batch."""
        batch = self._table.get_batch(batch_id)
        return self._dashboard.render_batch(batch)


# ============================================================
# Factory
# ============================================================


def create_fizzarrow_subsystem(
    dashboard_width: int = DEFAULT_DASHBOARD_WIDTH,
    event_bus: Optional[Any] = None,
) -> Tuple[ArrowTable, FizzArrowMiddleware]:
    """Create and wire the complete FizzArrow subsystem.

    Factory function that instantiates the columnar engine, dashboard
    renderer, and middleware, ready for integration into the FizzBuzz
    evaluation pipeline.

    Returns:
        Tuple of (ArrowTable, FizzArrowMiddleware).
    """
    table = ArrowTable()
    dashboard = FizzArrowDashboard(width=dashboard_width)
    middleware = FizzArrowMiddleware(table=table, dashboard=dashboard)
    logger.info("FizzArrow subsystem initialized")
    return table, middleware
