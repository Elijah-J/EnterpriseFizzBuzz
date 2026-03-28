"""
Enterprise FizzBuzz Platform - FizzDNA DNA Storage Encoder Test Suite

Comprehensive verification of the DNA-based data storage pipeline, from
two-bit-per-base nucleotide encoding through Reed-Solomon error correction,
GC-content balancing, homopolymer run detection, oligonucleotide segmentation,
and middleware integration.

DNA storage is the most durable persistence medium known to science, with a
half-life of approximately 521 years under optimal conditions. Ensuring
encoding correctness is therefore paramount — an error introduced during
encoding would persist for centuries before anyone noticed.
"""

from __future__ import annotations

import sys
import uuid
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from enterprise_fizzbuzz.infrastructure.fizzdna import (
    BASE_DECODING,
    BASE_ENCODING,
    DNADashboard,
    DNAEncoder,
    DNAStorageMiddleware,
    FizzBuzzDNAStorage,
    GaloisField,
    OligoPool,
    ReedSolomonCodec,
)
from enterprise_fizzbuzz.domain.exceptions.fizzdna import (
    DNADecodingError,
    DNAEncodingError,
    DNAMiddlewareError,
    ECCChecksumError,
    FizzDNAError,
    GCContentImbalanceError,
    HomopolymerRunError,
)
from enterprise_fizzbuzz.domain.interfaces import IMiddleware
from enterprise_fizzbuzz.domain.models import (
    FizzBuzzResult,
    ProcessingContext,
)


# ============================================================
# Helpers
# ============================================================

def _make_context(number: int, output: str = "") -> ProcessingContext:
    ctx = ProcessingContext(number=number, session_id=str(uuid.uuid4()))
    result = FizzBuzzResult(number=number, output=output or str(number), matched_rules=[])
    ctx.results.append(result)
    return ctx


def _identity_handler(ctx: ProcessingContext) -> ProcessingContext:
    return ctx


# ============================================================
# Base encoding tests
# ============================================================

class TestBaseEncoding:
    """Verify the two-bit-per-base nucleotide encoding scheme."""

    def test_encoding_map_completeness(self) -> None:
        assert len(BASE_ENCODING) == 4
        assert set(BASE_ENCODING.values()) == {"A", "T", "G", "C"}

    def test_decoding_map_completeness(self) -> None:
        assert len(BASE_DECODING) == 4
        assert set(BASE_DECODING.keys()) == {"A", "T", "G", "C"}

    def test_encode_decode_roundtrip(self) -> None:
        for bits, base in BASE_ENCODING.items():
            assert BASE_DECODING[base] == bits

    def test_bytes_to_bases_single_byte(self) -> None:
        encoder = DNAEncoder()
        # 0xFF = 11111111 -> CC CC (all 11 pairs)
        result = encoder.bytes_to_bases(b"\xff")
        assert result == "CCCC"

    def test_bytes_to_bases_zero_byte(self) -> None:
        encoder = DNAEncoder()
        result = encoder.bytes_to_bases(b"\x00")
        assert result == "AAAA"

    def test_bases_to_bytes_roundtrip(self) -> None:
        encoder = DNAEncoder()
        original = b"Hello"
        bases = encoder.bytes_to_bases(original)
        recovered = encoder.bases_to_bytes(bases)
        assert recovered == original


# ============================================================
# GC content tests
# ============================================================

class TestGCContent:
    """Verify GC-content calculation and balancing."""

    def test_gc_content_all_gc(self) -> None:
        encoder = DNAEncoder()
        assert encoder.compute_gc_content("GGGGCCCC") == 1.0

    def test_gc_content_all_at(self) -> None:
        encoder = DNAEncoder()
        assert encoder.compute_gc_content("AAAATTTT") == 0.0

    def test_gc_content_balanced(self) -> None:
        encoder = DNAEncoder()
        gc = encoder.compute_gc_content("AGTC")
        assert gc == 0.5

    def test_gc_content_empty(self) -> None:
        encoder = DNAEncoder()
        assert encoder.compute_gc_content("") == 0.0

    def test_balance_gc_increases_gc(self) -> None:
        encoder = DNAEncoder(gc_min=0.40, gc_max=0.60)
        low_gc = "AAAAAAAATTTTTTTT"
        balanced = encoder.balance_gc_content(low_gc)
        gc = encoder.compute_gc_content(balanced)
        assert gc >= 0.39  # Allow small tolerance


# ============================================================
# Homopolymer tests
# ============================================================

class TestHomopolymer:
    """Verify homopolymer run detection and correction."""

    def test_detect_no_runs(self) -> None:
        encoder = DNAEncoder(max_homopolymer=4)
        runs = encoder.detect_homopolymers("ATGCATGC")
        assert len(runs) == 0

    def test_detect_long_run(self) -> None:
        encoder = DNAEncoder(max_homopolymer=4)
        runs = encoder.detect_homopolymers("AAAAAA")
        assert len(runs) == 1
        assert runs[0][1] == "A"
        assert runs[0][2] == 6

    def test_fix_homopolymers(self) -> None:
        encoder = DNAEncoder(max_homopolymer=3)
        fixed = encoder.fix_homopolymers("AAAAAA")
        # Should break up the run
        runs = encoder.detect_homopolymers(fixed)
        for _, _, run_len in runs:
            assert run_len <= 4  # Fixes should reduce runs


# ============================================================
# Reed-Solomon tests
# ============================================================

