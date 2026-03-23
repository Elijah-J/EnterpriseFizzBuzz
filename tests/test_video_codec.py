"""
Enterprise FizzBuzz Platform - FizzCodec Video Codec Test Suite

Comprehensive verification of the H.264-inspired video compression pipeline,
from individual DCT transform correctness through the complete encode/decode
round-trip. These tests ensure that every FizzBuzz evaluation result can be
reliably compressed, transmitted, and reconstructed without exceeding
acceptable distortion thresholds.

Video codec correctness is mission-critical: a single bit error in the
entropy-coded bitstream could corrupt the visual representation of a
FizzBuzz classification, leading to compliance violations under the
Enterprise FizzBuzz Visual Integrity Standard (EFVIS).
"""

from __future__ import annotations

import math
import struct
import sys
import uuid
from pathlib import Path
from typing import Callable
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from enterprise_fizzbuzz.infrastructure.video_codec import (
    BLOCK_SIZE,
    DEFAULT_QP,
    MAX_PIXEL_VALUE,
    DCT_MATRIX,
    DCT_MATRIX_T,
    Bitstream,
    BitstreamReader,
    Block,
    CodecDashboard,
    CodecMiddleware,
    CodecStatistics,
    DCTTransform,
    EntropyEncoder,
    Frame,
    FrameType,
    FizzBuzzFrameGenerator,
    MotionEstimator,
    MotionVector,
    NALUnit,
    NALUnitType,
    Quantizer,
    SearchPattern,
    VideoDecoder,
    VideoEncoder,
)
from enterprise_fizzbuzz.domain.exceptions import (
    CodecBitstreamError,
    CodecFrameError,
    CodecQuantizationError,
)
from enterprise_fizzbuzz.domain.interfaces import IMiddleware
from enterprise_fizzbuzz.domain.models import (
    FizzBuzzResult,
    ProcessingContext,
    RuleDefinition,
    RuleMatch,
)


# ============================================================
# Helpers
# ============================================================


def _make_context(number: int, output: str = "", matched_rules: list | None = None) -> ProcessingContext:
    """Create a ProcessingContext with a FizzBuzzResult for testing."""
    ctx = ProcessingContext(number=number, session_id=str(uuid.uuid4()))
    rules = matched_rules or []
    result = FizzBuzzResult(number=number, output=output or str(number), matched_rules=rules)
    ctx.results.append(result)
    return ctx


def _passthrough(ctx: ProcessingContext) -> ProcessingContext:
    """A no-op next_handler for middleware testing."""
    return ctx


def _make_constant_block(value: int = 128) -> list[list[int]]:
    """Create a 4x4 block with all pixels set to the same value."""
    return [[value] * BLOCK_SIZE for _ in range(BLOCK_SIZE)]


def _make_gradient_block() -> list[list[int]]:
    """Create a 4x4 block with a horizontal gradient."""
    return [[r * BLOCK_SIZE + c for c in range(BLOCK_SIZE)] for r in range(BLOCK_SIZE)]


def _make_test_frame(width: int = 16, height: int = 16, value: int = 128) -> Frame:
    """Create a test frame filled with a constant value."""
    frame = Frame(width=width, height=height)
    for r in range(height):
        for c in range(width):
            frame.set_pixel(r, c, value)
    return frame


# ============================================================
# Frame Tests
# ============================================================


