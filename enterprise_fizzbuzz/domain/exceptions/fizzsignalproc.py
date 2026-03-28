"""
Enterprise FizzBuzz Platform - FizzSignalProc Exceptions (EFP-DSP00 through EFP-DSP07)
"""

from __future__ import annotations

from typing import Any, Optional

from ._base import FizzBuzzError


class FizzSignalProcError(FizzBuzzError):
    """Base exception for the FizzSignalProc digital signal processing subsystem.

    Digital signal processing of FizzBuzz evaluation sequences involves
    FFT computation, FIR/IIR filter design, windowing, spectral analysis,
    and sample rate conversion. Each operation has specific preconditions
    regarding signal length, sampling rate, and numerical stability that
    must be satisfied for correct results.
    """

    def __init__(
        self,
        message: str,
        *,
        error_code: str = "EFP-DSP00",
        context: dict | None = None,
    ) -> None:
        super().__init__(message, error_code=error_code, context=context)


class FFTError(FizzSignalProcError):
    """Raised when FFT computation encounters degenerate input.

    The Cooley-Tukey FFT algorithm requires input length to be
    decomposable into small prime factors for optimal performance.
    Zero-length signals or signals containing NaN values prevent
    meaningful spectral analysis.
    """

    def __init__(self, signal_length: int, reason: str) -> None:
        super().__init__(
            f"FFT failed for signal of length {signal_length}: {reason}",
            error_code="EFP-DSP01",
            context={"signal_length": signal_length, "reason": reason},
        )


class FilterDesignError(FizzSignalProcError):
    """Raised when filter design parameters are unphysical or contradictory.

    FIR and IIR filter design requires that cutoff frequencies lie
    within the Nyquist band (0, fs/2), that filter orders are
    positive integers, and that passband/stopband specifications
    are achievable within the given order.
    """

    def __init__(self, filter_type: str, reason: str) -> None:
        super().__init__(
            f"Filter design failed for {filter_type}: {reason}",
            error_code="EFP-DSP02",
            context={"filter_type": filter_type, "reason": reason},
        )


class FilterStabilityError(FizzSignalProcError):
    """Raised when an IIR filter has poles outside the unit circle.

    An IIR filter is stable if and only if all poles of its transfer
    function lie strictly inside the unit circle in the z-plane.
    Poles on or outside the unit circle produce unbounded output,
    which is unacceptable for FizzBuzz signal conditioning.
    """

    def __init__(self, max_pole_magnitude: float) -> None:
        super().__init__(
            f"IIR filter unstable: maximum pole magnitude "
            f"{max_pole_magnitude:.6f} >= 1.0",
            error_code="EFP-DSP03",
            context={"max_pole_magnitude": max_pole_magnitude},
        )


class WindowError(FizzSignalProcError):
    """Raised when a windowing function receives invalid parameters.

    Window functions require a positive length parameter and, for
    parameterized windows like Kaiser, valid shape parameters within
    their defined domains.
    """

    def __init__(self, window_type: str, reason: str) -> None:
        super().__init__(
            f"Window function '{window_type}' error: {reason}",
            error_code="EFP-DSP04",
            context={"window_type": window_type, "reason": reason},
        )


class SampleRateError(FizzSignalProcError):
    """Raised when sample rate conversion parameters are invalid.

    Decimation and interpolation factors must be positive integers.
    The anti-aliasing filter cutoff for decimation must satisfy the
    Nyquist criterion relative to the target sample rate.
    """

    def __init__(self, operation: str, factor: int, reason: str) -> None:
        super().__init__(
            f"Sample rate {operation} by factor {factor} failed: {reason}",
            error_code="EFP-DSP05",
            context={"operation": operation, "factor": factor, "reason": reason},
        )


class ConvolutionError(FizzSignalProcError):
    """Raised when convolution encounters incompatible signal dimensions."""

    def __init__(self, signal_length: int, kernel_length: int, reason: str) -> None:
        super().__init__(
            f"Convolution failed: signal length {signal_length}, "
            f"kernel length {kernel_length}: {reason}",
            error_code="EFP-DSP06",
            context={
                "signal_length": signal_length,
                "kernel_length": kernel_length,
                "reason": reason,
            },
        )


class SignalProcMiddlewareError(FizzSignalProcError):
    """Raised when the FizzSignalProc middleware encounters a fault."""

    def __init__(self, reason: str) -> None:
        super().__init__(
            f"FizzSignalProc middleware error: {reason}",
            error_code="EFP-DSP07",
            context={"reason": reason},
        )
