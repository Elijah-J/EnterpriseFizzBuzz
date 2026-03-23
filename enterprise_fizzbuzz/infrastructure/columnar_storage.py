"""
Enterprise FizzBuzz Platform - FizzColumn Columnar Storage Engine

Provides Parquet-style column-oriented storage with four encoding
strategies (PLAIN, DICTIONARY, RLE, DELTA), zone maps for predicate
pushdown, vectorized batch processing with selection bitmasks, and
binary Parquet export with PAR1 magic bytes.

Because storing FizzBuzz results row-by-row is a data warehousing
anti-pattern. Columnar storage unlocks vectorized SIMD-style
processing, superior compression ratios through value locality, and
zone-map-based predicate pushdown that can skip entire row groups
when the min/max statistics prove no matching rows exist. All of
this for a dataset that typically contains fewer than 100 rows and
exactly four distinct string values.
"""

from __future__ import annotations

import enum
import io
import json
import logging
import struct
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Optional, Sequence

from enterprise_fizzbuzz.domain.exceptions import (
    ColumnEncodingError,
    ColumnarStorageError,
    ParquetExportError,
    RowGroupError,
)
from enterprise_fizzbuzz.domain.interfaces import IMiddleware
from enterprise_fizzbuzz.domain.models import ProcessingContext

logger = logging.getLogger(__name__)


# ============================================================
# Column Encoding Enum
# ============================================================


class ColumnEncoding(enum.Enum):
    """Encoding strategies for column chunks.

    Each encoding exploits a different statistical property of the data:
    - PLAIN: No encoding. Raw values. The null hypothesis of encodings.
    - DICTIONARY: Maps distinct values to integer codes. Optimal when
      cardinality is low (e.g., "Fizz", "Buzz", "FizzBuzz", or the number).
    - RLE: Run-length encoding. Stores (value, run_length) pairs.
      Optimal for sorted or clustered columns.
    - DELTA: Stores first value plus successive differences. Optimal
      for monotonically increasing sequences like input numbers.
    """

    PLAIN = "PLAIN"
    DICTIONARY = "DICTIONARY"
    RLE = "RLE"
    DELTA = "DELTA"


# ============================================================
# Column Type Enum
# ============================================================


class ColumnType(enum.Enum):
    """Supported column data types in the columnar storage engine."""

    INT64 = "INT64"
    STRING = "STRING"
    FLOAT64 = "FLOAT64"
    BOOLEAN = "BOOLEAN"


# ============================================================
# ZoneMap — Min/Max Statistics for Predicate Pushdown
# ============================================================


@dataclass
class ZoneMap:
    """Min/max statistics for a column chunk, enabling predicate pushdown.

    Zone maps allow the query engine to skip entire row groups when the
    predicate cannot possibly match any value in the chunk. For example,
    if a zone map shows min=50, max=75 and the predicate is number < 10,
    the entire row group can be pruned without reading a single value.

    This optimization is critical for FizzBuzz workloads where the
    evaluation range rarely exceeds three digits, making zone map
    overhead approximately 1000x the useful data size.
    """

    min_value: Any = None
    max_value: Any = None
    null_count: int = 0
    distinct_count: int = 0

    def can_contain(self, predicate_min: Any = None,
                    predicate_max: Any = None) -> bool:
        """Check if this zone map's range could satisfy a range predicate.

        Returns True if the zone map range overlaps with the predicate
        range. Returns True conservatively when types are incompatible
        or values are None (cannot prove non-overlap).
        """
        if self.min_value is None or self.max_value is None:
            return True  # Conservative: cannot prove absence

        try:
            if predicate_min is not None and self.max_value < predicate_min:
                return False  # All values below predicate minimum
            if predicate_max is not None and self.min_value > predicate_max:
                return False  # All values above predicate maximum
        except TypeError:
            return True  # Incomparable types — conservative fallback

        return True

    def merge(self, other: ZoneMap) -> ZoneMap:
        """Merge two zone maps, producing a zone map spanning both ranges."""
        new_min = self.min_value
        new_max = self.max_value

        if other.min_value is not None:
            if new_min is None:
                new_min = other.min_value
            else:
                try:
                    new_min = min(new_min, other.min_value)
                except TypeError:
                    pass

        if other.max_value is not None:
            if new_max is None:
                new_max = other.max_value
            else:
                try:
                    new_max = max(new_max, other.max_value)
                except TypeError:
                    pass

        return ZoneMap(
            min_value=new_min,
            max_value=new_max,
            null_count=self.null_count + other.null_count,
            distinct_count=max(self.distinct_count, other.distinct_count),
        )


# ============================================================
# Column — Typed Values with Null Bitmap
# ============================================================


@dataclass
class Column:
    """A typed column of values with a null bitmap.

    Each column has a name, a data type, and an ordered sequence of
    values. The null bitmap tracks which positions contain null values
    (represented as None in the values list). This separation of
    null tracking from value storage mirrors the Apache Arrow memory
    layout, because FizzBuzz results deserve the same memory
    representation as petabyte-scale analytics workloads.
    """

    name: str
    dtype: ColumnType
    values: list[Any] = field(default_factory=list)
    null_bitmap: list[bool] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.null_bitmap and self.values:
            self.null_bitmap = [v is not None for v in self.values]

    def append(self, value: Any) -> None:
        """Append a value to the column."""
        self.values.append(value)
        self.null_bitmap.append(value is not None)

    def __len__(self) -> int:
        return len(self.values)

    @property
    def non_null_count(self) -> int:
        """Number of non-null values."""
        return sum(self.null_bitmap)

    @property
    def null_count(self) -> int:
        """Number of null values."""
        return len(self.values) - self.non_null_count

    def compute_zone_map(self) -> ZoneMap:
        """Compute zone map statistics for this column."""
        non_null_values = [v for v, valid in zip(self.values, self.null_bitmap) if valid]

        if not non_null_values:
            return ZoneMap(null_count=self.null_count, distinct_count=0)

        try:
            min_val = min(non_null_values)
            max_val = max(non_null_values)
        except TypeError:
            min_val = non_null_values[0]
            max_val = non_null_values[-1]

        distinct = len(set(str(v) for v in non_null_values))

        return ZoneMap(
            min_value=min_val,
            max_value=max_val,
            null_count=self.null_count,
            distinct_count=distinct,
        )


