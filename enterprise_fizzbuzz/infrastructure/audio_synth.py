"""
Enterprise FizzBuzz Platform - FizzSynth Digital Audio Synthesizer

Provides real-time audio synthesis of FizzBuzz evaluation sequences. Every
FizzBuzz classification maps to distinct timbral and melodic parameters,
transforming the natural 3-against-5 polyrhythmic structure of the FizzBuzz
sequence into audible music.

The Fizz/Buzz divisibility pattern produces an inherent polyrhythm:
Fizz triggers on every 3rd beat and Buzz on every 5th, creating a 15-beat
composite cycle. This subsystem renders that pattern as PCM audio using
subtractive synthesis with ADSR envelope shaping, biquad filtering,
and Schroeder reverb.

Audio pipeline: Oscillator -> ADSR Envelope -> Biquad Filter -> Reverb -> WAV

All DSP is implemented in pure Python using only the standard library
(math, struct, wave). No external audio libraries are required.
"""

from __future__ import annotations

import logging
import math
import struct
import wave
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Callable, Optional

from enterprise_fizzbuzz.domain.interfaces import IMiddleware
from enterprise_fizzbuzz.domain.models import ProcessingContext

logger = logging.getLogger(__name__)

# Standard audio constants
SAMPLE_RATE = 44100
BIT_DEPTH = 16
NUM_CHANNELS = 1
MAX_AMPLITUDE = 32767  # 2^15 - 1 for 16-bit signed PCM


# ============================================================
# Waveform Enum
# ============================================================


class Waveform(Enum):
    """Oscillator waveform types available in the FizzSynth engine.

    Each waveform has distinct harmonic content, making it suitable
    for different FizzBuzz classifications. SINE is the purest tone,
    SQUARE adds odd harmonics for a hollow quality, SAWTOOTH contains
    all harmonics for brightness, and TRIANGLE provides a softer,
    rounder character.
    """

    SINE = auto()
    SQUARE = auto()
    SAWTOOTH = auto()
    TRIANGLE = auto()


# ============================================================
# Oscillator
# ============================================================


class Oscillator:
    """Digital oscillator that generates waveform samples at a given frequency.

    Implements four standard waveform generators using band-limited
    approximations suitable for 44.1 kHz sample rate output. Phase
    continuity is maintained across successive sample blocks to prevent
    audible discontinuities at buffer boundaries.
    """

    def __init__(
        self,
        frequency: float,
        waveform: Waveform = Waveform.SINE,
        sample_rate: int = SAMPLE_RATE,
        phase: float = 0.0,
    ) -> None:
        self.frequency = frequency
        self.waveform = waveform
        self.sample_rate = sample_rate
        self.phase = phase

    def generate(self, num_samples: int) -> list[float]:
        """Generate a buffer of waveform samples in the range [-1.0, 1.0].

        The phase accumulator advances continuously, ensuring glitch-free
        audio across consecutive generate() calls.
        """
        samples: list[float] = []
        phase_increment = self.frequency / self.sample_rate

        for _ in range(num_samples):
            sample = self._sample_at_phase(self.phase)
            samples.append(sample)
            self.phase += phase_increment
            if self.phase >= 1.0:
                self.phase -= 1.0

        return samples

    def _sample_at_phase(self, phase: float) -> float:
        """Compute a single sample value for the current waveform at the given phase."""
        if self.waveform == Waveform.SINE:
            return math.sin(2.0 * math.pi * phase)
        elif self.waveform == Waveform.SQUARE:
            return 1.0 if phase < 0.5 else -1.0
        elif self.waveform == Waveform.SAWTOOTH:
            return 2.0 * phase - 1.0
        elif self.waveform == Waveform.TRIANGLE:
            if phase < 0.25:
                return 4.0 * phase
            elif phase < 0.75:
                return 2.0 - 4.0 * phase
            else:
                return -4.0 + 4.0 * phase
        return 0.0

    def reset(self) -> None:
        """Reset the oscillator phase to zero."""
        self.phase = 0.0


# ============================================================
# ADSR Envelope
# ============================================================


