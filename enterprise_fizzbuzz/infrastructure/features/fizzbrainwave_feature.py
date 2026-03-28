"""Feature descriptor for the FizzBrainwave brain-computer interface."""

from __future__ import annotations

from typing import Any, Optional

from enterprise_fizzbuzz.infrastructure.features._registry import FeatureDescriptor


class FizzBrainwaveFeature(FeatureDescriptor):
    name = "fizzbrainwave"
    description = "Brain-computer interface with EEG signal processing, mental state classification, and neural FizzBuzz decoding"
    middleware_priority = 268
    cli_flags = [
        ("--brainwave", {"action": "store_true", "default": False,
                         "help": "Enable FizzBrainwave: classify FizzBuzz using simulated brain-computer interface"}),
        ("--brainwave-dashboard", {"action": "store_true", "default": False,
                                   "help": "Display the FizzBrainwave ASCII dashboard with EEG spectral analysis"}),
    ]

    def is_enabled(self, args: Any) -> bool:
        return any([
            getattr(args, "brainwave", False),
            getattr(args, "brainwave_dashboard", False),
        ])

    def create(self, config: Any, args: Any, event_bus: Any = None) -> tuple:
        from enterprise_fizzbuzz.infrastructure.fizzbrainwave import (
            ArtifactRejector,
            BrainwaveMiddleware,
            EEGSignalGenerator,
            MentalStateClassifier,
            NeuralDecoder,
            SpectralAnalyzer,
        )

        signal_gen = EEGSignalGenerator(
            num_channels=config.fizzbrainwave_num_channels,
            sample_rate=config.fizzbrainwave_sample_rate,
        )
        artifact_rej = ArtifactRejector(
            max_rejection_rate=config.fizzbrainwave_artifact_max_rate,
        )
        spectral = SpectralAnalyzer(sample_rate=config.fizzbrainwave_sample_rate)
        classifier = MentalStateClassifier()
        decoder = NeuralDecoder(
            confidence_threshold=config.fizzbrainwave_confidence_threshold,
        )
        middleware = BrainwaveMiddleware(
            signal_generator=signal_gen,
            artifact_rejector=artifact_rej,
            spectral_analyzer=spectral,
            mental_state_classifier=classifier,
            neural_decoder=decoder,
            enable_dashboard=getattr(args, "brainwave_dashboard", False),
        )
        return decoder, middleware

    def get_banner(self, config: Any, args: Any) -> Optional[str]:
        if getattr(args, "no_banner", False):
            return None
        return (
            "  +---------------------------------------------------------+\n"
            "  | FIZZBRAINWAVE: BRAIN-COMPUTER INTERFACE                  |\n"
            f"  |   Channels: {config.fizzbrainwave_num_channels:<4} Sample rate: {config.fizzbrainwave_sample_rate} Hz           |\n"
            f"  |   SNR threshold: {config.fizzbrainwave_snr_threshold:.1f} dB                          |\n"
            "  |   EEG -> FFT -> Mental State -> FizzBuzz                |\n"
            "  +---------------------------------------------------------+"
        )

    def render(self, middleware: Any, args: Any) -> Optional[str]:
        if middleware is None:
            return None
        if not getattr(args, "brainwave_dashboard", False):
            return None
        from enterprise_fizzbuzz.infrastructure.fizzbrainwave import BrainwaveDashboard
        from enterprise_fizzbuzz.infrastructure.config import ConfigurationManager
        config = ConfigurationManager()
        if hasattr(middleware, "last_result") and middleware.last_result:
            return BrainwaveDashboard.render(
                middleware.last_result,
                width=config.fizzbrainwave_dashboard_width,
            )
        return None