# ============================================================
# Encoding / Decoding Functions
# ============================================================


def encode_plain(values: list[Any], dtype: ColumnType) -> bytes:
    """Encode values using PLAIN encoding — raw serialization.

    No compression, no cleverness, no dignity. Each value is stored
    in its native binary representation. This is the encoding of last
    resort, used when the data resists all attempts at compression.
    """
    buf = io.BytesIO()
    buf.write(struct.pack("<I", len(values)))

    for v in values:
        if v is None:
            buf.write(struct.pack("<B", 0))  # null marker
        else:
            buf.write(struct.pack("<B", 1))  # non-null marker
            if dtype == ColumnType.INT64:
                buf.write(struct.pack("<q", int(v)))
            elif dtype == ColumnType.FLOAT64:
                buf.write(struct.pack("<d", float(v)))
            elif dtype == ColumnType.BOOLEAN:
                buf.write(struct.pack("<B", 1 if v else 0))
            elif dtype == ColumnType.STRING:
                encoded = str(v).encode("utf-8")
                buf.write(struct.pack("<I", len(encoded)))
                buf.write(encoded)

    return buf.getvalue()


def decode_plain(data: bytes, dtype: ColumnType) -> list[Any]:
    """Decode PLAIN-encoded column data."""
    buf = io.BytesIO(data)
    count = struct.unpack("<I", buf.read(4))[0]
    values: list[Any] = []

    for _ in range(count):
        marker = struct.unpack("<B", buf.read(1))[0]
        if marker == 0:
            values.append(None)
        else:
            if dtype == ColumnType.INT64:
                values.append(struct.unpack("<q", buf.read(8))[0])
            elif dtype == ColumnType.FLOAT64:
                values.append(struct.unpack("<d", buf.read(8))[0])
            elif dtype == ColumnType.BOOLEAN:
                values.append(bool(struct.unpack("<B", buf.read(1))[0]))
            elif dtype == ColumnType.STRING:
                slen = struct.unpack("<I", buf.read(4))[0]
                values.append(buf.read(slen).decode("utf-8"))

    return values


def encode_dictionary(values: list[Any], dtype: ColumnType) -> bytes:
    """Encode values using DICTIONARY encoding.

    Maps each distinct value to an integer code and stores:
    1. The dictionary (ordered list of distinct values)
    2. The code array (integer indices into the dictionary)

    This encoding is optimal when cardinality is low — for FizzBuzz,
    the label column typically has cardinality 4 ("Fizz", "Buzz",
    "FizzBuzz", and the number itself). A dictionary of 4 entries
    reducing each value to a 2-bit code represents a compression
    breakthrough of the highest order.
    """
    # Build dictionary
    dictionary: list[Any] = []
    code_map: dict[str, int] = {}

    for v in values:
        key = str(v) if v is not None else "__NULL__"
        if key not in code_map:
            code_map[key] = len(dictionary)
            dictionary.append(v)

    # Encode
    buf = io.BytesIO()

    # Write dictionary size
    buf.write(struct.pack("<I", len(dictionary)))

    # Write dictionary entries
    for entry in dictionary:
        if entry is None:
            buf.write(struct.pack("<B", 0))
        else:
            buf.write(struct.pack("<B", 1))
            encoded = str(entry).encode("utf-8")
            buf.write(struct.pack("<I", len(encoded)))
            buf.write(encoded)

    # Write codes
    buf.write(struct.pack("<I", len(values)))
    for v in values:
        key = str(v) if v is not None else "__NULL__"
        buf.write(struct.pack("<H", code_map[key]))

    return buf.getvalue()


def decode_dictionary(data: bytes, dtype: ColumnType) -> list[Any]:
    """Decode DICTIONARY-encoded column data."""
    buf = io.BytesIO(data)

    # Read dictionary
    dict_size = struct.unpack("<I", buf.read(4))[0]
    dictionary: list[Any] = []
    for _ in range(dict_size):
        marker = struct.unpack("<B", buf.read(1))[0]
        if marker == 0:
            dictionary.append(None)
        else:
            slen = struct.unpack("<I", buf.read(4))[0]
            val_str = buf.read(slen).decode("utf-8")
            if dtype == ColumnType.INT64:
                try:
                    dictionary.append(int(val_str))
                except ValueError:
                    dictionary.append(val_str)
            elif dtype == ColumnType.FLOAT64:
                try:
                    dictionary.append(float(val_str))
                except ValueError:
                    dictionary.append(val_str)
            elif dtype == ColumnType.BOOLEAN:
                dictionary.append(val_str.lower() in ("true", "1"))
            else:
                dictionary.append(val_str)

    # Read codes
    count = struct.unpack("<I", buf.read(4))[0]
    values: list[Any] = []
    for _ in range(count):
        code = struct.unpack("<H", buf.read(2))[0]
        values.append(dictionary[code])

    return values