@dataclass
class ADSREnvelope:
    """Attack-Decay-Sustain-Release envelope generator.

    Shapes the amplitude contour of each note to prevent clicking
    artifacts and provide musical dynamics. The four stages model
    the natural amplitude behavior of acoustic instruments:

    - Attack: initial amplitude ramp from 0 to peak (1.0)
    - Decay: drop from peak to sustain level
    - Sustain: held amplitude during the body of the note
    - Release: final fade from sustain level to silence

    All durations are in seconds. Sustain is a level (0.0 to 1.0),
    not a duration.
    """

    attack: float = 0.01
    decay: float = 0.05
    sustain: float = 0.7
    release: float = 0.1

    def apply(
        self,
        samples: list[float],
        sample_rate: int = SAMPLE_RATE,
        note_duration: float = 0.0,
    ) -> list[float]:
        """Apply the ADSR envelope to a buffer of audio samples.

        The note_duration parameter determines when the release phase
        begins. If note_duration is 0 or exceeds the buffer, the
        release begins at the end of the buffer.
        """
        total_samples = len(samples)
        attack_samples = int(self.attack * sample_rate)
        decay_samples = int(self.decay * sample_rate)
        release_samples = int(self.release * sample_rate)

        if note_duration > 0.0:
            sustain_end_sample = int(note_duration * sample_rate)
        else:
            sustain_end_sample = max(0, total_samples - release_samples)

        result: list[float] = []
        for i in range(total_samples):
            if i < attack_samples:
                # Attack phase: linear ramp from 0 to 1
                envelope = i / max(attack_samples, 1)
            elif i < attack_samples + decay_samples:
                # Decay phase: linear ramp from 1 to sustain level
                decay_progress = (i - attack_samples) / max(decay_samples, 1)
                envelope = 1.0 - (1.0 - self.sustain) * decay_progress
            elif i < sustain_end_sample:
                # Sustain phase: constant level
                envelope = self.sustain
            else:
                # Release phase: linear ramp from sustain to 0
                release_progress = (i - sustain_end_sample) / max(release_samples, 1)
                envelope = self.sustain * max(0.0, 1.0 - release_progress)

            result.append(samples[i] * envelope)

        return result

    def get_total_minimum_duration(self) -> float:
        """Return the minimum duration needed to complete all envelope stages."""
        return self.attack + self.decay + self.release


# ============================================================
# Biquad Filter
# ============================================================


class FilterType(Enum):
    """Biquad filter response types.

    LOW_PASS attenuates frequencies above the cutoff, suitable for
    softening harsh timbres. HIGH_PASS removes low-frequency content.
    BAND_PASS isolates a narrow frequency range.
    """

    LOW_PASS = auto()
    HIGH_PASS = auto()
    BAND_PASS = auto()


