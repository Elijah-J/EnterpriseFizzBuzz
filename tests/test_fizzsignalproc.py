"""
Enterprise FizzBuzz Platform - FizzSignalProc Digital Signal Processing Test Suite

Comprehensive verification of the DSP pipeline, from FFT computation
through filter design, windowing, convolution, and sample rate conversion.
An incorrect spectral peak at 1/3 fs could indicate a Fizz rule misfire,
which would constitute a frequency-domain compliance violation.
"""

from __future__ import annotations

import math
import sys
import uuid
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from enterprise_fizzbuzz.infrastructure.fizzsignalproc import (
    DEFAULT_FIR_ORDER,
    DEFAULT_SAMPLE_RATE,
    TWO_PI,
    DSPEngine,
    FilterCoefficients,
    FilterType,
    SignalProcMiddleware,
    SpectralBin,
    SpectrogramFrame,
    WindowType,
    apply_fir_filter,
    apply_iir_filter,
    check_iir_stability,
    compute_spectrogram,
    convolve,
    decimate,
    design_fir_highpass,
    design_fir_lowpass,
    design_iir_lowpass,
    envelope,
    fft,
    hilbert_transform,
    interpolate,
    magnitude_spectrum,
    power_spectrum,
    spectral_bins,
    window_function,
)
from enterprise_fizzbuzz.domain.exceptions.fizzsignalproc import (
    ConvolutionError,
    FFTError,
    FilterDesignError,
    FilterStabilityError,
    FizzSignalProcError,
    SampleRateError,
    SignalProcMiddlewareError,
    WindowError,
)
from enterprise_fizzbuzz.domain.models import (
    FizzBuzzResult,
    ProcessingContext,
)


# ===========================================================================
# Helpers
# ===========================================================================

def _make_context(number: int, output: str = "", is_fizz: bool = False, is_buzz: bool = False):
    ctx = ProcessingContext(number=number, session_id=str(uuid.uuid4()))
    result = FizzBuzzResult(number=number, output=output or str(number), matched_rules=[])
    result._is_fizz = is_fizz
    result._is_buzz = is_buzz
    ctx.results.append(result)
    return ctx


def _sine_signal(freq: float, length: int, sample_rate: float = 1.0) -> list[float]:
    return [math.sin(TWO_PI * freq * i / sample_rate) for i in range(length)]


# ===========================================================================
# Window Function Tests
# ===========================================================================

class TestWindowFunctions:
    """Verification of window function generation."""

    def test_rectangular_all_ones(self):
        w = window_function(WindowType.RECTANGULAR, 10)
        assert all(v == 1.0 for v in w)

    def test_hann_endpoints_zero(self):
        w = window_function(WindowType.HANN, 100)
        assert w[0] == pytest.approx(0.0, abs=1e-10)
        assert w[-1] == pytest.approx(0.0, abs=1e-10)

    def test_hamming_symmetric(self):
        w = window_function(WindowType.HAMMING, 50)
        for i in range(25):
            assert w[i] == pytest.approx(w[49 - i], abs=1e-10)

    def test_blackman_peak_at_center(self):
        w = window_function(WindowType.BLACKMAN, 51)
        center = w[25]
        assert center == max(w)

    def test_kaiser_positive(self):
        w = window_function(WindowType.KAISER, 20, beta=5.0)
        assert all(v > 0.0 for v in w)

    def test_zero_length_raises(self):
        with pytest.raises(WindowError):
            window_function(WindowType.HANN, 0)


# ===========================================================================
# FFT Tests
# ===========================================================================