def encode_rle(values: list[Any], dtype: ColumnType) -> bytes:
    """Encode values using Run-Length Encoding (RLE).

    Stores (value, run_length) pairs. Optimal for sorted or clustered
    columns where consecutive values are identical. For a perfectly
    sorted FizzBuzz output, this encoding achieves remarkable
    compression: all the "Fizz" values collapse into a single pair,
    all the "Buzz" values into another, and so forth.

    Of course, FizzBuzz output is never sorted by label, which makes
    RLE approximately the worst possible encoding choice. The auto-
    selector will never pick it. But we implement it anyway, because
    completeness is a virtue.
    """
    buf = io.BytesIO()

    if not values:
        buf.write(struct.pack("<I", 0))
        return buf.getvalue()

    # Build runs
    runs: list[tuple[Any, int]] = []
    current_val = values[0]
    current_count = 1

    for v in values[1:]:
        if v == current_val:
            current_count += 1
        else:
            runs.append((current_val, current_count))
            current_val = v
            current_count = 1
    runs.append((current_val, current_count))

    # Write run count
    buf.write(struct.pack("<I", len(runs)))

    # Write each run
    for val, count in runs:
        if val is None:
            buf.write(struct.pack("<B", 0))
        else:
            buf.write(struct.pack("<B", 1))
            encoded = str(val).encode("utf-8")
            buf.write(struct.pack("<I", len(encoded)))
            buf.write(encoded)
        buf.write(struct.pack("<I", count))

    return buf.getvalue()


def decode_rle(data: bytes, dtype: ColumnType) -> list[Any]:
    """Decode RLE-encoded column data."""
    buf = io.BytesIO(data)
    run_count = struct.unpack("<I", buf.read(4))[0]
    values: list[Any] = []

    for _ in range(run_count):
        marker = struct.unpack("<B", buf.read(1))[0]
        if marker == 0:
            val = None
        else:
            slen = struct.unpack("<I", buf.read(4))[0]
            val_str = buf.read(slen).decode("utf-8")
            if dtype == ColumnType.INT64:
                try:
                    val = int(val_str)
                except ValueError:
                    val = val_str
            elif dtype == ColumnType.FLOAT64:
                try:
                    val = float(val_str)
                except ValueError:
                    val = val_str
            elif dtype == ColumnType.BOOLEAN:
                val = val_str.lower() in ("true", "1")
            else:
                val = val_str

        count = struct.unpack("<I", buf.read(4))[0]
        values.extend([val] * count)

    return values


def encode_delta(values: list[Any], dtype: ColumnType) -> bytes:
    """Encode values using DELTA encoding.

    Stores the first value followed by successive differences. Optimal
    for monotonically increasing sequences — such as the input number
    column in FizzBuzz, which goes 1, 2, 3, ..., N. The delta sequence
    is [1, 1, 1, ...], which compresses beautifully. This is the
    one encoding that actually makes sense for FizzBuzz input data.

    Only applicable to numeric columns. Falls back to PLAIN for
    non-numeric data, because you cannot compute deltas on strings.
    (You could compute edit distances, but we have standards.)
    """
    buf = io.BytesIO()

    if not values:
        buf.write(struct.pack("<I", 0))
        return buf.getvalue()

    # Filter nulls — delta encoding does not support nulls inline
    numeric_values: list[int] = []
    null_positions: list[int] = []

    for i, v in enumerate(values):
        if v is None:
            null_positions.append(i)
        else:
            numeric_values.append(int(v))

    # Write count
    buf.write(struct.pack("<I", len(values)))

    # Write null position count and positions
    buf.write(struct.pack("<I", len(null_positions)))
    for pos in null_positions:
        buf.write(struct.pack("<I", pos))

    if not numeric_values:
        return buf.getvalue()

    # Write first value
    buf.write(struct.pack("<q", numeric_values[0]))

    # Write deltas
    buf.write(struct.pack("<I", len(numeric_values) - 1))
    for i in range(1, len(numeric_values)):
        delta = numeric_values[i] - numeric_values[i - 1]
        buf.write(struct.pack("<q", delta))

    return buf.getvalue()


def decode_delta(data: bytes, dtype: ColumnType) -> list[Any]:
    """Decode DELTA-encoded column data."""
    buf = io.BytesIO(data)
    total_count = struct.unpack("<I", buf.read(4))[0]

    if total_count == 0:
        return []

    # Read null positions
    null_count = struct.unpack("<I", buf.read(4))[0]
    null_positions = set()
    for _ in range(null_count):
        null_positions.add(struct.unpack("<I", buf.read(4))[0])

    numeric_count = total_count - null_count
    if numeric_count == 0:
        return [None] * total_count

    # Read first value
    first_value = struct.unpack("<q", buf.read(8))[0]

    # Read deltas
    delta_count = struct.unpack("<I", buf.read(4))[0]
    deltas = []
    for _ in range(delta_count):
        deltas.append(struct.unpack("<q", buf.read(8))[0])

    # Reconstruct numeric values
    numeric_values = [first_value]
    current = first_value
    for d in deltas:
        current += d
        numeric_values.append(current)

    # Merge with nulls
    values: list[Any] = []
    numeric_idx = 0
    for i in range(total_count):
        if i in null_positions:
            values.append(None)
        else:
            values.append(numeric_values[numeric_idx])
            numeric_idx += 1

    return values


# Encoder/decoder registry
_ENCODERS: dict[ColumnEncoding, Callable] = {
    ColumnEncoding.PLAIN: encode_plain,
    ColumnEncoding.DICTIONARY: encode_dictionary,
    ColumnEncoding.RLE: encode_rle,
    ColumnEncoding.DELTA: encode_delta,
}