class BiquadFilter:
    """Second-order IIR (Infinite Impulse Response) biquad filter.

    Implements the standard direct-form II transposed biquad topology
    with configurable cutoff frequency and Q factor. Coefficient
    computation follows the Audio EQ Cookbook (Robert Bristow-Johnson).

    Transfer function: H(z) = (b0 + b1*z^-1 + b2*z^-2) / (a0 + a1*z^-1 + a2*z^-2)
    """

    def __init__(
        self,
        filter_type: FilterType = FilterType.LOW_PASS,
        cutoff_hz: float = 4000.0,
        q: float = 0.707,
        sample_rate: int = SAMPLE_RATE,
    ) -> None:
        self.filter_type = filter_type
        self.cutoff_hz = cutoff_hz
        self.q = q
        self.sample_rate = sample_rate

        # Filter state (delay elements)
        self._x1 = 0.0
        self._x2 = 0.0
        self._y1 = 0.0
        self._y2 = 0.0

        # Coefficients
        self.b0 = 0.0
        self.b1 = 0.0
        self.b2 = 0.0
        self.a0 = 1.0
        self.a1 = 0.0
        self.a2 = 0.0

        self._compute_coefficients()

    def _compute_coefficients(self) -> None:
        """Compute biquad filter coefficients from the Audio EQ Cookbook.

        The coefficient derivation uses bilinear transform pre-warping
        to map the analog prototype to the digital domain with accurate
        frequency response at the specified cutoff.
        """
        omega = 2.0 * math.pi * self.cutoff_hz / self.sample_rate
        sin_omega = math.sin(omega)
        cos_omega = math.cos(omega)
        alpha = sin_omega / (2.0 * self.q)

        if self.filter_type == FilterType.LOW_PASS:
            self.b0 = (1.0 - cos_omega) / 2.0
            self.b1 = 1.0 - cos_omega
            self.b2 = (1.0 - cos_omega) / 2.0
            self.a0 = 1.0 + alpha
            self.a1 = -2.0 * cos_omega
            self.a2 = 1.0 - alpha
        elif self.filter_type == FilterType.HIGH_PASS:
            self.b0 = (1.0 + cos_omega) / 2.0
            self.b1 = -(1.0 + cos_omega)
            self.b2 = (1.0 + cos_omega) / 2.0
            self.a0 = 1.0 + alpha
            self.a1 = -2.0 * cos_omega
            self.a2 = 1.0 - alpha
        elif self.filter_type == FilterType.BAND_PASS:
            self.b0 = alpha
            self.b1 = 0.0
            self.b2 = -alpha
            self.a0 = 1.0 + alpha
            self.a1 = -2.0 * cos_omega
            self.a2 = 1.0 - alpha

        # Normalize coefficients
        if self.a0 != 0.0:
            self.b0 /= self.a0
            self.b1 /= self.a0
            self.b2 /= self.a0
            self.a1 /= self.a0
            self.a2 /= self.a0
            self.a0 = 1.0

    def process(self, samples: list[float]) -> list[float]:
        """Apply the biquad filter to a buffer of samples.

        Uses the direct-form I difference equation:
            y[n] = b0*x[n] + b1*x[n-1] + b2*x[n-2] - a1*y[n-1] - a2*y[n-2]
        """
        output: list[float] = []
        for x in samples:
            y = (
                self.b0 * x
                + self.b1 * self._x1
                + self.b2 * self._x2
                - self.a1 * self._y1
                - self.a2 * self._y2
            )
            self._x2 = self._x1
            self._x1 = x
            self._y2 = self._y1
            self._y1 = y
            output.append(y)
        return output

    def reset(self) -> None:
        """Clear the filter state registers."""
        self._x1 = 0.0
        self._x2 = 0.0
        self._y1 = 0.0
        self._y2 = 0.0


# ============================================================
# Reverb Effect (Schroeder)
# ============================================================


class _CombFilter:
    """Single comb filter element for the Schroeder reverb topology.

    Implements a feedback comb filter with configurable delay and
    gain. The delay line length determines the frequency spacing
    of the comb's spectral peaks, while the gain controls decay time.
    """

    def __init__(self, delay_samples: int, gain: float) -> None:
        self.delay_samples = delay_samples
        self.gain = gain
        self._buffer = [0.0] * delay_samples
        self._index = 0

    def process_sample(self, x: float) -> float:
        """Process a single sample through the comb filter."""
        delayed = self._buffer[self._index]
        output = delayed
        self._buffer[self._index] = x + delayed * self.gain
        self._index = (self._index + 1) % self.delay_samples
        return output

    def reset(self) -> None:
        """Clear the delay buffer."""
        self._buffer = [0.0] * self.delay_samples
        self._index = 0


class _AllpassFilter:
    """Single allpass filter element for the Schroeder reverb topology.

    Passes all frequencies at equal amplitude but introduces
    frequency-dependent phase shift, which increases echo density
    without coloring the spectrum.
    """

    def __init__(self, delay_samples: int, gain: float) -> None:
        self.delay_samples = delay_samples
        self.gain = gain
        self._buffer = [0.0] * delay_samples
        self._index = 0

    def process_sample(self, x: float) -> float:
        """Process a single sample through the allpass filter."""
        delayed = self._buffer[self._index]
        output = -x + delayed
        self._buffer[self._index] = x + delayed * self.gain
        self._index = (self._index + 1) % self.delay_samples
        return output

    def reset(self) -> None:
        """Clear the delay buffer."""
        self._buffer = [0.0] * self.delay_samples
        self._index = 0


