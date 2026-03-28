"""Feature descriptor for the FizzMusic music theory engine."""

from __future__ import annotations

from typing import Any, Optional

from enterprise_fizzbuzz.infrastructure.features._registry import FeatureDescriptor


class FizzMusicFeature(FeatureDescriptor):
    name = "fizzmusic"
    description = "Music theory engine with chord recognition, key detection, scale generation, and MIDI sequencing"
    middleware_priority = 279
    cli_flags = [
        ("--fizzmusic", {"action": "store_true", "default": False,
                         "help": "Enable FizzMusic: apply music theory analysis to FizzBuzz sequences with chord recognition and key detection"}),
        ("--fizzmusic-scale", {"type": str, "metavar": "TYPE", "default": None,
                               "help": "Default scale type for analysis (major, minor, dorian, etc.)"}),
        ("--fizzmusic-key-threshold", {"type": float, "metavar": "CORR", "default": None,
                                       "help": "Minimum Pearson correlation for key detection acceptance (default: 0.3)"}),
    ]

    def is_enabled(self, args: Any) -> bool:
        return getattr(args, "fizzmusic", False)

    def create(self, config: Any, args: Any, event_bus: Any = None) -> tuple:
        from enterprise_fizzbuzz.infrastructure.fizzmusic import (
            FizzBuzzMusicEncoder,
            KeyDetector,
            MusicMiddleware,
        )

        threshold = getattr(args, "fizzmusic_key_threshold", None) or config.fizzmusic_key_confidence_threshold
        encoder = FizzBuzzMusicEncoder()
        key_detector = KeyDetector(min_confidence=threshold)
        middleware = MusicMiddleware(
            encoder=encoder,
            key_detector=key_detector,
        )

        return encoder, middleware

    def get_banner(self, config: Any, args: Any) -> Optional[str]:
        if getattr(args, "no_banner", False):
            return None
        return (
            "  +---------------------------------------------------------+\n"
            "  | FIZZMUSIC: MUSIC THEORY ENGINE                           |\n"
            "  |   Krumhansl-Schmuckler key detection algorithm            |\n"
            "  |   Chord recognition via pitch-class set theory            |\n"
            "  |   MIDI sequencing with IV-V-I cadential structure         |\n"
            "  +---------------------------------------------------------+"
        )
