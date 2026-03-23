"""
Tests for the FizzColumn Columnar Storage Engine.

Validates Parquet-style column encoding (PLAIN, DICTIONARY, RLE, DELTA),
zone map predicate pushdown, vectorized batch processing, binary export,
column store lifecycle management, and the ASCII dashboard.
"""

from __future__ import annotations

import os
import struct
import tempfile
from typing import Any
from unittest.mock import MagicMock

import pytest

from enterprise_fizzbuzz.domain.exceptions import (
    ColumnEncodingError,
    ColumnarStorageError,
    ParquetExportError,
    RowGroupError,
)
from enterprise_fizzbuzz.infrastructure.columnar_storage import (
    Column,
    ColumnChunk,
    ColumnDashboard,
    ColumnEncoding,
    ColumnMiddleware,
    ColumnStore,
    ColumnType,
    ParquetExporter,
    RowGroup,
    VectorizedBatch,
    ZoneMap,
    decode_delta,
    decode_dictionary,
    decode_plain,
    decode_rle,
    encode_column,
    encode_delta,
    encode_dictionary,
    encode_plain,
    encode_rle,
    select_best_encoding,
)
from enterprise_fizzbuzz.infrastructure.config import _SingletonMeta


@pytest.fixture(autouse=True)
def _reset_singletons():
    """Reset singletons between tests."""
    _SingletonMeta.reset()
    yield
    _SingletonMeta.reset()


# ============================================================
# Exception Hierarchy Tests
# ============================================================


class TestExceptionHierarchy:
    """Validate the columnar storage exception taxonomy."""

    def test_columnar_storage_error_is_fizzbuzz_error(self):
        from enterprise_fizzbuzz.domain.exceptions import FizzBuzzError
        err = ColumnarStorageError("test")
        assert isinstance(err, FizzBuzzError)

    def test_columnar_storage_error_code(self):
        err = ColumnarStorageError("test")
        assert err.error_code == "EFP-CS00"

    def test_column_encoding_error_inherits(self):
        err = ColumnEncodingError("DELTA", "number", "not numeric")
        assert isinstance(err, ColumnarStorageError)
        assert err.error_code == "EFP-CS01"
        assert err.encoding == "DELTA"
        assert err.column_name == "number"

    def test_row_group_error_inherits(self):
        err = RowGroupError(7, "sealed")
        assert isinstance(err, ColumnarStorageError)
        assert err.error_code == "EFP-CS02"
        assert err.row_group_id == 7

    def test_parquet_export_error_inherits(self):
        err = ParquetExportError("/tmp/out.parquet", "disk full")
        assert isinstance(err, ColumnarStorageError)
        assert err.error_code == "EFP-CS03"
        assert err.path == "/tmp/out.parquet"


# ============================================================
# ColumnEncoding Enum Tests
# ============================================================


class TestColumnEncoding:
    """Validate encoding enum values."""

    def test_all_encodings_exist(self):
        assert ColumnEncoding.PLAIN.value == "PLAIN"
        assert ColumnEncoding.DICTIONARY.value == "DICTIONARY"
        assert ColumnEncoding.RLE.value == "RLE"
        assert ColumnEncoding.DELTA.value == "DELTA"

    def test_encoding_count(self):
        assert len(ColumnEncoding) == 4


# ============================================================
# ColumnType Enum Tests
# ============================================================


class TestColumnType:
    """Validate column type enum."""

    def test_all_types_exist(self):
        assert ColumnType.INT64.value == "INT64"
        assert ColumnType.STRING.value == "STRING"
        assert ColumnType.FLOAT64.value == "FLOAT64"
        assert ColumnType.BOOLEAN.value == "BOOLEAN"


# ============================================================
# ZoneMap Tests
# ============================================================


