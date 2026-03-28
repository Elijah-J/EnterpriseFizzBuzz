"""
Enterprise FizzBuzz Platform - FizzMusic Music Theory Engine

Provides pitch and rhythm representation, chord recognition, key detection,
scale generation, MIDI event sequencing, and harmonic analysis for the
musicological interpretation of FizzBuzz sequences.

The FizzBuzz sequence produces a natural 15-beat rhythmic cycle (LCM of 3
and 5). Within this cycle, "Fizz" events on beats 3, 6, 9, 12 create a
4-note pattern, while "Buzz" events on beats 5, 10 create a 2-note
pattern. The "FizzBuzz" event on beat 15 marks the cycle boundary with
a cadential chord. This polyrhythmic structure maps directly to standard
music theory concepts: the Fizz pattern suggests a IV chord arpeggiation,
the Buzz pattern implies a V chord, and FizzBuzz resolves to I, creating
a IV-V-I cadence — the most fundamental harmonic progression in Western
tonal music.

Key detection uses the Krumhansl-Schmuckler algorithm, which correlates
the pitch-class distribution of a sequence against major and minor key
profiles. Chord recognition uses pitch-class set theory. Scale generation
produces pitch collections from interval patterns.

All music theory computations use pure Python. No external music libraries
are required.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Callable, Optional

from enterprise_fizzbuzz.domain.exceptions.fizzmusic import (
    ChordRecognitionError,
    HarmonicAnalysisError,
    InvalidPitchError,
    KeyDetectionError,
    MIDISequenceError,
    MusicMiddlewareError,
    ScaleGenerationError,
)
from enterprise_fizzbuzz.domain.interfaces import IMiddleware
from enterprise_fizzbuzz.domain.models import ProcessingContext

logger = logging.getLogger(__name__)

# MIDI constants
MIDI_MIN = 0
MIDI_MAX = 127
A4_MIDI = 69
A4_FREQ = 440.0
SEMITONES_PER_OCTAVE = 12

# Note names
NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]

# Krumhansl-Kessler major and minor key profiles
MAJOR_PROFILE = [6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88]
MINOR_PROFILE = [6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17]

# Chord interval templates (semitones from root)
CHORD_TEMPLATES = {
    "major": frozenset({0, 4, 7}),
    "minor": frozenset({0, 3, 7}),
    "diminished": frozenset({0, 3, 6}),
    "augmented": frozenset({0, 4, 8}),
    "major7": frozenset({0, 4, 7, 11}),
    "minor7": frozenset({0, 3, 7, 10}),
    "dominant7": frozenset({0, 4, 7, 10}),
    "sus2": frozenset({0, 2, 7}),
    "sus4": frozenset({0, 5, 7}),
}

# Scale interval patterns (semitones)
SCALE_PATTERNS = {
    "major": [2, 2, 1, 2, 2, 2, 1],
    "minor": [2, 1, 2, 2, 1, 2, 2],
    "harmonic_minor": [2, 1, 2, 2, 1, 3, 1],
    "melodic_minor": [2, 1, 2, 2, 2, 2, 1],
    "dorian": [2, 1, 2, 2, 2, 1, 2],
    "mixolydian": [2, 2, 1, 2, 2, 1, 2],
    "pentatonic_major": [2, 2, 3, 2, 3],
    "pentatonic_minor": [3, 2, 2, 3, 2],
    "chromatic": [1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1],
    "whole_tone": [2, 2, 2, 2, 2, 2],
}

# Roman numeral labels for scale degrees
ROMAN_NUMERALS = ["I", "II", "III", "IV", "V", "VI", "VII"]


# ============================================================
# Data Classes
# ============================================================


@dataclass
class Pitch:
    """A musical pitch represented as a MIDI note number."""

    midi_note: int

    def __post_init__(self) -> None:
        if self.midi_note < MIDI_MIN or self.midi_note > MIDI_MAX:
            raise InvalidPitchError(self.midi_note)

    @property
    def frequency(self) -> float:
        """Convert MIDI note to frequency in Hz."""
        return A4_FREQ * (2.0 ** ((self.midi_note - A4_MIDI) / 12.0))

    @property
    def note_name(self) -> str:
        """Get the note name (e.g., 'C4', 'F#5')."""
        octave = (self.midi_note // 12) - 1
        name = NOTE_NAMES[self.midi_note % 12]
        return f"{name}{octave}"

    @property
    def pitch_class(self) -> int:
        """Get the pitch class (0-11, where 0 = C)."""
        return self.midi_note % 12


@dataclass
class Rhythm:
    """Rhythmic value as a fraction of a whole note."""

    numerator: int = 1
    denominator: int = 4  # quarter note by default

    @property
    def duration_beats(self) -> float:
        """Duration in quarter-note beats."""
        return (self.numerator / self.denominator) * 4.0


@dataclass
class MIDIEvent:
    """A MIDI event with timestamp, type, and parameters."""

    tick: int
    event_type: str  # "note_on", "note_off", "control_change"
    channel: int = 0
    note: int = 60
    velocity: int = 64

    def validate(self) -> None:
        """Validate MIDI event parameters."""
        if self.tick < 0:
            raise MIDISequenceError(self.event_type, f"Negative tick value: {self.tick}")
        if self.channel < 0 or self.channel > 15:
            raise MIDISequenceError(self.event_type, f"Invalid channel: {self.channel}")
        if self.velocity < 0 or self.velocity > 127:
            raise MIDISequenceError(self.event_type, f"Invalid velocity: {self.velocity}")


@dataclass
class Chord:
    """A musical chord defined by a root and quality."""

    root: int  # pitch class 0-11
    quality: str  # "major", "minor", etc.
    pitch_classes: frozenset[int] = field(default_factory=frozenset)

    @property
    def name(self) -> str:
        """Human-readable chord name."""
        root_name = NOTE_NAMES[self.root % 12]
        quality_suffix = {
            "major": "", "minor": "m", "diminished": "dim",
            "augmented": "aug", "major7": "maj7", "minor7": "m7",
            "dominant7": "7", "sus2": "sus2", "sus4": "sus4",
        }
        return f"{root_name}{quality_suffix.get(self.quality, self.quality)}"


@dataclass
class Key:
    """A musical key with tonic and mode."""

    tonic: int  # pitch class 0-11
    mode: str  # "major" or "minor"
    confidence: float

    @property
    def name(self) -> str:
        mode_suffix = "" if self.mode == "major" else "m"
        return f"{NOTE_NAMES[self.tonic]}{mode_suffix}"


@dataclass
class HarmonicLabel:
    """Roman numeral analysis label for a chord in context."""

    chord: Chord
    key: Key
    roman_numeral: str
    function: str  # "tonic", "subdominant", "dominant"


# ============================================================
# Chord Recognizer
# ============================================================


class ChordRecognizer:
    """Identifies chords from sets of pitch classes.

    Matches a given set of pitch classes against known chord templates
    by testing all 12 transpositions of each template. The best match
    (highest overlap) determines the chord root and quality.
    """

    def recognize(self, pitch_classes: list[int]) -> Chord:
        """Identify a chord from a list of pitch classes."""
        if not pitch_classes:
            raise ChordRecognitionError([], "Empty pitch class set")

        pc_set = frozenset(pc % 12 for pc in pitch_classes)

        best_root = 0
        best_quality = "unknown"
        best_score = -1
        best_template_size = 999

        for root in range(12):
            for quality, template in CHORD_TEMPLATES.items():
                transposed = frozenset((pc + root) % 12 for pc in template)
                overlap = len(pc_set & transposed)
                # Prefer exact matches; on tie, prefer smaller templates (triads over 7ths)
                if overlap > best_score or (overlap == best_score and len(template) < best_template_size):
                    best_score = overlap
                    best_root = root
                    best_quality = quality
                    best_template_size = len(template)

        if best_score < 2:
            raise ChordRecognitionError(
                list(pc_set),
                "No chord template matches with sufficient overlap"
            )

        return Chord(
            root=best_root,
            quality=best_quality,
            pitch_classes=pc_set,
        )


# ============================================================
# Key Detector
# ============================================================


class KeyDetector:
    """Krumhansl-Schmuckler key detection algorithm.

    Correlates the pitch-class distribution of a musical passage
    against the Krumhansl-Kessler major and minor key profiles. The
    key with the highest Pearson correlation is selected as the
    detected key.
    """

    def __init__(self, min_confidence: float = 0.3) -> None:
        self._min_confidence = min_confidence

    def detect(self, pitch_class_counts: list[int]) -> Key:
        """Detect the key from a pitch-class histogram (12 bins, C=0)."""
        if len(pitch_class_counts) != 12:
            raise KeyDetectionError("unknown", 0.0)

        if sum(pitch_class_counts) == 0:
            raise KeyDetectionError("unknown", 0.0)

        best_key = 0
        best_mode = "major"
        best_corr = -2.0

        for tonic in range(12):
            # Rotate counts so tonic is at index 0
            rotated = [pitch_class_counts[(tonic + i) % 12] for i in range(12)]

            for mode, profile in [("major", MAJOR_PROFILE), ("minor", MINOR_PROFILE)]:
                corr = self._pearson(rotated, profile)
                if corr > best_corr:
                    best_corr = corr
                    best_key = tonic
                    best_mode = mode

        if best_corr < self._min_confidence:
            raise KeyDetectionError(
                NOTE_NAMES[best_key] + ("" if best_mode == "major" else "m"),
                best_corr,
            )

        return Key(tonic=best_key, mode=best_mode, confidence=best_corr)

    @staticmethod
    def _pearson(x: list[float], y: list[float]) -> float:
        """Compute Pearson correlation coefficient."""
        n = len(x)
        if n == 0:
            return 0.0
        mean_x = sum(x) / n
        mean_y = sum(y) / n
        num = sum((xi - mean_x) * (yi - mean_y) for xi, yi in zip(x, y))
        den_x = math.sqrt(sum((xi - mean_x) ** 2 for xi in x))
        den_y = math.sqrt(sum((yi - mean_y) ** 2 for yi in y))
        if den_x < 1e-10 or den_y < 1e-10:
            return 0.0
        return num / (den_x * den_y)


# ============================================================
# Scale Generator
# ============================================================


class ScaleGenerator:
    """Generates musical scales from root pitch and interval patterns."""

    def generate(
        self,
        root: int,
        scale_type: str = "major",
        octaves: int = 1,
    ) -> list[Pitch]:
        """Generate a scale starting from the given MIDI root note."""
        if root < MIDI_MIN or root > MIDI_MAX:
            raise ScaleGenerationError(root, scale_type, "Root note out of MIDI range")

        if scale_type not in SCALE_PATTERNS:
            raise ScaleGenerationError(
                root, scale_type,
                f"Unknown scale type. Available: {list(SCALE_PATTERNS.keys())}"
            )

        pattern = SCALE_PATTERNS[scale_type]
        pitches: list[Pitch] = []

        for octave in range(octaves):
            current = root + octave * 12
            if current > MIDI_MAX:
                break
            pitches.append(Pitch(midi_note=current))
            for interval in pattern:
                current += interval
                if current > MIDI_MAX:
                    break
                pitches.append(Pitch(midi_note=current))

        return pitches

    def scale_pitch_classes(self, root_pc: int, scale_type: str = "major") -> list[int]:
        """Get the pitch classes of a scale (independent of octave)."""
        if scale_type not in SCALE_PATTERNS:
            raise ScaleGenerationError(
                root_pc, scale_type, "Unknown scale type"
            )
        pattern = SCALE_PATTERNS[scale_type]
        pcs = [root_pc]
        current = root_pc
        for interval in pattern[:-1]:  # Don't add the octave
            current = (current + interval) % 12
            pcs.append(current)
        return pcs


# ============================================================
# MIDI Sequencer
# ============================================================


class MIDISequencer:
    """Sequences FizzBuzz classifications as MIDI events.

    Maps FizzBuzz output to MIDI note events:
    - "Fizz"     -> C4 (MIDI 60), quarter note, mf
    - "Buzz"     -> E4 (MIDI 64), quarter note, f
    - "FizzBuzz" -> G4 (MIDI 67), half note, ff
    - numeric    -> rest (no note), eighth note

    The resulting MIDI sequence encodes the FizzBuzz pattern as music,
    with the 15-beat cycle producing a recognizable melodic motif.
    """

    FIZZ_NOTE = 60      # C4
    BUZZ_NOTE = 64      # E4
    FIZZBUZZ_NOTE = 67  # G4
    TICKS_PER_BEAT = 480

    def __init__(self) -> None:
        self._events: list[MIDIEvent] = []
        self._current_tick = 0

    def add_fizzbuzz_event(self, label: str) -> None:
        """Add a MIDI event for a FizzBuzz classification."""
        if label == "FizzBuzz":
            note = self.FIZZBUZZ_NOTE
            velocity = 100
            duration_ticks = self.TICKS_PER_BEAT * 2
        elif label == "Fizz":
            note = self.FIZZ_NOTE
            velocity = 80
            duration_ticks = self.TICKS_PER_BEAT
        elif label == "Buzz":
            note = self.BUZZ_NOTE
            velocity = 90
            duration_ticks = self.TICKS_PER_BEAT
        else:
            # Rest for numeric values
            self._current_tick += self.TICKS_PER_BEAT // 2
            return

        note_on = MIDIEvent(
            tick=self._current_tick,
            event_type="note_on",
            channel=0,
            note=note,
            velocity=velocity,
        )
        note_on.validate()
        self._events.append(note_on)

        note_off = MIDIEvent(
            tick=self._current_tick + duration_ticks,
            event_type="note_off",
            channel=0,
            note=note,
            velocity=0,
        )
        note_off.validate()
        self._events.append(note_off)

        self._current_tick += duration_ticks

    @property
    def events(self) -> list[MIDIEvent]:
        """Get all sequenced MIDI events."""
        return list(self._events)

    @property
    def total_ticks(self) -> int:
        """Total duration in MIDI ticks."""
        return self._current_tick

    def clear(self) -> None:
        """Clear all events and reset the sequencer."""
        self._events.clear()
        self._current_tick = 0


# ============================================================
# Harmonic Analyzer
# ============================================================


class HarmonicAnalyzer:
    """Assigns Roman numeral labels to chords within a key context.

    Harmonic analysis contextualizes each chord relative to the
    current key, producing Roman numeral labels (I, ii, V7, etc.)
    and functional designations (tonic, subdominant, dominant).
    """

    _FUNCTION_MAP = {
        0: "tonic",
        1: "supertonic",
        2: "mediant",
        3: "subdominant",
        4: "dominant",
        5: "submediant",
        6: "leading_tone",
    }

    def __init__(self, key: Key) -> None:
        self._key = key
        self._scale_gen = ScaleGenerator()
        self._scale_pcs = self._scale_gen.scale_pitch_classes(
            key.tonic, key.mode
        )

    def analyze_chord(self, chord: Chord) -> HarmonicLabel:
        """Assign a Roman numeral label to a chord in the current key."""
        # Find which scale degree the chord root corresponds to
        try:
            degree_idx = self._scale_pcs.index(chord.root % 12)
        except ValueError:
            raise HarmonicAnalysisError(
                chord.name, self._key.name,
                f"Chord root {NOTE_NAMES[chord.root % 12]} is not diatonic "
                f"to {self._key.name}"
            )

        roman = ROMAN_NUMERALS[degree_idx]
        if chord.quality == "minor":
            roman = roman.lower()
        elif chord.quality == "diminished":
            roman = roman.lower() + "°"
        elif chord.quality == "augmented":
            roman = roman + "+"

        function = self._FUNCTION_MAP.get(degree_idx, "chromatic")

        return HarmonicLabel(
            chord=chord,
            key=self._key,
            roman_numeral=roman,
            function=function,
        )


# ============================================================
# FizzBuzz Music Encoder
# ============================================================


class FizzBuzzMusicEncoder:
    """Encodes FizzBuzz sequences as musical structures.

    Converts a sequence of FizzBuzz classifications into pitches,
    chords, and MIDI events, enabling music-theoretic analysis of
    the divisibility pattern.
    """

    def __init__(self) -> None:
        self._sequencer = MIDISequencer()
        self._recognizer = ChordRecognizer()
        self._pitch_classes_seen: list[int] = [0] * 12

    def encode(self, number: int, label: str) -> dict[str, Any]:
        """Encode a single FizzBuzz classification as music data."""
        self._sequencer.add_fizzbuzz_event(label)

        if label == "FizzBuzz":
            pc = MIDISequencer.FIZZBUZZ_NOTE % 12
        elif label == "Fizz":
            pc = MIDISequencer.FIZZ_NOTE % 12
        elif label == "Buzz":
            pc = MIDISequencer.BUZZ_NOTE % 12
        else:
            # Map number to pitch class
            pc = number % 12

        self._pitch_classes_seen[pc] += 1

        return {
            "pitch_class": pc,
            "note_name": NOTE_NAMES[pc],
            "total_events": len(self._sequencer.events),
            "total_ticks": self._sequencer.total_ticks,
        }

    @property
    def pitch_class_distribution(self) -> list[int]:
        """Get the accumulated pitch-class distribution."""
        return list(self._pitch_classes_seen)


# ============================================================
# FizzMusic Middleware
# ============================================================


class MusicMiddleware(IMiddleware):
    """Injects music theory analysis into the FizzBuzz pipeline.

    For each number evaluated, the middleware encodes the classification
    as a musical event and injects pitch, chord, key, and rhythm data
    into the processing context metadata.
    """

    def __init__(
        self,
        encoder: Optional[FizzBuzzMusicEncoder] = None,
        key_detector: Optional[KeyDetector] = None,
    ) -> None:
        self._encoder = encoder or FizzBuzzMusicEncoder()
        self._key_detector = key_detector or KeyDetector(min_confidence=0.1)
        self._event_count = 0

    def get_name(self) -> str:
        return "fizzmusic"

    def get_priority(self) -> int:
        return 279

    def process(
        self,
        context: ProcessingContext,
        next_handler: Callable[[ProcessingContext], ProcessingContext],
    ) -> ProcessingContext:
        """Inject music theory context and delegate to next handler."""
        try:
            output = ""
            if context.results:
                output = context.results[-1].output

            label = output if output in ("Fizz", "Buzz", "FizzBuzz") else str(context.number)
            music_data = self._encoder.encode(context.number, label)
            self._event_count += 1

            context.metadata["music_pitch_class"] = music_data["pitch_class"]
            context.metadata["music_note_name"] = music_data["note_name"]
            context.metadata["music_total_events"] = music_data["total_events"]

            # Attempt key detection every 15 events (one FizzBuzz cycle)
            if self._event_count % 15 == 0:
                try:
                    dist = self._encoder.pitch_class_distribution
                    key = self._key_detector.detect(dist)
                    context.metadata["music_detected_key"] = key.name
                    context.metadata["music_key_confidence"] = round(key.confidence, 4)
                except KeyDetectionError:
                    context.metadata["music_detected_key"] = "ambiguous"

        except Exception as exc:
            logger.error("FizzMusic middleware error: %s", exc)
            context.metadata["music_error"] = str(exc)

        return next_handler(context)