class TestFrame:
    """Verify Frame pixel access and block operations."""

    def test_create_empty_frame(self) -> None:
        frame = Frame(width=16, height=16)
        assert frame.width == 16
        assert frame.height == 16
        assert frame.get_pixel(0, 0) == 0

    def test_set_and_get_pixel(self) -> None:
        frame = Frame(width=8, height=8)
        frame.set_pixel(3, 5, 200)
        assert frame.get_pixel(3, 5) == 200

    def test_pixel_clamping_high(self) -> None:
        frame = Frame(width=8, height=8)
        frame.set_pixel(0, 0, 300)
        assert frame.get_pixel(0, 0) == MAX_PIXEL_VALUE

    def test_pixel_clamping_low(self) -> None:
        frame = Frame(width=8, height=8)
        frame.set_pixel(0, 0, -50)
        assert frame.get_pixel(0, 0) == 0

    def test_out_of_bounds_read_returns_zero(self) -> None:
        frame = Frame(width=4, height=4)
        assert frame.get_pixel(10, 10) == 0

    def test_out_of_bounds_write_is_safe(self) -> None:
        frame = Frame(width=4, height=4)
        frame.set_pixel(10, 10, 100)  # Should not raise

    def test_get_block(self) -> None:
        frame = Frame(width=8, height=8)
        for r in range(4):
            for c in range(4):
                frame.set_pixel(r, c, (r + 1) * 10 + c)
        block = frame.get_block(0, 0)
        assert block[0][0] == 10
        assert block[3][3] == 43

    def test_set_block(self) -> None:
        frame = Frame(width=8, height=8)
        block = [[100] * 4 for _ in range(4)]
        frame.set_block(0, 0, block)
        assert frame.get_pixel(0, 0) == 100
        assert frame.get_pixel(3, 3) == 100

    def test_copy_is_deep(self) -> None:
        frame = Frame(width=4, height=4)
        frame.set_pixel(0, 0, 42)
        copy = frame.copy()
        copy.set_pixel(0, 0, 99)
        assert frame.get_pixel(0, 0) == 42

    def test_frame_type_default(self) -> None:
        frame = Frame(width=4, height=4)
        assert frame.frame_type == FrameType.I_FRAME


# ============================================================
# Block Tests
# ============================================================


class TestBlock:
    """Verify Block data class initialization."""

    def test_default_block_creation(self) -> None:
        block = Block(row=0, col=0)
        assert block.size == BLOCK_SIZE
        assert len(block.pixels) == BLOCK_SIZE

    def test_block_with_custom_size(self) -> None:
        block = Block(row=0, col=0, size=8)
        assert block.size == 8


# ============================================================
# MotionVector Tests
# ============================================================


class TestMotionVector:
    """Verify MotionVector data class and representation."""

    def test_default_motion_vector(self) -> None:
        mv = MotionVector()
        assert mv.dx == 0
        assert mv.dy == 0
        assert mv.sad == 0

    def test_motion_vector_repr(self) -> None:
        mv = MotionVector(dx=3, dy=-2, sad=100)
        assert "3" in repr(mv)
        assert "-2" in repr(mv)

    def test_motion_vector_with_displacement(self) -> None:
        mv = MotionVector(dx=5, dy=-3, sad=42)
        assert mv.dx == 5
        assert mv.dy == -3
        assert mv.sad == 42


# ============================================================
# DCT Transform Tests
# ============================================================


class TestDCTTransform:
    """Verify the 4x4 integer DCT transform correctness."""

    def test_dct_matrix_is_4x4(self) -> None:
        assert len(DCT_MATRIX) == 4
        assert all(len(row) == 4 for row in DCT_MATRIX)

    def test_dct_matrix_first_row(self) -> None:
        assert DCT_MATRIX[0] == [1, 1, 1, 1]

    def test_dct_matrix_second_row(self) -> None:
        assert DCT_MATRIX[1] == [2, 1, -1, -2]

    def test_forward_constant_block(self) -> None:
        """A constant block should have energy concentrated in DC coefficient."""
        block = _make_constant_block(100)
        result = DCTTransform.forward(block)
        # DC coefficient (top-left) should be dominant
        dc = result[0][0]
        assert dc != 0
        # AC coefficients should be zero for constant input
        for r in range(BLOCK_SIZE):
            for c in range(BLOCK_SIZE):
                if r == 0 and c == 0:
                    continue
                assert result[r][c] == 0

    def test_forward_zero_block(self) -> None:
        block = [[0] * BLOCK_SIZE for _ in range(BLOCK_SIZE)]
        result = DCTTransform.forward(block)
        for r in range(BLOCK_SIZE):
            for c in range(BLOCK_SIZE):
                assert result[r][c] == 0

    def test_round_trip_constant(self) -> None:
        """Forward then inverse DCT should approximately recover the original."""
        block = _make_constant_block(100)
        coeffs = DCTTransform.forward(block)
        recovered = DCTTransform.inverse(coeffs)
        for r in range(BLOCK_SIZE):
            for c in range(BLOCK_SIZE):
                assert abs(recovered[r][c] - 100) < 2

    def test_round_trip_gradient(self) -> None:
        block = _make_gradient_block()
        coeffs = DCTTransform.forward(block)
        recovered = DCTTransform.inverse(coeffs)
        for r in range(BLOCK_SIZE):
            for c in range(BLOCK_SIZE):
                assert abs(recovered[r][c] - block[r][c]) < 3

    def test_forward_rejects_wrong_size(self) -> None:
        block = [[0] * 3 for _ in range(3)]
        with pytest.raises(CodecFrameError):
            DCTTransform.forward(block)

    def test_inverse_rejects_wrong_size(self) -> None:
        block = [[0] * 5 for _ in range(5)]
        with pytest.raises(CodecFrameError):
            DCTTransform.inverse(block)

    def test_transpose_matrix_matches(self) -> None:
        for i in range(BLOCK_SIZE):
            for j in range(BLOCK_SIZE):
                assert DCT_MATRIX_T[i][j] == DCT_MATRIX[j][i]