class ReverbEffect:
    """Schroeder reverb implementation using 4 comb filters and 2 allpass filters.

    The Schroeder reverb algorithm (1962) is the foundation of most
    digital reverberation systems. Four parallel feedback comb filters
    with mutually prime delay lengths provide initial echo density.
    Two series allpass filters then diffuse the output further,
    smoothing the echo pattern into a dense, natural-sounding tail.

    The wet/dry mix ratio controls the balance between the original
    signal (dry) and the reverberated signal (wet).
    """

    # Delay lengths in samples at 44100 Hz (mutually prime for maximal diffusion)
    COMB_DELAYS = [1557, 1617, 1491, 1422]
    COMB_GAINS = [0.84, 0.82, 0.80, 0.78]
    ALLPASS_DELAYS = [225, 556]
    ALLPASS_GAIN = 0.5

    def __init__(
        self,
        wet: float = 0.3,
        sample_rate: int = SAMPLE_RATE,
    ) -> None:
        self.wet = wet
        self.sample_rate = sample_rate

        scale = sample_rate / 44100.0
        self._combs = [
            _CombFilter(int(d * scale), g)
            for d, g in zip(self.COMB_DELAYS, self.COMB_GAINS)
        ]
        self._allpasses = [
            _AllpassFilter(int(d * scale), self.ALLPASS_GAIN)
            for d in self.ALLPASS_DELAYS
        ]

    def process(self, samples: list[float]) -> list[float]:
        """Apply Schroeder reverb to a buffer of samples."""
        output: list[float] = []
        for x in samples:
            # Parallel comb filters, summed
            comb_sum = 0.0
            for comb in self._combs:
                comb_sum += comb.process_sample(x)
            comb_sum /= len(self._combs)

            # Series allpass filters
            ap_out = comb_sum
            for ap in self._allpasses:
                ap_out = ap.process_sample(ap_out)

            # Wet/dry mix
            mixed = (1.0 - self.wet) * x + self.wet * ap_out
            output.append(mixed)

        return output

    def reset(self) -> None:
        """Reset all internal delay buffers."""
        for comb in self._combs:
            comb.reset()
        for ap in self._allpasses:
            ap.reset()


# ============================================================
# Note
# ============================================================


@dataclass
class Note:
    """A single musical note with full synthesis parameters.

    Encapsulates frequency, duration, waveform type, envelope settings,
    and velocity (amplitude scaling). Notes are the atomic units of
    the FizzBuzz musical sequence.
    """

    frequency: float
    duration: float
    waveform: Waveform = Waveform.SINE
    envelope: ADSREnvelope = field(default_factory=ADSREnvelope)
    velocity: float = 0.8
    detune_hz: float = 0.0

    def render(
        self,
        sample_rate: int = SAMPLE_RATE,
        filter_instance: Optional[BiquadFilter] = None,
    ) -> list[float]:
        """Render this note as a buffer of audio samples.

        The rendering pipeline: oscillator(s) -> envelope -> filter -> gain.
        When detune_hz is nonzero, a second oscillator is mixed in at
        50% amplitude to create a chorus/unison effect.
        """
        num_samples = int(self.duration * sample_rate)
        if num_samples <= 0:
            return []

        osc = Oscillator(self.frequency, self.waveform, sample_rate)
        samples = osc.generate(num_samples)

        # Optional detuned second oscillator for chorus effect
        if self.detune_hz != 0.0:
            osc2 = Oscillator(
                self.frequency + self.detune_hz,
                self.waveform,
                sample_rate,
            )
            samples2 = osc2.generate(num_samples)
            samples = [
                0.5 * (s1 + s2) for s1, s2 in zip(samples, samples2)
            ]

        # Apply ADSR envelope
        samples = self.envelope.apply(samples, sample_rate, self.duration)

        # Apply biquad filter if provided
        if filter_instance is not None:
            filter_instance.reset()
            samples = filter_instance.process(samples)

        # Apply velocity scaling
        samples = [s * self.velocity for s in samples]

        return samples


# ============================================================
# FizzBuzz Sonifier
# ============================================================