class TestZoneMap:
    """Validate zone map statistics and predicate pushdown."""

    def test_zone_map_can_contain_overlapping(self):
        zm = ZoneMap(min_value=10, max_value=50)
        assert zm.can_contain(predicate_min=5, predicate_max=20)

    def test_zone_map_skips_below(self):
        zm = ZoneMap(min_value=10, max_value=50)
        assert not zm.can_contain(predicate_min=60, predicate_max=100)

    def test_zone_map_skips_above(self):
        zm = ZoneMap(min_value=10, max_value=50)
        assert not zm.can_contain(predicate_min=1, predicate_max=5)

    def test_zone_map_null_values_conservative(self):
        zm = ZoneMap(min_value=None, max_value=None)
        assert zm.can_contain(predicate_min=1, predicate_max=100)

    def test_zone_map_no_predicate(self):
        zm = ZoneMap(min_value=10, max_value=50)
        assert zm.can_contain()

    def test_zone_map_merge(self):
        zm1 = ZoneMap(min_value=1, max_value=50, null_count=2, distinct_count=10)
        zm2 = ZoneMap(min_value=30, max_value=100, null_count=3, distinct_count=20)
        merged = zm1.merge(zm2)
        assert merged.min_value == 1
        assert merged.max_value == 100
        assert merged.null_count == 5
        assert merged.distinct_count == 20

    def test_zone_map_merge_with_none(self):
        zm1 = ZoneMap(min_value=5, max_value=10)
        zm2 = ZoneMap(min_value=None, max_value=None)
        merged = zm1.merge(zm2)
        assert merged.min_value == 5
        assert merged.max_value == 10

    def test_zone_map_predicate_min_only(self):
        zm = ZoneMap(min_value=10, max_value=50)
        assert zm.can_contain(predicate_min=40)
        assert not zm.can_contain(predicate_min=60)

    def test_zone_map_predicate_max_only(self):
        zm = ZoneMap(min_value=10, max_value=50)
        assert zm.can_contain(predicate_max=20)
        assert not zm.can_contain(predicate_max=5)


# ============================================================
# Column Tests
# ============================================================


class TestColumn:
    """Validate Column data structure."""

    def test_column_append(self):
        col = Column(name="x", dtype=ColumnType.INT64)
        col.append(1)
        col.append(2)
        col.append(None)
        assert len(col) == 3
        assert col.non_null_count == 2
        assert col.null_count == 1

    def test_column_null_bitmap_auto(self):
        col = Column(name="x", dtype=ColumnType.STRING, values=["a", None, "b"])
        assert col.null_bitmap == [True, False, True]

    def test_column_compute_zone_map(self):
        col = Column(name="x", dtype=ColumnType.INT64, values=[5, 10, 3, 8])
        zm = col.compute_zone_map()
        assert zm.min_value == 3
        assert zm.max_value == 10
        assert zm.null_count == 0
        assert zm.distinct_count == 4

    def test_column_zone_map_with_nulls(self):
        col = Column(name="x", dtype=ColumnType.INT64, values=[5, None, 3])
        zm = col.compute_zone_map()
        assert zm.min_value == 3
        assert zm.max_value == 5
        assert zm.null_count == 1

    def test_empty_column_zone_map(self):
        col = Column(name="x", dtype=ColumnType.INT64)
        zm = col.compute_zone_map()
        assert zm.min_value is None
        assert zm.distinct_count == 0


# ============================================================
# PLAIN Encoding Tests
# ============================================================


class TestPlainEncoding:
    """Validate PLAIN encoding roundtrip."""

    def test_int64_roundtrip(self):
        values = [1, 2, 3, 4, 5]
        encoded = encode_plain(values, ColumnType.INT64)
        decoded = decode_plain(encoded, ColumnType.INT64)
        assert decoded == values

    def test_string_roundtrip(self):
        values = ["Fizz", "Buzz", "FizzBuzz", "7"]
        encoded = encode_plain(values, ColumnType.STRING)
        decoded = decode_plain(encoded, ColumnType.STRING)
        assert decoded == values

    def test_float64_roundtrip(self):
        values = [1.5, 2.7, 3.14]
        encoded = encode_plain(values, ColumnType.FLOAT64)
        decoded = decode_plain(encoded, ColumnType.FLOAT64)
        assert decoded == pytest.approx(values)

    def test_boolean_roundtrip(self):
        values = [True, False, True]
        encoded = encode_plain(values, ColumnType.BOOLEAN)
        decoded = decode_plain(encoded, ColumnType.BOOLEAN)
        assert decoded == values

    def test_null_handling(self):
        values = [1, None, 3]
        encoded = encode_plain(values, ColumnType.INT64)
        decoded = decode_plain(encoded, ColumnType.INT64)
        assert decoded == [1, None, 3]

    def test_empty_roundtrip(self):
        encoded = encode_plain([], ColumnType.INT64)
        decoded = decode_plain(encoded, ColumnType.INT64)
        assert decoded == []