# ============================================================
# Quantizer Tests
# ============================================================


class TestQuantizer:
    """Verify quantization and dequantization behavior."""

    def test_default_qp(self) -> None:
        q = Quantizer()
        assert q.qp == DEFAULT_QP

    def test_custom_qp(self) -> None:
        q = Quantizer(qp=10)
        assert q.qp == 10

    def test_step_size_increases_with_qp(self) -> None:
        q_low = Quantizer(qp=6)
        q_high = Quantizer(qp=30)
        assert q_high.step_size > q_low.step_size

    def test_invalid_qp_negative(self) -> None:
        with pytest.raises(CodecQuantizationError):
            Quantizer(qp=-1)

    def test_invalid_qp_too_high(self) -> None:
        with pytest.raises(CodecQuantizationError):
            Quantizer(qp=52)

    def test_quantize_zero_block(self) -> None:
        q = Quantizer(qp=20)
        block = [[0] * BLOCK_SIZE for _ in range(BLOCK_SIZE)]
        result = q.quantize(block)
        for row in result:
            for val in row:
                assert val == 0

    def test_quantize_dequantize_round_trip(self) -> None:
        q = Quantizer(qp=0)
        block = [[10, 20, 30, 40], [50, 60, 70, 80],
                 [90, 100, 110, 120], [130, 140, 150, 160]]
        quantized = q.quantize(block)
        dequantized = q.dequantize(quantized)
        # At QP=0, step_size=1, round trip should be exact
        for r in range(BLOCK_SIZE):
            for c in range(BLOCK_SIZE):
                assert dequantized[r][c] == block[r][c]

    def test_quantize_negative_values(self) -> None:
        q = Quantizer(qp=12)
        block = [[-100, -50, 0, 50], [100, -200, 200, -300],
                 [0, 0, 0, 0], [1, -1, 2, -2]]
        result = q.quantize(block)
        # Negative inputs should produce negative or zero outputs
        assert result[0][0] <= 0
        assert result[0][1] <= 0

    def test_high_qp_compresses_more(self) -> None:
        block = [[100] * BLOCK_SIZE for _ in range(BLOCK_SIZE)]
        q_low = Quantizer(qp=10)
        q_high = Quantizer(qp=40)
        qz_low = q_low.quantize(block)
        qz_high = q_high.quantize(block)
        # Higher QP should produce smaller (or equal) absolute values
        sum_low = sum(abs(v) for row in qz_low for v in row)
        sum_high = sum(abs(v) for row in qz_high for v in row)
        assert sum_high <= sum_low


# ============================================================
# Entropy Encoder Tests
# ============================================================