_DECODERS: dict[ColumnEncoding, Callable] = {
    ColumnEncoding.PLAIN: decode_plain,
    ColumnEncoding.DICTIONARY: decode_dictionary,
    ColumnEncoding.RLE: decode_rle,
    ColumnEncoding.DELTA: decode_delta,
}


# ============================================================
# ColumnChunk — Encoded Segment with Zone Map
# ============================================================


@dataclass
class ColumnChunk:
    """An encoded column segment with associated zone map statistics.

    A column chunk is the encoded representation of a column within a
    row group. It stores the raw encoded bytes, the encoding used, the
    column metadata, and the zone map statistics that enable predicate
    pushdown. Column chunks are immutable once created — the encoder
    has spoken and its verdict is final.
    """

    column_name: str
    dtype: ColumnType
    encoding: ColumnEncoding
    encoded_data: bytes
    num_values: int
    zone_map: ZoneMap
    uncompressed_size: int = 0

    @property
    def compressed_size(self) -> int:
        """Size of the encoded data in bytes."""
        return len(self.encoded_data)

    @property
    def compression_ratio(self) -> float:
        """Compression ratio: uncompressed_size / compressed_size."""
        if self.compressed_size == 0:
            return 1.0
        return self.uncompressed_size / self.compressed_size

    def decode(self) -> list[Any]:
        """Decode this chunk back to raw values."""
        decoder = _DECODERS.get(self.encoding)
        if decoder is None:
            raise ColumnEncodingError(
                self.encoding.value, self.column_name,
                f"No decoder registered for encoding {self.encoding.value}")
        return decoder(self.encoded_data, self.dtype)


def encode_column(column: Column, encoding: ColumnEncoding) -> ColumnChunk:
    """Encode a Column into a ColumnChunk using the specified encoding."""
    encoder = _ENCODERS.get(encoding)
    if encoder is None:
        raise ColumnEncodingError(
            encoding.value, column.name,
            f"No encoder registered for encoding {encoding.value}")

    # Compute uncompressed size estimate
    if column.dtype == ColumnType.INT64:
        uncompressed = len(column.values) * 8
    elif column.dtype == ColumnType.FLOAT64:
        uncompressed = len(column.values) * 8
    elif column.dtype == ColumnType.BOOLEAN:
        uncompressed = len(column.values)
    elif column.dtype == ColumnType.STRING:
        uncompressed = sum(len(str(v).encode("utf-8")) if v is not None else 0
                          for v in column.values)
    else:
        uncompressed = len(column.values) * 8

    try:
        encoded = encoder(column.values, column.dtype)
    except Exception as e:
        raise ColumnEncodingError(
            encoding.value, column.name, str(e))

    zone_map = column.compute_zone_map()

    return ColumnChunk(
        column_name=column.name,
        dtype=column.dtype,
        encoding=encoding,
        encoded_data=encoded,
        num_values=len(column.values),
        zone_map=zone_map,
        uncompressed_size=uncompressed,
    )


# ============================================================
# Encoding Auto-Selection
# ============================================================


def select_best_encoding(
    column: Column,
    sample_size: int = 1024,
    dictionary_cardinality_limit: int = 256,
) -> ColumnEncoding:
    """Auto-select the best encoding for a column by trial compression.

    Samples the first `sample_size` values, encodes them with all four
    strategies, and picks the one producing the smallest output. This
    is the encoding equivalent of trying on four outfits and picking
    the most flattering — except here "flattering" means "smallest
    byte count."

    Special rules:
    - DELTA is only tried for INT64 and FLOAT64 columns.
    - DICTIONARY is rejected if cardinality exceeds the limit.
    """
    sample_values = column.values[:sample_size]
    sample_col = Column(
        name=column.name,
        dtype=column.dtype,
        values=sample_values,
    )

    candidates: list[tuple[ColumnEncoding, int]] = []

    # Always try PLAIN
    try:
        plain_data = encode_plain(sample_values, column.dtype)
        candidates.append((ColumnEncoding.PLAIN, len(plain_data)))
    except Exception:
        pass

    # Try DICTIONARY if cardinality is within limit
    non_null = [v for v in sample_values if v is not None]
    distinct_count = len(set(str(v) for v in non_null)) if non_null else 0

    if distinct_count <= dictionary_cardinality_limit:
        try:
            dict_data = encode_dictionary(sample_values, column.dtype)
            candidates.append((ColumnEncoding.DICTIONARY, len(dict_data)))
        except Exception:
            pass

    # Try RLE
    try:
        rle_data = encode_rle(sample_values, column.dtype)
        candidates.append((ColumnEncoding.RLE, len(rle_data)))
    except Exception:
        pass

    # Try DELTA for numeric types only
    if column.dtype in (ColumnType.INT64, ColumnType.FLOAT64):
        try:
            delta_data = encode_delta(sample_values, column.dtype)
            candidates.append((ColumnEncoding.DELTA, len(delta_data)))
        except Exception:
            pass

    if not candidates:
        return ColumnEncoding.PLAIN

    # Pick the smallest
    candidates.sort(key=lambda x: x[1])
    return candidates[0][0]


# ============================================================
# RowGroup — Immutable Collection of Column Chunks
# ============================================================


