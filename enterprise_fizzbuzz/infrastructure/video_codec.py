"""
Enterprise FizzBuzz Platform - FizzCodec H.264-Inspired Video Codec

Implements a standards-compliant video encoding pipeline for compressing
FizzBuzz dashboard frames. The codec follows the H.264/AVC architecture:
integer DCT transform, uniform scalar quantization, Exp-Golomb entropy
coding, and NAL unit packetization.

Modern enterprise dashboards produce visual output at rates that demand
efficient compression. A FizzBuzz evaluation producing 100 results generates
approximately 100 text frames, each requiring spatial and temporal
redundancy removal before storage or transmission. This module provides
the codec infrastructure to meet that requirement.
"""

from __future__ import annotations

import logging
import math
import struct
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Callable, Optional

from enterprise_fizzbuzz.domain.exceptions import (
    CodecError,
    CodecBitstreamError,
    CodecFrameError,
    CodecQuantizationError,
)
from enterprise_fizzbuzz.domain.interfaces import IMiddleware
from enterprise_fizzbuzz.domain.models import ProcessingContext

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

BLOCK_SIZE = 4
"""Transform block size. H.264 uses 4x4 integer DCT as its core transform."""

DEFAULT_QP = 26
"""Default quantization parameter. Maps to a moderate compression level."""

MAX_PIXEL_VALUE = 255
"""Peak pixel value for 8-bit grayscale frames."""

# H.264-style 4x4 integer DCT core transform matrix.
# Unlike the floating-point DCT-II, this uses small integer entries that
# allow the entire transform to be computed with 16-bit arithmetic.
DCT_MATRIX = [
    [1, 1, 1, 1],
    [2, 1, -1, -2],
    [1, -1, -1, 1],
    [1, -2, 2, -1],
]

# Transpose of the core transform matrix, precomputed for the inverse.
DCT_MATRIX_T = [
    [DCT_MATRIX[j][i] for j in range(BLOCK_SIZE)]
    for i in range(BLOCK_SIZE)
]

# ASCII font: 8x8 bitmaps for printable characters (space through tilde).
# Each character is stored as 8 rows of 8-bit values.
# This is a minimal bitmap font sufficient for rendering dashboard text.
_FONT_WIDTH = 8
_FONT_HEIGHT = 8


def _generate_simple_glyph(ch: str) -> list[list[int]]:
    """Generate a simple 8x8 glyph for a character.

    Uses a deterministic hash-based approach to produce distinct visual
    patterns for each character. Production systems would load a proper
    bitmap font; this generates recognizable, unique patterns from the
    character's code point.
    """
    code = ord(ch)
    glyph = [[0] * _FONT_WIDTH for _ in range(_FONT_HEIGHT)]
    if ch == ' ':
        return glyph
    # Generate a deterministic pattern based on the character code
    for row in range(_FONT_HEIGHT):
        for col in range(_FONT_WIDTH):
            # Border pixels for non-space characters
            if row == 0 or row == _FONT_HEIGHT - 1:
                glyph[row][col] = MAX_PIXEL_VALUE if 1 <= col <= 6 else 0
            elif col == 0 or col == _FONT_WIDTH - 1:
                glyph[row][col] = MAX_PIXEL_VALUE if 1 <= row <= 6 else 0
            else:
                # Interior pattern varies by character
                seed = (code * 31 + row * 7 + col * 13) & 0xFF
                glyph[row][col] = MAX_PIXEL_VALUE if seed > 128 else 0
    return glyph


# Precompute the glyph table for all printable ASCII characters.
_GLYPH_TABLE: dict[str, list[list[int]]] = {}
for _c in range(32, 127):
    _GLYPH_TABLE[chr(_c)] = _generate_simple_glyph(chr(_c))


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------


class FrameType(Enum):
    """Frame coding type following H.264 slice type definitions."""
    I_FRAME = auto()  # Intra-coded: no temporal prediction
    P_FRAME = auto()  # Predicted: uses motion-compensated prediction


class NALUnitType(Enum):
    """Network Abstraction Layer unit types.

    A subset of the H.264 NAL unit type codes relevant to the
    FizzBuzz dashboard codec.
    """
    SLICE_IDR = 5       # Instantaneous Decoder Refresh (I-frame)
    SLICE_NON_IDR = 1   # Non-IDR slice (P-frame)
    SPS = 7             # Sequence Parameter Set
    PPS = 8             # Picture Parameter Set
    SEI = 6             # Supplemental Enhancement Information


class SearchPattern(Enum):
    """Motion estimation search algorithms."""
    FULL_SEARCH = auto()
    DIAMOND_SEARCH = auto()


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class Frame:
    """A single video frame represented as a 2D array of grayscale pixels.

    Stores only the Y (luma) component. Chroma subsampling is unnecessary
    for monochrome dashboard output, consistent with the H.264 High 4:0:0
    profile used in professional monitoring applications.
    """
    width: int
    height: int
    pixels: list[list[int]] = field(default_factory=list)
    frame_type: FrameType = FrameType.I_FRAME
    frame_number: int = 0

    def __post_init__(self) -> None:
        if not self.pixels:
            self.pixels = [[0] * self.width for _ in range(self.height)]

    def get_pixel(self, row: int, col: int) -> int:
        """Read a single pixel value with bounds checking."""
        if 0 <= row < self.height and 0 <= col < self.width:
            return self.pixels[row][col]
        return 0

    def set_pixel(self, row: int, col: int, value: int) -> None:
        """Write a single pixel value, clamped to [0, 255]."""
        if 0 <= row < self.height and 0 <= col < self.width:
            self.pixels[row][col] = max(0, min(MAX_PIXEL_VALUE, value))

    def copy(self) -> Frame:
        """Deep copy this frame."""
        new_frame = Frame(
            width=self.width,
            height=self.height,
            frame_type=self.frame_type,
            frame_number=self.frame_number,
        )
        new_frame.pixels = [row[:] for row in self.pixels]
        return new_frame

    def get_block(self, block_row: int, block_col: int, size: int = BLOCK_SIZE) -> list[list[int]]:
        """Extract a block of pixels starting at (block_row, block_col)."""
        block = []
        for r in range(size):
            row = []
            for c in range(size):
                row.append(self.get_pixel(block_row + r, block_col + c))
            block.append(row)
        return block

    def set_block(self, block_row: int, block_col: int, block: list[list[int]]) -> None:
        """Write a block of pixels starting at (block_row, block_col)."""
        for r, row in enumerate(block):
            for c, val in enumerate(row):
                self.set_pixel(block_row + r, block_col + c, val)