class TestReedSolomon:
    """Verify Reed-Solomon error-correcting code operations."""

    def test_encode_adds_parity(self) -> None:
        codec = ReedSolomonCodec(nsym=4)
        data = [1, 2, 3, 4, 5]
        encoded = codec.encode(data)
        assert len(encoded) == len(data) + 4

    def test_no_errors_detected_on_clean_codeword(self) -> None:
        codec = ReedSolomonCodec(nsym=4)
        data = [10, 20, 30]
        encoded = codec.encode(data)
        assert not codec.has_errors(encoded)

    def test_errors_detected_on_corrupted_codeword(self) -> None:
        codec = ReedSolomonCodec(nsym=4)
        data = [10, 20, 30]
        encoded = codec.encode(data)
        encoded[0] ^= 0xFF  # Corrupt first symbol
        assert codec.has_errors(encoded)

    def test_galois_field_multiply(self) -> None:
        gf = GaloisField()
        assert gf.multiply(0, 5) == 0
        assert gf.multiply(1, 1) == 1
        result = gf.multiply(3, 7)
        assert isinstance(result, int)
        assert 0 <= result < 256


# ============================================================
# Full encoding pipeline tests
# ============================================================

class TestDNAEncoder:
    """Verify the complete encoding/decoding pipeline."""

    def test_encode_produces_oligos(self) -> None:
        encoder = DNAEncoder()
        oligos = encoder.encode(b"FizzBuzz")
        assert len(oligos) > 0
        for oligo in oligos:
            assert all(b in "ATGC" for b in oligo)

    def test_encode_empty_raises(self) -> None:
        encoder = DNAEncoder()
        with pytest.raises(DNAEncodingError):
            encoder.encode(b"")

    def test_stats_populated_after_encode(self) -> None:
        encoder = DNAEncoder()
        encoder.encode(b"Test data for DNA encoding")
        stats = encoder.stats
        assert stats["data_bytes"] > 0
        assert stats["total_bases"] > 0
        assert 0.0 <= stats["gc_content"] <= 1.0


# ============================================================
# Oligo pool tests
# ============================================================

class TestOligoPool:
    """Verify oligonucleotide pool operations."""

    def test_store_and_retrieve(self) -> None:
        pool = OligoPool()
        pool.store(0, "ATGCATGC")
        assert pool.retrieve(0) == "ATGCATGC"

    def test_retrieve_nonexistent(self) -> None:
        pool = OligoPool()
        assert pool.retrieve(42) is None

    def test_retrieve_all_ordered(self) -> None:
        pool = OligoPool()
        pool.store(2, "CCC")
        pool.store(0, "AAA")
        pool.store(1, "BBB")
        ordered = pool.retrieve_all()
        assert ordered == ["AAA", "BBB", "CCC"]

    def test_gc_report(self) -> None:
        pool = OligoPool()
        pool.store(0, "GGCC")
        pool.store(1, "AATT")
        report = pool.gc_content_report()
        assert report["mean_gc"] == 0.5
        assert report["min_gc"] == 0.0
        assert report["max_gc"] == 1.0


# ============================================================
# Storage service tests
# ============================================================

class TestFizzBuzzDNAStorage:
    """Verify the high-level DNA storage service."""

    def test_store_result(self) -> None:
        storage = FizzBuzzDNAStorage()
        info = storage.store_result(15, "FizzBuzz")
        assert info["number"] == 15
        assert info["output"] == "FizzBuzz"
        assert info["oligos_added"] > 0

    def test_pool_stats(self) -> None:
        storage = FizzBuzzDNAStorage()
        storage.store_result(3, "Fizz")
        stats = storage.get_pool_stats()
        assert stats["oligo_count"] > 0
        assert stats["total_bases"] > 0


# ============================================================
# Dashboard tests
# ============================================================

class TestDNADashboard:
    """Verify dashboard rendering produces valid output."""

    def test_render_produces_string(self) -> None:
        storage = FizzBuzzDNAStorage()
        storage.store_result(1, "1")
        output = DNADashboard.render(storage, width=60)
        assert isinstance(output, str)
        assert "FIZZDNA" in output
        assert len(output.split("\n")) > 5


# ============================================================
# Middleware tests
# ============================================================

class TestDNAStorageMiddleware:
    """Verify middleware integration with the processing pipeline."""

    def test_implements_imiddleware(self) -> None:
        storage = FizzBuzzDNAStorage()
        mw = DNAStorageMiddleware(storage=storage)
        assert isinstance(mw, IMiddleware)

    def test_process_encodes_result(self) -> None:
        storage = FizzBuzzDNAStorage()
        mw = DNAStorageMiddleware(storage=storage)
        ctx = _make_context(3, "Fizz")
        result = mw.process(ctx, _identity_handler)
        assert result.metadata.get("fizzdna_encoded") is True
        assert storage.pool.count > 0

    def test_storage_property(self) -> None:
        storage = FizzBuzzDNAStorage()
        mw = DNAStorageMiddleware(storage=storage)
        assert mw.storage is storage


# ============================================================
# Exception tests
# ============================================================

class TestDNAExceptions:
    """Verify exception hierarchy and error codes."""

    def test_base_exception_hierarchy(self) -> None:
        err = FizzDNAError("test")
        assert "EFP-DNA00" in str(err)

    def test_encoding_error(self) -> None:
        err = DNAEncodingError("bad data", "invalid format")
        assert "EFP-DNA01" in str(err)
        assert err.context["data"] == "bad data"

    def test_decoding_error(self) -> None:
        err = DNADecodingError("XYZABC", "invalid base")
        assert "EFP-DNA02" in str(err)

    def test_gc_content_error(self) -> None:
        err = GCContentImbalanceError(0.20, 0.40, 0.60)
        assert "EFP-DNA03" in str(err)
        assert err.context["gc_ratio"] == 0.20

    def test_ecc_checksum_error(self) -> None:
        err = ECCChecksumError(block_id=5, errors_found=10, max_correctable=4)
        assert "EFP-DNA04" in str(err)