@dataclass
class RowGroup:
    """An immutable collection of column chunks sharing the same row count.

    Row groups are the primary unit of I/O parallelism in the columnar
    storage engine. Each row group contains one chunk per column, all
    with the same number of rows. Once sealed, a row group cannot be
    modified — this immutability guarantee is essential for zone map
    correctness and concurrent read access.

    Row groups in Apache Parquet typically contain 128MB of data. Our
    row groups typically contain 128 bytes of data, because we are
    storing the output of a modulo operation, but the structural
    dignity remains intact.
    """

    row_group_id: int
    chunks: dict[str, ColumnChunk] = field(default_factory=dict)
    num_rows: int = 0
    sealed: bool = False
    created_at: float = field(default_factory=time.time)

    def add_chunk(self, chunk: ColumnChunk) -> None:
        """Add a column chunk to this row group."""
        if self.sealed:
            raise RowGroupError(
                self.row_group_id,
                f"Cannot add chunk '{chunk.column_name}' to sealed row group")

        if self.chunks and chunk.num_values != self.num_rows:
            raise RowGroupError(
                self.row_group_id,
                f"Row count mismatch: existing chunks have {self.num_rows} rows "
                f"but '{chunk.column_name}' has {chunk.num_values} rows")

        if not self.chunks:
            self.num_rows = chunk.num_values

        self.chunks[chunk.column_name] = chunk

    def seal(self) -> None:
        """Seal this row group, preventing further modifications."""
        self.sealed = True

    @property
    def total_compressed_size(self) -> int:
        """Total compressed size of all column chunks."""
        return sum(c.compressed_size for c in self.chunks.values())

    @property
    def total_uncompressed_size(self) -> int:
        """Total uncompressed size of all column chunks."""
        return sum(c.uncompressed_size for c in self.chunks.values())

    @property
    def compression_ratio(self) -> float:
        """Overall compression ratio for this row group."""
        if self.total_compressed_size == 0:
            return 1.0
        return self.total_uncompressed_size / self.total_compressed_size

    def get_zone_map(self, column_name: str) -> Optional[ZoneMap]:
        """Get the zone map for a specific column."""
        chunk = self.chunks.get(column_name)
        return chunk.zone_map if chunk else None


# ============================================================
# VectorizedBatch — 1024-Value Slice with Selection Bitmask
# ============================================================


@dataclass
class VectorizedBatch:
    """A batch of up to 1024 values with a selection bitmask for filtering.

    Vectorized processing operates on batches rather than individual
    rows, enabling SIMD-style parallelism (simulated, naturally, since
    Python's GIL makes actual SIMD parallelism approximately as likely
    as a FizzBuzz evaluation taking more than one nanosecond).

    The selection bitmask allows filtering without copying: values at
    positions where the bitmask is False are logically invisible to
    downstream operators, but physically present in the array. This
    avoids the allocation overhead of creating a new array for each
    filter operation — a critical optimization when your total dataset
    is 100 integers.
    """

    BATCH_SIZE: int = 1024

    columns: dict[str, list[Any]] = field(default_factory=dict)
    selection_mask: list[bool] = field(default_factory=list)
    num_rows: int = 0

    @classmethod
    def from_row_group(cls, row_group: RowGroup,
                       column_names: Optional[list[str]] = None) -> VectorizedBatch:
        """Create a VectorizedBatch from a RowGroup, decoding column chunks."""
        batch = cls()
        names = column_names or list(row_group.chunks.keys())

        for name in names:
            chunk = row_group.chunks.get(name)
            if chunk is not None:
                batch.columns[name] = chunk.decode()
                batch.num_rows = chunk.num_values

        batch.selection_mask = [True] * batch.num_rows
        return batch

    def apply_filter(self, column_name: str,
                     predicate: Callable[[Any], bool]) -> VectorizedBatch:
        """Apply a predicate filter, updating the selection bitmask.

        Does NOT copy data. Instead, the selection mask is updated
        to exclude values that don't match the predicate. This is
        vectorized in spirit if not in implementation.
        """
        col = self.columns.get(column_name)
        if col is None:
            return self

        new_mask = list(self.selection_mask)
        for i in range(self.num_rows):
            if new_mask[i]:
                try:
                    if not predicate(col[i]):
                        new_mask[i] = False
                except (TypeError, ValueError):
                    new_mask[i] = False

        result = VectorizedBatch(
            columns=self.columns,
            selection_mask=new_mask,
            num_rows=self.num_rows,
        )
        return result

    def selected_values(self, column_name: str) -> list[Any]:
        """Return only the values that pass the selection mask."""
        col = self.columns.get(column_name, [])
        return [v for v, selected in zip(col, self.selection_mask) if selected]

    @property
    def selected_count(self) -> int:
        """Number of rows passing the selection mask."""
        return sum(self.selection_mask)

    def materialize(self) -> dict[str, list[Any]]:
        """Materialize selected rows into a new dict of lists."""
        result: dict[str, list[Any]] = {}
        for name, col in self.columns.items():
            result[name] = [v for v, s in zip(col, self.selection_mask) if s]
        return result


# ============================================================
# ColumnStore — Manages Row Groups and Active Buffer
# ============================================================