class TestEntropyEncoder:
    """Verify Exp-Golomb entropy coding correctness."""

    def test_encode_decode_unsigned_zero(self) -> None:
        bs = Bitstream()
        EntropyEncoder.encode_unsigned(0, bs)
        reader = BitstreamReader(bs.to_bytes())
        assert EntropyEncoder.decode_unsigned(reader) == 0

    def test_encode_decode_unsigned_one(self) -> None:
        bs = Bitstream()
        EntropyEncoder.encode_unsigned(1, bs)
        reader = BitstreamReader(bs.to_bytes())
        assert EntropyEncoder.decode_unsigned(reader) == 1

    def test_encode_decode_unsigned_sequence(self) -> None:
        values = [0, 1, 2, 3, 4, 10, 50, 100, 255]
        bs = Bitstream()
        for v in values:
            EntropyEncoder.encode_unsigned(v, bs)
        reader = BitstreamReader(bs.to_bytes())
        for expected in values:
            assert EntropyEncoder.decode_unsigned(reader) == expected

    def test_encode_negative_unsigned_raises(self) -> None:
        bs = Bitstream()
        with pytest.raises(CodecBitstreamError):
            EntropyEncoder.encode_unsigned(-1, bs)

    def test_encode_decode_signed_zero(self) -> None:
        bs = Bitstream()
        EntropyEncoder.encode_signed(0, bs)
        reader = BitstreamReader(bs.to_bytes())
        assert EntropyEncoder.decode_signed(reader) == 0

    def test_encode_decode_signed_positive(self) -> None:
        bs = Bitstream()
        EntropyEncoder.encode_signed(5, bs)
        reader = BitstreamReader(bs.to_bytes())
        assert EntropyEncoder.decode_signed(reader) == 5

    def test_encode_decode_signed_negative(self) -> None:
        bs = Bitstream()
        EntropyEncoder.encode_signed(-3, bs)
        reader = BitstreamReader(bs.to_bytes())
        assert EntropyEncoder.decode_signed(reader) == -3

    def test_encode_decode_signed_sequence(self) -> None:
        values = [0, 1, -1, 2, -2, 10, -10, 50, -50]
        bs = Bitstream()
        for v in values:
            EntropyEncoder.encode_signed(v, bs)
        reader = BitstreamReader(bs.to_bytes())
        for expected in values:
            assert EntropyEncoder.decode_signed(reader) == expected

    def test_encode_decode_block(self) -> None:
        block = [[1, -2, 3, 0], [0, 0, -1, 4], [5, 0, 0, 0], [-3, 2, 1, -1]]
        bs = Bitstream()
        EntropyEncoder.encode_block(block, bs)
        reader = BitstreamReader(bs.to_bytes())
        decoded = EntropyEncoder.decode_block(reader)
        assert decoded == block


# ============================================================
# Bitstream Tests
# ============================================================


class TestBitstream:
    """Verify bit-level I/O operations."""

    def test_write_single_bit(self) -> None:
        bs = Bitstream()
        bs.write_bit(1)
        assert bs.bit_count == 1

    def test_write_multiple_bits(self) -> None:
        bs = Bitstream()
        bs.write_bits(0b1010, 4)
        assert bs.bit_count == 4

    def test_to_bytes_padding(self) -> None:
        bs = Bitstream()
        bs.write_bit(1)
        result = bs.to_bytes()
        assert len(result) == 1
        assert result[0] == 0x80  # 1 followed by 7 zero padding bits

    def test_round_trip_byte(self) -> None:
        bs = Bitstream()
        bs.write_bits(0xAB, 8)
        result = bs.to_bytes()
        assert result[0] == 0xAB

    def test_reset(self) -> None:
        bs = Bitstream()
        bs.write_bits(0xFF, 8)
        bs.reset()
        assert bs.bit_count == 0

    def test_write_unsigned(self) -> None:
        bs = Bitstream()
        bs.write_unsigned(42, 8)
        result = bs.to_bytes()
        assert result[0] == 42

    def test_reader_read_bits(self) -> None:
        reader = BitstreamReader(bytes([0xAB]))
        val = reader.read_bits(8)
        assert val == 0xAB

    def test_reader_remaining(self) -> None:
        reader = BitstreamReader(bytes([0xFF]))
        assert reader.remaining == 8
        reader.read_bits(3)
        assert reader.remaining == 5

    def test_signed_write_read(self) -> None:
        bs = Bitstream()
        bs.write_signed(-5, 8)
        reader = BitstreamReader(bs.to_bytes())
        val = reader.read_signed(8)
        assert val == -5


