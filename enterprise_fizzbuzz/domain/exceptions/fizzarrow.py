"""
Enterprise FizzBuzz Platform - FizzArrow Columnar Memory Format Exceptions (EFP-ARW00 .. EFP-ARW14)

The FizzArrow subsystem manages in-memory columnar data representation for the
Enterprise FizzBuzz Platform.  When a schema cannot be validated, a batch cannot
be constructed, a column projection fails, or an aggregation encounters type
incompatibilities, these exceptions provide the diagnostic specificity required
to resolve data pipeline issues at the columnar storage layer.
"""

from __future__ import annotations

from typing import Any, Optional

from ._base import FizzBuzzError


class FizzArrowError(FizzBuzzError):
    """Base exception for all FizzArrow columnar memory format errors.

    When the FizzArrow engine encounters a malformed schema, a type
    mismatch in column data, or an invalid aggregation request, this
    exception (or one of its children) is raised.  The data engineer
    has been paged.  The column store is intact.
    """

    def __init__(
        self,
        message: str,
        *,
        error_code: str = "EFP-ARW00",
        context: Optional[dict[str, Any]] = None,
    ) -> None:
        super().__init__(message, error_code=error_code, context=context)


class FizzArrowSchemaError(FizzArrowError):
    """Raised when a schema definition is invalid or inconsistent.

    Schemas must contain at least one field and all field names must
    be unique.  Duplicate field names or empty schemas violate the
    columnar format specification.
    """

    def __init__(self, message: str) -> None:
        super().__init__(
            message,
            error_code="EFP-ARW01",
        )


class FizzArrowBatchError(FizzArrowError):
    """Raised when a record batch cannot be constructed or retrieved.

    Batch construction requires all columns to have the same number
    of rows and all column names to match the schema fields.
    """

    def __init__(self, message: str, *, batch_id: Optional[str] = None) -> None:
        super().__init__(
            message,
            error_code="EFP-ARW02",
            context={"batch_id": batch_id},
        )
        self.batch_id = batch_id


class FizzArrowBatchNotFoundError(FizzArrowError):
    """Raised when a referenced record batch does not exist."""

    def __init__(self, batch_id: str) -> None:
        super().__init__(
            f"Record batch '{batch_id}' does not exist",
            error_code="EFP-ARW03",
            context={"batch_id": batch_id},
        )
        self.batch_id = batch_id


class FizzArrowColumnNotFoundError(FizzArrowError):
    """Raised when a referenced column does not exist in a record batch."""

    def __init__(self, column_name: str, batch_id: str) -> None:
        super().__init__(
            f"Column '{column_name}' not found in batch '{batch_id}'",
            error_code="EFP-ARW04",
            context={"column_name": column_name, "batch_id": batch_id},
        )
        self.column_name = column_name
        self.batch_id = batch_id


class FizzArrowTypeMismatchError(FizzArrowError):
    """Raised when column data does not match the declared data type."""

    def __init__(self, column_name: str, expected: str, actual: str) -> None:
        super().__init__(
            f"Type mismatch in column '{column_name}': expected {expected}, got {actual}",
            error_code="EFP-ARW05",
            context={"column_name": column_name, "expected": expected, "actual": actual},
        )
        self.column_name = column_name


class FizzArrowAggregationError(FizzArrowError):
    """Raised when an aggregation operation fails.

    Aggregation operations require numeric column types for sum, min,
    max, and avg operations.  Attempting to aggregate non-numeric data
    triggers this exception.
    """

    def __init__(self, message: str, *, operation: Optional[str] = None) -> None:
        super().__init__(
            message,
            error_code="EFP-ARW06",
            context={"operation": operation},
        )
        self.operation = operation


class FizzArrowFilterError(FizzArrowError):
    """Raised when a filter predicate cannot be applied to a column."""

    def __init__(self, message: str) -> None:
        super().__init__(
            message,
            error_code="EFP-ARW07",
        )


class FizzArrowNullBitmapError(FizzArrowError):
    """Raised when a null bitmap is inconsistent with column length."""

    def __init__(self, column_name: str, expected_len: int, actual_len: int) -> None:
        super().__init__(
            f"Null bitmap length mismatch in column '{column_name}': "
            f"expected {expected_len}, got {actual_len}",
            error_code="EFP-ARW08",
            context={"column_name": column_name, "expected_len": expected_len, "actual_len": actual_len},
        )
        self.column_name = column_name


class FizzArrowEmptyBatchError(FizzArrowError):
    """Raised when an operation requires a non-empty batch but receives one with zero rows."""

    def __init__(self, batch_id: str) -> None:
        super().__init__(
            f"Record batch '{batch_id}' contains zero rows",
            error_code="EFP-ARW09",
            context={"batch_id": batch_id},
        )
        self.batch_id = batch_id


class FizzArrowRowCountMismatchError(FizzArrowError):
    """Raised when columns in a batch have differing row counts."""

    def __init__(self, column_name: str, expected_rows: int, actual_rows: int) -> None:
        super().__init__(
            f"Column '{column_name}' has {actual_rows} rows, expected {expected_rows}",
            error_code="EFP-ARW10",
            context={"column_name": column_name, "expected_rows": expected_rows, "actual_rows": actual_rows},
        )
        self.column_name = column_name


class FizzArrowUnsupportedOperationError(FizzArrowError):
    """Raised when an unsupported aggregation operation is requested."""

    def __init__(self, operation: str) -> None:
        super().__init__(
            f"Unsupported aggregation operation: '{operation}'",
            error_code="EFP-ARW11",
            context={"operation": operation},
        )
        self.operation = operation


class FizzArrowMiddlewareError(FizzArrowError):
    """Raised when the FizzArrow middleware encounters an internal error."""

    def __init__(self, message: str) -> None:
        super().__init__(
            message,
            error_code="EFP-ARW12",
        )


class FizzArrowDashboardError(FizzArrowError):
    """Raised when the FizzArrow dashboard rendering fails."""

    def __init__(self, message: str) -> None:
        super().__init__(
            message,
            error_code="EFP-ARW13",
        )


class FizzArrowDuplicateColumnError(FizzArrowError):
    """Raised when a batch contains duplicate column names."""

    def __init__(self, column_name: str) -> None:
        super().__init__(
            f"Duplicate column name: '{column_name}'",
            error_code="EFP-ARW14",
            context={"column_name": column_name},
        )
        self.column_name = column_name