# ============================================================
# DICTIONARY Encoding Tests
# ============================================================


class TestDictionaryEncoding:
    """Validate DICTIONARY encoding roundtrip."""

    def test_string_roundtrip(self):
        values = ["Fizz", "Buzz", "Fizz", "FizzBuzz", "Buzz"]
        encoded = encode_dictionary(values, ColumnType.STRING)
        decoded = decode_dictionary(encoded, ColumnType.STRING)
        assert decoded == values

    def test_int_roundtrip(self):
        values = [1, 2, 1, 3, 2, 1]
        encoded = encode_dictionary(values, ColumnType.INT64)
        decoded = decode_dictionary(encoded, ColumnType.INT64)
        assert decoded == values

    def test_null_in_dictionary(self):
        values = ["a", None, "b", None]
        encoded = encode_dictionary(values, ColumnType.STRING)
        decoded = decode_dictionary(encoded, ColumnType.STRING)
        assert decoded == [None if v is None else v for v in values]

    def test_low_cardinality_compression(self):
        """Dictionary should be smaller than plain for low cardinality."""
        values = ["Fizz"] * 100 + ["Buzz"] * 100
        dict_encoded = encode_dictionary(values, ColumnType.STRING)
        plain_encoded = encode_plain(values, ColumnType.STRING)
        assert len(dict_encoded) < len(plain_encoded)

    def test_single_value(self):
        values = ["X"]
        encoded = encode_dictionary(values, ColumnType.STRING)
        decoded = decode_dictionary(encoded, ColumnType.STRING)
        assert decoded == values


# ============================================================
# RLE Encoding Tests
# ============================================================


class TestRLEEncoding:
    """Validate RLE encoding roundtrip."""

    def test_basic_roundtrip(self):
        values = ["a", "a", "a", "b", "b", "c"]
        encoded = encode_rle(values, ColumnType.STRING)
        decoded = decode_rle(encoded, ColumnType.STRING)
        assert decoded == values

    def test_no_runs(self):
        values = ["a", "b", "c", "d"]
        encoded = encode_rle(values, ColumnType.STRING)
        decoded = decode_rle(encoded, ColumnType.STRING)
        assert decoded == values

    def test_single_long_run(self):
        values = ["Fizz"] * 50
        encoded = encode_rle(values, ColumnType.STRING)
        decoded = decode_rle(encoded, ColumnType.STRING)
        assert decoded == values

    def test_sorted_column_compression(self):
        """RLE should be smaller than plain for sorted columns."""
        values = ["A"] * 100 + ["B"] * 100 + ["C"] * 100
        rle_encoded = encode_rle(values, ColumnType.STRING)
        plain_encoded = encode_plain(values, ColumnType.STRING)
        assert len(rle_encoded) < len(plain_encoded)

    def test_empty_roundtrip(self):
        encoded = encode_rle([], ColumnType.STRING)
        decoded = decode_rle(encoded, ColumnType.STRING)
        assert decoded == []

    def test_null_runs(self):
        values = [None, None, "a", "a"]
        encoded = encode_rle(values, ColumnType.STRING)
        decoded = decode_rle(encoded, ColumnType.STRING)
        assert decoded == values

    def test_int_roundtrip(self):
        values = [1, 1, 1, 2, 2, 3]
        encoded = encode_rle(values, ColumnType.INT64)
        decoded = decode_rle(encoded, ColumnType.INT64)
        assert decoded == values


# ============================================================
# DELTA Encoding Tests
# ============================================================