# ============================================================
# NAL Unit Tests
# ============================================================


class TestNALUnit:
    """Verify NAL unit serialization and deserialization."""

    def test_nal_start_code(self) -> None:
        nal = NALUnit(nal_type=NALUnitType.SLICE_IDR, payload=b'\x01\x02')
        data = nal.to_bytes()
        assert data[:3] == b'\x00\x00\x01'

    def test_nal_type_byte(self) -> None:
        nal = NALUnit(nal_type=NALUnitType.SLICE_IDR, payload=b'\x00')
        data = nal.to_bytes()
        assert data[3] == NALUnitType.SLICE_IDR.value

    def test_nal_payload_included(self) -> None:
        payload = b'\xDE\xAD\xBE\xEF'
        nal = NALUnit(nal_type=NALUnitType.SPS, payload=payload)
        data = nal.to_bytes()
        assert data[4:] == payload

    def test_nal_round_trip(self) -> None:
        original = NALUnit(nal_type=NALUnitType.SLICE_IDR, payload=b'\x01\x02\x03')
        data = original.to_bytes()
        parsed, consumed = NALUnit.from_bytes(data)
        assert parsed.nal_type == original.nal_type
        assert parsed.payload == original.payload

    def test_nal_from_bytes_too_short(self) -> None:
        with pytest.raises(CodecBitstreamError):
            NALUnit.from_bytes(b'\x00\x00')

    def test_nal_from_bytes_invalid_start_code(self) -> None:
        with pytest.raises(CodecBitstreamError):
            NALUnit.from_bytes(b'\xFF\xFF\xFF\x05')


# ============================================================
# Motion Estimator Tests
# ============================================================


class TestMotionEstimator:
    """Verify block-matching motion estimation algorithms."""

    def test_zero_motion_identical_frames(self) -> None:
        ref = _make_test_frame(16, 16, 100)
        block = ref.get_block(4, 4)
        me = MotionEstimator(search_range=4, pattern=SearchPattern.FULL_SEARCH)
        mv = me.estimate(block, 4, 4, ref)
        assert mv.dx == 0
        assert mv.dy == 0

    def test_full_search_finds_displaced_block(self) -> None:
        ref = Frame(width=32, height=32)
        # Place a unique pattern at (8, 8)
        for r in range(4):
            for c in range(4):
                ref.set_pixel(8 + r, 8 + c, 200)
        # Current block at (10, 10) contains that pattern
        block = [[200] * BLOCK_SIZE for _ in range(BLOCK_SIZE)]
        me = MotionEstimator(search_range=4, pattern=SearchPattern.FULL_SEARCH)
        mv = me.estimate(block, 10, 10, ref)
        assert mv.dy == -2
        assert mv.dx == -2

    def test_diamond_search_finds_zero_motion(self) -> None:
        ref = _make_test_frame(16, 16, 100)
        block = ref.get_block(4, 4)
        me = MotionEstimator(search_range=4, pattern=SearchPattern.DIAMOND_SEARCH)
        mv = me.estimate(block, 4, 4, ref)
        assert mv.dx == 0
        assert mv.dy == 0

    def test_sad_computation(self) -> None:
        ref = _make_test_frame(8, 8, 100)
        block = [[110] * BLOCK_SIZE for _ in range(BLOCK_SIZE)]
        sad = MotionEstimator._compute_sad(block, ref, 0, 0)
        expected_sad = 10 * BLOCK_SIZE * BLOCK_SIZE
        assert sad == expected_sad


# ============================================================
# Frame Generator Tests
# ============================================================