class FizzBuzzSonifier:
    """Maps FizzBuzz classifications to musical synthesis parameters.

    The timbral mapping is designed to make the 3-against-5 polyrhythmic
    structure of FizzBuzz audibly clear:

    - Fizz (divisible by 3): Square wave at C4 (261.63 Hz).
      The hollow, buzzy timbre of the square wave marks every third beat
      with a distinctive color.

    - Buzz (divisible by 5): Sawtooth wave at E4 (329.63 Hz).
      The bright, rich harmonic content of the sawtooth distinguishes
      every fifth beat from the Fizz pattern.

    - FizzBuzz (divisible by 15): Detuned dual oscillator at G4 (392.00 Hz).
      The coincidence of both divisibility conditions is marked by the
      thickened, chorused sound of two slightly detuned oscillators,
      creating the root-third-fifth triad when heard in context with
      Fizz and Buzz notes.

    - Plain number: Triangle wave with frequency proportional to the number.
      Each plain integer receives a unique pitch, creating a melodic
      contour that traces the number sequence.
    """

    # Musical reference frequencies (A4 = 440 Hz, equal temperament)
    FIZZ_FREQ = 261.63       # C4
    BUZZ_FREQ = 329.63       # E4
    FIZZBUZZ_FREQ = 392.00   # G4
    BASE_NUMBER_FREQ = 220.0  # A3 — base frequency for plain numbers

    # Default note duration in seconds
    DEFAULT_DURATION = 0.2

    def __init__(
        self,
        duration: float = DEFAULT_DURATION,
        envelope: Optional[ADSREnvelope] = None,
    ) -> None:
        self.duration = duration
        self.envelope = envelope or ADSREnvelope(
            attack=0.01,
            decay=0.05,
            sustain=0.7,
            release=0.1,
        )

    def classify_to_note(
        self,
        number: int,
        output: str,
        is_fizz: bool,
        is_buzz: bool,
    ) -> Note:
        """Convert a FizzBuzz classification into a Note with synthesis parameters.

        The classification hierarchy: FizzBuzz > Fizz > Buzz > plain number.
        """
        if is_fizz and is_buzz:
            return Note(
                frequency=self.FIZZBUZZ_FREQ,
                duration=self.duration,
                waveform=Waveform.SINE,
                envelope=self.envelope,
                velocity=0.9,
                detune_hz=2.0,
            )
        elif is_fizz:
            return Note(
                frequency=self.FIZZ_FREQ,
                duration=self.duration,
                waveform=Waveform.SQUARE,
                envelope=self.envelope,
                velocity=0.7,
            )
        elif is_buzz:
            return Note(
                frequency=self.BUZZ_FREQ,
                duration=self.duration,
                waveform=Waveform.SAWTOOTH,
                envelope=self.envelope,
                velocity=0.75,
            )
        else:
            # Plain number: frequency derived from the number itself
            # Maps numbers 1-100 across two octaves starting from A3
            freq = self.BASE_NUMBER_FREQ * (2.0 ** ((number % 24) / 12.0))
            return Note(
                frequency=freq,
                duration=self.duration,
                waveform=Waveform.TRIANGLE,
                envelope=self.envelope,
                velocity=0.5,
            )

    def get_classification_label(
        self, is_fizz: bool, is_buzz: bool
    ) -> str:
        """Return the human-readable classification label."""
        if is_fizz and is_buzz:
            return "FizzBuzz"
        elif is_fizz:
            return "Fizz"
        elif is_buzz:
            return "Buzz"
        else:
            return "Number"


# ============================================================
# WAV Writer
# ============================================================


