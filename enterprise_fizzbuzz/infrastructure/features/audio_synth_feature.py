"""Feature descriptor for the FizzSynth digital audio synthesizer."""

from __future__ import annotations

from typing import Any, Optional

from enterprise_fizzbuzz.infrastructure.features._registry import FeatureDescriptor


class AudioSynthFeature(FeatureDescriptor):
    name = "audio_synth"
    description = "Digital audio synthesizer with subtractive synthesis, ADSR envelopes, and polyrhythmic sonification"
    middleware_priority = 170
    cli_flags = [
        ("--synth", {"action": "store_true", "default": False,
                     "help": "Enable FizzSynth: sonify FizzBuzz sequences as music using subtractive synthesis with ADSR envelopes"}),
        ("--synth-wav", {"type": str, "metavar": "FILE", "default": None,
                         "help": "Write the FizzSynth composition to a 16-bit PCM WAV file (44100 Hz, mono)"}),
        ("--synth-dashboard", {"action": "store_true", "default": False,
                               "help": "Display the FizzSynth ASCII dashboard with waveform visualization and polyrhythm analysis"}),
    ]

    def is_enabled(self, args: Any) -> bool:
        return any([
            getattr(args, "synth", False),
            getattr(args, "synth_wav", None) is not None,
            getattr(args, "synth_dashboard", False),
        ])

    def create(self, config: Any, args: Any, event_bus: Any = None) -> tuple:
        from enterprise_fizzbuzz.infrastructure.audio_synth import (
            SequenceComposer,
            SynthMiddleware,
        )

        composer = SequenceComposer(
            bpm=config.synth_bpm,
            reverb_wet=config.synth_reverb_wet,
            filter_cutoff=config.synth_filter_cutoff,
        )

        middleware = SynthMiddleware(
            composer=composer,
            enable_dashboard=getattr(args, "synth_dashboard", False),
            wav_output_path=getattr(args, "synth_wav", None),
        )

        return composer, middleware

    def get_banner(self, config: Any, args: Any) -> Optional[str]:
        if getattr(args, "no_banner", False):
            return None
        return (
            "  +---------------------------------------------------------+\n"
            "  | FIZZSYNTH: DIGITAL AUDIO SYNTHESIZER                    |\n"
            f"  |   Tempo: {config.synth_bpm:.0f} BPM  Sample rate: 44100 Hz           |\n"
            "  |   3-against-5 polyrhythmic sonification enabled          |\n"
            "  |   Fizz=C4 square, Buzz=E4 saw, FizzBuzz=G4 detuned      |\n"
            "  +---------------------------------------------------------+"
        )

    def render(self, middleware: Any, args: Any) -> Optional[str]:
        if middleware is None:
            return None
        from enterprise_fizzbuzz.infrastructure.audio_synth import SynthDashboard
        from enterprise_fizzbuzz.infrastructure.config import ConfigurationManager
        config = ConfigurationManager()

        composer = middleware.composer if hasattr(middleware, "composer") else None
        if composer is None:
            return None

        parts = []

        if getattr(args, "synth_wav", None) and composer is not None:
            frames = composer.render_to_wav(args.synth_wav)
            duration = composer.total_duration
            parts.append(
                f"\n  FizzSynth WAV exported: {args.synth_wav}\n"
                f"  Frames: {frames}  Duration: {duration:.2f}s  "
                f"Format: 44100 Hz / 16-bit / mono\n"
            )

        if getattr(args, "synth_dashboard", False):
            parts.append(SynthDashboard.render(
                composer=composer,
                width=config.synth_dashboard_width,
            ))
        elif getattr(args, "synth_dashboard", False):
            parts.append("\n  FizzSynth not enabled. Use --synth to enable.\n")

        return "\n".join(parts) if parts else None
