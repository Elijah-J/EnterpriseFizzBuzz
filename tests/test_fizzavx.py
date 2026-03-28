"""
Enterprise FizzBuzz Platform - FizzAVX SIMD/AVX Instruction Engine Test Suite

Comprehensive tests for the AVX instruction engine, covering register file
operations, packed arithmetic (add, subtract, multiply), comparison
instructions, bitwise operations, horizontal sum, shuffle, blend, batch
classification, middleware integration, dashboard rendering, and exception
handling.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from enterprise_fizzbuzz.infrastructure.fizzavx import (
    FIZZAVX_VERSION,
    MIDDLEWARE_PRIORITY,
    NUM_LANES,
    NUM_REGISTERS,
    SIMD_CLASSIFY_BUZZ,
    SIMD_CLASSIFY_FIZZ,
    SIMD_CLASSIFY_FIZZBUZZ,
    SIMD_CLASSIFY_NONE,
    VECTOR_WIDTH_BITS,
    AVXDashboard,
    AVXEngine,
    AVXMiddleware,
    RegisterFile,
    YMMRegister,
    classification_code_to_string,
    create_fizzavx_subsystem,
)
from enterprise_fizzbuzz.domain.exceptions import (
    AVXMaskError,
    AVXRegisterError,
    AVXShuffleError,
)


# =========================================================================
# Constants
# =========================================================================

class TestConstants:
    def test_version(self):
        assert FIZZAVX_VERSION == "1.0.0"

    def test_middleware_priority(self):
        assert MIDDLEWARE_PRIORITY == 241

    def test_vector_width(self):
        assert VECTOR_WIDTH_BITS == 256

    def test_num_lanes(self):
        assert NUM_LANES == 8

    def test_num_registers(self):
        assert NUM_REGISTERS == 16


# =========================================================================
# YMMRegister
# =========================================================================

class TestYMMRegister:
    def test_default_zero(self):
        r = YMMRegister()
        assert all(v == 0 for v in r.lanes)
        assert len(r.lanes) == NUM_LANES

    def test_getitem_setitem(self):
        r = YMMRegister()
        r[3] = 42
        assert r[3] == 42

    def test_as_list(self):
        r = YMMRegister(lanes=[1, 2, 3, 4, 5, 6, 7, 8])
        assert r.as_list() == [1, 2, 3, 4, 5, 6, 7, 8]

    def test_truncates_to_num_lanes(self):
        r = YMMRegister(lanes=list(range(20)))
        assert len(r.lanes) == NUM_LANES


# =========================================================================
# RegisterFile
# =========================================================================

class TestRegisterFile:
    def test_read_write(self):
        rf = RegisterFile()
        rf.write(0, YMMRegister(lanes=[1] * NUM_LANES))
        assert rf.read(0).lanes == [1] * NUM_LANES

    def test_out_of_range_raises(self):
        rf = RegisterFile()
        with pytest.raises(AVXRegisterError):
            rf.read(16)

    def test_load(self):
        rf = RegisterFile()
        rf.load(5, [10, 20, 30, 40, 50, 60, 70, 80])
        assert rf.read(5)[0] == 10

    def test_clear(self):
        rf = RegisterFile()
        rf.load(0, [1] * NUM_LANES)
        rf.clear()
        assert rf.read(0).lanes == [0] * NUM_LANES

    def test_dump(self):
        rf = RegisterFile()
        d = rf.dump()
        assert "ymm0" in d
        assert "ymm15" in d


# =========================================================================
# AVXEngine - Arithmetic
# =========================================================================

class TestAVXArithmetic:
    def test_vpaddd(self):
        e = AVXEngine()
        e.registers.load(0, [1, 2, 3, 4, 5, 6, 7, 8])
        e.registers.load(1, [10, 20, 30, 40, 50, 60, 70, 80])
        e.vpaddd(2, 0, 1)
        assert e.registers.read(2).lanes == [11, 22, 33, 44, 55, 66, 77, 88]

    def test_vpsubd(self):
        e = AVXEngine()
        e.registers.load(0, [10, 20, 30, 40, 50, 60, 70, 80])
        e.registers.load(1, [1, 2, 3, 4, 5, 6, 7, 8])
        e.vpsubd(2, 0, 1)
        assert e.registers.read(2).lanes == [9, 18, 27, 36, 45, 54, 63, 72]

    def test_vpmulld(self):
        e = AVXEngine()
        e.registers.load(0, [2, 3, 4, 5, 6, 7, 8, 9])
        e.registers.load(1, [10, 10, 10, 10, 10, 10, 10, 10])
        e.vpmulld(2, 0, 1)
        assert e.registers.read(2).lanes == [20, 30, 40, 50, 60, 70, 80, 90]


# =========================================================================
# AVXEngine - Comparison
# =========================================================================

class TestAVXComparison:
    def test_vpcmpeqd(self):
        e = AVXEngine()
        e.registers.load(0, [1, 2, 3, 4, 5, 6, 7, 8])
        e.registers.load(1, [1, 0, 3, 0, 5, 0, 7, 0])
        e.vpcmpeqd(2, 0, 1)
        result = e.registers.read(2).lanes
        assert result[0] == 0xFFFFFFFF
        assert result[1] == 0
        assert result[2] == 0xFFFFFFFF

    def test_vpcmpgtd(self):
        e = AVXEngine()
        e.registers.load(0, [5, 5, 5, 5, 5, 5, 5, 5])
        e.registers.load(1, [3, 5, 7, 1, 9, 4, 6, 2])
        e.vpcmpgtd(2, 0, 1)
        result = e.registers.read(2).lanes
        assert result[0] == 0xFFFFFFFF  # 5 > 3
        assert result[1] == 0           # 5 == 5
        assert result[2] == 0           # 5 < 7


# =========================================================================
# AVXEngine - Bitwise
# =========================================================================

class TestAVXBitwise:
    def test_vpand(self):
        e = AVXEngine()
        e.registers.load(0, [0xFF, 0x0F, 0xAA, 0, 0, 0, 0, 0])
        e.registers.load(1, [0x0F, 0x0F, 0x55, 0, 0, 0, 0, 0])
        e.vpand(2, 0, 1)
        assert e.registers.read(2)[0] == 0x0F
        assert e.registers.read(2)[2] == 0x00

    def test_vpor(self):
        e = AVXEngine()
        e.registers.load(0, [0xF0, 0, 0, 0, 0, 0, 0, 0])
        e.registers.load(1, [0x0F, 0, 0, 0, 0, 0, 0, 0])
        e.vpor(2, 0, 1)
        assert e.registers.read(2)[0] == 0xFF

    def test_vpxor(self):
        e = AVXEngine()
        e.registers.load(0, [0xFF, 0, 0, 0, 0, 0, 0, 0])
        e.registers.load(1, [0xFF, 0, 0, 0, 0, 0, 0, 0])
        e.vpxor(2, 0, 1)
        assert e.registers.read(2)[0] == 0


# =========================================================================
# AVXEngine - Shuffle, Blend, Horizontal
# =========================================================================

class TestAVXShuffleBlend:
    def test_shuffle(self):
        e = AVXEngine()
        e.registers.load(0, [10, 20, 30, 40, 50, 60, 70, 80])
        e.shuffle(1, 0, (7, 6, 5, 4, 3, 2, 1, 0))
        assert e.registers.read(1).lanes == [80, 70, 60, 50, 40, 30, 20, 10]

    def test_shuffle_invalid_raises(self):
        e = AVXEngine()
        e.registers.load(0, [0] * NUM_LANES)
        with pytest.raises(AVXShuffleError):
            e.shuffle(1, 0, (0, 1, 2, 8, 4, 5, 6, 7))  # 8 is out of range

    def test_blend(self):
        e = AVXEngine()
        e.registers.load(0, [1, 1, 1, 1, 1, 1, 1, 1])
        e.registers.load(1, [2, 2, 2, 2, 2, 2, 2, 2])
        e.blend(2, 0, 1, 0b10101010)
        result = e.registers.read(2).lanes
        assert result[0] == 1  # bit 0 = 0, take from src1
        assert result[1] == 2  # bit 1 = 1, take from src2

    def test_blend_invalid_mask_raises(self):
        e = AVXEngine()
        e.registers.load(0, [0] * NUM_LANES)
        e.registers.load(1, [0] * NUM_LANES)
        with pytest.raises(AVXMaskError):
            e.blend(2, 0, 1, 0x1FF)  # 9-bit mask for 8 lanes

    def test_horizontal_sum(self):
        e = AVXEngine()
        e.registers.load(0, [1, 2, 3, 4, 5, 6, 7, 8])
        assert e.horizontal_sum(0) == 36


# =========================================================================
# AVXEngine - Classification
# =========================================================================

class TestAVXClassification:
    def test_classify_batch(self):
        e = AVXEngine()
        codes = e.classify_batch([1, 3, 5, 15, 7, 9, 10, 30])
        assert codes[0] == SIMD_CLASSIFY_NONE      # 1
        assert codes[1] == SIMD_CLASSIFY_FIZZ       # 3
        assert codes[2] == SIMD_CLASSIFY_BUZZ       # 5
        assert codes[3] == SIMD_CLASSIFY_FIZZBUZZ   # 15
        assert codes[4] == SIMD_CLASSIFY_NONE       # 7
        assert codes[5] == SIMD_CLASSIFY_FIZZ       # 9
        assert codes[6] == SIMD_CLASSIFY_BUZZ       # 10
        assert codes[7] == SIMD_CLASSIFY_FIZZBUZZ   # 30

    def test_classify_partial_batch(self):
        e = AVXEngine()
        codes = e.classify_batch([6, 10])
        assert len(codes) == 2
        assert codes[0] == SIMD_CLASSIFY_FIZZ
        assert codes[1] == SIMD_CLASSIFY_BUZZ

    def test_classification_code_to_string(self):
        assert classification_code_to_string(SIMD_CLASSIFY_FIZZBUZZ) == "FizzBuzz"
        assert classification_code_to_string(SIMD_CLASSIFY_FIZZ) == "Fizz"
        assert classification_code_to_string(SIMD_CLASSIFY_BUZZ) == "Buzz"
        assert classification_code_to_string(SIMD_CLASSIFY_NONE) == "0"


# =========================================================================
# Middleware
# =========================================================================

class TestMiddleware:
    def _make_context(self, number: int):
        from enterprise_fizzbuzz.domain.models import ProcessingContext
        return ProcessingContext(number=number, session_id="test-avx")

    def test_middleware_name(self):
        _, mw = create_fizzavx_subsystem()
        assert mw.get_name() == "fizzavx"

    def test_middleware_priority(self):
        _, mw = create_fizzavx_subsystem()
        assert mw.get_priority() == 241

    def test_classifies_fizzbuzz(self):
        _, mw = create_fizzavx_subsystem()
        ctx = self._make_context(30)
        result = mw.process(ctx, lambda c: c)
        assert result.metadata["avx_classification"] == "FizzBuzz"

    def test_classifies_plain_number(self):
        _, mw = create_fizzavx_subsystem()
        ctx = self._make_context(7)
        result = mw.process(ctx, lambda c: c)
        assert result.metadata["avx_classification"] == "0"


# =========================================================================
# Dashboard
# =========================================================================

class TestDashboard:
    def test_dashboard_renders(self):
        engine, _ = create_fizzavx_subsystem()
        output = AVXDashboard.render(engine)
        assert "FizzAVX" in output
        assert "256 bits" in output


# =========================================================================
# Factory
# =========================================================================

class TestFactory:
    def test_create_subsystem(self):
        engine, mw = create_fizzavx_subsystem()
        assert isinstance(engine, AVXEngine)
        assert isinstance(mw, AVXMiddleware)
        assert engine.instructions_executed == 0