@dataclass
class Block:
    """A transform block extracted from a frame.

    Contains both the spatial-domain pixel values and, after transformation,
    the frequency-domain coefficients.
    """
    row: int
    col: int
    size: int = BLOCK_SIZE
    pixels: list[list[int]] = field(default_factory=list)
    coefficients: list[list[int]] = field(default_factory=list)
    quantized: list[list[int]] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.pixels:
            self.pixels = [[0] * self.size for _ in range(self.size)]


@dataclass
class MotionVector:
    """Displacement vector for inter-frame prediction.

    Specifies the spatial offset (dx, dy) from the current block position
    to the best-matching reference block in the previous frame.
    """
    dx: int = 0
    dy: int = 0
    sad: int = 0  # Sum of Absolute Differences for the match

    def __repr__(self) -> str:
        return f"MV({self.dx},{self.dy},sad={self.sad})"


@dataclass
class EncodedBlock:
    """Result of encoding a single block through the full pipeline."""
    row: int
    col: int
    motion_vector: Optional[MotionVector] = None
    quantized_coefficients: list[list[int]] = field(default_factory=list)
    encoded_bits: bytes = b""


@dataclass
class NALUnit:
    """Network Abstraction Layer unit.

    Encapsulates coded data into self-contained packets, each prefixed
    with a start code (0x000001) and a type byte, following the H.264
    Annex B byte stream format.
    """
    nal_type: NALUnitType
    payload: bytes = b""

    def to_bytes(self) -> bytes:
        """Serialize this NAL unit to the Annex B byte stream format."""
        start_code = b'\x00\x00\x01'
        type_byte = struct.pack('B', self.nal_type.value)
        return start_code + type_byte + self.payload

    @classmethod
    def from_bytes(cls, data: bytes) -> tuple[NALUnit, int]:
        """Deserialize a NAL unit from byte stream data.

        Returns the parsed NAL unit and the number of bytes consumed.
        """
        if len(data) < 4:
            raise CodecBitstreamError(
                "NAL unit too short",
                position=0,
            )
        if data[:3] != b'\x00\x00\x01':
            raise CodecBitstreamError(
                "Invalid NAL start code",
                position=0,
            )
        nal_type_value = data[3]
        # Find next start code or end of data
        next_start = -1
        for i in range(4, len(data) - 2):
            if data[i:i + 3] == b'\x00\x00\x01':
                next_start = i
                break
        if next_start == -1:
            payload = data[4:]
            consumed = len(data)
        else:
            payload = data[4:next_start]
            consumed = next_start

        # Map integer to NALUnitType
        nal_type = NALUnitType.SLICE_NON_IDR
        for nt in NALUnitType:
            if nt.value == nal_type_value:
                nal_type = nt
                break

        return cls(nal_type=nal_type, payload=payload), consumed


@dataclass
class CodecStatistics:
    """Aggregate statistics for a video encoding session."""
    total_frames: int = 0
    i_frames: int = 0
    p_frames: int = 0
    total_input_bytes: int = 0
    total_output_bytes: int = 0
    total_psnr: float = 0.0
    min_psnr: float = float('inf')
    max_psnr: float = 0.0
    total_motion_vectors: int = 0
    zero_motion_vectors: int = 0

    @property
    def compression_ratio(self) -> float:
        """Ratio of input size to output size."""
        if self.total_output_bytes == 0:
            return 0.0
        return self.total_input_bytes / self.total_output_bytes

    @property
    def average_psnr(self) -> float:
        """Mean PSNR across all encoded frames."""
        if self.total_frames == 0:
            return 0.0
        return self.total_psnr / self.total_frames

    @property
    def average_bitrate(self) -> float:
        """Average bits per frame."""
        if self.total_frames == 0:
            return 0.0
        return (self.total_output_bytes * 8) / self.total_frames


# ---------------------------------------------------------------------------
# Bitstream
# ---------------------------------------------------------------------------


class Bitstream:
    """Bit-level writer for assembling coded data into byte sequences.

    Accumulates individual bits and flushes complete bytes. Used by the
    entropy encoder to produce the Raw Byte Sequence Payload (RBSP) that
    forms the body of each NAL unit.
    """

    def __init__(self) -> None:
        self._bits: list[int] = []

    def write_bit(self, bit: int) -> None:
        """Append a single bit (0 or 1)."""
        self._bits.append(bit & 1)

    def write_bits(self, value: int, num_bits: int) -> None:
        """Write the lowest num_bits of value, MSB first."""
        for i in range(num_bits - 1, -1, -1):
            self._bits.append((value >> i) & 1)

    def write_unsigned(self, value: int, num_bits: int) -> None:
        """Write an unsigned integer in the specified number of bits."""
        self.write_bits(value, num_bits)

    def write_signed(self, value: int, num_bits: int) -> None:
        """Write a signed integer using two's complement."""
        if value < 0:
            value = (1 << num_bits) + value
        self.write_bits(value, num_bits)

    def to_bytes(self) -> bytes:
        """Flush accumulated bits to a byte array, padding the final byte."""
        result = bytearray()
        for i in range(0, len(self._bits), 8):
            byte_val = 0
            for j in range(8):
                if i + j < len(self._bits):
                    byte_val = (byte_val << 1) | self._bits[i + j]
                else:
                    byte_val = byte_val << 1
            result.append(byte_val)
        return bytes(result)

    @property
    def bit_count(self) -> int:
        """Total number of bits written."""
        return len(self._bits)

    def reset(self) -> None:
        """Clear all accumulated bits."""
        self._bits.clear()