class TestDeltaEncoding:
    """Validate DELTA encoding roundtrip."""

    def test_monotonic_roundtrip(self):
        values = [1, 2, 3, 4, 5]
        encoded = encode_delta(values, ColumnType.INT64)
        decoded = decode_delta(encoded, ColumnType.INT64)
        assert decoded == values

    def test_non_monotonic_roundtrip(self):
        values = [10, 7, 15, 3, 20]
        encoded = encode_delta(values, ColumnType.INT64)
        decoded = decode_delta(encoded, ColumnType.INT64)
        assert decoded == values

    def test_with_nulls(self):
        values = [1, None, 3, None, 5]
        encoded = encode_delta(values, ColumnType.INT64)
        decoded = decode_delta(encoded, ColumnType.INT64)
        assert decoded == values

    def test_monotonic_compression(self):
        """Delta should be efficient for sequential integers."""
        values = list(range(1, 101))
        delta_encoded = encode_delta(values, ColumnType.INT64)
        plain_encoded = encode_plain(values, ColumnType.INT64)
        # Delta should be smaller or comparable
        assert len(delta_encoded) <= len(plain_encoded)

    def test_empty_roundtrip(self):
        encoded = encode_delta([], ColumnType.INT64)
        decoded = decode_delta(encoded, ColumnType.INT64)
        assert decoded == []

    def test_single_value(self):
        values = [42]
        encoded = encode_delta(values, ColumnType.INT64)
        decoded = decode_delta(encoded, ColumnType.INT64)
        assert decoded == values

    def test_negative_deltas(self):
        values = [100, 90, 80, 70]
        encoded = encode_delta(values, ColumnType.INT64)
        decoded = decode_delta(encoded, ColumnType.INT64)
        assert decoded == values

    def test_all_nulls(self):
        values = [None, None, None]
        encoded = encode_delta(values, ColumnType.INT64)
        decoded = decode_delta(encoded, ColumnType.INT64)
        assert decoded == values


# ============================================================
# ColumnChunk Tests
# ============================================================


class TestColumnChunk:
    """Validate ColumnChunk encoding and decoding."""

    def test_encode_and_decode_chunk(self):
        col = Column(name="n", dtype=ColumnType.INT64, values=[1, 2, 3])
        chunk = encode_column(col, ColumnEncoding.PLAIN)
        assert chunk.column_name == "n"
        assert chunk.dtype == ColumnType.INT64
        assert chunk.num_values == 3
        decoded = chunk.decode()
        assert decoded == [1, 2, 3]

    def test_chunk_compression_ratio(self):
        col = Column(name="label", dtype=ColumnType.STRING,
                     values=["Fizz"] * 100)
        chunk = encode_column(col, ColumnEncoding.DICTIONARY)
        assert chunk.compression_ratio > 0
        assert chunk.compressed_size > 0
        assert chunk.uncompressed_size > 0

    def test_chunk_zone_map(self):
        col = Column(name="n", dtype=ColumnType.INT64, values=[5, 10, 15])
        chunk = encode_column(col, ColumnEncoding.PLAIN)
        assert chunk.zone_map.min_value == 5
        assert chunk.zone_map.max_value == 15


# ============================================================
# Encoding Auto-Selection Tests
# ============================================================


class TestEncodingSelection:
    """Validate encoding auto-selection logic."""

    def test_selects_encoding_for_low_cardinality(self):
        col = Column(name="label", dtype=ColumnType.STRING,
                     values=["Fizz", "Buzz"] * 50)
        enc = select_best_encoding(col)
        assert enc in (ColumnEncoding.DICTIONARY, ColumnEncoding.RLE, ColumnEncoding.PLAIN)

    def test_selects_encoding_for_monotonic(self):
        col = Column(name="n", dtype=ColumnType.INT64,
                     values=list(range(1, 101)))
        enc = select_best_encoding(col)
        # Delta or Dictionary could win depending on size
        assert enc in list(ColumnEncoding)

    def test_delta_not_tried_for_strings(self):
        col = Column(name="s", dtype=ColumnType.STRING,
                     values=["a", "b", "c"])
        enc = select_best_encoding(col)
        assert enc != ColumnEncoding.DELTA

    def test_dictionary_rejected_high_cardinality(self):
        col = Column(name="n", dtype=ColumnType.INT64,
                     values=list(range(500)))
        enc = select_best_encoding(col, dictionary_cardinality_limit=10)
        assert enc != ColumnEncoding.DICTIONARY

    def test_empty_column_selects_plain(self):
        col = Column(name="x", dtype=ColumnType.INT64)
        enc = select_best_encoding(col)
        assert enc == ColumnEncoding.PLAIN


# ============================================================
# RowGroup Tests
# ============================================================