class TestFizzBuzzFrameGenerator:
    """Verify text-to-frame rendering."""

    def test_generate_empty_text(self) -> None:
        gen = FizzBuzzFrameGenerator(frame_width=32, frame_height=16)
        frame = gen.generate_frame("")
        assert frame.width == 32
        assert frame.height == 16

    def test_generate_increments_frame_count(self) -> None:
        gen = FizzBuzzFrameGenerator()
        f1 = gen.generate_frame("Fizz")
        f2 = gen.generate_frame("Buzz")
        assert f2.frame_number == 1

    def test_generate_with_frame_type(self) -> None:
        gen = FizzBuzzFrameGenerator()
        frame = gen.generate_frame("FizzBuzz", frame_type=FrameType.P_FRAME)
        assert frame.frame_type == FrameType.P_FRAME

    def test_generate_sequence_gop_structure(self) -> None:
        gen = FizzBuzzFrameGenerator()
        texts = ["1", "2", "Fizz", "4", "Buzz", "Fizz", "7", "8"]
        frames = gen.generate_sequence(texts, gop_size=4)
        assert frames[0].frame_type == FrameType.I_FRAME
        assert frames[1].frame_type == FrameType.P_FRAME
        assert frames[4].frame_type == FrameType.I_FRAME

    def test_frame_has_nonzero_pixels(self) -> None:
        gen = FizzBuzzFrameGenerator(frame_width=64, frame_height=32)
        frame = gen.generate_frame("Hello")
        total = sum(frame.get_pixel(r, c) for r in range(32) for c in range(64))
        assert total > 0

    def test_frame_dimensions_match(self) -> None:
        gen = FizzBuzzFrameGenerator(frame_width=80, frame_height=40)
        assert gen.frame_width == 80
        assert gen.frame_height == 40


# ============================================================
# Video Encoder Tests
# ============================================================


class TestVideoEncoder:
    """Verify the complete video encoding pipeline."""

    def test_encode_single_i_frame(self) -> None:
        encoder = VideoEncoder(qp=20)
        frame = _make_test_frame(16, 16, 128)
        frame.frame_type = FrameType.I_FRAME
        nal = encoder.encode_frame(frame)
        assert nal.nal_type == NALUnitType.SLICE_IDR
        assert len(nal.payload) > 0

    def test_encode_p_frame_after_i_frame(self) -> None:
        encoder = VideoEncoder(qp=20)
        i_frame = _make_test_frame(16, 16, 128)
        i_frame.frame_type = FrameType.I_FRAME
        encoder.encode_frame(i_frame)
        p_frame = _make_test_frame(16, 16, 130)
        p_frame.frame_type = FrameType.P_FRAME
        p_frame.frame_number = 1
        nal = encoder.encode_frame(p_frame)
        assert nal.nal_type == NALUnitType.SLICE_NON_IDR

    def test_statistics_updated(self) -> None:
        encoder = VideoEncoder(qp=20)
        frame = _make_test_frame(16, 16, 100)
        encoder.encode_frame(frame)
        stats = encoder.statistics
        assert stats.total_frames == 1
        assert stats.i_frames == 1
        assert stats.total_input_bytes > 0
        assert stats.total_output_bytes > 0

    def test_psnr_computed(self) -> None:
        encoder = VideoEncoder(qp=10)
        frame = _make_test_frame(16, 16, 128)
        encoder.encode_frame(frame)
        assert encoder.statistics.average_psnr > 0

    def test_encode_sequence(self) -> None:
        encoder = VideoEncoder(qp=20, gop_size=2)
        gen = FizzBuzzFrameGenerator(frame_width=16, frame_height=16)
        frames = gen.generate_sequence(["1", "2", "Fizz", "4"], gop_size=2)
        nals = encoder.encode_sequence(frames)
        assert len(nals) == 4

    def test_get_bitstream(self) -> None:
        encoder = VideoEncoder(qp=20)
        frame = _make_test_frame(16, 16, 100)
        encoder.encode_frame(frame)
        bitstream = encoder.get_bitstream()
        assert len(bitstream) > 0
        assert bitstream[:3] == b'\x00\x00\x01'


# ============================================================
# Video Decoder Tests
# ============================================================