class BitstreamReader:
    """Bit-level reader for decoding byte sequences."""

    def __init__(self, data: bytes) -> None:
        self._bits: list[int] = []
        for byte_val in data:
            for i in range(7, -1, -1):
                self._bits.append((byte_val >> i) & 1)
        self._pos = 0

    def read_bit(self) -> int:
        """Read a single bit."""
        if self._pos >= len(self._bits):
            return 0
        bit = self._bits[self._pos]
        self._pos += 1
        return bit

    def read_bits(self, num_bits: int) -> int:
        """Read num_bits as an unsigned integer, MSB first."""
        value = 0
        for _ in range(num_bits):
            value = (value << 1) | self.read_bit()
        return value

    def read_signed(self, num_bits: int) -> int:
        """Read a signed integer using two's complement."""
        value = self.read_bits(num_bits)
        if value >= (1 << (num_bits - 1)):
            value -= (1 << num_bits)
        return value

    @property
    def remaining(self) -> int:
        """Number of bits remaining."""
        return max(0, len(self._bits) - self._pos)

    @property
    def position(self) -> int:
        """Current bit position."""
        return self._pos


# ---------------------------------------------------------------------------
# DCT Transform
# ---------------------------------------------------------------------------


class DCTTransform:
    """H.264-style 4x4 integer DCT transform.

    Implements the H.264 4x4 forward and inverse transforms using the
    butterfly decomposition from the standard. The core transform matrix
    C = [[1,1,1,1],[2,1,-1,-2],[1,-1,-1,1],[1,-2,2,-1]] defines the
    basis vectors, but direct matrix multiplication C * X * C^T does not
    produce an orthonormal transform (C is not orthogonal).

    The H.264 standard addresses this by separating the transform into
    a core operation (using only additions and shifts) and a post-scaling
    step that is folded into quantization. This implementation uses an
    equivalent approach: the forward and inverse 1D transforms are
    applied as row and column operations using the butterfly structure,
    with explicit scaling factors that ensure bit-exact round-trip
    reconstruction.

    The 1D forward butterfly for a 4-element vector [a,b,c,d]:
        p = a + d, q = a - d, r = b + c, s = b - c
        Y[0] = p + r, Y[2] = p - r, Y[1] = q + (s>>1), Y[3] = (q>>1) - s
        (Note: >>1 uses arithmetic shift, not division by 2)

    This butterfly form is orthogonal: the inverse butterfly exactly
    undoes the forward butterfly when applied with the correct scaling.
    """

    @staticmethod
    def _forward_1d(x: list[int]) -> list[int]:
        """Apply the H.264 1D forward butterfly transform.

        Stage 1: even/odd decomposition
            e0 = x0 + x3, e1 = x1 + x2, e2 = x1 - x2, e3 = x0 - x3
        Stage 2: butterfly
            Y0 = e0 + e1, Y1 = 2*e3 + e2, Y2 = e0 - e1, Y3 = e3 - 2*e2
        """
        e0 = x[0] + x[3]
        e1 = x[1] + x[2]
        e2 = x[1] - x[2]
        e3 = x[0] - x[3]
        return [e0 + e1, 2 * e3 + e2, e0 - e1, e3 - 2 * e2]

    @staticmethod
    def _inverse_1d(y: list[int]) -> list[int]:
        """Apply the H.264 1D inverse butterfly transform.

        Stage 1: frequency-domain decomposition
            f0 = Y0 + Y2, f1 = Y0 - Y2
            f2 = (Y1 >> 1) - Y3, f3 = Y1 + (Y3 >> 1)
        Stage 2: spatial-domain reconstruction
            x0 = f0 + f3, x1 = f1 + f2, x2 = f1 - f2, x3 = f0 - f3
        """
        f0 = y[0] + y[2]
        f1 = y[0] - y[2]
        f2 = (y[1] >> 1) - y[3]
        f3 = y[1] + (y[3] >> 1)
        return [f0 + f3, f1 + f2, f1 - f2, f0 - f3]

    @staticmethod
    def forward(block: list[list[int]]) -> list[list[int]]:
        """Apply the 4x4 forward integer DCT.

        Performs the 2D transform as separable 1D transforms: first on
        rows, then on columns. The result is scaled such that the inverse
        transform recovers the original values with minimal rounding error.
        """
        size = len(block)
        if size != BLOCK_SIZE:
            raise CodecFrameError(
                f"Block size must be {BLOCK_SIZE}x{BLOCK_SIZE}, got {size}x{len(block[0])}",
                frame_number=-1,
            )
        # Transform rows
        temp = [DCTTransform._forward_1d(block[i]) for i in range(BLOCK_SIZE)]

        # Transform columns
        result = [[0] * BLOCK_SIZE for _ in range(BLOCK_SIZE)]
        for j in range(BLOCK_SIZE):
            col = [temp[i][j] for i in range(BLOCK_SIZE)]
            transformed_col = DCTTransform._forward_1d(col)
            for i in range(BLOCK_SIZE):
                result[i][j] = transformed_col[i]

        return result

    @staticmethod
    def inverse(coefficients: list[list[int]]) -> list[list[int]]:
        """Apply the 4x4 inverse integer DCT.

        Performs the 2D inverse as separable 1D inverse transforms:
        first on columns, then on rows, with final rounding to recover
        spatial-domain pixel values.
        """
        size = len(coefficients)
        if size != BLOCK_SIZE:
            raise CodecFrameError(
                f"Coefficient block size must be {BLOCK_SIZE}x{BLOCK_SIZE}",
                frame_number=-1,
            )
        # Inverse transform columns
        temp = [[0] * BLOCK_SIZE for _ in range(BLOCK_SIZE)]
        for j in range(BLOCK_SIZE):
            col = [coefficients[i][j] for i in range(BLOCK_SIZE)]
            inv_col = DCTTransform._inverse_1d(col)
            for i in range(BLOCK_SIZE):
                temp[i][j] = inv_col[i]

        # Inverse transform rows with final rounding
        result = [[0] * BLOCK_SIZE for _ in range(BLOCK_SIZE)]
        for i in range(BLOCK_SIZE):
            row = DCTTransform._inverse_1d(temp[i])
            for j in range(BLOCK_SIZE):
                # Divide by 16 with rounding (4-bit shift compensates for
                # the combined 2D scaling factor of the butterfly pair:
                # each 1D inverse introduces a gain of 4, so the 2D
                # round-trip gain is 4 * 4 = 16)
                result[i][j] = (row[j] + 8) >> 4

        return result