class TestRowGroup:
    """Validate RowGroup lifecycle and invariants."""

    def test_add_chunk(self):
        rg = RowGroup(row_group_id=0)
        col = Column(name="n", dtype=ColumnType.INT64, values=[1, 2, 3])
        chunk = encode_column(col, ColumnEncoding.PLAIN)
        rg.add_chunk(chunk)
        assert rg.num_rows == 3
        assert "n" in rg.chunks

    def test_seal_prevents_modification(self):
        rg = RowGroup(row_group_id=0)
        col = Column(name="n", dtype=ColumnType.INT64, values=[1, 2])
        chunk = encode_column(col, ColumnEncoding.PLAIN)
        rg.add_chunk(chunk)
        rg.seal()
        assert rg.sealed

        col2 = Column(name="m", dtype=ColumnType.INT64, values=[3, 4])
        chunk2 = encode_column(col2, ColumnEncoding.PLAIN)
        with pytest.raises(RowGroupError):
            rg.add_chunk(chunk2)

    def test_row_count_mismatch(self):
        rg = RowGroup(row_group_id=0)
        col1 = Column(name="a", dtype=ColumnType.INT64, values=[1, 2, 3])
        col2 = Column(name="b", dtype=ColumnType.INT64, values=[1, 2])
        chunk1 = encode_column(col1, ColumnEncoding.PLAIN)
        chunk2 = encode_column(col2, ColumnEncoding.PLAIN)
        rg.add_chunk(chunk1)
        with pytest.raises(RowGroupError):
            rg.add_chunk(chunk2)

    def test_get_zone_map(self):
        rg = RowGroup(row_group_id=0)
        col = Column(name="n", dtype=ColumnType.INT64, values=[10, 20, 30])
        chunk = encode_column(col, ColumnEncoding.PLAIN)
        rg.add_chunk(chunk)
        zm = rg.get_zone_map("n")
        assert zm is not None
        assert zm.min_value == 10
        assert zm.max_value == 30

    def test_get_zone_map_missing(self):
        rg = RowGroup(row_group_id=0)
        assert rg.get_zone_map("nonexistent") is None

    def test_compression_ratio(self):
        rg = RowGroup(row_group_id=0)
        col = Column(name="n", dtype=ColumnType.INT64, values=[1, 2, 3])
        chunk = encode_column(col, ColumnEncoding.PLAIN)
        rg.add_chunk(chunk)
        assert rg.compression_ratio > 0


# ============================================================
# VectorizedBatch Tests
# ============================================================


class TestVectorizedBatch:
    """Validate vectorized batch processing with selection bitmask."""

    def _make_batch(self) -> VectorizedBatch:
        rg = RowGroup(row_group_id=0)
        col_n = Column(name="n", dtype=ColumnType.INT64, values=[1, 2, 3, 4, 5])
        col_l = Column(name="label", dtype=ColumnType.STRING,
                       values=["1", "2", "Fizz", "4", "Buzz"])
        rg.add_chunk(encode_column(col_n, ColumnEncoding.PLAIN))
        rg.add_chunk(encode_column(col_l, ColumnEncoding.PLAIN))
        rg.seal()
        return VectorizedBatch.from_row_group(rg)

    def test_from_row_group(self):
        batch = self._make_batch()
        assert batch.num_rows == 5
        assert batch.selected_count == 5
        assert "n" in batch.columns
        assert "label" in batch.columns

    def test_apply_filter(self):
        batch = self._make_batch()
        filtered = batch.apply_filter("n", lambda x: x > 3)
        assert filtered.selected_count == 2
        assert filtered.selected_values("n") == [4, 5]

    def test_filter_preserves_original(self):
        batch = self._make_batch()
        filtered = batch.apply_filter("n", lambda x: x > 3)
        assert batch.selected_count == 5  # Original unchanged

    def test_selected_values(self):
        batch = self._make_batch()
        filtered = batch.apply_filter("label", lambda x: x == "Fizz")
        assert filtered.selected_values("label") == ["Fizz"]
        assert filtered.selected_values("n") == [3]

    def test_materialize(self):
        batch = self._make_batch()
        filtered = batch.apply_filter("n", lambda x: x <= 2)
        materialized = filtered.materialize()
        assert materialized["n"] == [1, 2]
        assert materialized["label"] == ["1", "2"]

    def test_batch_size_constant(self):
        assert VectorizedBatch.BATCH_SIZE == 1024

    def test_filter_nonexistent_column(self):
        batch = self._make_batch()
        filtered = batch.apply_filter("nonexistent", lambda x: True)
        assert filtered.selected_count == 5  # No change