class ColumnStore:
    """The primary columnar storage engine.

    Manages a collection of sealed row groups plus an active buffer
    that accumulates values until the row group size threshold is
    reached. When the active buffer fills, it is encoded, sealed
    into a row group, and added to the archive.

    The ColumnStore also handles encoding auto-selection, zone map
    aggregation, and vectorized batch construction.
    """

    def __init__(
        self,
        row_group_size: int = 1024,
        encoding_sample_size: int = 1024,
        dictionary_cardinality_limit: int = 256,
    ) -> None:
        self._row_group_size = row_group_size
        self._encoding_sample_size = encoding_sample_size
        self._dictionary_cardinality_limit = dictionary_cardinality_limit
        self._row_groups: list[RowGroup] = []
        self._active_columns: dict[str, Column] = {}
        self._schema: dict[str, ColumnType] = {}
        self._next_row_group_id: int = 0
        self._total_rows_ingested: int = 0
        self._encoding_selections: dict[str, ColumnEncoding] = {}

    @property
    def row_groups(self) -> list[RowGroup]:
        """Sealed row groups."""
        return list(self._row_groups)

    @property
    def active_row_count(self) -> int:
        """Number of rows in the active (unsaved) buffer."""
        if not self._active_columns:
            return 0
        return len(next(iter(self._active_columns.values())))

    @property
    def total_rows(self) -> int:
        """Total rows across all sealed row groups and the active buffer."""
        return sum(rg.num_rows for rg in self._row_groups) + self.active_row_count

    @property
    def total_rows_ingested(self) -> int:
        """Total rows ever ingested."""
        return self._total_rows_ingested

    @property
    def schema(self) -> dict[str, ColumnType]:
        """Current schema."""
        return dict(self._schema)

    def define_column(self, name: str, dtype: ColumnType) -> None:
        """Define a column in the schema."""
        self._schema[name] = dtype
        if name not in self._active_columns:
            self._active_columns[name] = Column(name=name, dtype=dtype)

    def append_row(self, values: dict[str, Any]) -> None:
        """Append a row of values to the active buffer.

        If the active buffer reaches the row group size threshold,
        it is automatically flushed into a sealed row group.
        """
        for col_name, dtype in self._schema.items():
            col = self._active_columns.get(col_name)
            if col is None:
                col = Column(name=col_name, dtype=dtype)
                self._active_columns[col_name] = col
            col.append(values.get(col_name))

        self._total_rows_ingested += 1

        # Check if we need to flush
        if self.active_row_count >= self._row_group_size:
            self.flush()

    def flush(self) -> Optional[RowGroup]:
        """Flush the active buffer into a sealed row group.

        Returns the newly created row group, or None if the buffer
        is empty.
        """
        if self.active_row_count == 0:
            return None

        row_group = RowGroup(row_group_id=self._next_row_group_id)
        self._next_row_group_id += 1

        for col_name, col in self._active_columns.items():
            # Auto-select encoding
            best_encoding = select_best_encoding(
                col,
                sample_size=self._encoding_sample_size,
                dictionary_cardinality_limit=self._dictionary_cardinality_limit,
            )
            self._encoding_selections[col_name] = best_encoding

            # Encode the column
            chunk = encode_column(col, best_encoding)
            row_group.add_chunk(chunk)

        row_group.seal()
        self._row_groups.append(row_group)

        # Reset active buffer
        self._active_columns = {
            name: Column(name=name, dtype=dtype)
            for name, dtype in self._schema.items()
        }

        logger.debug(
            "Flushed row group %d: %d rows, %d bytes compressed",
            row_group.row_group_id, row_group.num_rows,
            row_group.total_compressed_size)

        return row_group

    def scan(
        self,
        column_names: Optional[list[str]] = None,
        predicate_column: Optional[str] = None,
        predicate_min: Any = None,
        predicate_max: Any = None,
    ) -> list[VectorizedBatch]:
        """Scan the column store, returning vectorized batches.

        Uses zone maps for predicate pushdown: row groups whose zone
        map proves no matching rows exist are skipped entirely.

        Args:
            column_names: Columns to project (None = all columns).
            predicate_column: Column to apply range predicate on.
            predicate_min: Minimum value for range predicate.
            predicate_max: Maximum value for range predicate.

        Returns:
            List of VectorizedBatch objects.
        """
        batches: list[VectorizedBatch] = []

        for rg in self._row_groups:
            # Zone map pushdown
            if predicate_column is not None:
                zone_map = rg.get_zone_map(predicate_column)
                if zone_map is not None:
                    if not zone_map.can_contain(predicate_min, predicate_max):
                        logger.debug(
                            "Skipping row group %d: zone map pruned "
                            "(min=%s, max=%s, pred_min=%s, pred_max=%s)",
                            rg.row_group_id, zone_map.min_value,
                            zone_map.max_value, predicate_min, predicate_max)
                        continue

            batch = VectorizedBatch.from_row_group(rg, column_names)
            batches.append(batch)

        return batches

    def get_statistics(self) -> dict[str, Any]:
        """Get comprehensive storage statistics."""
        total_compressed = sum(rg.total_compressed_size for rg in self._row_groups)
        total_uncompressed = sum(rg.total_uncompressed_size for rg in self._row_groups)

        column_stats: dict[str, dict[str, Any]] = {}
        for col_name in self._schema:
            col_chunks = [rg.chunks[col_name] for rg in self._row_groups
                          if col_name in rg.chunks]
            if col_chunks:
                col_compressed = sum(c.compressed_size for c in col_chunks)
                col_uncompressed = sum(c.uncompressed_size for c in col_chunks)
                encodings_used = set(c.encoding.value for c in col_chunks)

                # Merge zone maps
                merged_zm = col_chunks[0].zone_map
                for c in col_chunks[1:]:
                    merged_zm = merged_zm.merge(c.zone_map)

                column_stats[col_name] = {
                    "dtype": self._schema[col_name].value,
                    "encoding": self._encoding_selections.get(col_name, ColumnEncoding.PLAIN).value,
                    "encodings_used": sorted(encodings_used),
                    "compressed_size": col_compressed,
                    "uncompressed_size": col_uncompressed,
                    "compression_ratio": col_uncompressed / col_compressed if col_compressed > 0 else 1.0,
                    "zone_map": {
                        "min": str(merged_zm.min_value),
                        "max": str(merged_zm.max_value),
                        "null_count": merged_zm.null_count,
                        "distinct_count": merged_zm.distinct_count,
                    },
                }

        return {
            "row_group_count": len(self._row_groups),
            "total_rows": self.total_rows,
            "total_rows_ingested": self._total_rows_ingested,
            "active_buffer_rows": self.active_row_count,
            "total_compressed_bytes": total_compressed,
            "total_uncompressed_bytes": total_uncompressed,
            "overall_compression_ratio": (
                total_uncompressed / total_compressed if total_compressed > 0 else 1.0
            ),
            "columns": column_stats,
        }