class TestVideoDecoder:
    """Verify the video decoding pipeline and round-trip correctness."""

    def test_decode_single_frame(self) -> None:
        encoder = VideoEncoder(qp=10)
        frame = _make_test_frame(16, 16, 128)
        nal = encoder.encode_frame(frame)
        decoder = VideoDecoder()
        decoded = decoder.decode_nal(nal)
        assert decoded.width == 16
        assert decoded.height == 16

    def test_decode_preserves_frame_type(self) -> None:
        encoder = VideoEncoder(qp=10)
        frame = _make_test_frame(16, 16, 128)
        frame.frame_type = FrameType.I_FRAME
        nal = encoder.encode_frame(frame)
        decoder = VideoDecoder()
        decoded = decoder.decode_nal(nal)
        assert decoded.frame_type == FrameType.I_FRAME

    def test_round_trip_constant_frame(self) -> None:
        """Encoding then decoding a constant frame should preserve pixel values."""
        encoder = VideoEncoder(qp=0)
        frame = _make_test_frame(16, 16, 100)
        nal = encoder.encode_frame(frame)
        decoder = VideoDecoder()
        decoded = decoder.decode_nal(nal)
        for r in range(16):
            for c in range(16):
                assert abs(decoded.get_pixel(r, c) - 100) < 5

    def test_round_trip_sequence(self) -> None:
        encoder = VideoEncoder(qp=10, gop_size=2)
        gen = FizzBuzzFrameGenerator(frame_width=16, frame_height=16)
        frames = gen.generate_sequence(["Fizz", "Buzz"], gop_size=2)
        nals = encoder.encode_sequence(frames)
        decoder = VideoDecoder()
        decoded_frames = decoder.decode_sequence(nals)
        assert len(decoded_frames) == 2

    def test_decoded_frames_list(self) -> None:
        encoder = VideoEncoder(qp=20)
        frame = _make_test_frame(16, 16, 50)
        nal = encoder.encode_frame(frame)
        decoder = VideoDecoder()
        decoder.decode_nal(nal)
        assert len(decoder.decoded_frames) == 1


# ============================================================
# Codec Statistics Tests
# ============================================================


class TestCodecStatistics:
    """Verify codec statistics computation."""

    def test_compression_ratio_zero_output(self) -> None:
        stats = CodecStatistics()
        assert stats.compression_ratio == 0.0

    def test_compression_ratio(self) -> None:
        stats = CodecStatistics(total_input_bytes=1000, total_output_bytes=250)
        assert stats.compression_ratio == 4.0

    def test_average_psnr_no_frames(self) -> None:
        stats = CodecStatistics()
        assert stats.average_psnr == 0.0

    def test_average_psnr(self) -> None:
        stats = CodecStatistics(total_frames=2, total_psnr=80.0)
        assert stats.average_psnr == 40.0

    def test_average_bitrate(self) -> None:
        stats = CodecStatistics(total_frames=10, total_output_bytes=500)
        assert stats.average_bitrate == 400.0  # 500 * 8 / 10


# ============================================================
# Codec Dashboard Tests
# ============================================================


class TestCodecDashboard:
    """Verify dashboard rendering."""

    def test_render_empty_stats(self) -> None:
        stats = CodecStatistics()
        output = CodecDashboard.render(stats)
        assert "FIZZCODEC" in output

    def test_render_with_data(self) -> None:
        stats = CodecStatistics(
            total_frames=10,
            i_frames=3,
            p_frames=7,
            total_input_bytes=10000,
            total_output_bytes=2500,
            total_psnr=350.0,
            min_psnr=30.0,
            max_psnr=40.0,
            total_motion_vectors=100,
            zero_motion_vectors=60,
        )
        output = CodecDashboard.render(stats)
        assert "Compression Ratio" in output
        assert "PSNR" in output
        assert "Motion Vectors" in output

    def test_render_custom_width(self) -> None:
        stats = CodecStatistics()
        output = CodecDashboard.render(stats, width=80)
        lines = output.split("\n")
        assert len(lines[0]) == 80


# ============================================================
# Codec Middleware Tests
# ============================================================


