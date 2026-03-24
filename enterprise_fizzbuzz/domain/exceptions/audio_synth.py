"""
Enterprise FizzBuzz Platform - Audio Synthesis Exceptions (EFP-AS00 through EFP-AS09)
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from ._base import FizzBuzzError


class AudioSynthError(FizzBuzzError):
    """Base exception for all FizzSynth digital audio synthesizer errors.

    The audio synthesis pipeline converts FizzBuzz evaluation sequences
    into PCM audio. When the pipeline fails, the polyrhythmic
    sonification of the 3-against-5 divisibility pattern is compromised,
    leaving the operator unable to hear whether a number is divisible
    by 3, 5, or both.
    """

    def __init__(
        self,
        message: str,
        *,
        error_code: str = "EFP-AS00",
        context: Optional[dict[str, Any]] = None,
    ) -> None:
        super().__init__(message, error_code=error_code, context=context)


class InvalidWaveformError(AudioSynthError):
    """Raised when an unsupported waveform type is requested.

    The FizzSynth engine supports four waveform types: SINE, SQUARE,
    SAWTOOTH, and TRIANGLE. Requesting any other waveform would require
    extending the oscillator's sample generation kernel, which is a
    non-trivial DSP engineering effort.
    """

    def __init__(self, waveform_name: str) -> None:
        super().__init__(
            f"Unsupported waveform type: '{waveform_name}'. "
            f"Supported types: SINE, SQUARE, SAWTOOTH, TRIANGLE.",
            error_code="EFP-AS01",
            context={"waveform_name": waveform_name},
        )


class InvalidFrequencyError(AudioSynthError):
    """Raised when a frequency value is outside the audible or safe range.

    Human hearing spans roughly 20 Hz to 20,000 Hz. Frequencies below
    this range produce inaudible infrasound; frequencies above it
    risk aliasing artifacts at the 44.1 kHz sample rate. Both are
    unacceptable for enterprise-grade FizzBuzz sonification.
    """

    def __init__(self, frequency: float) -> None:
        super().__init__(
            f"Frequency {frequency:.2f} Hz is outside the supported range. "
            f"The audible spectrum for FizzBuzz sonification is 20 Hz to 20,000 Hz.",
            error_code="EFP-AS02",
            context={"frequency": frequency},
        )


class WAVWriteError(AudioSynthError):
    """Raised when the WAV file writer fails to produce output.

    WAV file generation requires writing a valid RIFF header followed
    by 16-bit signed PCM sample data. Failure at any stage of this
    process means the FizzBuzz composition cannot be persisted to disk
    for later auditory analysis.
    """

    def __init__(self, filepath: str, reason: str) -> None:
        super().__init__(
            f"Failed to write WAV file '{filepath}': {reason}",
            error_code="EFP-AS03",
            context={"filepath": filepath},
        )


class EnvelopeConfigurationError(AudioSynthError):
    """Raised when ADSR envelope parameters are invalid.

    All envelope durations must be non-negative, and the sustain
    level must be between 0.0 and 1.0. An improperly configured
    envelope can cause amplitude discontinuities (clicks) or
    silence where music was expected.
    """

    def __init__(self, parameter: str, value: float, reason: str) -> None:
        super().__init__(
            f"Invalid ADSR envelope parameter '{parameter}' = {value}: {reason}",
            error_code="EFP-AS04",
            context={"parameter": parameter, "value": value},
        )


class FilterInstabilityError(AudioSynthError):
    """Raised when biquad filter coefficients produce an unstable response.

    An unstable IIR filter will produce exponentially growing output,
    which rapidly exceeds the representable range and results in
    digital clipping or complete signal destruction. This typically
    occurs when the cutoff frequency is too close to the Nyquist
    limit or when the Q factor is unreasonably high.
    """

    def __init__(self, filter_type: str, cutoff_hz: float, q: float) -> None:
        super().__init__(
            f"Biquad filter instability detected: type={filter_type}, "
            f"cutoff={cutoff_hz:.1f} Hz, Q={q:.3f}. "
            f"The filter poles have escaped the unit circle.",
            error_code="EFP-AS05",
            context={"filter_type": filter_type, "cutoff_hz": cutoff_hz, "q": q},
        )

