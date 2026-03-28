"""
Enterprise FizzBuzz Platform - FizzMusic Exceptions (EFP-MUS00 through EFP-MUS09)
"""

from __future__ import annotations

from typing import Any, Optional

from ._base import FizzBuzzError


class FizzMusicError(FizzBuzzError):
    """Base exception for all FizzMusic theory engine errors.

    The FizzMusic engine applies music theory analysis to FizzBuzz
    sequences, transforming the inherent numeric patterns into
    harmonic structures. Chord recognition, key detection, and
    scale analysis provide a musicological perspective on divisibility.
    """

    def __init__(
        self,
        message: str,
        *,
        error_code: str = "EFP-MUS00",
        context: dict | None = None,
    ) -> None:
        super().__init__(message, error_code=error_code, context=context)


class InvalidPitchError(FizzMusicError):
    """Raised when a pitch value is outside the representable range.

    MIDI pitch values range from 0 to 127, corresponding to
    frequencies from approximately 8.18 Hz (C-1) to 12543.85 Hz (G9).
    A pitch outside this range cannot be represented in the MIDI
    standard and has no defined musical interpretation.
    """

    def __init__(self, midi_note: int) -> None:
        super().__init__(
            f"MIDI pitch {midi_note} is outside the valid range [0, 127]",
            error_code="EFP-MUS01",
            context={"midi_note": midi_note},
        )


class ChordRecognitionError(FizzMusicError):
    """Raised when a set of pitches cannot be identified as a known chord.

    Chord recognition maps pitch-class sets to named chord types
    (major, minor, diminished, augmented, etc.). An unrecognized
    pitch-class set may represent a cluster or atonal aggregate that
    has no standard chord name.
    """

    def __init__(self, pitch_classes: list[int], reason: str) -> None:
        super().__init__(
            f"Chord recognition failed for pitch classes {pitch_classes}: {reason}",
            error_code="EFP-MUS02",
            context={"pitch_classes": pitch_classes, "reason": reason},
        )


class KeyDetectionError(FizzMusicError):
    """Raised when key detection produces an ambiguous or invalid result.

    The Krumhansl-Schmuckler key-finding algorithm correlates pitch-class
    distributions against major and minor key profiles. When the
    correlation coefficients are too close, key detection is ambiguous
    and the tonal center of the FizzBuzz sequence is indeterminate.
    """

    def __init__(self, best_key: str, confidence: float) -> None:
        super().__init__(
            f"Key detection ambiguous: best candidate '{best_key}' with "
            f"confidence {confidence:.4f}, below the minimum threshold",
            error_code="EFP-MUS03",
            context={"best_key": best_key, "confidence": confidence},
        )


class ScaleGenerationError(FizzMusicError):
    """Raised when scale generation parameters are invalid.

    A musical scale requires a valid root pitch class (0-11) and a
    non-empty interval pattern. Invalid parameters produce a degenerate
    scale that cannot support harmonic analysis of FizzBuzz sequences.
    """

    def __init__(self, root: int, scale_type: str, reason: str) -> None:
        super().__init__(
            f"Scale generation failed for root={root}, type='{scale_type}': {reason}",
            error_code="EFP-MUS04",
            context={"root": root, "scale_type": scale_type, "reason": reason},
        )


class MIDISequenceError(FizzMusicError):
    """Raised when MIDI event sequencing encounters an error.

    MIDI events must have non-negative timestamps, valid channel
    numbers (0-15), and velocities in [0, 127]. An invalid event
    would corrupt the MIDI stream and produce garbled musical output.
    """

    def __init__(self, event_type: str, reason: str) -> None:
        super().__init__(
            f"MIDI sequence error for event type '{event_type}': {reason}",
            error_code="EFP-MUS05",
            context={"event_type": event_type, "reason": reason},
        )


class HarmonicAnalysisError(FizzMusicError):
    """Raised when harmonic analysis cannot determine chord function.

    Harmonic analysis assigns Roman numeral labels (I, IV, V, etc.) to
    chords within a key context. Without a determined key or with
    ambiguous chord spellings, functional harmony analysis of the
    FizzBuzz sequence is not possible.
    """

    def __init__(self, chord_name: str, key: str, reason: str) -> None:
        super().__init__(
            f"Harmonic analysis error for chord '{chord_name}' in key "
            f"'{key}': {reason}",
            error_code="EFP-MUS06",
            context={"chord_name": chord_name, "key": key, "reason": reason},
        )


class MusicMiddlewareError(FizzMusicError):
    """Raised when the FizzMusic middleware pipeline encounters a fault."""

    def __init__(self, reason: str) -> None:
        super().__init__(
            f"FizzMusic middleware error: {reason}",
            error_code="EFP-MUS07",
            context={"reason": reason},
        )