class WAVWriter:
    """Writes 16-bit PCM WAV files using the standard library wave module.

    Converts floating-point sample buffers [-1.0, 1.0] to signed
    16-bit integers and writes them as a RIFF/WAVE file with proper
    headers. The resulting files are playable by any audio application
    that supports the baseline WAV format.

    Format: 44100 Hz, 16-bit, mono, PCM (format code 1).
    """

    def __init__(
        self,
        sample_rate: int = SAMPLE_RATE,
        bit_depth: int = BIT_DEPTH,
        channels: int = NUM_CHANNELS,
    ) -> None:
        self.sample_rate = sample_rate
        self.bit_depth = bit_depth
        self.channels = channels

    def float_to_pcm16(self, samples: list[float]) -> bytes:
        """Convert a buffer of float samples to 16-bit signed PCM bytes.

        Samples are clamped to [-1.0, 1.0] before conversion to prevent
        integer overflow in the PCM representation.
        """
        pcm_data = bytearray()
        for s in samples:
            clamped = max(-1.0, min(1.0, s))
            pcm_value = int(clamped * MAX_AMPLITUDE)
            pcm_data.extend(struct.pack("<h", pcm_value))
        return bytes(pcm_data)

    def write(self, filepath: str, samples: list[float]) -> int:
        """Write audio samples to a WAV file.

        Returns the number of frames written.
        """
        pcm_data = self.float_to_pcm16(samples)

        with wave.open(filepath, "wb") as wf:
            wf.setnchannels(self.channels)
            wf.setsampwidth(self.bit_depth // 8)
            wf.setframerate(self.sample_rate)
            wf.writeframes(pcm_data)

        num_frames = len(samples)
        logger.info(
            "WAV file written: %s (%d frames, %.2f seconds)",
            filepath,
            num_frames,
            num_frames / self.sample_rate,
        )
        return num_frames

    def write_from_bytes(self, filepath: str, pcm_data: bytes) -> int:
        """Write raw PCM bytes to a WAV file.

        Returns the number of frames written.
        """
        with wave.open(filepath, "wb") as wf:
            wf.setnchannels(self.channels)
            wf.setsampwidth(self.bit_depth // 8)
            wf.setframerate(self.sample_rate)
            wf.writeframes(pcm_data)

        num_frames = len(pcm_data) // (self.bit_depth // 8)
        return num_frames


# ============================================================
# Sequence Composer
# ============================================================


@dataclass
class NoteEvent:
    """A note placed at a specific time offset in the composition.

    Combines a Note with its temporal position in the sequence,
    its source number, and the FizzBuzz classification label.
    """

    note: Note
    time_offset: float
    number: int
    classification: str


class SequenceComposer:
    """Arranges FizzBuzz evaluation results as a temporal musical sequence.

    Each evaluation result becomes a note placed at a time offset
    determined by the tempo (BPM). The composer manages the overall
    timeline, applies global effects (filter, reverb), and renders
    the complete sequence to a sample buffer.

    The default tempo of 120 BPM yields one note every 0.5 seconds,
    providing clear articulation of the polyrhythmic Fizz/Buzz pattern.
    """

    def __init__(
        self,
        bpm: float = 120.0,
        sample_rate: int = SAMPLE_RATE,
        reverb_wet: float = 0.2,
        filter_cutoff: float = 8000.0,
    ) -> None:
        self.bpm = bpm
        self.sample_rate = sample_rate
        self.beat_duration = 60.0 / bpm
        self.sonifier = FizzBuzzSonifier(duration=self.beat_duration * 0.8)
        self.reverb = ReverbEffect(wet=reverb_wet, sample_rate=sample_rate)
        self.filter = BiquadFilter(
            filter_type=FilterType.LOW_PASS,
            cutoff_hz=filter_cutoff,
            sample_rate=sample_rate,
        )
        self._events: list[NoteEvent] = []

    def add_result(
        self,
        number: int,
        output: str,
        is_fizz: bool,
        is_buzz: bool,
    ) -> NoteEvent:
        """Add a FizzBuzz result to the composition timeline.

        Returns the NoteEvent created for this result.
        """
        time_offset = len(self._events) * self.beat_duration
        note = self.sonifier.classify_to_note(number, output, is_fizz, is_buzz)
        classification = self.sonifier.get_classification_label(is_fizz, is_buzz)

        event = NoteEvent(
            note=note,
            time_offset=time_offset,
            number=number,
            classification=classification,
        )
        self._events.append(event)
        return event

    @property
    def events(self) -> list[NoteEvent]:
        """Return the list of all note events in the composition."""
        return list(self._events)

    @property
    def total_duration(self) -> float:
        """Return the total duration of the composition in seconds."""
        if not self._events:
            return 0.0
        last_event = self._events[-1]
        return last_event.time_offset + last_event.note.duration + 0.5

    def render(self, apply_reverb: bool = True) -> list[float]:
        """Render the complete composition to a sample buffer.

        All note events are mixed into a single timeline. After mixing,
        global filtering and optional reverb are applied.
        """
        if not self._events:
            return []

        total_samples = int(self.total_duration * self.sample_rate)
        mix_buffer = [0.0] * total_samples

        for event in self._events:
            start_sample = int(event.time_offset * self.sample_rate)
            note_samples = event.note.render(
                sample_rate=self.sample_rate,
            )

            for i, s in enumerate(note_samples):
                idx = start_sample + i
                if idx < total_samples:
                    mix_buffer[idx] += s

        # Normalize to prevent clipping
        peak = max((abs(s) for s in mix_buffer), default=0.0)
        if peak > 1.0:
            scale = 0.95 / peak
            mix_buffer = [s * scale for s in mix_buffer]

        # Apply global low-pass filter
        self.filter.reset()
        mix_buffer = self.filter.process(mix_buffer)

        # Apply reverb
        if apply_reverb:
            self.reverb.reset()
            mix_buffer = self.reverb.process(mix_buffer)

        return mix_buffer

    def render_to_wav(self, filepath: str, apply_reverb: bool = True) -> int:
        """Render the composition and write it to a WAV file.

        Returns the number of frames written.
        """
        samples = self.render(apply_reverb=apply_reverb)
        writer = WAVWriter(sample_rate=self.sample_rate)
        return writer.write(filepath, samples)

    def get_sequence_summary(self) -> dict[str, Any]:
        """Return a summary of the composition for dashboard display."""
        classification_counts: dict[str, int] = {}
        for event in self._events:
            classification_counts[event.classification] = (
                classification_counts.get(event.classification, 0) + 1
            )

        return {
            "total_notes": len(self._events),
            "total_duration_sec": round(self.total_duration, 2),
            "bpm": self.bpm,
            "classifications": classification_counts,
            "sample_rate": self.sample_rate,
            "bit_depth": BIT_DEPTH,
            "channels": NUM_CHANNELS,
        }


# ============================================================
# Synth Dashboard
# ============================================================


class SynthDashboard:
    """ASCII dashboard for the FizzSynth digital audio synthesizer.

    Displays waveform visualization, note sequence timeline,
    spectrum information, and synthesis statistics. Provides
    at-a-glance monitoring of the audio rendering pipeline.
    """

    @staticmethod
    def render(
        composer: SequenceComposer,
        width: int = 60,
    ) -> str:
        """Render the FizzSynth dashboard as an ASCII string."""
        lines: list[str] = []
        border = "+" + "-" * (width - 2) + "+"

        lines.append("")
        lines.append(border)
        lines.append(
            SynthDashboard._center("FIZZSYNTH DIGITAL AUDIO SYNTHESIZER", width)
        )
        lines.append(
            SynthDashboard._center("Polyrhythmic FizzBuzz Sonification Engine", width)
        )
        lines.append(border)

        # Synthesis parameters
        summary = composer.get_sequence_summary()
        lines.append(SynthDashboard._center("Synthesis Parameters", width))
        lines.append(SynthDashboard._kv("Sample Rate", f"{summary['sample_rate']} Hz", width))
        lines.append(SynthDashboard._kv("Bit Depth", f"{summary['bit_depth']}-bit PCM", width))
        lines.append(SynthDashboard._kv("Channels", "Mono" if summary["channels"] == 1 else "Stereo", width))
        lines.append(SynthDashboard._kv("Tempo", f"{summary['bpm']:.0f} BPM", width))
        lines.append(SynthDashboard._kv("Total Duration", f"{summary['total_duration_sec']:.2f}s", width))
        lines.append(SynthDashboard._kv("Total Notes", str(summary["total_notes"]), width))
        lines.append(border)

        # Classification breakdown
        lines.append(SynthDashboard._center("Classification Timbral Map", width))
        timbral_map = {
            "Fizz": "Square wave @ 261.63 Hz (C4)",
            "Buzz": "Sawtooth wave @ 329.63 Hz (E4)",
            "FizzBuzz": "Detuned dual osc @ 392.00 Hz (G4)",
            "Number": "Triangle wave (pitch by value)",
        }
        for label, description in timbral_map.items():
            count = summary["classifications"].get(label, 0)
            lines.append(
                SynthDashboard._kv(f"  {label}", f"{description}  [{count}]", width)
            )
        lines.append(border)

        # Waveform visualization (ASCII approximation of last few notes)
        lines.append(SynthDashboard._center("Waveform Preview (8 samples per note)", width))
        events = composer.events[-8:] if len(composer.events) > 8 else composer.events
        for event in events:
            wave_str = SynthDashboard._mini_waveform(event.note.waveform, 16)
            label = f"  {event.number:>4} ({event.classification:>8})"
            padded_label = label[:24].ljust(24)
            line_content = f"| {padded_label} {wave_str}"
            lines.append(line_content + " " * max(0, width - len(line_content) - 1) + "|")
        lines.append(border)

        # Polyrhythm analysis
        lines.append(SynthDashboard._center("Polyrhythm Analysis", width))
        fizz_count = summary["classifications"].get("Fizz", 0)
        buzz_count = summary["classifications"].get("Buzz", 0)
        fb_count = summary["classifications"].get("FizzBuzz", 0)
        total = summary["total_notes"]
        if total > 0:
            lines.append(
                SynthDashboard._kv(
                    "  3-beat pattern (Fizz)",
                    f"{fizz_count + fb_count}/{total} beats ({100 * (fizz_count + fb_count) / total:.1f}%)",
                    width,
                )
            )
            lines.append(
                SynthDashboard._kv(
                    "  5-beat pattern (Buzz)",
                    f"{buzz_count + fb_count}/{total} beats ({100 * (buzz_count + fb_count) / total:.1f}%)",
                    width,
                )
            )
            lines.append(
                SynthDashboard._kv(
                    "  15-beat coincidence",
                    f"{fb_count}/{total} beats ({100 * fb_count / total:.1f}%)",
                    width,
                )
            )
        lines.append(border)
        lines.append("")

        return "\n".join(lines)

    @staticmethod
    def _center(text: str, width: int) -> str:
        """Center text within the dashboard border."""
        inner = width - 4
        return "| " + text.center(inner) + " |"

    @staticmethod
    def _kv(key: str, value: str, width: int) -> str:
        """Render a key-value pair within the dashboard border."""
        inner = width - 4
        content = f"{key}: {value}"
        if len(content) > inner:
            content = content[:inner]
        return "| " + content.ljust(inner) + " |"

    @staticmethod
    def _mini_waveform(waveform: Waveform, length: int) -> str:
        """Generate a miniature ASCII waveform visualization."""
        chars = {
            Waveform.SINE: list("~^~v" * ((length // 4) + 1)),
            Waveform.SQUARE: list("__--" * ((length // 4) + 1)),
            Waveform.SAWTOOTH: list("/|/|" * ((length // 4) + 1)),
            Waveform.TRIANGLE: list("/\\/\\" * ((length // 4) + 1)),
        }
        pattern = chars.get(waveform, list("." * length))
        return "".join(pattern[:length])


# ============================================================
# Synth Middleware
# ============================================================


class SynthMiddleware(IMiddleware):
    """Middleware that generates audio samples for each FizzBuzz evaluation.

    Intercepts every number passing through the evaluation pipeline and
    converts the classification result into a musical note, building up
    a complete composition as the sequence is processed.

    Priority 930 places this middleware late in the chain, ensuring that
    the classification result is finalized before sonification occurs.
    """

    def __init__(
        self,
        composer: SequenceComposer,
        enable_dashboard: bool = False,
        wav_output_path: Optional[str] = None,
    ) -> None:
        self._composer = composer
        self._enable_dashboard = enable_dashboard
        self._wav_output_path = wav_output_path
        self._notes_generated = 0

    def process(
        self,
        context: ProcessingContext,
        next_handler: Callable[[ProcessingContext], ProcessingContext],
    ) -> ProcessingContext:
        """Process a number through the pipeline and sonify the result."""
        result = next_handler(context)

        if result.results:
            latest = result.results[-1]
            is_fizz = latest.is_fizz
            is_buzz = latest.is_buzz
            output = latest.output

            event = self._composer.add_result(
                number=latest.number,
                output=output,
                is_fizz=is_fizz,
                is_buzz=is_buzz,
            )
            self._notes_generated += 1

            result.metadata["synth_note_freq"] = event.note.frequency
            result.metadata["synth_note_waveform"] = event.note.waveform.name
            result.metadata["synth_classification"] = event.classification

        return result

    @property
    def composer(self) -> SequenceComposer:
        """Access the underlying SequenceComposer."""
        return self._composer

    @property
    def notes_generated(self) -> int:
        """Return the total number of notes generated."""
        return self._notes_generated

    def get_name(self) -> str:
        return "SynthMiddleware"

    def get_priority(self) -> int:
        return 930
