"""
Enterprise FizzBuzz Platform - FizzMusic Music Theory Test Suite

Comprehensive verification of the music theory engine, including pitch
representation, chord recognition, key detection, scale generation,
MIDI sequencing, and harmonic analysis. These tests ensure that the
musicological interpretation of FizzBuzz sequences is theoretically
sound and harmonically correct.

Music theory accuracy is non-negotiable: misidentifying the key of a
FizzBuzz sequence would assign incorrect harmonic functions to the
Fizz and Buzz events, constituting a violation of the Enterprise
FizzBuzz Musicological Compliance Standard (EFMCS).
"""

from __future__ import annotations

import math
import sys
import uuid
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from enterprise_fizzbuzz.infrastructure.fizzmusic import (
    Chord,
    ChordRecognizer,
    FizzBuzzMusicEncoder,
    HarmonicAnalyzer,
    Key,
    KeyDetector,
    MIDIEvent,
    MIDISequencer,
    MusicMiddleware,
    NOTE_NAMES,
    Pitch,
    Rhythm,
    ScaleGenerator,
    SCALE_PATTERNS,
)
from enterprise_fizzbuzz.domain.exceptions.fizzmusic import (
    ChordRecognitionError,
    HarmonicAnalysisError,
    InvalidPitchError,
    KeyDetectionError,
    MIDISequenceError,
    ScaleGenerationError,
)
from enterprise_fizzbuzz.domain.models import (
    FizzBuzzResult,
    ProcessingContext,
)


# ============================================================
# Helpers
# ============================================================


def _make_context(number: int, output: str = "") -> ProcessingContext:
    ctx = ProcessingContext(number=number, session_id=str(uuid.uuid4()))
    result = FizzBuzzResult(number=number, output=output or str(number), matched_rules=[])
    ctx.results.append(result)
    return ctx


def _identity_handler(ctx: ProcessingContext) -> ProcessingContext:
    return ctx


# ============================================================
# Pitch Tests
# ============================================================


class TestPitch:
    def test_a4_frequency(self):
        p = Pitch(midi_note=69)
        assert abs(p.frequency - 440.0) < 0.01

    def test_c4_note_name(self):
        p = Pitch(midi_note=60)
        assert p.note_name == "C4"

    def test_pitch_class(self):
        p = Pitch(midi_note=60)
        assert p.pitch_class == 0  # C

    def test_invalid_pitch_raises(self):
        with pytest.raises(InvalidPitchError):
            Pitch(midi_note=128)

    def test_negative_pitch_raises(self):
        with pytest.raises(InvalidPitchError):
            Pitch(midi_note=-1)

    def test_octave_doubles_frequency(self):
        p1 = Pitch(midi_note=60)
        p2 = Pitch(midi_note=72)
        assert abs(p2.frequency / p1.frequency - 2.0) < 0.01


# ============================================================
# Rhythm Tests
# ============================================================


class TestRhythm:
    def test_quarter_note_duration(self):
        r = Rhythm(numerator=1, denominator=4)
        assert r.duration_beats == 1.0

    def test_whole_note_duration(self):
        r = Rhythm(numerator=1, denominator=1)
        assert r.duration_beats == 4.0


# ============================================================
# Chord Recognition Tests
# ============================================================


class TestChordRecognizer:
    def test_c_major_chord(self):
        cr = ChordRecognizer()
        chord = cr.recognize([0, 4, 7])  # C, E, G
        assert chord.quality == "major"
        assert chord.root == 0

    def test_a_minor_chord(self):
        cr = ChordRecognizer()
        chord = cr.recognize([9, 0, 4])  # A, C, E
        assert chord.quality == "minor"

    def test_empty_pitch_classes_raises(self):
        cr = ChordRecognizer()
        with pytest.raises(ChordRecognitionError):
            cr.recognize([])

    def test_chord_name_format(self):
        chord = Chord(root=0, quality="major", pitch_classes=frozenset({0, 4, 7}))
        assert chord.name == "C"

    def test_minor_chord_name(self):
        chord = Chord(root=9, quality="minor", pitch_classes=frozenset({9, 0, 4}))
        assert chord.name == "Am"


# ============================================================
# Key Detection Tests
# ============================================================


class TestKeyDetector:
    def test_c_major_key(self):
        detector = KeyDetector(min_confidence=0.1)
        # C major scale pitch class distribution
        counts = [10, 0, 8, 0, 8, 6, 0, 10, 0, 6, 0, 4]
        key = detector.detect(counts)
        assert key.tonic == 0  # C
        assert key.mode == "major"

    def test_empty_distribution_raises(self):
        detector = KeyDetector()
        with pytest.raises(KeyDetectionError):
            detector.detect([0] * 12)

    def test_wrong_length_raises(self):
        detector = KeyDetector()
        with pytest.raises(KeyDetectionError):
            detector.detect([1, 2, 3])

    def test_confidence_positive(self):
        detector = KeyDetector(min_confidence=0.0)
        counts = [5, 1, 3, 1, 4, 3, 1, 5, 1, 3, 1, 2]
        key = detector.detect(counts)
        assert key.confidence > 0


