"""
Enterprise FizzBuzz Platform - FizzColumn — Columnar Storage Engine Exceptions
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from ._base import FizzBuzzError


class ColumnarStorageError(FizzBuzzError):
    """Base exception for all columnar storage engine errors.

    The columnar storage engine provides Parquet-style column-oriented
    storage with dictionary, RLE, and delta encoding for FizzBuzz
    evaluation results. When column operations fail — whether during
    encoding, row group management, or Parquet export — this hierarchy
    provides precise diagnostic information for the storage reliability
    engineering team.
    """

    def __init__(self, message: str, *, error_code: str = "EFP-CS00",
                 context: Optional[dict[str, Any]] = None) -> None:
        super().__init__(message, error_code=error_code, context=context)


class ColumnEncodingError(ColumnarStorageError):
    """Raised when a column encoding or decoding operation fails.

    Each column chunk is encoded using one of four strategies: PLAIN,
    DICTIONARY, RLE (run-length encoding), or DELTA. Encoding failures
    may occur when the input data is incompatible with the selected
    encoding — for example, attempting delta encoding on non-numeric
    data, or dictionary encoding when the cardinality exceeds the
    dictionary size limit. The encoder selection algorithm samples the
    first 1024 values to choose the optimal encoding; this error
    indicates the sample was not representative of the full dataset.
    """

    def __init__(self, encoding: str, column_name: str, detail: str) -> None:
        self.encoding = encoding
        self.column_name = column_name
        self.detail = detail
        super().__init__(
            f"Column encoding failure: {encoding} encoding on column "
            f"'{column_name}': {detail}. The columnar storage engine cannot "
            f"persist this column chunk until the encoding issue is resolved.",
            error_code="EFP-CS01",
            context={
                "encoding": encoding,
                "column_name": column_name,
                "detail": detail,
            },
        )


class RowGroupError(ColumnarStorageError):
    """Raised when a row group operation violates structural invariants.

    Row groups are immutable collections of column chunks that share
    the same row count. Once sealed, a row group's dimensions are
    fixed — attempting to add columns with mismatched row counts, or
    modifying a sealed row group, triggers this error. Row groups are
    the fundamental unit of I/O parallelism in the columnar engine;
    their structural integrity is non-negotiable.
    """

    def __init__(self, row_group_id: int, detail: str) -> None:
        self.row_group_id = row_group_id
        self.detail = detail
        super().__init__(
            f"Row group {row_group_id} structural violation: {detail}. "
            f"Row groups are immutable once sealed. This invariant ensures "
            f"predicate pushdown correctness via zone maps.",
            error_code="EFP-CS02",
            context={"row_group_id": row_group_id, "detail": detail},
        )


class ParquetExportError(ColumnarStorageError):
    """Raised when the Parquet binary export process encounters a failure.

    The Parquet exporter writes a binary file with PAR1 magic bytes,
    schema metadata, encoded column chunks with offsets, and a footer.
    Export failures may occur due to I/O errors, schema inconsistencies,
    or corrupted column chunk data. The resulting file would not be
    readable by any Parquet-compatible reader, which is unacceptable
    for enterprise-grade FizzBuzz data archival.
    """

    def __init__(self, path: str, detail: str) -> None:
        self.path = path
        self.detail = detail
        super().__init__(
            f"Parquet export failure to '{path}': {detail}. "
            f"The binary file may be incomplete or corrupted. "
            f"PAR1 magic byte integrity cannot be guaranteed.",
            error_code="EFP-CS03",
            context={"path": path, "detail": detail},
        )