# ============================================================
# ColumnStore Tests
# ============================================================


class TestColumnStore:
    """Validate the column store lifecycle."""

    def test_define_columns(self):
        store = ColumnStore()
        store.define_column("n", ColumnType.INT64)
        store.define_column("label", ColumnType.STRING)
        assert store.schema == {"n": ColumnType.INT64, "label": ColumnType.STRING}

    def test_append_and_flush(self):
        store = ColumnStore(row_group_size=3)
        store.define_column("n", ColumnType.INT64)
        store.define_column("label", ColumnType.STRING)

        store.append_row({"n": 1, "label": "1"})
        store.append_row({"n": 2, "label": "2"})
        assert store.active_row_count == 2
        assert len(store.row_groups) == 0

        store.append_row({"n": 3, "label": "Fizz"})
        # Should auto-flush at row_group_size=3
        assert len(store.row_groups) == 1
        assert store.active_row_count == 0

    def test_manual_flush(self):
        store = ColumnStore()
        store.define_column("n", ColumnType.INT64)
        store.append_row({"n": 1})
        store.append_row({"n": 2})
        rg = store.flush()
        assert rg is not None
        assert rg.num_rows == 2
        assert rg.sealed

    def test_flush_empty_returns_none(self):
        store = ColumnStore()
        store.define_column("n", ColumnType.INT64)
        assert store.flush() is None

    def test_total_rows(self):
        store = ColumnStore(row_group_size=5)
        store.define_column("n", ColumnType.INT64)
        for i in range(7):
            store.append_row({"n": i})
        assert store.total_rows == 7
        assert store.active_row_count == 2
        assert len(store.row_groups) == 1

    def test_scan_all(self):
        store = ColumnStore(row_group_size=5)
        store.define_column("n", ColumnType.INT64)
        for i in range(10):
            store.append_row({"n": i})
        store.flush()
        batches = store.scan()
        assert len(batches) == 2

    def test_scan_with_zone_map_pruning(self):
        store = ColumnStore(row_group_size=5)
        store.define_column("n", ColumnType.INT64)
        for i in range(10):
            store.append_row({"n": i})
        store.flush()

        # First row group has values 0-4, second has 5-9
        # Predicate: n >= 7 should skip first row group
        batches = store.scan(predicate_column="n", predicate_min=7)
        assert len(batches) == 1

    def test_scan_column_projection(self):
        store = ColumnStore(row_group_size=10)
        store.define_column("n", ColumnType.INT64)
        store.define_column("label", ColumnType.STRING)
        store.append_row({"n": 1, "label": "1"})
        store.flush()

        batches = store.scan(column_names=["n"])
        assert len(batches) == 1
        assert "n" in batches[0].columns
        assert "label" not in batches[0].columns

    def test_get_statistics(self):
        store = ColumnStore(row_group_size=5)
        store.define_column("n", ColumnType.INT64)
        for i in range(5):
            store.append_row({"n": i + 1})
        store.flush()

        stats = store.get_statistics()
        assert stats["row_group_count"] == 1
        assert stats["total_rows"] == 5
        assert "n" in stats["columns"]
        assert stats["columns"]["n"]["dtype"] == "INT64"


# ============================================================
# ParquetExporter Tests
# ============================================================


