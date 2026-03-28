"""
Enterprise FizzBuzz Platform - FizzSignalProc: Digital Signal Processing Engine

Implements FFT, FIR/IIR filters, windowing functions, spectrograms,
convolution, decimation, interpolation, and the Hilbert transform for
digital signal processing of FizzBuzz evaluation sequences.

The FizzBuzz evaluation pipeline produces a discrete-time signal where
each sample is the numeric value (or a classification code) at the
corresponding index. This signal contains strong spectral content at
frequencies 1/3, 1/5, and 1/15 of the sampling rate, corresponding
to the Fizz, Buzz, and FizzBuzz periods respectively. The DSP engine
extracts these spectral features and applies filtering to isolate
each classification component.

The FFT implementation uses the Cooley-Tukey radix-2 decimation-in-time
algorithm with bit-reversal permutation. FIR filters are designed using
the windowed sinc method, and IIR filters use the bilinear transform
from analog prototype transfer functions. The Hilbert transform provides
the analytic signal representation for envelope detection.

Physical justification: Spectral analysis of the FizzBuzz signal verifies
that the divisibility pattern has the correct frequency content. A missing
or attenuated spectral peak at 1/3 fs indicates that the Fizz rule is
not firing correctly — a condition that would be difficult to diagnose
from time-domain inspection alone.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Callable, List, Optional, Tuple

from enterprise_fizzbuzz.domain.interfaces import IMiddleware
from enterprise_fizzbuzz.domain.models import ProcessingContext

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

TWO_PI = 2.0 * math.pi
DEFAULT_SAMPLE_RATE = 1.0  # normalized
DEFAULT_FIR_ORDER = 31
DEFAULT_IIR_ORDER = 4


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------

class WindowType(Enum):
    """Window function types for spectral analysis."""
    RECTANGULAR = auto()
    HANN = auto()
    HAMMING = auto()
    BLACKMAN = auto()
    KAISER = auto()


class FilterType(Enum):
    """Digital filter type classification."""
    LOW_PASS = auto()
    HIGH_PASS = auto()
    BAND_PASS = auto()
    BAND_STOP = auto()


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------

@dataclass
class SpectralBin:
    """A single frequency bin from FFT analysis."""
    frequency: float  # normalized frequency (0 to 0.5)
    magnitude: float  # |X[k]|
    phase: float  # arg(X[k]) in radians
    power: float  # |X[k]|^2


@dataclass
class FilterCoefficients:
    """FIR or IIR filter coefficients.

    For FIR filters, only b_coeffs is populated (a_coeffs = [1.0]).
    For IIR filters, both b_coeffs and a_coeffs are populated.
    """
    b_coeffs: list[float] = field(default_factory=list)  # numerator
    a_coeffs: list[float] = field(default_factory=list)  # denominator

    @property
    def is_fir(self) -> bool:
        return len(self.a_coeffs) <= 1

    @property
    def order(self) -> int:
        return max(len(self.b_coeffs), len(self.a_coeffs)) - 1


@dataclass
class SpectrogramFrame:
    """A single time frame of a spectrogram."""
    time_index: int
    bins: list[SpectralBin] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Window functions
# ---------------------------------------------------------------------------

def window_function(window_type: WindowType, length: int, beta: float = 5.0) -> list[float]:
    """Generate a window function of the specified type and length.

    Args:
        window_type: The window function to generate.
        length: Number of samples.
        beta: Shape parameter for Kaiser window.

    Returns:
        List of window coefficients.
    """
    from enterprise_fizzbuzz.domain.exceptions.fizzsignalproc import WindowError

    if length <= 0:
        raise WindowError(window_type.name, f"length must be positive, got {length}")

    if length == 1:
        return [1.0]

    n = length
    w = [0.0] * n

    if window_type == WindowType.RECTANGULAR:
        w = [1.0] * n
    elif window_type == WindowType.HANN:
        for i in range(n):
            w[i] = 0.5 * (1.0 - math.cos(TWO_PI * i / (n - 1)))
    elif window_type == WindowType.HAMMING:
        for i in range(n):
            w[i] = 0.54 - 0.46 * math.cos(TWO_PI * i / (n - 1))
    elif window_type == WindowType.BLACKMAN:
        for i in range(n):
            w[i] = (
                0.42
                - 0.5 * math.cos(TWO_PI * i / (n - 1))
                + 0.08 * math.cos(2.0 * TWO_PI * i / (n - 1))
            )
    elif window_type == WindowType.KAISER:
        if beta < 0:
            raise WindowError("Kaiser", f"beta must be non-negative, got {beta}")
        # Approximate I0 (modified Bessel function of the first kind, order 0)
        def _bessel_i0(x: float) -> float:
            total = 1.0
            term = 1.0
            for k in range(1, 25):
                term *= (x / (2.0 * k)) ** 2
                total += term
                if term < 1e-12:
                    break
            return total

        denom = _bessel_i0(beta)
        for i in range(n):
            arg = beta * math.sqrt(1.0 - ((2.0 * i / (n - 1)) - 1.0) ** 2)
            w[i] = _bessel_i0(arg) / denom

    return w


# ---------------------------------------------------------------------------
# FFT (Cooley-Tukey radix-2)
# ---------------------------------------------------------------------------

def _next_power_of_two(n: int) -> int:
    """Return the smallest power of 2 >= n."""
    p = 1
    while p < n:
        p <<= 1
    return p


def fft(signal: list[float]) -> list[complex]:
    """Compute the FFT of a real-valued signal using Cooley-Tukey radix-2.

    The input is zero-padded to the next power of 2 if necessary.

    Returns a list of complex frequency-domain values.
    """
    from enterprise_fizzbuzz.domain.exceptions.fizzsignalproc import FFTError

    if not signal:
        raise FFTError(0, "empty signal")

    n = _next_power_of_two(len(signal))
    # Zero-pad
    x = [complex(s) for s in signal] + [complex(0)] * (n - len(signal))

    # Bit-reversal permutation
    bits = int(math.log2(n))
    for i in range(n):
        j = 0
        for b in range(bits):
            if i & (1 << b):
                j |= 1 << (bits - 1 - b)
        if j > i:
            x[i], x[j] = x[j], x[i]

    # Butterfly computation
    length = 2
    while length <= n:
        half = length // 2
        w_base = math.e ** (complex(0, -TWO_PI / length))
        for start in range(0, n, length):
            w = complex(1.0, 0.0)
            for k in range(half):
                t = w * x[start + k + half]
                x[start + k + half] = x[start + k] - t
                x[start + k] = x[start + k] + t
                w *= w_base
        length *= 2

    return x


def magnitude_spectrum(fft_result: list[complex]) -> list[float]:
    """Compute the magnitude spectrum from FFT output."""
    return [abs(c) for c in fft_result]


def power_spectrum(fft_result: list[complex]) -> list[float]:
    """Compute the power spectrum from FFT output."""
    return [abs(c) ** 2 for c in fft_result]


def spectral_bins(fft_result: list[complex], sample_rate: float = 1.0) -> list[SpectralBin]:
    """Convert FFT output to a list of SpectralBin objects."""
    n = len(fft_result)
    bins = []
    for k in range(n // 2 + 1):
        freq = k * sample_rate / n
        mag = abs(fft_result[k])
        phase = math.atan2(fft_result[k].imag, fft_result[k].real)
        pwr = mag ** 2
        bins.append(SpectralBin(frequency=freq, magnitude=mag, phase=phase, power=pwr))
    return bins


# ---------------------------------------------------------------------------
# FIR filter design (windowed sinc)
# ---------------------------------------------------------------------------

def design_fir_lowpass(
    cutoff: float, order: int = DEFAULT_FIR_ORDER, window: WindowType = WindowType.HAMMING
) -> FilterCoefficients:
    """Design a FIR low-pass filter using the windowed sinc method.

    Args:
        cutoff: Normalized cutoff frequency (0 to 0.5).
        order: Filter order (must be even for Type I FIR).
        window: Window function to apply.
    """
    from enterprise_fizzbuzz.domain.exceptions.fizzsignalproc import FilterDesignError

    if not 0.0 < cutoff < 0.5:
        raise FilterDesignError("FIR low-pass", f"cutoff {cutoff} not in (0, 0.5)")
    if order < 1:
        raise FilterDesignError("FIR low-pass", f"order must be >= 1, got {order}")

    n = order + 1
    mid = order / 2.0
    wc = TWO_PI * cutoff

    # Ideal sinc impulse response
    h = []
    for i in range(n):
        if i == mid:
            h.append(2.0 * cutoff)
        else:
            x = i - mid
            h.append(math.sin(wc * x) / (math.pi * x))

    # Apply window
    w = window_function(window, n)
    h = [h[i] * w[i] for i in range(n)]

    # Normalize to unity gain at DC
    gain = sum(h)
    if abs(gain) > 1e-12:
        h = [v / gain for v in h]

    return FilterCoefficients(b_coeffs=h, a_coeffs=[1.0])


def design_fir_highpass(
    cutoff: float, order: int = DEFAULT_FIR_ORDER, window: WindowType = WindowType.HAMMING
) -> FilterCoefficients:
    """Design a FIR high-pass filter using spectral inversion."""
    from enterprise_fizzbuzz.domain.exceptions.fizzsignalproc import FilterDesignError

    if not 0.0 < cutoff < 0.5:
        raise FilterDesignError("FIR high-pass", f"cutoff {cutoff} not in (0, 0.5)")

    lp = design_fir_lowpass(cutoff, order, window)
    n = len(lp.b_coeffs)
    mid = (n - 1) // 2

    hp = [-c for c in lp.b_coeffs]
    hp[mid] += 1.0

    return FilterCoefficients(b_coeffs=hp, a_coeffs=[1.0])


# ---------------------------------------------------------------------------
# IIR filter (simple first-order)
# ---------------------------------------------------------------------------

def design_iir_lowpass(cutoff: float) -> FilterCoefficients:
    """Design a first-order IIR low-pass filter.

    Uses the bilinear transform of the analog prototype H(s) = 1/(1+s/wc).

    Args:
        cutoff: Normalized cutoff frequency (0 to 0.5).
    """
    from enterprise_fizzbuzz.domain.exceptions.fizzsignalproc import FilterDesignError

    if not 0.0 < cutoff < 0.5:
        raise FilterDesignError("IIR low-pass", f"cutoff {cutoff} not in (0, 0.5)")

    # Frequency pre-warping
    wc = math.tan(math.pi * cutoff)

    # Bilinear transform coefficients
    b0 = wc / (1.0 + wc)
    b1 = b0
    a1 = (wc - 1.0) / (1.0 + wc)

    return FilterCoefficients(b_coeffs=[b0, b1], a_coeffs=[1.0, a1])


def check_iir_stability(coeffs: FilterCoefficients) -> bool:
    """Check that all IIR filter poles are inside the unit circle.

    For a first-order filter, the single pole is at -a1.
    For higher orders, a full root-finding algorithm would be needed.
    """
    if len(coeffs.a_coeffs) == 2:
        pole_mag = abs(coeffs.a_coeffs[1])
        return pole_mag < 1.0
    # For higher orders, approximate check
    return all(abs(a) < 2.0 for a in coeffs.a_coeffs[1:])


# ---------------------------------------------------------------------------
# Filter application
# ---------------------------------------------------------------------------

def apply_fir_filter(signal: list[float], coeffs: FilterCoefficients) -> list[float]:
    """Apply a FIR filter to a signal using direct convolution."""
    n = len(signal)
    m = len(coeffs.b_coeffs)
    output = [0.0] * n

    for i in range(n):
        acc = 0.0
        for k in range(m):
            if i - k >= 0:
                acc += coeffs.b_coeffs[k] * signal[i - k]
        output[i] = acc

    return output


def apply_iir_filter(signal: list[float], coeffs: FilterCoefficients) -> list[float]:
    """Apply an IIR filter using the direct form II transposed structure."""
    from enterprise_fizzbuzz.domain.exceptions.fizzsignalproc import FilterStabilityError

    if not check_iir_stability(coeffs):
        max_pole = max(abs(a) for a in coeffs.a_coeffs[1:]) if len(coeffs.a_coeffs) > 1 else 0.0
        raise FilterStabilityError(max_pole)

    n = len(signal)
    nb = len(coeffs.b_coeffs)
    na = len(coeffs.a_coeffs)
    output = [0.0] * n

    for i in range(n):
        acc = 0.0
        for k in range(nb):
            if i - k >= 0:
                acc += coeffs.b_coeffs[k] * signal[i - k]
        for k in range(1, na):
            if i - k >= 0:
                acc -= coeffs.a_coeffs[k] * output[i - k]
        output[i] = acc

    return output


# ---------------------------------------------------------------------------
# Convolution
# ---------------------------------------------------------------------------

def convolve(signal: list[float], kernel: list[float]) -> list[float]:
    """Linear convolution of two signals.

    Returns a signal of length len(signal) + len(kernel) - 1.
    """
    from enterprise_fizzbuzz.domain.exceptions.fizzsignalproc import ConvolutionError

    if not signal or not kernel:
        raise ConvolutionError(len(signal), len(kernel), "empty input")

    n = len(signal)
    m = len(kernel)
    out_len = n + m - 1
    output = [0.0] * out_len

    for i in range(out_len):
        acc = 0.0
        for k in range(m):
            j = i - k
            if 0 <= j < n:
                acc += signal[j] * kernel[k]
        output[i] = acc

    return output


# ---------------------------------------------------------------------------
# Sample rate conversion
# ---------------------------------------------------------------------------

def decimate(signal: list[float], factor: int) -> list[float]:
    """Downsample a signal by an integer factor.

    Anti-aliasing is applied via a low-pass FIR filter with cutoff
    at 0.5/factor before downsampling.
    """
    from enterprise_fizzbuzz.domain.exceptions.fizzsignalproc import SampleRateError

    if factor < 1:
        raise SampleRateError("decimation", factor, "factor must be >= 1")

    if factor == 1:
        return list(signal)

    # Anti-alias filter
    cutoff = 0.4 / factor
    if cutoff >= 0.5:
        cutoff = 0.49
    filt = design_fir_lowpass(cutoff, order=2 * factor + 1)
    filtered = apply_fir_filter(signal, filt)

    # Downsample
    return filtered[::factor]


def interpolate(signal: list[float], factor: int) -> list[float]:
    """Upsample a signal by an integer factor with zero-insertion and filtering."""
    from enterprise_fizzbuzz.domain.exceptions.fizzsignalproc import SampleRateError

    if factor < 1:
        raise SampleRateError("interpolation", factor, "factor must be >= 1")

    if factor == 1:
        return list(signal)

    # Zero-insertion
    upsampled = [0.0] * (len(signal) * factor)
    for i, s in enumerate(signal):
        upsampled[i * factor] = s * factor

    # Interpolation filter
    cutoff = 0.4 / factor
    if cutoff >= 0.5:
        cutoff = 0.49
    filt = design_fir_lowpass(cutoff, order=2 * factor + 1)
    return apply_fir_filter(upsampled, filt)


# ---------------------------------------------------------------------------
# Hilbert transform
# ---------------------------------------------------------------------------

def hilbert_transform(signal: list[float]) -> list[complex]:
    """Compute the analytic signal using the Hilbert transform.

    The analytic signal z(t) = x(t) + j * H{x(t)} where H{} is the
    Hilbert transform. This is computed via FFT: zero the negative
    frequencies and double the positive frequencies.
    """
    fft_result = fft(signal)
    n = len(fft_result)
    half = n // 2

    # Modify spectrum for analytic signal
    analytic_fft = list(fft_result)
    analytic_fft[0] = fft_result[0]  # DC unchanged
    for k in range(1, half):
        analytic_fft[k] = 2.0 * fft_result[k]
    for k in range(half + 1, n):
        analytic_fft[k] = complex(0, 0)

    # Inverse FFT (conjugate trick)
    conjugated = [c.conjugate() for c in analytic_fft]
    inv = fft_list_complex(conjugated)
    return [c.conjugate() / n for c in inv]


def fft_list_complex(x: list[complex]) -> list[complex]:
    """FFT for a complex input (in-place Cooley-Tukey)."""
    n = len(x)
    if n <= 1:
        return x

    x = list(x)
    bits = int(math.log2(n))
    for i in range(n):
        j = 0
        for b in range(bits):
            if i & (1 << b):
                j |= 1 << (bits - 1 - b)
        if j > i:
            x[i], x[j] = x[j], x[i]

    length = 2
    while length <= n:
        half = length // 2
        w_base = math.e ** (complex(0, -TWO_PI / length))
        for start in range(0, n, length):
            w = complex(1.0, 0.0)
            for k in range(half):
                t = w * x[start + k + half]
                x[start + k + half] = x[start + k] - t
                x[start + k] = x[start + k] + t
                w *= w_base
        length *= 2

    return x


def envelope(signal: list[float]) -> list[float]:
    """Compute the amplitude envelope of a signal via the Hilbert transform."""
    analytic = hilbert_transform(signal)
    return [abs(c) for c in analytic]


# ---------------------------------------------------------------------------
# Spectrogram
# ---------------------------------------------------------------------------

def compute_spectrogram(
    signal: list[float],
    frame_size: int = 64,
    hop_size: int = 32,
    window: WindowType = WindowType.HANN,
) -> list[SpectrogramFrame]:
    """Compute a short-time Fourier transform (STFT) spectrogram.

    Divides the signal into overlapping frames, applies a window function,
    and computes the FFT of each frame.
    """
    frames = []
    w = window_function(window, frame_size)
    n = len(signal)

    time_idx = 0
    pos = 0
    while pos + frame_size <= n:
        # Extract and window the frame
        frame = [signal[pos + i] * w[i] for i in range(frame_size)]
        fft_result = fft(frame)
        bins = spectral_bins(fft_result)

        frames.append(SpectrogramFrame(time_index=time_idx, bins=bins))
        pos += hop_size
        time_idx += 1

    return frames


# ---------------------------------------------------------------------------
# DSP engine (composition root)
# ---------------------------------------------------------------------------

class DSPEngine:
    """Integrates all DSP components for FizzBuzz signal analysis.

    Maintains a running buffer of FizzBuzz evaluation values and performs
    spectral analysis, filtering, and envelope detection on the accumulated
    signal.
    """

    def __init__(
        self,
        buffer_size: int = 256,
        sample_rate: float = DEFAULT_SAMPLE_RATE,
    ) -> None:
        self.buffer_size = buffer_size
        self.sample_rate = sample_rate
        self._buffer: list[float] = []
        self._step_count = 0

    def add_sample(self, value: float) -> None:
        """Add a sample to the running buffer."""
        self._buffer.append(value)
        if len(self._buffer) > self.buffer_size:
            self._buffer = self._buffer[-self.buffer_size:]
        self._step_count += 1

    def analyze(self) -> dict:
        """Perform spectral analysis on the current buffer."""
        if len(self._buffer) < 4:
            return {
                "buffer_length": len(self._buffer),
                "dominant_frequency": 0.0,
                "spectral_energy": 0.0,
            }

        fft_result = fft(self._buffer)
        bins = spectral_bins(fft_result, self.sample_rate)

        # Find dominant frequency (exclude DC)
        non_dc = bins[1:] if len(bins) > 1 else bins
        if non_dc:
            dominant = max(non_dc, key=lambda b: b.magnitude)
        else:
            dominant = SpectralBin(0, 0, 0, 0)

        total_energy = sum(b.power for b in bins)

        return {
            "buffer_length": len(self._buffer),
            "dominant_frequency": dominant.frequency,
            "dominant_magnitude": dominant.magnitude,
            "spectral_energy": total_energy,
            "num_bins": len(bins),
        }

    @property
    def buffer(self) -> list[float]:
        return list(self._buffer)

    @property
    def step_count(self) -> int:
        return self._step_count


# ---------------------------------------------------------------------------
# Middleware
# ---------------------------------------------------------------------------

class SignalProcMiddleware(IMiddleware):
    """Middleware that performs DSP analysis on the FizzBuzz evaluation stream.

    Each evaluated number contributes a sample to the DSP buffer. The
    sample value encodes the classification: 0 for plain numbers, 3 for
    Fizz, 5 for Buzz, 15 for FizzBuzz. Spectral analysis is run
    periodically and results are attached to the processing context.

    Priority 290 positions this in the signal analysis tier.
    """

    def __init__(self, buffer_size: int = 256) -> None:
        self._engine = DSPEngine(buffer_size=buffer_size)
        self._evaluations = 0

    def process(
        self,
        context: ProcessingContext,
        next_handler: Callable[[ProcessingContext], ProcessingContext],
    ) -> ProcessingContext:
        result = next_handler(context)

        number = context.number
        is_fizz = False
        is_buzz = False
        if result.results:
            latest = result.results[-1]
            is_fizz = latest.is_fizz
            is_buzz = latest.is_buzz

        # Encode classification as signal value
        if is_fizz and is_buzz:
            sample_value = 15.0
        elif is_fizz:
            sample_value = 3.0
        elif is_buzz:
            sample_value = 5.0
        else:
            sample_value = 0.0

        self._engine.add_sample(sample_value)
        self._evaluations += 1

        try:
            analysis = self._engine.analyze()
            result.metadata["dsp_dominant_freq"] = analysis["dominant_frequency"]
            result.metadata["dsp_spectral_energy"] = analysis["spectral_energy"]
            result.metadata["dsp_buffer_length"] = analysis["buffer_length"]
        except Exception as e:
            logger.warning("DSP analysis failed for number %d: %s", number, e)
            result.metadata["dsp_error"] = str(e)

        return result

    def get_name(self) -> str:
        return "SignalProcMiddleware"

    def get_priority(self) -> int:
        return 290

    @property
    def engine(self) -> DSPEngine:
        return self._engine

    @property
    def evaluations(self) -> int:
        return self._evaluations