# ============================================================
# Scale Generator Tests
# ============================================================


class TestScaleGenerator:
    def test_c_major_scale(self):
        gen = ScaleGenerator()
        pitches = gen.generate(60, "major")  # C4 major
        notes = [p.note_name for p in pitches]
        assert notes[0] == "C4"
        assert "D4" in notes
        assert "E4" in notes

    def test_pitch_classes_major(self):
        gen = ScaleGenerator()
        pcs = gen.scale_pitch_classes(0, "major")
        assert pcs == [0, 2, 4, 5, 7, 9, 11]

    def test_unknown_scale_raises(self):
        gen = ScaleGenerator()
        with pytest.raises(ScaleGenerationError):
            gen.generate(60, "nonexistent")

    def test_chromatic_scale_twelve_notes(self):
        gen = ScaleGenerator()
        pitches = gen.generate(60, "chromatic")
        assert len(pitches) == 13  # 12 semitones + octave


# ============================================================
# MIDI Sequencer Tests
# ============================================================


class TestMIDISequencer:
    def test_fizz_event(self):
        seq = MIDISequencer()
        seq.add_fizzbuzz_event("Fizz")
        assert len(seq.events) == 2  # note_on + note_off
        assert seq.events[0].event_type == "note_on"
        assert seq.events[0].note == 60  # C4

    def test_buzz_event(self):
        seq = MIDISequencer()
        seq.add_fizzbuzz_event("Buzz")
        assert seq.events[0].note == 64  # E4

    def test_fizzbuzz_event_longer(self):
        seq = MIDISequencer()
        seq.add_fizzbuzz_event("FizzBuzz")
        assert seq.events[0].velocity == 100
        assert seq.total_ticks == 960  # half note

    def test_numeric_is_rest(self):
        seq = MIDISequencer()
        seq.add_fizzbuzz_event("7")
        assert len(seq.events) == 0
        assert seq.total_ticks == 240  # eighth note rest

    def test_invalid_midi_event_raises(self):
        event = MIDIEvent(tick=-1, event_type="note_on")
        with pytest.raises(MIDISequenceError):
            event.validate()

    def test_clear_resets(self):
        seq = MIDISequencer()
        seq.add_fizzbuzz_event("Fizz")
        seq.clear()
        assert len(seq.events) == 0
        assert seq.total_ticks == 0


# ============================================================
# Harmonic Analysis Tests
# ============================================================


class TestHarmonicAnalyzer:
    def test_tonic_chord(self):
        key = Key(tonic=0, mode="major", confidence=0.9)
        analyzer = HarmonicAnalyzer(key)
        chord = Chord(root=0, quality="major", pitch_classes=frozenset({0, 4, 7}))
        label = analyzer.analyze_chord(chord)
        assert label.roman_numeral == "I"
        assert label.function == "tonic"

    def test_dominant_chord(self):
        key = Key(tonic=0, mode="major", confidence=0.9)
        analyzer = HarmonicAnalyzer(key)
        chord = Chord(root=7, quality="major", pitch_classes=frozenset({7, 11, 2}))
        label = analyzer.analyze_chord(chord)
        assert label.roman_numeral == "V"
        assert label.function == "dominant"

    def test_non_diatonic_chord_raises(self):
        key = Key(tonic=0, mode="major", confidence=0.9)
        analyzer = HarmonicAnalyzer(key)
        chord = Chord(root=1, quality="major", pitch_classes=frozenset({1, 5, 8}))
        with pytest.raises(HarmonicAnalysisError):
            analyzer.analyze_chord(chord)


# ============================================================
# FizzBuzz Music Encoder Tests
# ============================================================


class TestFizzBuzzMusicEncoder:
    def test_encode_fizz(self):
        encoder = FizzBuzzMusicEncoder()
        data = encoder.encode(3, "Fizz")
        assert data["pitch_class"] == 0  # C

    def test_pitch_class_distribution_accumulates(self):
        encoder = FizzBuzzMusicEncoder()
        encoder.encode(3, "Fizz")
        encoder.encode(5, "Buzz")
        dist = encoder.pitch_class_distribution
        assert sum(dist) == 2


# ============================================================
# Middleware Tests
# ============================================================


class TestMusicMiddleware:
    def test_middleware_injects_pitch(self):
        mw = MusicMiddleware()
        ctx = _make_context(3, "Fizz")
        result = mw.process(ctx, _identity_handler)
        assert "music_pitch_class" in result.metadata
        assert "music_note_name" in result.metadata

    def test_middleware_detects_key_after_cycle(self):
        mw = MusicMiddleware()
        for i in range(1, 16):
            output = "FizzBuzz" if i % 15 == 0 else "Fizz" if i % 3 == 0 else "Buzz" if i % 5 == 0 else str(i)
            ctx = _make_context(i, output)
            result = mw.process(ctx, _identity_handler)
        assert "music_detected_key" in result.metadata

    def test_middleware_implements_imiddleware(self):
        from enterprise_fizzbuzz.domain.interfaces import IMiddleware
        mw = MusicMiddleware()
        assert isinstance(mw, IMiddleware)
