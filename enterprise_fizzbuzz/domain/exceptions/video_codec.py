"""
Enterprise FizzBuzz Platform - Video Codec Exceptions
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from ._base import FizzBuzzError


class CodecError(FizzBuzzError):
    """Base exception for the FizzCodec H.264-inspired video codec subsystem.

    Video compression failures in the Enterprise FizzBuzz Platform are
    treated with the same severity as production video pipeline outages.
    A corrupted NAL unit or misquantized DCT coefficient could render
    an entire FizzBuzz dashboard sequence undecodable, preventing
    stakeholders from visually verifying evaluation correctness.
    """

    def __init__(
        self,
        message: str,
        *,
        error_code: str = "EFP-VC00",
        context: Optional[dict[str, Any]] = None,
    ) -> None:
        super().__init__(message, error_code=error_code, context=context)


class CodecBitstreamError(CodecError):
    """Raised when the entropy coding bitstream is malformed or corrupted.

    Exp-Golomb prefix codes are self-synchronizing, but a single bit
    flip in the coded data can cascade into a sequence of incorrect
    coefficient values, producing visual artifacts across all subsequent
    macroblocks in the slice. This exception indicates that the
    bitstream invariant has been violated at a specific bit position.
    """

    def __init__(self, message: str, *, position: int = 0) -> None:
        super().__init__(
            f"Bitstream error at position {position}: {message}",
            error_code="EFP-VC01",
            context={"position": position},
        )


class CodecFrameError(CodecError):
    """Raised when a frame cannot be encoded or decoded.

    Possible causes include unsupported frame dimensions, invalid block
    partitioning, or a reference frame mismatch during inter prediction.
    In a production codec, this would trigger a keyframe insertion to
    restore decoder synchronization.
    """

    def __init__(self, message: str, *, frame_number: int = -1) -> None:
        super().__init__(
            f"Frame error (frame {frame_number}): {message}",
            error_code="EFP-VC02",
            context={"frame_number": frame_number},
        )


class CodecQuantizationError(CodecError):
    """Raised when the quantization parameter is out of the valid range.

    The H.264 standard defines QP values from 0 (near-lossless) to 51
    (maximum compression). Values outside this range have no defined
    quantization step size and would produce undefined transform behavior.
    """

    def __init__(self, qp: int, message: str = "") -> None:
        super().__init__(
            message or f"Invalid quantization parameter: {qp}. Must be in [0, 51].",
            error_code="EFP-VC03",
            context={"qp": qp},
        )