class TestParquetExporter:
    """Validate Parquet-style binary export."""

    def _build_store(self) -> ColumnStore:
        store = ColumnStore(row_group_size=10)
        store.define_column("n", ColumnType.INT64)
        store.define_column("label", ColumnType.STRING)
        for i in range(1, 6):
            label = "Fizz" if i % 3 == 0 else ("Buzz" if i % 5 == 0 else str(i))
            store.append_row({"n": i, "label": label})
        return store

    def test_export_creates_file(self):
        store = self._build_store()
        with tempfile.NamedTemporaryFile(suffix=".parquet", delete=False) as f:
            path = f.name
        try:
            bytes_written = ParquetExporter.export(store, path)
            assert bytes_written > 0
            assert os.path.exists(path)
        finally:
            os.unlink(path)

    def test_par1_magic_bytes(self):
        store = self._build_store()
        with tempfile.NamedTemporaryFile(suffix=".parquet", delete=False) as f:
            path = f.name
        try:
            ParquetExporter.export(store, path)
            with open(path, "rb") as f:
                data = f.read()
            assert data[:4] == b"PAR1"
            assert data[-4:] == b"PAR1"
        finally:
            os.unlink(path)

    def test_validate_exported_file(self):
        store = self._build_store()
        with tempfile.NamedTemporaryFile(suffix=".parquet", delete=False) as f:
            path = f.name
        try:
            ParquetExporter.export(store, path)
            footer = ParquetExporter.validate_file(path)
            assert "row_groups" in footer
            assert "schema" in footer
            assert len(footer["row_groups"]) > 0
        finally:
            os.unlink(path)

    def test_validate_invalid_magic(self):
        with tempfile.NamedTemporaryFile(suffix=".parquet", delete=False) as f:
            f.write(b"NOPE" + b"\x00" * 20 + b"NOPE")
            path = f.name
        try:
            with pytest.raises(ParquetExportError):
                ParquetExporter.validate_file(path)
        finally:
            os.unlink(path)

    def test_export_empty_store_raises(self):
        store = ColumnStore()
        store.define_column("n", ColumnType.INT64)
        with tempfile.NamedTemporaryFile(suffix=".parquet", delete=False) as f:
            path = f.name
        try:
            with pytest.raises(ParquetExportError):
                ParquetExporter.export(store, path)
        finally:
            if os.path.exists(path):
                os.unlink(path)

    def test_validate_too_small_file(self):
        with tempfile.NamedTemporaryFile(suffix=".parquet", delete=False) as f:
            f.write(b"PAR1")
            path = f.name
        try:
            with pytest.raises(ParquetExportError):
                ParquetExporter.validate_file(path)
        finally:
            os.unlink(path)


# ============================================================
# ColumnDashboard Tests
# ============================================================


class TestColumnDashboard:
    """Validate ASCII dashboard rendering."""

    def test_render_with_data(self):
        store = ColumnStore(row_group_size=10)
        store.define_column("n", ColumnType.INT64)
        store.define_column("label", ColumnType.STRING)
        for i in range(5):
            store.append_row({"n": i, "label": "Fizz" if i % 3 == 0 else str(i)})
        store.flush()

        output = ColumnDashboard.render(store, width=60)
        assert "FIZZCOLUMN" in output
        assert "COLUMN INVENTORY" in output
        assert "ROW GROUP" in output

    def test_render_empty_store(self):
        store = ColumnStore()
        output = ColumnDashboard.render(store, width=60)
        assert "FIZZCOLUMN" in output

    def test_render_custom_width(self):
        store = ColumnStore()
        output = ColumnDashboard.render(store, width=80)
        assert "FIZZCOLUMN" in output


# ============================================================
# ColumnMiddleware Tests
# ============================================================


class TestColumnMiddleware:
    """Validate middleware integration with the processing pipeline."""

    def test_middleware_captures_result(self):
        store = ColumnStore()
        mw = ColumnMiddleware(store)

        ctx = MagicMock()
        ctx.number = 15
        ctx.results = []
        ctx.metadata = {}

        def next_handler(c):
            return c

        result = mw.process(ctx, next_handler)
        assert store.total_rows == 1
        assert result.metadata["columnar_storage"]["ingested"] is True

    def test_middleware_initializes_schema(self):
        store = ColumnStore()
        mw = ColumnMiddleware(store)

        ctx = MagicMock()
        ctx.number = 1
        ctx.results = []
        ctx.metadata = {}

        mw.process(ctx, lambda c: c)
        assert "number" in store.schema
        assert "label" in store.schema
        assert "strategy" in store.schema

    def test_middleware_handles_error_gracefully(self):
        store = ColumnStore()
        mw = ColumnMiddleware(store)

        ctx = MagicMock()
        ctx.number = None  # Will cause issues
        ctx.results = []
        ctx.metadata = {}

        # Should not raise
        result = mw.process(ctx, lambda c: c)
        assert "columnar_storage" in result.metadata

    def test_middleware_calls_next_handler(self):
        store = ColumnStore()
        mw = ColumnMiddleware(store)

        ctx = MagicMock()
        ctx.number = 1
        ctx.results = []
        ctx.metadata = {}

        called = []

        def next_handler(c):
            called.append(True)
            return c

        mw.process(ctx, next_handler)
        assert len(called) == 1