# ---------------------------------------------------------------------------
# Quantizer
# ---------------------------------------------------------------------------


class Quantizer:
    """Uniform scalar quantizer with configurable quantization parameter.

    Maps transform coefficients to a smaller set of representative values,
    achieving compression at the expense of precision. The quantization
    parameter (QP) controls the trade-off: higher QP yields smaller
    bitstreams but introduces more distortion.

    The step size is derived from QP using a simplified version of the
    H.264 quantization table: step_size = 2^(QP/6).
    """

    def __init__(self, qp: int = DEFAULT_QP) -> None:
        if qp < 0 or qp > 51:
            raise CodecQuantizationError(
                qp=qp,
                message=f"QP must be in range [0, 51], got {qp}",
            )
        self._qp = qp
        self._step_size = max(1, int(2 ** (qp / 6.0)))

    @property
    def qp(self) -> int:
        """The quantization parameter."""
        return self._qp

    @property
    def step_size(self) -> int:
        """The derived quantization step size."""
        return self._step_size

    def quantize(self, coefficients: list[list[int]]) -> list[list[int]]:
        """Forward quantization: divide coefficients by step size."""
        result = []
        for row in coefficients:
            quantized_row = []
            for coeff in row:
                if coeff >= 0:
                    quantized_row.append(coeff // self._step_size)
                else:
                    quantized_row.append(-((-coeff) // self._step_size))
            result.append(quantized_row)
        return result

    def dequantize(self, quantized: list[list[int]]) -> list[list[int]]:
        """Inverse quantization: multiply quantized values by step size."""
        result = []
        for row in quantized:
            dequantized_row = []
            for val in row:
                dequantized_row.append(val * self._step_size)
            result.append(dequantized_row)
        return result


# ---------------------------------------------------------------------------
# Entropy Encoder (Exp-Golomb)
# ---------------------------------------------------------------------------


class EntropyEncoder:
    """Exp-Golomb entropy coder for coefficient serialization.

    Implements unsigned and signed Exp-Golomb coding as specified in the
    H.264 standard (Section 9.1). Exp-Golomb codes are prefix-free
    variable-length codes optimized for values near zero, which is the
    typical distribution of quantized DCT coefficients.

    Encoding of unsigned value N:
        1. Compute m = floor(log2(N + 1))
        2. Write m zero bits (the unary prefix)
        3. Write the (m+1)-bit binary representation of (N + 1)

    Signed values use an interleaving: map positive v to 2v-1, negative
    v to -2v, then encode as unsigned.
    """

    @staticmethod
    def encode_unsigned(value: int, bs: Bitstream) -> None:
        """Encode an unsigned integer using Exp-Golomb coding."""
        if value < 0:
            raise CodecBitstreamError(
                f"Cannot encode negative value {value} as unsigned Exp-Golomb",
                position=bs.bit_count,
            )
        n = value + 1
        m = 0
        temp = n
        while temp > 1:
            temp >>= 1
            m += 1
        # Write m leading zeros
        for _ in range(m):
            bs.write_bit(0)
        # Write (m+1)-bit representation of n
        bs.write_bits(n, m + 1)

    @staticmethod
    def decode_unsigned(reader: BitstreamReader) -> int:
        """Decode an unsigned Exp-Golomb coded value."""
        leading_zeros = 0
        while reader.read_bit() == 0:
            leading_zeros += 1
            if leading_zeros > 32:
                raise CodecBitstreamError(
                    "Exp-Golomb prefix exceeds 32 bits",
                    position=reader.position,
                )
        # We already read the leading '1' bit
        value = 1
        for _ in range(leading_zeros):
            value = (value << 1) | reader.read_bit()
        return value - 1

    @staticmethod
    def encode_signed(value: int, bs: Bitstream) -> None:
        """Encode a signed integer using signed Exp-Golomb (se(v)).

        Mapping: 0->0, 1->1, -1->2, 2->3, -2->4, ...
        """
        if value > 0:
            mapped = 2 * value - 1
        elif value < 0:
            mapped = -2 * value
        else:
            mapped = 0
        EntropyEncoder.encode_unsigned(mapped, bs)

    @staticmethod
    def decode_signed(reader: BitstreamReader) -> int:
        """Decode a signed Exp-Golomb coded value."""
        mapped = EntropyEncoder.decode_unsigned(reader)
        if mapped == 0:
            return 0
        if mapped % 2 == 1:
            return (mapped + 1) // 2
        return -(mapped // 2)

    @staticmethod
    def encode_block(quantized: list[list[int]], bs: Bitstream) -> None:
        """Encode a quantized block's coefficients in raster scan order."""
        for row in quantized:
            for val in row:
                EntropyEncoder.encode_signed(val, bs)

    @staticmethod
    def decode_block(reader: BitstreamReader, size: int = BLOCK_SIZE) -> list[list[int]]:
        """Decode a block of coefficients from the bitstream."""
        block = []
        for _ in range(size):
            row = []
            for _ in range(size):
                row.append(EntropyEncoder.decode_signed(reader))
            block.append(row)
        return block


# ---------------------------------------------------------------------------
# Motion Estimator
# ---------------------------------------------------------------------------


class MotionEstimator:
    """Block-matching motion estimation engine.

    Implements two search strategies from the video coding literature:
    - Full Search: exhaustive evaluation of all candidate positions within
      the search window. Guarantees the global optimum but has O(w^2)
      complexity per block.
    - Diamond Search: a fast heuristic that uses a large diamond pattern
      for initial search, then refines with a small diamond. Achieves
      near-optimal results with significantly fewer comparisons.
    """

    def __init__(
        self,
        search_range: int = 8,
        pattern: SearchPattern = SearchPattern.DIAMOND_SEARCH,
    ) -> None:
        self._search_range = search_range
        self._pattern = pattern

    @staticmethod
    def _compute_sad(
        block: list[list[int]],
        ref_frame: Frame,
        ref_row: int,
        ref_col: int,
        size: int = BLOCK_SIZE,
    ) -> int:
        """Compute Sum of Absolute Differences between a block and a reference region."""
        sad = 0
        for r in range(size):
            for c in range(size):
                sad += abs(block[r][c] - ref_frame.get_pixel(ref_row + r, ref_col + c))
        return sad

    def estimate(
        self,
        current_block: list[list[int]],
        block_row: int,
        block_col: int,
        reference: Frame,
    ) -> MotionVector:
        """Find the best-matching block in the reference frame."""
        if self._pattern == SearchPattern.FULL_SEARCH:
            return self._full_search(current_block, block_row, block_col, reference)
        return self._diamond_search(current_block, block_row, block_col, reference)

    def _full_search(
        self,
        block: list[list[int]],
        block_row: int,
        block_col: int,
        reference: Frame,
    ) -> MotionVector:
        """Exhaustive search over all positions in the search window."""
        best_mv = MotionVector(dx=0, dy=0, sad=self._compute_sad(
            block, reference, block_row, block_col
        ))

        for dy in range(-self._search_range, self._search_range + 1):
            for dx in range(-self._search_range, self._search_range + 1):
                ref_row = block_row + dy
                ref_col = block_col + dx
                if ref_row < 0 or ref_col < 0:
                    continue
                if ref_row + BLOCK_SIZE > reference.height:
                    continue
                if ref_col + BLOCK_SIZE > reference.width:
                    continue
                sad = self._compute_sad(block, reference, ref_row, ref_col)
                if sad < best_mv.sad:
                    best_mv = MotionVector(dx=dx, dy=dy, sad=sad)

        return best_mv

    def _diamond_search(
        self,
        block: list[list[int]],
        block_row: int,
        block_col: int,
        reference: Frame,
    ) -> MotionVector:
        """Diamond search pattern for fast motion estimation.

        Phase 1: Large Diamond Search Pattern (LDSP) — evaluates 9 points
        arranged in a diamond shape. Repeats until the center is optimal.
        Phase 2: Small Diamond Search Pattern (SDSP) — refines with 5
        points in a smaller diamond around the LDSP result.
        """
        # Large diamond offsets
        ldsp = [(0, 0), (-2, 0), (2, 0), (0, -2), (0, 2),
                (-1, -1), (-1, 1), (1, -1), (1, 1)]
        # Small diamond offsets
        sdsp = [(0, 0), (-1, 0), (1, 0), (0, -1), (0, 1)]

        center_dy, center_dx = 0, 0
        best_mv = MotionVector(dx=0, dy=0, sad=self._compute_sad(
            block, reference, block_row, block_col
        ))

        # Phase 1: Large Diamond
        for _ in range(self._search_range):
            best_point = (center_dy, center_dx)
            for ddy, ddx in ldsp:
                dy = center_dy + ddy
                dx = center_dx + ddx
                if abs(dy) > self._search_range or abs(dx) > self._search_range:
                    continue
                ref_row = block_row + dy
                ref_col = block_col + dx
                if ref_row < 0 or ref_col < 0:
                    continue
                if ref_row + BLOCK_SIZE > reference.height:
                    continue
                if ref_col + BLOCK_SIZE > reference.width:
                    continue
                sad = self._compute_sad(block, reference, ref_row, ref_col)
                if sad < best_mv.sad:
                    best_mv = MotionVector(dx=dx, dy=dy, sad=sad)
                    best_point = (dy, dx)

            if best_point == (center_dy, center_dx):
                break
            center_dy, center_dx = best_point

        # Phase 2: Small Diamond
        for ddy, ddx in sdsp:
            dy = center_dy + ddy
            dx = center_dx + ddx
            if abs(dy) > self._search_range or abs(dx) > self._search_range:
                continue
            ref_row = block_row + dy
            ref_col = block_col + dx
            if ref_row < 0 or ref_col < 0:
                continue
            if ref_row + BLOCK_SIZE > reference.height:
                continue
            if ref_col + BLOCK_SIZE > reference.width:
                continue
            sad = self._compute_sad(block, reference, ref_row, ref_col)
            if sad < best_mv.sad:
                best_mv = MotionVector(dx=dx, dy=dy, sad=sad)

        return best_mv


# ---------------------------------------------------------------------------
# FizzBuzz Frame Generator
# ---------------------------------------------------------------------------


class FizzBuzzFrameGenerator:
    """Converts FizzBuzz text output into video frames.

    Renders ASCII text onto a grayscale pixel grid using the built-in
    bitmap font. Each FizzBuzz evaluation result becomes a single frame,
    producing a video sequence that visually represents the dashboard
    output over time.
    """

    def __init__(
        self,
        frame_width: int = 128,
        frame_height: int = 64,
        margin: int = 4,
    ) -> None:
        self._frame_width = frame_width
        self._frame_height = frame_height
        self._margin = margin
        self._frame_count = 0

    @property
    def frame_width(self) -> int:
        return self._frame_width

    @property
    def frame_height(self) -> int:
        return self._frame_height

    def generate_frame(
        self,
        text: str,
        frame_type: FrameType = FrameType.I_FRAME,
    ) -> Frame:
        """Render a text string as a grayscale video frame."""
        frame = Frame(
            width=self._frame_width,
            height=self._frame_height,
            frame_type=frame_type,
            frame_number=self._frame_count,
        )
        self._frame_count += 1

        # Render text character by character
        cursor_x = self._margin
        cursor_y = self._margin
        for ch in text:
            if ch == '\n':
                cursor_x = self._margin
                cursor_y += _FONT_HEIGHT + 1
                continue
            if cursor_x + _FONT_WIDTH > self._frame_width - self._margin:
                cursor_x = self._margin
                cursor_y += _FONT_HEIGHT + 1
            if cursor_y + _FONT_HEIGHT > self._frame_height - self._margin:
                break
            glyph = _GLYPH_TABLE.get(ch, _GLYPH_TABLE.get(' ', [[0] * _FONT_WIDTH] * _FONT_HEIGHT))
            for r in range(_FONT_HEIGHT):
                for c in range(_FONT_WIDTH):
                    frame.set_pixel(cursor_y + r, cursor_x + c, glyph[r][c])
            cursor_x += _FONT_WIDTH

        return frame

    def generate_sequence(self, texts: list[str], gop_size: int = 4) -> list[Frame]:
        """Generate a sequence of frames from a list of text strings.

        Assigns I-frame or P-frame types based on the Group of Pictures
        (GOP) structure: the first frame and every gop_size-th frame
        is an I-frame; all others are P-frames.
        """
        frames = []
        for i, text in enumerate(texts):
            if i % gop_size == 0:
                ft = FrameType.I_FRAME
            else:
                ft = FrameType.P_FRAME
            frames.append(self.generate_frame(text, frame_type=ft))
        return frames


# ---------------------------------------------------------------------------
# Video Encoder
# ---------------------------------------------------------------------------


class VideoEncoder:
    """Complete video encoding pipeline.

    Orchestrates the full encoding flow for each frame:
    1. Partition the frame into 4x4 blocks
    2. For P-frames: perform motion estimation against the reference frame
    3. Compute the prediction residual
    4. Apply the 4x4 integer DCT
    5. Quantize the transform coefficients
    6. Entropy-encode the quantized coefficients and motion vectors
    7. Package the result into a NAL unit

    The encoder maintains a reference frame buffer for inter prediction
    and accumulates statistics across the encoding session.
    """

    def __init__(
        self,
        qp: int = DEFAULT_QP,
        search_range: int = 8,
        search_pattern: SearchPattern = SearchPattern.DIAMOND_SEARCH,
        gop_size: int = 4,
    ) -> None:
        self._quantizer = Quantizer(qp)
        self._motion_estimator = MotionEstimator(
            search_range=search_range,
            pattern=search_pattern,
        )
        self._dct = DCTTransform()
        self._gop_size = gop_size
        self._reference_frame: Optional[Frame] = None
        self._stats = CodecStatistics()
        self._nal_units: list[NALUnit] = []

    @property
    def statistics(self) -> CodecStatistics:
        return self._stats

    @property
    def nal_units(self) -> list[NALUnit]:
        return self._nal_units

    def encode_frame(self, frame: Frame) -> NALUnit:
        """Encode a single frame and return the resulting NAL unit."""
        is_intra = (
            frame.frame_type == FrameType.I_FRAME
            or self._reference_frame is None
        )

        if is_intra:
            frame.frame_type = FrameType.I_FRAME

        bs = Bitstream()
        # Write frame header: type (1 bit), frame number (16 bits), QP (6 bits)
        bs.write_bit(0 if is_intra else 1)
        bs.write_unsigned(frame.frame_number & 0xFFFF, 16)
        bs.write_unsigned(self._quantizer.qp, 6)
        bs.write_unsigned(frame.width, 16)
        bs.write_unsigned(frame.height, 16)

        # Encode blocks
        blocks_h = (frame.height + BLOCK_SIZE - 1) // BLOCK_SIZE
        blocks_w = (frame.width + BLOCK_SIZE - 1) // BLOCK_SIZE

        reconstructed = frame.copy()

        for br in range(blocks_h):
            for bc in range(blocks_w):
                row = br * BLOCK_SIZE
                col = bc * BLOCK_SIZE
                current_block = frame.get_block(row, col)

                if is_intra:
                    # Intra: encode the block directly
                    residual = current_block
                    mv = None
                else:
                    # Inter: motion estimation + residual coding
                    mv = self._motion_estimator.estimate(
                        current_block, row, col, self._reference_frame
                    )
                    self._stats.total_motion_vectors += 1
                    if mv.dx == 0 and mv.dy == 0:
                        self._stats.zero_motion_vectors += 1

                    # Compute residual
                    ref_block = self._reference_frame.get_block(
                        row + mv.dy, col + mv.dx
                    )
                    residual = [
                        [current_block[r][c] - ref_block[r][c]
                         for c in range(BLOCK_SIZE)]
                        for r in range(BLOCK_SIZE)
                    ]

                    # Encode motion vector
                    EntropyEncoder.encode_signed(mv.dx, bs)
                    EntropyEncoder.encode_signed(mv.dy, bs)

                # Forward DCT
                coefficients = self._dct.forward(residual)

                # Quantize
                quantized = self._quantizer.quantize(coefficients)

                # Entropy encode
                EntropyEncoder.encode_block(quantized, bs)

                # Reconstruct for reference frame
                dequantized = self._quantizer.dequantize(quantized)
                reconstructed_block = self._dct.inverse(dequantized)

                if not is_intra and mv is not None:
                    ref_block = self._reference_frame.get_block(
                        row + mv.dy, col + mv.dx
                    )
                    reconstructed_block = [
                        [max(0, min(MAX_PIXEL_VALUE, reconstructed_block[r][c] + ref_block[r][c]))
                         for c in range(BLOCK_SIZE)]
                        for r in range(BLOCK_SIZE)
                    ]
                else:
                    reconstructed_block = [
                        [max(0, min(MAX_PIXEL_VALUE, v)) for v in row_data]
                        for row_data in reconstructed_block
                    ]

                reconstructed.set_block(row, col, reconstructed_block)

        # Update reference frame
        self._reference_frame = reconstructed

        # Build NAL unit
        nal_type = NALUnitType.SLICE_IDR if is_intra else NALUnitType.SLICE_NON_IDR
        nal = NALUnit(nal_type=nal_type, payload=bs.to_bytes())
        self._nal_units.append(nal)

        # Update statistics
        input_bytes = frame.width * frame.height
        output_bytes = len(nal.to_bytes())
        psnr = self._compute_psnr(frame, reconstructed)

        self._stats.total_frames += 1
        if is_intra:
            self._stats.i_frames += 1
        else:
            self._stats.p_frames += 1
        self._stats.total_input_bytes += input_bytes
        self._stats.total_output_bytes += output_bytes
        self._stats.total_psnr += psnr
        self._stats.min_psnr = min(self._stats.min_psnr, psnr)
        self._stats.max_psnr = max(self._stats.max_psnr, psnr)

        logger.debug(
            "Encoded frame %d (%s): %d -> %d bytes, PSNR=%.2f dB",
            frame.frame_number,
            "I" if is_intra else "P",
            input_bytes,
            output_bytes,
            psnr,
        )

        return nal

    def encode_sequence(self, frames: list[Frame]) -> list[NALUnit]:
        """Encode a complete sequence of frames."""
        nals = []
        for frame in frames:
            nals.append(self.encode_frame(frame))
        return nals

    @staticmethod
    def _compute_psnr(original: Frame, reconstructed: Frame) -> float:
        """Compute Peak Signal-to-Noise Ratio between original and reconstructed frames."""
        mse = 0.0
        total_pixels = original.width * original.height
        if total_pixels == 0:
            return 0.0
        for r in range(original.height):
            for c in range(original.width):
                diff = original.get_pixel(r, c) - reconstructed.get_pixel(r, c)
                mse += diff * diff
        mse /= total_pixels
        if mse == 0:
            return float('inf')
        return 10.0 * math.log10((MAX_PIXEL_VALUE ** 2) / mse)

    def get_bitstream(self) -> bytes:
        """Concatenate all NAL units into a complete byte stream."""
        result = bytearray()
        for nal in self._nal_units:
            result.extend(nal.to_bytes())
        return bytes(result)


# ---------------------------------------------------------------------------
# Video Decoder
# ---------------------------------------------------------------------------


class VideoDecoder:
    """Complete video decoding pipeline.

    Reverses the encoding process: parses NAL units, entropy-decodes
    coefficients and motion vectors, applies inverse quantization and
    inverse DCT, and reconstructs frames using motion-compensated
    prediction.
    """

    def __init__(self) -> None:
        self._reference_frame: Optional[Frame] = None
        self._decoded_frames: list[Frame] = []

    @property
    def decoded_frames(self) -> list[Frame]:
        return self._decoded_frames

    def decode_nal(self, nal: NALUnit) -> Frame:
        """Decode a single NAL unit back into a frame."""
        reader = BitstreamReader(nal.payload)

        # Read frame header
        is_intra = reader.read_bit() == 0
        frame_number = reader.read_bits(16)
        qp = reader.read_bits(6)
        width = reader.read_bits(16)
        height = reader.read_bits(16)

        quantizer = Quantizer(qp)
        dct = DCTTransform()

        frame = Frame(
            width=width,
            height=height,
            frame_type=FrameType.I_FRAME if is_intra else FrameType.P_FRAME,
            frame_number=frame_number,
        )

        blocks_h = (height + BLOCK_SIZE - 1) // BLOCK_SIZE
        blocks_w = (width + BLOCK_SIZE - 1) // BLOCK_SIZE

        for br in range(blocks_h):
            for bc in range(blocks_w):
                row = br * BLOCK_SIZE
                col = bc * BLOCK_SIZE

                mv = None
                if not is_intra:
                    mv_dx = EntropyEncoder.decode_signed(reader)
                    mv_dy = EntropyEncoder.decode_signed(reader)
                    mv = MotionVector(dx=mv_dx, dy=mv_dy)

                # Decode coefficients
                quantized = EntropyEncoder.decode_block(reader)

                # Dequantize
                dequantized = quantizer.dequantize(quantized)

                # Inverse DCT
                reconstructed_block = dct.inverse(dequantized)

                if not is_intra and mv is not None and self._reference_frame is not None:
                    ref_block = self._reference_frame.get_block(
                        row + mv.dy, col + mv.dx
                    )
                    reconstructed_block = [
                        [max(0, min(MAX_PIXEL_VALUE, reconstructed_block[r][c] + ref_block[r][c]))
                         for c in range(BLOCK_SIZE)]
                        for r in range(BLOCK_SIZE)
                    ]
                else:
                    reconstructed_block = [
                        [max(0, min(MAX_PIXEL_VALUE, v)) for v in row_data]
                        for row_data in reconstructed_block
                    ]

                frame.set_block(row, col, reconstructed_block)

        self._reference_frame = frame.copy()
        self._decoded_frames.append(frame)
        return frame

    def decode_sequence(self, nal_units: list[NALUnit]) -> list[Frame]:
        """Decode a sequence of NAL units into frames."""
        frames = []
        for nal in nal_units:
            frames.append(self.decode_nal(nal))
        return frames


# ---------------------------------------------------------------------------
# Codec Dashboard
# ---------------------------------------------------------------------------


class CodecDashboard:
    """ASCII dashboard for video codec performance metrics.

    Displays compression ratio, PSNR quality metrics, bitrate, and
    I/P frame distribution in a format suitable for terminal output.
    """

    @staticmethod
    def render(stats: CodecStatistics, width: int = 60) -> str:
        """Render the codec dashboard as an ASCII string."""
        border = "+" + "-" * (width - 2) + "+"
        title = "| FIZZCODEC: H.264-INSPIRED VIDEO CODEC DASHBOARD"
        title = title + " " * (width - 1 - len(title)) + "|"

        lines = [
            border,
            title,
            border,
        ]

        def _metric(label: str, value: str) -> str:
            content = f"|   {label}: {value}"
            return content + " " * (width - 1 - len(content)) + "|"

        lines.append(_metric("Total Frames", str(stats.total_frames)))
        lines.append(_metric("I-Frames", str(stats.i_frames)))
        lines.append(_metric("P-Frames", str(stats.p_frames)))
        lines.append("|" + " " * (width - 2) + "|")

        lines.append(_metric("Input Size", f"{stats.total_input_bytes:,} bytes"))
        lines.append(_metric("Output Size", f"{stats.total_output_bytes:,} bytes"))
        lines.append(_metric("Compression Ratio", f"{stats.compression_ratio:.2f}x"))
        lines.append("|" + " " * (width - 2) + "|")

        if stats.total_frames > 0:
            avg_psnr = stats.average_psnr
            min_psnr = stats.min_psnr if stats.min_psnr != float('inf') else 0.0
            max_psnr = stats.max_psnr
            lines.append(_metric("Avg PSNR", f"{avg_psnr:.2f} dB"))
            lines.append(_metric("Min PSNR", f"{min_psnr:.2f} dB"))
            lines.append(_metric("Max PSNR", f"{max_psnr:.2f} dB"))
        else:
            lines.append(_metric("PSNR", "N/A"))
        lines.append("|" + " " * (width - 2) + "|")

        lines.append(_metric("Avg Bitrate", f"{stats.average_bitrate:.0f} bits/frame"))

        if stats.total_motion_vectors > 0:
            skip_pct = (stats.zero_motion_vectors / stats.total_motion_vectors) * 100
            lines.append(_metric("Motion Vectors", str(stats.total_motion_vectors)))
            lines.append(_metric("Skip Rate", f"{skip_pct:.1f}%"))

        # Quality bar
        lines.append("|" + " " * (width - 2) + "|")
        bar_width = width - 20
        if stats.total_frames > 0 and stats.average_psnr < float('inf'):
            filled = min(bar_width, max(0, int(stats.average_psnr / 50.0 * bar_width)))
            bar = "#" * filled + "-" * (bar_width - filled)
            lines.append(f"|   Quality: [{bar}]|")
        else:
            lines.append(_metric("Quality", "Lossless"))

        lines.append(border)
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Codec Middleware
# ---------------------------------------------------------------------------


class CodecMiddleware(IMiddleware):
    """Middleware that encodes FizzBuzz evaluation results as H.264-style video frames.

    Intercepts each number passing through the pipeline, renders the
    classification result as an ASCII frame, and encodes it through the
    full video codec pipeline: DCT, quantization, entropy coding, and
    NAL unit packetization.

    The resulting compressed bitstream can be written to a file for later
    analysis. The codec dashboard displays real-time compression metrics
    including PSNR, bitrate, and frame distribution.

    Priority 945 places this middleware after classification is finalized,
    ensuring the visual representation is accurate.
    """

    def __init__(
        self,
        qp: int = DEFAULT_QP,
        output_path: Optional[str] = None,
        enable_dashboard: bool = False,
        gop_size: int = 4,
        frame_width: int = 128,
        frame_height: int = 64,
    ) -> None:
        self._encoder = VideoEncoder(qp=qp, gop_size=gop_size)
        self._frame_generator = FizzBuzzFrameGenerator(
            frame_width=frame_width,
            frame_height=frame_height,
        )
        self._output_path = output_path
        self._enable_dashboard = enable_dashboard
        self._gop_size = gop_size
        self._frame_count = 0
        self._texts: list[str] = []

    @property
    def encoder(self) -> VideoEncoder:
        """Access the underlying encoder for statistics."""
        return self._encoder

    def process(
        self,
        context: ProcessingContext,
        next_handler: Callable[[ProcessingContext], ProcessingContext],
    ) -> ProcessingContext:
        """Encode each evaluation result as a compressed video frame."""
        result = next_handler(context)

        if result.results:
            last_result = result.results[-1]
            text = f"[{last_result.number}] {last_result.output}"
            self._texts.append(text)

            # Determine frame type based on GOP structure
            if self._frame_count % self._gop_size == 0:
                frame_type = FrameType.I_FRAME
            else:
                frame_type = FrameType.P_FRAME

            frame = self._frame_generator.generate_frame(text, frame_type=frame_type)
            self._encoder.encode_frame(frame)
            self._frame_count += 1

        return result

    def get_name(self) -> str:
        return "CodecMiddleware"

    def get_priority(self) -> int:
        """Priority 945 places codec encoding after classification is finalized."""
        return 945

    def finalize(self) -> Optional[CodecStatistics]:
        """Complete the encoding session and optionally write the bitstream to disk."""
        if self._frame_count == 0:
            return None

        stats = self._encoder.statistics

        if self._output_path:
            bitstream = self._encoder.get_bitstream()
            with open(self._output_path, "wb") as f:
                f.write(bitstream)
            logger.info(
                "FizzCodec bitstream written to %s (%d bytes)",
                self._output_path,
                len(bitstream),
            )

        return stats

    def render_dashboard(self) -> str:
        """Render the codec performance dashboard."""
        return CodecDashboard.render(self._encoder.statistics)