# ============================================================
# ParquetExporter — Binary Export with PAR1 Magic
# ============================================================


class ParquetExporter:
    """Exports the column store to a Parquet-compatible binary format.

    The output file follows the Parquet structure:
    1. PAR1 magic bytes (4 bytes)
    2. Schema metadata (JSON-encoded)
    3. Column chunks with offsets
    4. Footer with row group metadata
    5. Footer length (4 bytes, little-endian)
    6. PAR1 magic bytes (4 bytes)

    This is not a standards-compliant Apache Parquet file — reading
    it with PyArrow would cause a segfault, a stack overflow, and a
    sternly-worded Jira ticket. But the structural homage is genuine.
    """

    MAGIC = b"PAR1"

    @staticmethod
    def export(store: ColumnStore, path: str) -> int:
        """Export the column store to a binary Parquet-style file.

        Returns the total number of bytes written.
        """
        # Flush any remaining active data
        store.flush()

        if not store.row_groups:
            raise ParquetExportError(path, "No row groups to export")

        try:
            buf = io.BytesIO()

            # 1. Magic bytes
            buf.write(ParquetExporter.MAGIC)

            # 2. Schema metadata
            schema_meta = {
                "version": 1,
                "columns": {
                    name: dtype.value for name, dtype in store.schema.items()
                },
                "row_group_count": len(store.row_groups),
                "total_rows": store.total_rows,
                "created_by": "Enterprise FizzBuzz Platform - FizzColumn v1.0",
            }
            schema_json = json.dumps(schema_meta).encode("utf-8")
            buf.write(struct.pack("<I", len(schema_json)))
            buf.write(schema_json)

            # 3. Column chunks with offsets
            chunk_offsets: list[dict[str, Any]] = []

            for rg in store.row_groups:
                rg_offsets: dict[str, dict[str, Any]] = {}
                for col_name, chunk in rg.chunks.items():
                    offset = buf.tell()
                    buf.write(chunk.encoded_data)
                    rg_offsets[col_name] = {
                        "offset": offset,
                        "length": len(chunk.encoded_data),
                        "encoding": chunk.encoding.value,
                        "num_values": chunk.num_values,
                        "zone_map": {
                            "min": str(chunk.zone_map.min_value),
                            "max": str(chunk.zone_map.max_value),
                            "null_count": chunk.zone_map.null_count,
                            "distinct_count": chunk.zone_map.distinct_count,
                        },
                    }
                chunk_offsets.append({
                    "row_group_id": rg.row_group_id,
                    "num_rows": rg.num_rows,
                    "columns": rg_offsets,
                })

            # 4. Footer
            footer = {
                "row_groups": chunk_offsets,
                "schema": schema_meta,
            }
            footer_json = json.dumps(footer).encode("utf-8")
            footer_offset = buf.tell()
            buf.write(footer_json)

            # 5. Footer length
            footer_length = buf.tell() - footer_offset
            buf.write(struct.pack("<I", footer_length))

            # 6. Trailing magic bytes
            buf.write(ParquetExporter.MAGIC)

            # Write to file
            data = buf.getvalue()
            with open(path, "wb") as f:
                f.write(data)

            logger.info(
                "Exported %d row groups (%d rows) to %s (%d bytes)",
                len(store.row_groups), store.total_rows, path, len(data))

            return len(data)

        except (OSError, IOError) as e:
            raise ParquetExportError(path, str(e))

    @staticmethod
    def validate_file(path: str) -> dict[str, Any]:
        """Validate a Parquet-style file and return its metadata.

        Checks PAR1 magic bytes at start and end, reads the footer,
        and returns the schema and row group metadata.
        """
        try:
            with open(path, "rb") as f:
                data = f.read()
        except (OSError, IOError) as e:
            raise ParquetExportError(path, f"Cannot read file: {e}")

        if len(data) < 12:
            raise ParquetExportError(path, "File too small to be a valid Parquet file")

        # Check magic bytes
        if data[:4] != ParquetExporter.MAGIC:
            raise ParquetExportError(path, f"Missing PAR1 header magic (got {data[:4]!r})")

        if data[-4:] != ParquetExporter.MAGIC:
            raise ParquetExportError(path, f"Missing PAR1 footer magic (got {data[-4:]!r})")

        # Read footer length
        footer_length = struct.unpack("<I", data[-8:-4])[0]

        # Read footer
        footer_start = len(data) - 8 - footer_length
        footer_json = data[footer_start:footer_start + footer_length]

        try:
            footer = json.loads(footer_json.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            raise ParquetExportError(path, f"Corrupted footer: {e}")

        return footer


# ============================================================
# ColumnDashboard — ASCII Dashboard
# ============================================================


class ColumnDashboard:
    """Renders an ASCII dashboard for the columnar storage engine.

    Displays:
    - Column inventory with types and encodings
    - Compression ratios per column
    - Zone map summaries
    - Row group statistics
    - Storage efficiency metrics

    The dashboard width is configurable, because dashboard width
    preferences are the kind of thing that should absolutely be
    managed through a YAML configuration file with environment
    variable overrides.
    """

    @staticmethod
    def render(store: ColumnStore, width: int = 60) -> str:
        """Render the columnar storage dashboard."""
        stats = store.get_statistics()
        lines: list[str] = []

        border = "+" + "=" * (width - 2) + "+"
        thin_border = "+" + "-" * (width - 2) + "+"

        # Header
        lines.append("")
        lines.append(border)
        lines.append("|" + " FIZZCOLUMN COLUMNAR STORAGE ENGINE ".center(width - 2) + "|")
        lines.append("|" + " Parquet-Style Encoding | Vectorized Execution ".center(width - 2) + "|")
        lines.append(border)

        # Overview
        lines.append("|" + " STORAGE OVERVIEW ".center(width - 2, "-") + "|")
        lines.append("|" + f"  Row Groups: {stats['row_group_count']}".ljust(width - 2) + "|")
        lines.append("|" + f"  Total Rows: {stats['total_rows']}".ljust(width - 2) + "|")
        lines.append("|" + f"  Active Buffer: {stats['active_buffer_rows']} rows".ljust(width - 2) + "|")
        lines.append("|" + f"  Compressed: {stats['total_compressed_bytes']} bytes".ljust(width - 2) + "|")
        lines.append("|" + f"  Uncompressed: {stats['total_uncompressed_bytes']} bytes".ljust(width - 2) + "|")
        lines.append("|" + f"  Compression Ratio: {stats['overall_compression_ratio']:.2f}x".ljust(width - 2) + "|")
        lines.append(thin_border)

        # Column Inventory
        if stats["columns"]:
            lines.append("|" + " COLUMN INVENTORY ".center(width - 2, "-") + "|")
            for col_name, col_info in stats["columns"].items():
                lines.append("|" + f"  {col_name}:".ljust(width - 2) + "|")
                lines.append("|" + f"    Type: {col_info['dtype']}".ljust(width - 2) + "|")
                lines.append("|" + f"    Encoding: {col_info['encoding']}".ljust(width - 2) + "|")
                lines.append("|" + f"    Compressed: {col_info['compressed_size']}B / Uncompressed: {col_info['uncompressed_size']}B".ljust(width - 2) + "|")
                lines.append("|" + f"    Compression Ratio: {col_info['compression_ratio']:.2f}x".ljust(width - 2) + "|")

                # Zone map
                zm = col_info["zone_map"]
                lines.append("|" + f"    Zone Map: min={zm['min']}, max={zm['max']}".ljust(width - 2) + "|")
                lines.append("|" + f"    Nulls: {zm['null_count']}, Distinct: {zm['distinct_count']}".ljust(width - 2) + "|")

            lines.append(thin_border)

        # Row Group Details
        if store.row_groups:
            lines.append("|" + " ROW GROUP DETAILS ".center(width - 2, "-") + "|")
            for rg in store.row_groups:
                lines.append("|" + f"  Row Group {rg.row_group_id}: {rg.num_rows} rows, {rg.total_compressed_size}B compressed".ljust(width - 2) + "|")
                lines.append("|" + f"    Compression: {rg.compression_ratio:.2f}x | Sealed: {rg.sealed}".ljust(width - 2) + "|")
            lines.append(thin_border)

        # Footer
        lines.append("|" + "".center(width - 2) + "|")
        lines.append("|" + "Because row-oriented storage is a".center(width - 2) + "|")
        lines.append("|" + "relic of the OLTP dark ages.".center(width - 2) + "|")
        lines.append(border)
        lines.append("")

        return "\n".join(lines)


# ============================================================
# ColumnMiddleware — Captures Results into Column Store
# ============================================================


class ColumnMiddleware(IMiddleware):
    """Middleware that captures every FizzBuzz evaluation result into
    the columnar storage engine.

    Runs after the main evaluation, extracting the number and label
    from each result and appending them as rows to the column store.
    The middleware initializes the schema on first use, defining
    columns for number (INT64), label (STRING), and strategy (STRING).

    This middleware does not modify results — it merely archives them
    in columnar format for future analytical queries that will never
    be executed. The data is there, waiting, organized in beautiful
    column-major order, for the day when someone needs to run a
    vectorized aggregate over FizzBuzz classifications. That day
    may never come, but when it does, we will be ready.
    """

    def __init__(self, store: ColumnStore) -> None:
        self._store = store
        self._schema_initialized = False

    def get_name(self) -> str:
        """Return the middleware identifier."""
        return "ColumnMiddleware"

    def get_priority(self) -> int:
        """Return execution priority (910 — after archaeology, before CDC)."""
        return 910

    def _ensure_schema(self) -> None:
        """Initialize the column store schema on first use."""
        if not self._schema_initialized:
            self._store.define_column("number", ColumnType.INT64)
            self._store.define_column("label", ColumnType.STRING)
            self._store.define_column("strategy", ColumnType.STRING)
            self._schema_initialized = True

    def process(
        self,
        context: ProcessingContext,
        next_handler: Callable[[ProcessingContext], ProcessingContext],
    ) -> ProcessingContext:
        """Process the context, then archive results in columnar format."""
        result = next_handler(context)

        self._ensure_schema()

        # Extract data from the processing context
        try:
            number = context.number
            label = ""
            strategy = ""

            if context.results:
                last_result = context.results[-1]
                if hasattr(last_result, "classification"):
                    label = str(last_result.classification.value) if hasattr(
                        last_result.classification, "value") else str(last_result.classification)
                if hasattr(last_result, "strategy_name"):
                    strategy = last_result.strategy_name

            self._store.append_row({
                "number": number,
                "label": label,
                "strategy": strategy,
            })

            result.metadata["columnar_storage"] = {
                "ingested": True,
                "total_rows": self._store.total_rows,
                "row_groups": len(self._store.row_groups),
            }
        except Exception as e:
            logger.warning("FizzColumn middleware error: %s", e)
            result.metadata["columnar_storage"] = {
                "ingested": False,
                "error": str(e),
            }

        return result