class TestFFT:
    """Verification of the Cooley-Tukey FFT implementation."""

    def test_fft_dc_signal(self):
        signal = [1.0] * 8
        result = fft(signal)
        # DC bin should be 8.0
        assert abs(result[0]) == pytest.approx(8.0, rel=1e-6)

    def test_fft_single_frequency(self):
        n = 64
        signal = _sine_signal(0.125, n)  # frequency at bin 8
        result = fft(signal)
        mags = magnitude_spectrum(result)
        # Peak should be at bin 8
        peak_bin = max(range(1, n // 2), key=lambda k: mags[k])
        assert peak_bin == 8

    def test_fft_empty_raises(self):
        with pytest.raises(FFTError):
            fft([])

    def test_power_spectrum_non_negative(self):
        signal = [1.0, -1.0, 1.0, -1.0]
        result = fft(signal)
        ps = power_spectrum(result)
        assert all(p >= 0.0 for p in ps)

    def test_spectral_bins_have_frequency(self):
        signal = [1.0] * 16
        result = fft(signal)
        bins = spectral_bins(result, sample_rate=1.0)
        assert bins[0].frequency == pytest.approx(0.0)
        assert all(isinstance(b, SpectralBin) for b in bins)


# ===========================================================================
# FIR Filter Tests
# ===========================================================================

class TestFIRFilter:
    """Verification of FIR filter design and application."""

    def test_lowpass_design(self):
        coeffs = design_fir_lowpass(0.25, order=15)
        assert coeffs.is_fir
        assert len(coeffs.b_coeffs) == 16

    def test_lowpass_unity_gain_at_dc(self):
        coeffs = design_fir_lowpass(0.25, order=31)
        dc_gain = sum(coeffs.b_coeffs)
        assert dc_gain == pytest.approx(1.0, abs=0.01)

    def test_highpass_design(self):
        coeffs = design_fir_highpass(0.25, order=15)
        assert coeffs.is_fir

    def test_invalid_cutoff_raises(self):
        with pytest.raises(FilterDesignError):
            design_fir_lowpass(0.6)

    def test_apply_fir_preserves_length(self):
        signal = [1.0] * 20
        coeffs = design_fir_lowpass(0.25, order=7)
        filtered = apply_fir_filter(signal, coeffs)
        assert len(filtered) == len(signal)


# ===========================================================================
# IIR Filter Tests
# ===========================================================================

class TestIIRFilter:
    """Verification of IIR filter design and stability."""

    def test_iir_lowpass_design(self):
        coeffs = design_iir_lowpass(0.25)
        assert not coeffs.is_fir

    def test_iir_stability_check(self):
        coeffs = design_iir_lowpass(0.25)
        assert check_iir_stability(coeffs)

    def test_unstable_filter_detected(self):
        bad = FilterCoefficients(b_coeffs=[1.0], a_coeffs=[1.0, -2.0])
        assert not check_iir_stability(bad)

    def test_unstable_filter_application_raises(self):
        bad = FilterCoefficients(b_coeffs=[1.0], a_coeffs=[1.0, -2.0])
        with pytest.raises(FilterStabilityError):
            apply_iir_filter([1.0] * 10, bad)


# ===========================================================================
# Convolution and Sample Rate Tests
# ===========================================================================

class TestConvolutionAndResampling:
    """Verification of convolution and sample rate conversion."""

    def test_convolution_length(self):
        result = convolve([1.0, 2.0, 3.0], [1.0, 1.0])
        assert len(result) == 4

    def test_convolution_identity(self):
        result = convolve([1.0, 2.0, 3.0], [1.0])
        assert result == pytest.approx([1.0, 2.0, 3.0])

    def test_convolution_empty_raises(self):
        with pytest.raises(ConvolutionError):
            convolve([], [1.0])

    def test_decimate_by_two(self):
        signal = list(range(100))
        decimated = decimate([float(x) for x in signal], 2)
        assert len(decimated) == 50

    def test_decimate_by_one_identity(self):
        signal = [1.0, 2.0, 3.0]
        assert decimate(signal, 1) == signal

    def test_interpolate_by_two(self):
        signal = [1.0, 2.0, 3.0, 4.0]
        result = interpolate(signal, 2)
        assert len(result) == 8

    def test_invalid_decimate_factor_raises(self):
        with pytest.raises(SampleRateError):
            decimate([1.0], 0)


# ===========================================================================
# DSP Engine and Middleware Tests
# ===========================================================================

class TestDSPEngine:
    """Verification of the integrated DSP engine."""

    def test_add_sample_buffers(self):
        engine = DSPEngine(buffer_size=10)
        for i in range(5):
            engine.add_sample(float(i))
        assert engine.step_count == 5
        assert len(engine.buffer) == 5

    def test_analyze_returns_metrics(self):
        engine = DSPEngine(buffer_size=64)
        for i in range(64):
            engine.add_sample(math.sin(TWO_PI * i / 16.0))
        result = engine.analyze()
        assert "dominant_frequency" in result
        assert result["spectral_energy"] > 0.0


class TestSignalProcMiddleware:
    """Verification of the FizzSignalProc middleware integration."""

    def test_middleware_name(self):
        mw = SignalProcMiddleware()
        assert mw.get_name() == "SignalProcMiddleware"

    def test_middleware_priority(self):
        mw = SignalProcMiddleware()
        assert mw.get_priority() == 290

    def test_middleware_attaches_metadata(self):
        mw = SignalProcMiddleware(buffer_size=16)
        for i in range(1, 5):
            ctx = _make_context(i, str(i))
            mw.process(ctx, lambda c: c)
        ctx = _make_context(5, "Buzz", is_buzz=True)
        result = mw.process(ctx, lambda c: c)
        assert "dsp_dominant_freq" in result.metadata

    def test_middleware_increments_evaluations(self):
        mw = SignalProcMiddleware()
        ctx = _make_context(1, "1")
        mw.process(ctx, lambda c: c)
        assert mw.evaluations == 1
