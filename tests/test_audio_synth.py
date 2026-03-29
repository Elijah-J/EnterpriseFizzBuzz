"""
Enterprise FizzBuzz Platform - FizzSynth Audio Synthesizer Test Suite

Comprehensive verification of the digital audio synthesis pipeline, from
individual oscillator sample generation through the complete WAV rendering
chain. These tests ensure that every FizzBuzz classification produces
acoustically correct and musically meaningful audio output.

Audio synthesis correctness is mission-critical: an incorrect waveform
could misrepresent whether a number is divisible by 3, which would
constitute an auditory compliance violation under the Enterprise
FizzBuzz Audio Accessibility Standard (EFAAS).
"""

from __future__ import annotations

import math
import os
import struct
import sys
import tempfile
import uuid
import wave
from pathlib import Path
from typing import Callable
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from enterprise_fizzbuzz.infrastructure.audio_synth import (
    SAMPLE_RATE,
    BIT_DEPTH,
    MAX_AMPLITUDE,
    NUM_CHANNELS,
    ADSREnvelope,
    BiquadFilter,
    FilterType,
    FizzBuzzSonifier,
    Note,
    NoteEvent,
    Oscillator,
    ReverbEffect,
    SequenceComposer,
    SynthDashboard,
    SynthMiddleware,
    WAVWriter,
    Waveform,
    _AllpassFilter,
    _CombFilter,
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


def _fizz_rule_match(number: int = 3) -> RuleMatch:
    """Create a RuleMatch for the Fizz rule."""
    return RuleMatch(rule=RuleDefinition(name="FizzRule", divisor=3, label="Fizz", priority=1), number=number)


def _buzz_rule_match(number: int = 5) -> RuleMatch:
    """Create a RuleMatch for the Buzz rule."""
    return RuleMatch(rule=RuleDefinition(name="BuzzRule", divisor=5, label="Buzz", priority=2), number=number)


def _passthrough(ctx: ProcessingContext) -> ProcessingContext:
    """A no-op next_handler for middleware testing."""
    return ctx


# ============================================================
# Waveform Enum Tests
# ============================================================


class TestWaveform:
    """Verify the Waveform enumeration defines all required synthesis modes."""

    def test_sine_exists(self) -> None:
        assert Waveform.SINE.name == "SINE"

    def test_square_exists(self) -> None:
        assert Waveform.SQUARE.name == "SQUARE"

    def test_sawtooth_exists(self) -> None:
        assert Waveform.SAWTOOTH.name == "SAWTOOTH"

    def test_triangle_exists(self) -> None:
        assert Waveform.TRIANGLE.name == "TRIANGLE"

    def test_four_waveforms(self) -> None:
        assert len(Waveform) == 4


# ============================================================
# Oscillator Tests
# ============================================================


class TestOscillator:
    """Verify waveform generation across all oscillator modes."""

    def test_sine_generates_correct_length(self) -> None:
        osc = Oscillator(440.0, Waveform.SINE, 44100)
        samples = osc.generate(44100)
        assert len(samples) == 44100

    def test_sine_range(self) -> None:
        osc = Oscillator(440.0, Waveform.SINE, 44100)
        samples = osc.generate(4410)
        assert all(-1.0 <= s <= 1.0 for s in samples)

    def test_sine_zero_crossing(self) -> None:
        osc = Oscillator(1.0, Waveform.SINE, 100)
        samples = osc.generate(100)
        # At 1 Hz with 100 samples, sample 0 should be near 0
        assert abs(samples[0]) < 0.1

    def test_square_values(self) -> None:
        osc = Oscillator(1.0, Waveform.SQUARE, 100)
        samples = osc.generate(100)
        for s in samples:
            assert s == 1.0 or s == -1.0

    def test_sawtooth_range(self) -> None:
        osc = Oscillator(1.0, Waveform.SAWTOOTH, 100)
        samples = osc.generate(100)
        assert all(-1.0 <= s <= 1.0 for s in samples)

    def test_sawtooth_ramp(self) -> None:
        osc = Oscillator(1.0, Waveform.SAWTOOTH, 100)
        samples = osc.generate(50)
        # Sawtooth should generally increase across the first half-cycle
        assert samples[25] > samples[0]

    def test_triangle_range(self) -> None:
        osc = Oscillator(1.0, Waveform.TRIANGLE, 100)
        samples = osc.generate(100)
        assert all(-1.0 <= s <= 1.0 for s in samples)

    def test_triangle_peak(self) -> None:
        osc = Oscillator(1.0, Waveform.TRIANGLE, 400)
        samples = osc.generate(400)
        # Peak should be at phase 0.25 (sample index 100)
        assert samples[100] == pytest.approx(1.0, abs=0.05)

    def test_phase_continuity(self) -> None:
        osc = Oscillator(440.0, Waveform.SINE, 44100)
        batch1 = osc.generate(100)
        batch2 = osc.generate(100)
        # The transition between batches should be smooth
        assert abs(batch1[-1] - batch2[0]) < 0.1

    def test_reset_phase(self) -> None:
        osc = Oscillator(440.0, Waveform.SINE, 44100)
        osc.generate(1000)
        assert osc.phase != 0.0
        osc.reset()
        assert osc.phase == 0.0

    def test_zero_frequency(self) -> None:
        osc = Oscillator(0.0, Waveform.SINE, 44100)
        samples = osc.generate(100)
        # At 0 Hz, sine should produce all zeros
        assert all(abs(s) < 1e-10 for s in samples)

    def test_high_frequency(self) -> None:
        osc = Oscillator(20000.0, Waveform.SINE, 44100)
        samples = osc.generate(441)
        assert len(samples) == 441
        assert all(-1.0 <= s <= 1.0 for s in samples)


# ============================================================
# ADSR Envelope Tests
# ============================================================


class TestADSREnvelope:
    """Verify the attack-decay-sustain-release envelope shaper."""

    def test_default_parameters(self) -> None:
        env = ADSREnvelope()
        assert env.attack == 0.01
        assert env.decay == 0.05
        assert env.sustain == 0.7
        assert env.release == 0.1

    def test_attack_ramp(self) -> None:
        env = ADSREnvelope(attack=0.1, decay=0.0, sustain=1.0, release=0.0)
        samples = [1.0] * 44100
        result = env.apply(samples, 44100)
        # During attack phase, amplitude should increase
        assert result[0] < result[4000]

    def test_sustain_level(self) -> None:
        env = ADSREnvelope(attack=0.01, decay=0.01, sustain=0.5, release=0.01)
        samples = [1.0] * 44100
        result = env.apply(samples, 44100)
        # Mid-sustain samples should be near sustain level
        mid = len(result) // 2
        assert abs(result[mid] - 0.5) < 0.1

    def test_release_fade(self) -> None:
        env = ADSREnvelope(attack=0.01, decay=0.01, sustain=0.8, release=0.5)
        samples = [1.0] * 44100
        result = env.apply(samples, 44100, note_duration=0.5)
        # After release, samples should approach zero
        assert abs(result[-1]) < 0.1

    def test_zero_attack(self) -> None:
        env = ADSREnvelope(attack=0.0, decay=0.0, sustain=1.0, release=0.0)
        samples = [1.0] * 100
        result = env.apply(samples, 44100)
        # Should be at sustain level from the start
        assert result[0] == pytest.approx(1.0, abs=0.01)

    def test_total_minimum_duration(self) -> None:
        env = ADSREnvelope(attack=0.01, decay=0.05, sustain=0.7, release=0.1)
        assert env.get_total_minimum_duration() == pytest.approx(0.16, abs=0.001)

    def test_preserves_silence(self) -> None:
        env = ADSREnvelope()
        samples = [0.0] * 1000
        result = env.apply(samples, 44100)
        assert all(s == 0.0 for s in result)

    def test_output_length_matches_input(self) -> None:
        env = ADSREnvelope()
        samples = [1.0] * 500
        result = env.apply(samples, 44100)
        assert len(result) == 500


# ============================================================
# Biquad Filter Tests
# ============================================================


class TestBiquadFilter:
    """Verify the IIR biquad filter across all response types."""

    def test_lowpass_creation(self) -> None:
        f = BiquadFilter(FilterType.LOW_PASS, 1000.0, 0.707)
        assert f.a0 == pytest.approx(1.0)

    def test_highpass_creation(self) -> None:
        f = BiquadFilter(FilterType.HIGH_PASS, 1000.0, 0.707)
        assert f.a0 == pytest.approx(1.0)

    def test_bandpass_creation(self) -> None:
        f = BiquadFilter(FilterType.BAND_PASS, 1000.0, 1.0)
        assert f.a0 == pytest.approx(1.0)

    def test_lowpass_attenuates_high_freq(self) -> None:
        """A low-pass filter at 500 Hz should attenuate a 10 kHz tone."""
        f = BiquadFilter(FilterType.LOW_PASS, 500.0, 0.707)
        osc = Oscillator(10000.0, Waveform.SINE, 44100)
        samples = osc.generate(4410)
        filtered = f.process(samples)
        # RMS of filtered signal should be much less than input
        rms_in = math.sqrt(sum(s * s for s in samples) / len(samples))
        rms_out = math.sqrt(sum(s * s for s in filtered) / len(filtered))
        assert rms_out < rms_in * 0.3

    def test_lowpass_passes_low_freq(self) -> None:
        """A low-pass filter at 5000 Hz should pass a 100 Hz tone with minimal loss."""
        f = BiquadFilter(FilterType.LOW_PASS, 5000.0, 0.707)
        osc = Oscillator(100.0, Waveform.SINE, 44100)
        samples = osc.generate(4410)
        filtered = f.process(samples)
        # Steady-state RMS should be close to input RMS
        # Skip first 500 samples (transient settling)
        rms_in = math.sqrt(sum(s * s for s in samples[500:]) / len(samples[500:]))
        rms_out = math.sqrt(sum(s * s for s in filtered[500:]) / len(filtered[500:]))
        assert rms_out > rms_in * 0.8

    def test_reset_clears_state(self) -> None:
        f = BiquadFilter(FilterType.LOW_PASS, 1000.0)
        osc = Oscillator(440.0, Waveform.SINE, 44100)
        f.process(osc.generate(1000))
        f.reset()
        assert f._x1 == 0.0
        assert f._y1 == 0.0

    def test_process_empty_input(self) -> None:
        f = BiquadFilter()
        result = f.process([])
        assert result == []

    def test_output_length(self) -> None:
        f = BiquadFilter()
        samples = [0.5] * 100
        result = f.process(samples)
        assert len(result) == 100


# ============================================================
# Reverb Tests
# ============================================================


class TestReverbEffect:
    """Verify the Schroeder reverb produces correct diffuse reflections."""

    def test_impulse_response_nonzero(self) -> None:
        reverb = ReverbEffect(wet=1.0)
        # Send an impulse (1 sample of energy followed by silence)
        impulse = [1.0] + [0.0] * 4410
        result = reverb.process(impulse)
        # The reverb tail should contain nonzero samples after the impulse
        assert any(abs(s) > 0.001 for s in result[100:])

    def test_dry_passthrough(self) -> None:
        reverb = ReverbEffect(wet=0.0)
        samples = [0.5] * 100
        result = reverb.process(samples)
        # With 0% wet, output should equal input
        for i in range(100):
            assert result[i] == pytest.approx(0.5, abs=0.01)

    def test_output_length(self) -> None:
        reverb = ReverbEffect()
        samples = [0.1] * 1000
        result = reverb.process(samples)
        assert len(result) == 1000

    def test_reset(self) -> None:
        reverb = ReverbEffect(wet=0.5)
        reverb.process([1.0] * 1000)
        reverb.reset()
        # After reset, processing silence should produce silence
        result = reverb.process([0.0] * 100)
        assert all(abs(s) < 1e-10 for s in result)

    def test_four_comb_filters(self) -> None:
        reverb = ReverbEffect()
        assert len(reverb._combs) == 4

    def test_two_allpass_filters(self) -> None:
        reverb = ReverbEffect()
        assert len(reverb._allpasses) == 2


# ============================================================
# Comb Filter Tests
# ============================================================


class TestCombFilter:
    """Verify the feedback comb filter delay element."""

    def test_delay(self) -> None:
        comb = _CombFilter(10, 0.5)
        # Send impulse
        outputs = []
        for i in range(20):
            outputs.append(comb.process_sample(1.0 if i == 0 else 0.0))
        # First output should be 0 (delayed), output at index 10 should be nonzero
        assert outputs[0] == 0.0
        assert abs(outputs[10]) > 0.0

    def test_reset(self) -> None:
        comb = _CombFilter(5, 0.8)
        for _ in range(10):
            comb.process_sample(1.0)
        comb.reset()
        assert comb.process_sample(0.0) == 0.0


# ============================================================
# Allpass Filter Tests
# ============================================================


class TestAllpassFilter:
    """Verify the allpass filter preserves amplitude while shifting phase."""

    def test_output_nonzero(self) -> None:
        ap = _AllpassFilter(10, 0.5)
        outputs = []
        for i in range(30):
            outputs.append(ap.process_sample(1.0 if i == 0 else 0.0))
        # Should produce non-zero output
        assert any(abs(s) > 0.0 for s in outputs)

    def test_reset(self) -> None:
        ap = _AllpassFilter(5, 0.5)
        for _ in range(10):
            ap.process_sample(1.0)
        ap.reset()
        assert ap.process_sample(0.0) == 0.0


# ============================================================
# Note Tests
# ============================================================


class TestNote:
    """Verify individual note rendering with all synthesis parameters."""

    def test_render_basic(self) -> None:
        note = Note(frequency=440.0, duration=0.1)
        samples = note.render()
        expected_length = int(0.1 * SAMPLE_RATE)
        assert len(samples) == expected_length

    def test_render_with_detune(self) -> None:
        note = Note(frequency=440.0, duration=0.1, detune_hz=2.0)
        samples = note.render()
        assert len(samples) > 0

    def test_render_with_filter(self) -> None:
        note = Note(frequency=440.0, duration=0.1)
        f = BiquadFilter(FilterType.LOW_PASS, 2000.0)
        samples = note.render(filter_instance=f)
        assert len(samples) > 0

    def test_velocity_scaling(self) -> None:
        note_loud = Note(frequency=440.0, duration=0.05, velocity=1.0,
                         envelope=ADSREnvelope(attack=0.0, decay=0.0, sustain=1.0, release=0.0))
        note_quiet = Note(frequency=440.0, duration=0.05, velocity=0.5,
                          envelope=ADSREnvelope(attack=0.0, decay=0.0, sustain=1.0, release=0.0))
        loud = note_loud.render()
        quiet = note_quiet.render()
        # RMS of loud should be roughly 2x RMS of quiet
        rms_loud = math.sqrt(sum(s * s for s in loud) / len(loud))
        rms_quiet = math.sqrt(sum(s * s for s in quiet) / len(quiet))
        assert rms_loud > rms_quiet * 1.5

    def test_zero_duration(self) -> None:
        note = Note(frequency=440.0, duration=0.0)
        samples = note.render()
        assert samples == []

    def test_different_waveforms_differ(self) -> None:
        n1 = Note(frequency=440.0, duration=0.01, waveform=Waveform.SINE,
                  envelope=ADSREnvelope(attack=0.0, decay=0.0, sustain=1.0, release=0.0))
        n2 = Note(frequency=440.0, duration=0.01, waveform=Waveform.SQUARE,
                  envelope=ADSREnvelope(attack=0.0, decay=0.0, sustain=1.0, release=0.0))
        s1 = n1.render()
        s2 = n2.render()
        # Different waveforms at same freq/duration should produce different samples
        differences = sum(1 for a, b in zip(s1, s2) if abs(a - b) > 0.01)
        assert differences > 0


# ============================================================
# FizzBuzz Sonifier Tests
# ============================================================


class TestFizzBuzzSonifier:
    """Verify the FizzBuzz-to-music mapping logic."""

    def test_fizz_maps_to_square_c4(self) -> None:
        s = FizzBuzzSonifier()
        note = s.classify_to_note(3, "Fizz", is_fizz=True, is_buzz=False)
        assert note.waveform == Waveform.SQUARE
        assert note.frequency == pytest.approx(261.63, abs=0.01)

    def test_buzz_maps_to_sawtooth_e4(self) -> None:
        s = FizzBuzzSonifier()
        note = s.classify_to_note(5, "Buzz", is_fizz=False, is_buzz=True)
        assert note.waveform == Waveform.SAWTOOTH
        assert note.frequency == pytest.approx(329.63, abs=0.01)

    def test_fizzbuzz_maps_to_detuned_g4(self) -> None:
        s = FizzBuzzSonifier()
        note = s.classify_to_note(15, "FizzBuzz", is_fizz=True, is_buzz=True)
        assert note.frequency == pytest.approx(392.00, abs=0.01)
        assert note.detune_hz != 0.0

    def test_plain_number_maps_to_triangle(self) -> None:
        s = FizzBuzzSonifier()
        note = s.classify_to_note(7, "7", is_fizz=False, is_buzz=False)
        assert note.waveform == Waveform.TRIANGLE

    def test_plain_number_frequency_varies(self) -> None:
        s = FizzBuzzSonifier()
        n1 = s.classify_to_note(1, "1", is_fizz=False, is_buzz=False)
        n2 = s.classify_to_note(7, "7", is_fizz=False, is_buzz=False)
        # Different numbers should produce different frequencies
        assert n1.frequency != n2.frequency

    def test_classification_label_fizz(self) -> None:
        s = FizzBuzzSonifier()
        assert s.get_classification_label(True, False) == "Fizz"

    def test_classification_label_buzz(self) -> None:
        s = FizzBuzzSonifier()
        assert s.get_classification_label(False, True) == "Buzz"

    def test_classification_label_fizzbuzz(self) -> None:
        s = FizzBuzzSonifier()
        assert s.get_classification_label(True, True) == "FizzBuzz"

    def test_classification_label_number(self) -> None:
        s = FizzBuzzSonifier()
        assert s.get_classification_label(False, False) == "Number"

    def test_fizzbuzz_velocity_highest(self) -> None:
        s = FizzBuzzSonifier()
        fb_note = s.classify_to_note(15, "FizzBuzz", True, True)
        fizz_note = s.classify_to_note(3, "Fizz", True, False)
        assert fb_note.velocity >= fizz_note.velocity


# ============================================================
# WAV Writer Tests
# ============================================================


class TestWAVWriter:
    """Verify WAV file output correctness."""

    def test_float_to_pcm16(self) -> None:
        writer = WAVWriter()
        pcm = writer.float_to_pcm16([0.0, 1.0, -1.0])
        values = struct.unpack("<3h", pcm)
        assert values[0] == 0
        assert values[1] == MAX_AMPLITUDE
        assert values[2] == -MAX_AMPLITUDE

    def test_clipping(self) -> None:
        writer = WAVWriter()
        pcm = writer.float_to_pcm16([2.0, -2.0])
        values = struct.unpack("<2h", pcm)
        assert values[0] == MAX_AMPLITUDE
        assert values[1] == -MAX_AMPLITUDE

    def test_write_wav_file(self) -> None:
        writer = WAVWriter()
        samples = [math.sin(2 * math.pi * 440 * i / 44100) for i in range(4410)]
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            path = f.name
        try:
            frames = writer.write(path, samples)
            assert frames == 4410
            # Verify the WAV file is valid
            with wave.open(path, "rb") as wf:
                assert wf.getnchannels() == 1
                assert wf.getsampwidth() == 2
                assert wf.getframerate() == 44100
                assert wf.getnframes() == 4410
        finally:
            os.unlink(path)

    def test_write_empty(self) -> None:
        writer = WAVWriter()
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            path = f.name
        try:
            frames = writer.write(path, [])
            assert frames == 0
        finally:
            os.unlink(path)

    def test_write_from_bytes(self) -> None:
        writer = WAVWriter()
        pcm = struct.pack("<3h", 0, 16383, -16383)
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            path = f.name
        try:
            frames = writer.write_from_bytes(path, pcm)
            assert frames == 3
        finally:
            os.unlink(path)


# ============================================================
# Sequence Composer Tests
# ============================================================


class TestSequenceComposer:
    """Verify the musical sequence arrangement and rendering pipeline."""

    def test_add_result_creates_event(self) -> None:
        composer = SequenceComposer(bpm=120.0)
        event = composer.add_result(3, "Fizz", True, False)
        assert event.number == 3
        assert event.classification == "Fizz"

    def test_events_accumulate(self) -> None:
        composer = SequenceComposer(bpm=120.0)
        composer.add_result(1, "1", False, False)
        composer.add_result(2, "2", False, False)
        composer.add_result(3, "Fizz", True, False)
        assert len(composer.events) == 3

    def test_time_offsets(self) -> None:
        composer = SequenceComposer(bpm=120.0)
        composer.add_result(1, "1", False, False)
        e2 = composer.add_result(2, "2", False, False)
        # At 120 BPM, beat duration is 0.5s
        assert e2.time_offset == pytest.approx(0.5, abs=0.01)

    def test_total_duration(self) -> None:
        composer = SequenceComposer(bpm=120.0)
        assert composer.total_duration == 0.0
        composer.add_result(1, "1", False, False)
        assert composer.total_duration > 0.0

    def test_render_produces_samples(self) -> None:
        composer = SequenceComposer(bpm=120.0)
        composer.add_result(3, "Fizz", True, False)
        samples = composer.render(apply_reverb=False)
        assert len(samples) > 0

    def test_render_empty(self) -> None:
        composer = SequenceComposer(bpm=120.0)
        samples = composer.render()
        assert samples == []

    def test_render_normalized(self) -> None:
        composer = SequenceComposer(bpm=300.0)
        for i in range(1, 20):
            is_fizz = i % 3 == 0
            is_buzz = i % 5 == 0
            output = "FizzBuzz" if is_fizz and is_buzz else "Fizz" if is_fizz else "Buzz" if is_buzz else str(i)
            composer.add_result(i, output, is_fizz, is_buzz)
        samples = composer.render(apply_reverb=False)
        # All samples should be within valid range
        assert all(-1.5 <= s <= 1.5 for s in samples)

    def test_render_to_wav(self) -> None:
        composer = SequenceComposer(bpm=120.0)
        composer.add_result(3, "Fizz", True, False)
        composer.add_result(5, "Buzz", False, True)
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            path = f.name
        try:
            frames = composer.render_to_wav(path, apply_reverb=False)
            assert frames > 0
            with wave.open(path, "rb") as wf:
                assert wf.getframerate() == SAMPLE_RATE
        finally:
            os.unlink(path)

    def test_get_sequence_summary(self) -> None:
        composer = SequenceComposer(bpm=120.0)
        composer.add_result(3, "Fizz", True, False)
        composer.add_result(5, "Buzz", False, True)
        composer.add_result(15, "FizzBuzz", True, True)
        summary = composer.get_sequence_summary()
        assert summary["total_notes"] == 3
        assert summary["bpm"] == 120.0
        assert summary["classifications"]["Fizz"] == 1
        assert summary["classifications"]["Buzz"] == 1
        assert summary["classifications"]["FizzBuzz"] == 1

    def test_different_bpm_affects_duration(self) -> None:
        c1 = SequenceComposer(bpm=60.0)
        c2 = SequenceComposer(bpm=120.0)
        c1.add_result(1, "1", False, False)
        c2.add_result(1, "1", False, False)
        assert c1.total_duration > c2.total_duration


# ============================================================
# Synth Dashboard Tests
# ============================================================


class TestSynthDashboard:
    """Verify the ASCII dashboard renders correctly."""

    def test_render_empty_composer(self) -> None:
        composer = SequenceComposer(bpm=120.0)
        dashboard = SynthDashboard.render(composer)
        assert "FIZZSYNTH" in dashboard
        assert "Total Notes" in dashboard

    def test_render_with_notes(self) -> None:
        composer = SequenceComposer(bpm=120.0)
        composer.add_result(3, "Fizz", True, False)
        composer.add_result(5, "Buzz", False, True)
        dashboard = SynthDashboard.render(composer)
        assert "Fizz" in dashboard
        assert "Buzz" in dashboard
        assert "Polyrhythm" in dashboard

    def test_render_custom_width(self) -> None:
        composer = SequenceComposer(bpm=120.0)
        dashboard = SynthDashboard.render(composer, width=80)
        for line in dashboard.split("\n"):
            if line.startswith("+"):
                assert len(line) == 80

    def test_mini_waveform_sine(self) -> None:
        wf = SynthDashboard._mini_waveform(Waveform.SINE, 8)
        assert len(wf) == 8

    def test_mini_waveform_square(self) -> None:
        wf = SynthDashboard._mini_waveform(Waveform.SQUARE, 8)
        assert len(wf) == 8

    def test_timbral_map_displayed(self) -> None:
        composer = SequenceComposer()
        dashboard = SynthDashboard.render(composer)
        assert "261.63" in dashboard
        assert "329.63" in dashboard
        assert "392.00" in dashboard


# ============================================================
# Synth Middleware Tests
# ============================================================


class TestSynthMiddleware:
    """Verify middleware integration with the evaluation pipeline."""

    def test_implements_imiddleware(self) -> None:
        composer = SequenceComposer()
        mw = SynthMiddleware(composer)
        assert isinstance(mw, IMiddleware)

    def test_get_name(self) -> None:
        composer = SequenceComposer()
        mw = SynthMiddleware(composer)
        assert mw.get_name() == "SynthMiddleware"

    def test_get_priority(self) -> None:
        composer = SequenceComposer()
        mw = SynthMiddleware(composer)
        assert mw.get_priority() == 930

    def test_process_adds_note(self) -> None:
        composer = SequenceComposer()
        mw = SynthMiddleware(composer)
        ctx = _make_context(3, "Fizz", [_fizz_rule_match()])
        result = mw.process(ctx, _passthrough)
        assert mw.notes_generated == 1
        assert len(composer.events) == 1

    def test_process_fizzbuzz(self) -> None:
        composer = SequenceComposer()
        mw = SynthMiddleware(composer)
        ctx = _make_context(15, "FizzBuzz", [_fizz_rule_match(15), _buzz_rule_match(15)])
        result = mw.process(ctx, _passthrough)
        assert result.metadata["synth_classification"] == "FizzBuzz"

    def test_process_plain_number(self) -> None:
        composer = SequenceComposer()
        mw = SynthMiddleware(composer)
        ctx = _make_context(7, "7")
        result = mw.process(ctx, _passthrough)
        assert result.metadata["synth_classification"] == "Number"

    def test_metadata_includes_frequency(self) -> None:
        composer = SequenceComposer()
        mw = SynthMiddleware(composer)
        ctx = _make_context(3, "Fizz", [_fizz_rule_match(3)])
        result = mw.process(ctx, _passthrough)
        assert "synth_note_freq" in result.metadata
        assert result.metadata["synth_note_freq"] == pytest.approx(261.63, abs=0.01)

    def test_metadata_includes_waveform(self) -> None:
        composer = SequenceComposer()
        mw = SynthMiddleware(composer)
        ctx = _make_context(5, "Buzz", [_buzz_rule_match(5)])
        result = mw.process(ctx, _passthrough)
        assert result.metadata["synth_note_waveform"] == "SAWTOOTH"

    def test_process_empty_results(self) -> None:
        composer = SequenceComposer()
        mw = SynthMiddleware(composer)
        ctx = ProcessingContext(number=1, session_id="test")
        result = mw.process(ctx, _passthrough)
        assert mw.notes_generated == 0

    def test_multiple_evaluations(self) -> None:
        composer = SequenceComposer()
        mw = SynthMiddleware(composer)
        for i in range(1, 16):
            is_fizz = i % 3 == 0
            is_buzz = i % 5 == 0
            rules = []
            if is_fizz:
                rules.append(_fizz_rule_match(i))
            if is_buzz:
                rules.append(_buzz_rule_match(i))
            output = "FizzBuzz" if is_fizz and is_buzz else "Fizz" if is_fizz else "Buzz" if is_buzz else str(i)
            ctx = _make_context(i, output, rules)
            mw.process(ctx, _passthrough)
        assert mw.notes_generated == 15
        assert len(composer.events) == 15