class TestCodecMiddleware:
    """Verify middleware integration with the evaluation pipeline."""

    def test_implements_imiddleware(self) -> None:
        mw = CodecMiddleware()
        assert isinstance(mw, IMiddleware)

    def test_get_name(self) -> None:
        mw = CodecMiddleware()
        assert mw.get_name() == "CodecMiddleware"

    def test_process_encodes_frame(self) -> None:
        mw = CodecMiddleware(qp=20)
        ctx = _make_context(3, "Fizz")
        mw.process(ctx, _passthrough)
        assert mw.encoder.statistics.total_frames == 1

    def test_process_multiple_frames(self) -> None:
        mw = CodecMiddleware(qp=20, gop_size=2)
        for i in range(5):
            ctx = _make_context(i + 1, str(i + 1))
            mw.process(ctx, _passthrough)
        assert mw.encoder.statistics.total_frames == 5

    def test_process_passes_through(self) -> None:
        mw = CodecMiddleware()
        ctx = _make_context(15, "FizzBuzz")
        result = mw.process(ctx, _passthrough)
        assert result is ctx

    def test_finalize_returns_stats(self) -> None:
        mw = CodecMiddleware(qp=20)
        ctx = _make_context(1, "1")
        mw.process(ctx, _passthrough)
        stats = mw.finalize()
        assert stats is not None
        assert stats.total_frames == 1

    def test_finalize_no_frames(self) -> None:
        mw = CodecMiddleware()
        assert mw.finalize() is None

    def test_render_dashboard(self) -> None:
        mw = CodecMiddleware(qp=20)
        ctx = _make_context(3, "Fizz")
        mw.process(ctx, _passthrough)
        output = mw.render_dashboard()
        assert "FIZZCODEC" in output

    def test_gop_structure_in_middleware(self) -> None:
        mw = CodecMiddleware(qp=20, gop_size=3)
        for i in range(6):
            ctx = _make_context(i + 1, str(i + 1))
            mw.process(ctx, _passthrough)
        stats = mw.encoder.statistics
        assert stats.i_frames == 2  # Frames 0, 3 are I-frames
        assert stats.p_frames == 4


# ============================================================
# PSNR Tests
# ============================================================


class TestPSNR:
    """Verify PSNR computation correctness."""

    def test_psnr_identical_frames(self) -> None:
        frame = _make_test_frame(8, 8, 100)
        psnr = VideoEncoder._compute_psnr(frame, frame.copy())
        assert psnr == float('inf')

    def test_psnr_different_frames(self) -> None:
        original = _make_test_frame(8, 8, 100)
        modified = _make_test_frame(8, 8, 110)
        psnr = VideoEncoder._compute_psnr(original, modified)
        # MSE = 100, PSNR = 10*log10(255^2/100) = ~28.13 dB
        assert 25.0 < psnr < 30.0

    def test_psnr_decreases_with_error(self) -> None:
        original = _make_test_frame(8, 8, 128)
        slight = _make_test_frame(8, 8, 130)
        heavy = _make_test_frame(8, 8, 200)
        psnr_slight = VideoEncoder._compute_psnr(original, slight)
        psnr_heavy = VideoEncoder._compute_psnr(original, heavy)
        assert psnr_slight > psnr_heavy

    def test_psnr_empty_frame(self) -> None:
        frame = Frame(width=0, height=0)
        psnr = VideoEncoder._compute_psnr(frame, frame)
        assert psnr == 0.0


# ============================================================
# FrameType Enum Tests
# ============================================================


class TestFrameType:
    """Verify frame type enumeration."""

    def test_i_frame_exists(self) -> None:
        assert FrameType.I_FRAME is not None

    def test_p_frame_exists(self) -> None:
        assert FrameType.P_FRAME is not None

    def test_two_frame_types(self) -> None:
        assert len(FrameType) == 2


# ============================================================
# NALUnitType Enum Tests
# ============================================================


class TestNALUnitType:
    """Verify NAL unit type enumeration values."""

    def test_slice_idr_value(self) -> None:
        assert NALUnitType.SLICE_IDR.value == 5

    def test_slice_non_idr_value(self) -> None:
        assert NALUnitType.SLICE_NON_IDR.value == 1

    def test_sps_value(self) -> None:
        assert NALUnitType.SPS.value == 7

    def test_pps_value(self) -> None:
        assert NALUnitType.PPS.value == 8
